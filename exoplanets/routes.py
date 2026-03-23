"""
exoplanets/routes.py - API Analisi Transiti Esopianeti

Endpoint:
- GET  / - Homepage modulo
- GET  /api/lightcurve - Carica dati transiti
- POST /api/bls - Box Least Squares detection
- POST /api/validate - Validazione fisica pianeta

Autore: AGATA Project Team
Data: 2026-01-03
"""

import json
import logging
import numpy as np
from flask import render_template, request, jsonify, Response

import pyarrow as pa
import pyarrow.ipc as ipc

from astropy.timeseries import BoxLeastSquares
from astropy import units as u

from . import exoplanets_bp
from agata.services.synthetic_exoplanets import generate_exoplanet_lightcurve_sessions
from agata.services.ephemeris_exoplanets import (
    detect_individual_transits,
    calculate_ephemeris,
    calculate_oc,
    export_exoclock_format,
    predict_future_transits
)
from agata.services.data_loader_exoplanets import load_observation_file

# Setup logger
logger = logging.getLogger(__name__)


# =============================================================================
# API UPLOAD FILE
# =============================================================================

@exoplanets_bp.post("/api/upload")
def api_upload_file():
    """
    Upload file osservazioni reali.
    
    Form Data:
        file: File binario (CSV/TXT/FITS)
    
    Returns:
        JSON con dati parsati e preview
    """
    try:
        # Check file presente
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({"error": "Empty filename"}), 400
        
        logger.info(f"Upload file: {file.filename}")
        
        # =====================================================================
        # READ FILE
        # =====================================================================
        
        file_content = file.read()
        
        if len(file_content) == 0:
            return jsonify({"error": "Empty file"}), 400
        
        logger.info(f"File size: {len(file_content)} bytes")
        
        # =====================================================================
        # PARSE FILE
        # =====================================================================
        
        data = load_observation_file(
            file_content,
            file.filename,
            file_format='auto'
        )
        
        logger.info(f"Parsed {data['metadata']['n_points']} points")
        
        # =====================================================================
        # PREPARE RESPONSE
        # =====================================================================
        
        # Converti numpy arrays a liste per JSON
        response_data = {
            "success": True,
            "filename": file.filename,
            
            # Dati completi
            "jd": data['jd'].tolist(),
            "flux": data['flux'].tolist(),
            
            # Metadata
            "metadata": data['metadata'],
            
            # Validation
            "validation": data['validation'],
            
            # Preview (primi/ultimi 100 punti)
            "preview": {
                "jd": data['jd'][:100].tolist(),
                "flux": data['flux'][:100].tolist()
            }
        }
        
        # Aggiungi errori se presenti
        if 'flux_err' in data:
            response_data['flux_err'] = data['flux_err'].tolist()
        
        if 'mag' in data:
            response_data['mag'] = data['mag'].tolist()
        
        if 'mag_err' in data:
            response_data['mag_err'] = data['mag_err'].tolist()
        
        # =====================================================================
        # LOG WARNINGS
        # =====================================================================
        
        for warning in data['validation']['warnings']:
            if warning.startswith('ERROR'):
                logger.error(warning)
            elif warning.startswith('WARNING'):
                logger.warning(warning)
            else:
                logger.info(warning)
        
        return jsonify(response_data)
    
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return jsonify({"error": f"Validation error: {str(e)}"}), 400
    
    except Exception as e:
        logger.error(f"Upload error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# =============================================================================
# COSTANTI FISICHE
# =============================================================================

G_SI = 6.67430e-11
M_SUN = 1.98847e30
R_SUN = 6.95700e8
R_JUP = 6.9911e7
R_EARTH = 6.371e6
AU = 1.495978707e11


# =============================================================================
# HOMEPAGE
# =============================================================================

@exoplanets_bp.route("/")
def index():
    """
    Homepage modulo esopianeti.
    """
    logger.info("Servendo homepage esopianeti")
    return render_template("exoplanets/index.html")


# =============================================================================
# API CARICAMENTO DATI
# =============================================================================

@exoplanets_bp.get("/api/lightcurve")
def api_lightcurve():
    """
    Carica curva di luce con transiti esopianeti.
    
    Query Parameters:
        planet_type: Tipo pianeta
            - "hot_jupiter" (default)
            - "neptune"
            - "super_earth"
            - "earth"
        n_transits: Numero transiti (default: 10)
        seed: Seed RNG (default: 42)
    
    Returns:
        JSON con dati:
        {
            "jd": [...],
            "flux": [...],
            "mag": [...],
            "params": {...}
        }
    """
    try:
        # Parametri
        planet_type = request.args.get("planet_type", "hot_jupiter")
        n_transits = int(request.args.get("n_transits", "10"))
        seed = int(request.args.get("seed", "42"))
        
        logger.info(
            f"Caricamento dati: planet_type={planet_type}, "
            f"n_transits={n_transits}, seed={seed}"
        )
        
        # Genera dati
        sessions = generate_exoplanet_lightcurve_sessions(
            planet_type=planet_type,
            n_transits=n_transits,
            seed=seed
        )
        
        if not sessions:
            return jsonify({"error": "Nessun dato generato"}), 500
        
        # Estrai prima sessione (ce n'è solo una per esopianeti)
        session = sessions[0]
        
        # Return JSON
        return jsonify({
            "jd": session["jd"].tolist(),
            "flux": session["flux"].tolist(),
            "mag": session["mag"].tolist(),
            "params": session["params"],
            "n_points": len(session["jd"])
        })
    
    except Exception as e:
        logger.error(f"Errore caricamento dati: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# =============================================================================
# API BLS DETECTION
# =============================================================================

@exoplanets_bp.post("/api/bls")
def api_bls():
    """
    Esegue Box Least Squares detection.
    
    Request Body (JSON):
        {
            "jd": [...],           # Julian Dates
            "flux": [...],         # Flussi relativi
            "period_min": 0.5,     # [giorni]
            "period_max": 20.0,
            "duration_min": 0.01,  # [frazione periodo]
            "duration_max": 0.2
        }
    
    Returns:
        JSON con risultati BLS
    """
    try:
        data = request.get_json()
        
        # Estrai dati
        jd = np.array(data["jd"])
        flux = np.array(data["flux"])
        
        # Parametri BLS
        period_min = float(data.get("period_min", 0.5))
        period_max = float(data.get("period_max", 20.0))
        duration_min = float(data.get("duration_min", 0.01))
        duration_max = float(data.get("duration_max", 0.2))
        
        logger.info(
            f"BLS detection: {len(jd)} punti, "
            f"P=[{period_min}, {period_max}]d"
        )
        
        # =====================================================================
        # VALIDAZIONE INPUT
        # =====================================================================
        
        if len(jd) < 100:
            return jsonify({"error": "Troppo pochi punti (min 100)"}), 400
        
        if period_max > (jd.max() - jd.min()):
            period_max = jd.max() - jd.min()
            logger.warning(f"period_max ridotto a baseline: {period_max:.2f}d")
        
        # =====================================================================
        # ESECUZIONE BLS
        # =====================================================================
        
        # Inizializza BLS
        bls = BoxLeastSquares(jd * u.day, flux)
        
        # Grid periodi (logaritmico)
        periods = np.exp(np.linspace(
            np.log(period_min),
            np.log(period_max),
            5000
        )) * u.day
        
        # Grid durate
        durations = np.linspace(duration_min, duration_max, 10)
        
        # Calcola periodogram
        logger.info("Calcolo BLS periodogram...")
        result = bls.power(periods, durations)
        
        # =====================================================================
        # ESTRAZIONE RISULTATI
        # =====================================================================
        
        idx_max = np.argmax(result.power)
        
        best_period = float(result.period[idx_max].value)
        best_power = float(result.power[idx_max])
        best_duration = float(result.duration[idx_max].value)
        best_depth = float(result.depth[idx_max])
        best_t0 = float(result.transit_time[idx_max].value)
        
        # =====================================================================
        # STATISTICHE
        # =====================================================================
        
        # Signal Detection Efficiency
        power_mean = np.mean(result.power)
        power_std = np.std(result.power)
        sde = (best_power - power_mean) / power_std if power_std > 0 else 0
        
        # Numero transiti
        baseline = jd.max() - jd.min()
        n_transits = int(baseline / best_period)
        
        # SNR approssimato
        flux_std = np.std(flux)
        median_cadence = np.median(np.diff(np.sort(jd)))
        points_per_transit = best_duration / median_cadence
        snr = best_depth * np.sqrt(n_transits * points_per_transit) / flux_std
        
        logger.info(
            f"BLS risultati:\n"
            f"  Periodo: {best_period:.4f}d\n"
            f"  Durata: {best_duration:.4f}d\n"
            f"  Profondità: {best_depth:.6f}\n"
            f"  SDE: {sde:.2f}\n"
            f"  SNR: {snr:.2f}"
        )
        
        # =====================================================================
        # CALCOLO FASE FOLDATO
        # =====================================================================
        
        # Folda dati sul periodo trovato
        phase = ((jd - best_t0) % best_period) / best_period
        
        # Ordina per fase
        sort_idx = np.argsort(phase)
        phase_sorted = phase[sort_idx]
        flux_sorted = flux[sort_idx]
        
        # =====================================================================
        # RETURN
        # =====================================================================
        
        return jsonify({
            "success": True,
            
            # Periodogram completo
            "periods": result.period.value.tolist(),
            "power": result.power.tolist(),
            
            # Best fit
            "best_period": best_period,
            "best_duration": best_duration,
            "best_depth": best_depth,
            "best_t0": best_t0,
            
            # Statistiche
            "sde": sde,
            "snr": snr,
            "n_transits": n_transits,
            
            # Fase foldato
            "phase": phase_sorted.tolist(),
            "flux_folded": flux_sorted.tolist(),
            
            # Metadata
            "algorithm": "Box Least Squares (Astropy)",
            "n_periods_tested": len(periods),
            "baseline_days": float(baseline)
        })
    
    except KeyError as e:
        logger.error(f"Campo mancante: {e}")
        return jsonify({"error": f"Campo richiesto mancante: {e}"}), 400
    
    except Exception as e:
        logger.error(f"Errore BLS: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# =============================================================================
# API VALIDAZIONE FISICA
# =============================================================================

@exoplanets_bp.post("/api/validate")
def api_validate():
    """
    Validazione fisica parametri pianeta.
    
    Request Body (JSON):
        {
            "period": 3.5,           # [giorni]
            "depth": 0.01,           # ΔF/F
            "duration": 0.12,        # [giorni]
            "stellar_mass": 1.0,     # [M☉]
            "stellar_radius": 1.0    # [R☉]
        }
    
    Returns:
        JSON con validazione e parametri fisici derivati
    """
    try:
        data = request.get_json()
        
        # Parametri osservati
        period = float(data["period"])
        depth = float(data["depth"])
        duration = float(data["duration"])
        
        # Parametri stella
        stellar_mass = float(data.get("stellar_mass", 1.0))
        stellar_radius = float(data.get("stellar_radius", 1.0))
        stellar_teff = float(data.get("stellar_teff", 5778))
        
        logger.info(
            f"Validazione: P={period:.2f}d, "
            f"depth={depth:.4f}, dur={duration:.2f}d"
        )
        
        # =====================================================================
        # CALCOLO PARAMETRI FISICI
        # =====================================================================
        
        # Raggio pianeta
        rp_over_rs = np.sqrt(depth)
        rp_rsun = rp_over_rs * stellar_radius
        rp_rjup = rp_rsun * (R_SUN / R_JUP)
        rp_rearth = rp_rsun * (R_SUN / R_EARTH)
        
        # Semiasse orbitale (Keplero III)
        mass_kg = stellar_mass * M_SUN
        period_sec = period * 86400
        a_meters = ((G_SI * mass_kg * period_sec**2) / (4 * np.pi**2)) ** (1/3)
        a_au = a_meters / AU
        a_rsun = a_meters / R_SUN
        a_over_rs = a_rsun / stellar_radius
        
        # Temperatura equilibrio (albedo = 0.3)
        albedo = 0.3
        teq = stellar_teff * np.sqrt(stellar_radius / (2 * a_rsun)) * (1 - albedo)**0.25
        
        # Velocità orbitale
        v_orbit = 2 * np.pi * a_au * AU / period_sec / 1000  # [km/s]
        
        # =====================================================================
        # VALIDAZIONE FISICA
        # =====================================================================
        
        warnings = []
        is_valid = True
        
        # Check 1: Rp < R★
        if rp_over_rs > 1.0:
            warnings.append({
                "level": "error",
                "message": f"ERRORE FISICO: Rp/R* = {rp_over_rs:.3f} > 1 (pianeta più grande della stella!)"
            })
            is_valid = False
        elif rp_over_rs > 0.2:
            warnings.append({
                "level": "warning",
                "message": f"Pianeta molto grande: Rp/R* = {rp_over_rs:.3f} (possibile brown dwarf)"
            })
        
        # Check 2: Durata ragionevole
        duration_frac = duration / period
        if duration_frac > 0.3:
            warnings.append({
                "level": "warning",
                "message": f"Durata anomala: {duration_frac:.1%} del periodo (tipico: 1-10%)"
            })
        
        # Check 3: Orbita stabile (a > R★ + Rp)
        min_distance_rsun = stellar_radius + rp_rsun
        if a_rsun < min_distance_rsun:
            warnings.append({
                "level": "error",
                "message": f"ERRORE: Orbita instabile (a={a_rsun:.2f} R☉ < R★+Rp={min_distance_rsun:.2f} R☉)"
            })
            is_valid = False
        
        # Check 4: Limite Roche (semplificato)
        roche_limit = 2.46 * stellar_radius * (stellar_mass / (rp_rsun**3 * 5.5))**(1/3)  # densità ~5.5 g/cm³
        if a_rsun < roche_limit:
            warnings.append({
                "level": "warning",
                "message": f"Possibile disgregazione mareale (a={a_rsun:.2f} < Roche={roche_limit:.2f} R☉)"
            })
        
        # Check 5: Temperatura
        if teq > 2500:
            warnings.append({
                "level": "info",
                "message": f"Pianeta ultra-caldo: Teq={teq:.0f}K (possibile evaporazione atmosfera)"
            })
        
        # Check 6: Classificazione
        if rp_rearth < 1.5:
            planet_class = "Rocky / Earth-like"
        elif rp_rearth < 4:
            planet_class = "Super-Earth / Mini-Neptune"
        elif rp_rearth < 10:
            planet_class = "Neptune-like"
        else:
            planet_class = "Jupiter-like / Brown Dwarf"
        
        logger.info(
            f"Validazione completata:\n"
            f"  Raggio: {rp_rjup:.3f} Rjup = {rp_rearth:.2f} Rearth\n"
            f"  Orbita: {a_au:.4f} AU\n"
            f"  Temperatura: {teq:.0f}K\n"
            f"  Classe: {planet_class}\n"
            f"  Valido: {is_valid}\n"
            f"  Warning: {len(warnings)}"
        )
        
        # =====================================================================
        # RETURN
        # =====================================================================
        
        return jsonify({
            "success": True,
            "is_valid": is_valid,
            "warnings": warnings,
            
            # Parametri fisici
            "physical_params": {
                "rp_over_rs": rp_over_rs,
                "rp_rjup": rp_rjup,
                "rp_rearth": rp_rearth,
                "a_au": a_au,
                "a_over_rs": a_over_rs,
                "teq_kelvin": teq,
                "v_orbit_kms": v_orbit,
                "planet_class": planet_class
            },
            
            # Input echo
            "input_params": {
                "period": period,
                "depth": depth,
                "duration": duration,
                "stellar_mass": stellar_mass,
                "stellar_radius": stellar_radius,
                "stellar_teff": stellar_teff
            }
        })
    
    except KeyError as e:
        logger.error(f"Campo mancante: {e}")
        return jsonify({"error": f"Campo richiesto: {e}"}), 400
    
    except Exception as e:
        logger.error(f"Errore validazione: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# =============================================================================
# API EFFEMERIDI
# =============================================================================

@exoplanets_bp.post("/api/ephemeris")
def api_ephemeris():
    """
    Calcola effemeridi da transiti rilevati.
    
    Request Body (JSON):
        {
            "jd": [...],
            "flux": [...],
            "period": 3.5,
            "t0": 2460000.5,
            "duration": 0.12
        }
    
    Returns:
        JSON con effemeridi e O-C
    """
    try:
        data = request.get_json()
        
        # Estrai dati
        jd = np.array(data["jd"])
        flux = np.array(data["flux"])
        period = float(data["period"])
        t0 = float(data["t0"])
        duration = float(data["duration"])
        
        logger.info(
            f"Calcolo effemeridi: P={period:.4f}d, "
            f"T0={t0:.6f}, dur={duration:.4f}d"
        )
        
        # =====================================================================
        # RILEVAMENTO TRANSITI INDIVIDUALI
        # =====================================================================
        
        transits = detect_individual_transits(jd, flux, period, t0, duration)
        
        if len(transits) < 2:
            return jsonify({
                "error": "Troppo pochi transiti rilevati (min 2)",
                "n_detected": len(transits)
            }), 400
        
        logger.info(f"Rilevati {len(transits)} transiti")
        
        # =====================================================================
        # CALCOLO EFFEMERIDI
        # =====================================================================
        
        ephemeris = calculate_ephemeris(transits)
        
        # =====================================================================
        # CALCOLO O-C
        # =====================================================================
        
        oc_data = calculate_oc(transits, ephemeris)
        
        # =====================================================================
        # RETURN
        # =====================================================================
        
        return jsonify({
            "success": True,
            
            # Effemeridi
            "ephemeris": {
                "t0": ephemeris.t0,
                "t0_err": ephemeris.t0_err,
                "t0_err_minutes": ephemeris.t0_err * 1440,
                "period": ephemeris.period,
                "period_err": ephemeris.period_err,
                "period_err_seconds": ephemeris.period_err * 86400,
                "n_transits": ephemeris.n_transits,
                "rms_oc_minutes": ephemeris.rms_oc,
                "chi2_reduced": ephemeris.chi2_reduced
            },
            
            # O-C data
            "oc": oc_data,
            
            # Transiti individuali
            "transits": [
                {
                    "epoch": t.epoch,
                    "t_mid": t.t_mid,
                    "t_mid_err": t.t_mid_err,
                    "depth": t.depth,
                    "snr": t.snr,
                    "is_valid": t.is_valid
                }
                for t in transits
            ]
        })
    
    except KeyError as e:
        logger.error(f"Campo mancante: {e}")
        return jsonify({"error": f"Campo richiesto: {e}"}), 400
    
    except Exception as e:
        logger.error(f"Errore calcolo effemeridi: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# =============================================================================
# API PREDIZIONE TRANSITI
# =============================================================================

@exoplanets_bp.post("/api/ephemeris/predict")
def api_predict_transits():
    """
    Predice transiti futuri date le effemeridi.
    
    Request Body (JSON):
        {
            "t0": 2460000.5,
            "t0_err": 0.0005,
            "period": 3.5,
            "period_err": 0.00001,
            "jd_start": 2460100.0,
            "jd_end": 2460200.0
        }
    
    Returns:
        JSON con lista transiti predetti
    """
    try:
        data = request.get_json()
        
        # Crea oggetto effemeridi
        from agata.services.ephemeris_exoplanets import Ephemeris
        
        ephemeris = Ephemeris(
            t0=float(data["t0"]),
            t0_err=float(data["t0_err"]),
            period=float(data["period"]),
            period_err=float(data["period_err"]),
            n_transits=0,
            rms_oc=0.0,
            chi2_reduced=1.0
        )
        
        jd_start = float(data["jd_start"])
        jd_end = float(data["jd_end"])
        
        logger.info(
            f"Predizione transiti: JD=[{jd_start:.1f}, {jd_end:.1f}]"
        )
        
        # Predici transiti
        predictions = predict_future_transits(ephemeris, jd_start, jd_end)
        
        logger.info(f"Predetti {len(predictions)} transiti")
        
        return jsonify({
            "success": True,
            "n_predictions": len(predictions),
            "predictions": predictions
        })
    
    except KeyError as e:
        logger.error(f"Campo mancante: {e}")
        return jsonify({"error": f"Campo richiesto: {e}"}), 400
    
    except Exception as e:
        logger.error(f"Errore predizione: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# =============================================================================
# API EXPORT EXOCLOCK
# =============================================================================

@exoplanets_bp.post("/api/export/exoclock")
def api_export_exoclock():
    """
    Esporta dati in formato ExoClock CSV.
    
    Request Body (JSON):
        {
            "transits": [...],
            "ephemeris": {...},
            "planet_name": "WASP-12b",
            "observer": "AGATA",
            "filter": "Clear"
        }
    
    Returns:
        CSV file download
    """
    try:
        data = request.get_json()
        
        # Ricostruisci transiti
        from agata.services.ephemeris_exoplanets import TransitTime, Ephemeris
        
        transits = [
            TransitTime(
                epoch=t["epoch"],
                t_mid=t["t_mid"],
                t_mid_err=t["t_mid_err"],
                depth=t["depth"],
                duration=t.get("duration", 0.0),
                snr=t.get("snr", 0.0),
                is_valid=t.get("is_valid", True)
            )
            for t in data["transits"]
        ]
        
        # Ricostruisci effemeridi
        eph_data = data["ephemeris"]
        ephemeris = Ephemeris(
            t0=eph_data["t0"],
            t0_err=eph_data["t0_err"],
            period=eph_data["period"],
            period_err=eph_data["period_err"],
            n_transits=eph_data["n_transits"],
            rms_oc=eph_data["rms_oc_minutes"],
            chi2_reduced=eph_data["chi2_reduced"]
        )
        
        # Parametri export
        planet_name = data.get("planet_name", "Unknown Planet")
        observer = data.get("observer", "AGATA")
        filter_band = data.get("filter", "Clear")
        
        logger.info(
            f"Export ExoClock: {planet_name}, "
            f"{len(transits)} transiti, observer={observer}"
        )
        
        # Genera CSV
        csv_content = export_exoclock_format(
            transits,
            ephemeris,
            planet_name,
            observer,
            filter_band
        )
        
        # Return come file download
        response = Response(
            csv_content,
            mimetype="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={planet_name.replace(' ', '_')}_exoclock.csv"
            }
        )
        
        logger.info("Export completato")
        
        return response
    
    except KeyError as e:
        logger.error(f"Campo mancante: {e}")
        return jsonify({"error": f"Campo richiesto: {e}"}), 400
    
    except Exception as e:
        logger.error(f"Errore export: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# =============================================================================
# FINE FILE
# =============================================================================
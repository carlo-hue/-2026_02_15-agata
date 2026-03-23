"""
extrema.py - Calcolo estremi (massimi/minimi) per sessione

Identifica massimi e minimi robusti usando:
- Binning mediano (riduce rumore)
- scipy.signal.find_peaks per estremi locali significativi
"""

import logging
import numpy as np
from flask import request, jsonify

from agata.variable_stars import variable_stars_bp
from agata.variable_stars.constants import MIN_POINTS_PER_SESSION
from agata.variable_stars.services.arrow_parser import read_arrow_table_from_request
from agata.variable_stars.services.peak_detection import compute_extrema_binned

logger = logging.getLogger(__name__)


@variable_stars_bp.post("/api/extrema.arrow")
def api_compute_extrema_per_session():
    """
    Calcola massimi e minimi robusti per sessione usando binning mediano.

    Approccio scientifico:
    1. Binning temporale con mediana (riduce rumore fotometrico)
    2. scipy.signal.find_peaks per identificare estremi locali significativi
    3. Analisi per sessione (rispetta differenze strumentali)

    Request:
        Body: Arrow stream (jd, mag, session_id)
        Query params:
            - bin_size: float (default: 0.05) - Dimensione bin in giorni (~1h)
            - prominence: float (default: 0.1) - Prominenza minima picchi [mag]

    Returns:
        JSON con per ogni sessione:
        {
            "session_id": {
                "global_max": {
                    "jd": float,           // JD del massimo globale (stella più debole)
                    "mag": float           // Magnitudine massima
                },
                "global_min": {
                    "jd": float,           // JD del minimo globale (stella più luminosa)
                    "mag": float           // Magnitudine minima
                },
                "amplitude": float,        // Ampiezza totale (max - min) [mag]
                "local_maxima": [          // Lista massimi locali significativi
                    {
                        "jd": float,
                        "mag": float,
                        "prominence": float  // Prominenza del picco
                    },
                    ...
                ],
                "local_minima": [...],     // Lista minimi locali significativi
                "n_bins": int,             // Numero bin usati
                "bin_size_used": float     // Dimensione bin effettiva
            },
            ...
        },
        "method": "Median binning + scipy.signal.find_peaks",
        "parameters": {...}

    Riferimenti:
        - Binning mediano: Stetson 1996, PASP 108, 851
        - find_peaks: scipy.signal documentation
    """
    try:
        # Leggi dati Arrow
        table = read_arrow_table_from_request()

        jd = np.asarray(table["jd"].to_numpy(zero_copy_only=False), dtype=float)
        mag = np.asarray(table["mag"].to_numpy(zero_copy_only=False), dtype=float)
        session_id = np.asarray(table["session_id"].to_numpy(zero_copy_only=False), dtype=np.int32)

        # Parametri con validazione
        bin_size = float(request.args.get("bin_size", 0.05))  # 0.05 giorni ≈ 1.2h
        prominence = float(request.args.get("prominence", 0.1))  # 0.1 mag

        # Sanitizza input
        bin_size = max(0.01, min(bin_size, 1.0))  # 0.01-1.0 giorni
        prominence = max(0.01, min(prominence, 2.0))  # 0.01-2.0 mag

        logger.info(f"Calcolo estremi: bin_size={bin_size}d, prominence={prominence} mag")

        results = {}

        # Analizza ogni sessione indipendentemente
        unique_sessions = np.unique(session_id)

        for sid in unique_sessions:
            # ===== ISOLAMENTO SESSIONE =====
            mask = (session_id == sid)
            session_jd = jd[mask]
            session_mag = mag[mask]

            n_points = len(session_mag)

            # Skip se troppo pochi punti
            if n_points < MIN_POINTS_PER_SESSION:
                logger.warning(f"Sessione {sid}: solo {n_points} punti, skip")
                continue

            # ===== CALCOLA ESTREMI CON BINNING =====
            extrema = compute_extrema_binned(
                session_jd,
                session_mag,
                bin_size=bin_size,
                prominence=prominence
            )

            binned_jd = extrema["binned_jd"]
            binned_mag = extrema["binned_mag"]

            global_max_idx = extrema["global_max_idx"]
            global_min_idx = extrema["global_min_idx"]

            mag_max = float(binned_mag[global_max_idx])
            mag_min = float(binned_mag[global_min_idx])
            amplitude = mag_max - mag_min

            # ===== COSTRUISCI RISULTATO =====
            results[int(sid)] = {
                "global_max": {
                    "jd": float(binned_jd[global_max_idx]),
                    "mag": mag_max
                },
                "global_min": {
                    "jd": float(binned_jd[global_min_idx]),
                    "mag": mag_min
                },
                "amplitude": float(amplitude),
                "local_maxima": [
                    {
                        "jd": float(binned_jd[i]),
                        "mag": float(binned_mag[i]),
                        "prominence": float(extrema["max_prominences"][j])
                    }
                    for j, i in enumerate(extrema["local_max_idx"])
                ],
                "local_minima": [
                    {
                        "jd": float(binned_jd[i]),
                        "mag": float(binned_mag[i]),
                        "prominence": float(extrema["min_prominences"][j])
                    }
                    for j, i in enumerate(extrema["local_min_idx"])
                ],
                "n_bins": len(binned_mag),
                "bin_size_used": bin_size,
                "n_points_original": n_points
            }

            logger.info(f"Sessione {sid}: amplitude={amplitude:.3f} mag, {len(extrema['local_max_idx'])} max, {len(extrema['local_min_idx'])} min")

        # ===== RISPOSTA GLOBALE =====
        logger.info(f"Estremi calcolati per {len(results)} sessioni")

        return jsonify({
            "sessions": results,
            "method": "Median binning + scipy.signal.find_peaks",
            "parameters": {
                "bin_size": bin_size,
                "prominence": prominence,
                "min_points_per_bin": 3
            }
        })

    except ValueError as e:
        logger.error(f"Errore validazione extrema: {e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Errore calcolo extrema: {e}", exc_info=True)
        return jsonify({"error": "Errore interno"}), 500

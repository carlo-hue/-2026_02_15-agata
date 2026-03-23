# agata/admin/services/variability_analysis.py
"""
Servizio per Analisi Comparativa di Stelle Variabili.

Funzionalità:
- Query cataloghi (Gaia DR3 Variability, VSX, ASAS-SN)
- Phased light curves con Lomb-Scargle
- Confronto χ² per similarità
- Caching Redis per performance
"""
import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
import requests
from io import BytesIO
import base64

# Astropy & Astroquery
from astropy.timeseries import LombScargle
from astroquery.gaia import Gaia

# Lightkurve per LC handling
try:
    from lightkurve import LightCurve
    LIGHTKURVE_AVAILABLE = True
except ImportError:
    LIGHTKURVE_AVAILABLE = False

# Scipy per curve fitting
from scipy.optimize import curve_fit

# Matplotlib per plot generation
import matplotlib
matplotlib.use('Agg')  # Backend non-interattivo per server
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURAZIONE CATALOGHI
# =============================================================================

# Gaia DR3 Variability Tables (via TAP)
GAIA_TAP_URL = "https://gea.esac.esa.int/tap-server/tap"

# VSX (AAVSO Variable Star Index)
# Dominio corretto: vsx.aavso.org (www.aavso.org redirige con 301)
# Formato: view=query.votable restituisce VOTable XML
VSX_API_URL = "https://vsx.aavso.org/index.php"

# ASAS-SN (già implementato in asassn.py, qui usiamo solo per cross-ref)
ASASSN_MASTER_URL = "https://asas-sn.ifa.hawaii.edu/api/v0.1/master_list"

# Tolleranze scientifiche (configurabili)
DEFAULT_TOLERANCES = {
    'bp_rp': 0.15,      # mag in color index
    'mag': 0.5,         # mag in brightness
    'teff': 300,        # Kelvin
    'period_pct': 0.005 # 0.5% del periodo
}

MAX_CANDIDATES = 100  # Limite iniziale per cache


# =============================================================================
# FUNZIONI QUERY CATALOGHI
# =============================================================================

def query_gaia_variability(
    bp_rp: float,
    mag: float,
    teff: Optional[float],
    periodo: float,
    tolerances: Dict = None
) -> List[Dict]:
    """
    Query Gaia DR3 variability tables per stelle analoghe.

    Args:
        bp_rp: Colore BP-RP della stella target
        mag: Magnitudine G della stella target
        teff: Temperatura efficace (opzionale)
        periodo: Periodo in giorni
        tolerances: Dict con tolleranze custom

    Returns:
        Lista di candidati con source_id, parametri, similarity_score
    """
    tol = tolerances or DEFAULT_TOLERANCES
    delta_p = periodo * tol['period_pct']

    try:
        # Query TAP ADQL (Gaia DR3 vari_summary + vari_time_series_statistics)
        # Nota: vari_summary non ha period, usiamo vari_classifier_result
        query = f"""
        SELECT TOP {MAX_CANDIDATES}
            vr.source_id,
            g.bp_rp,
            g.phot_g_mean_mag,
            g.teff_gspphot,
            vr.best_class_name,
            vr.best_class_score
        FROM gaiadr3.vari_classifier_result AS vr
        JOIN gaiadr3.gaia_source AS g ON vr.source_id = g.source_id
        WHERE ABS(g.bp_rp - {bp_rp}) < {tol['bp_rp']}
        AND ABS(g.phot_g_mean_mag - {mag}) < {tol['mag']}
        """

        if teff is not None:
            query += f" AND ABS(g.teff_gspphot - {teff}) < {tol['teff']}"

        # Filtra per classe variabile (es. DSCT, RR, MIRA)
        # Nota: period non direttamente in vari_classifier_result,
        # serve vari_time_series_statistics (ma è pesante)

        logger.info(f"Gaia TAP query: {query[:200]}...")

        job = Gaia.launch_job(query)
        results = job.get_results()

        if len(results) == 0:
            return []

        # Converti in lista dict
        df = results.to_pandas()
        candidates = []

        for _, row in df.iterrows():
            # Calcola distanza euclidea normalizzata
            dist = np.sqrt(
                ((row['bp_rp'] - bp_rp) / tol['bp_rp'])**2 +
                ((row['phot_g_mean_mag'] - mag) / tol['mag'])**2
            )

            if teff and not pd.isna(row['teff_gspphot']):
                dist += ((row['teff_gspphot'] - teff) / tol['teff'])**2
                dist = np.sqrt(dist)

            similarity = 1 / (1 + dist)

            candidates.append({
                'source_id': str(row['source_id']),
                'catalog': 'Gaia DR3',
                'bp_rp': float(row['bp_rp']) if not pd.isna(row['bp_rp']) else None,
                'mag': float(row['phot_g_mean_mag']),
                'teff': float(row['teff_gspphot']) if not pd.isna(row['teff_gspphot']) else None,
                'var_type': row['best_class_name'] if not pd.isna(row['best_class_name']) else 'unknown',
                'class_score': float(row['best_class_score']) if not pd.isna(row['best_class_score']) else None,
                'period': None,  # Non disponibile in vari_classifier_result
                'similarity_score': float(similarity)
            })

        logger.info(f"Gaia: trovati {len(candidates)} candidati")
        return candidates

    except Exception as e:
        logger.error(f"Errore query Gaia Variability: {e}", exc_info=True)
        return []


def query_vsx(
    ra: float,
    dec: float,
    mag: float = None,
    periodo: float = None,
    tolerances: Dict = None,
    radius_deg: float = 5.0,
    max_mag: float = None,
    min_mag: float = None,
    period_min: float = None,
    period_max: float = None,
    vartype: str = None,
    spec_type: str = None
) -> List[Dict]:
    """
    Query VSX (AAVSO Variable Star Index) per stelle analoghe.

    VSX API supporta ricerca avanzata per magnitudine, periodo, tipo variabile e classe spettrale.
    Docs: https://www.aavso.org/apis-aavso-resources

    Args:
        ra: Right Ascension in gradi
        dec: Declination in gradi
        mag: Magnitudine centrale (V o G) - usato se max_mag/min_mag non specificati
        periodo: Periodo centrale in giorni - usato se period_min/max non specificati
        tolerances: Dict tolleranze (usate solo se mag/periodo centrali specificati)
        radius_deg: Raggio ricerca in gradi (default 5°)
        max_mag: Magnitudine massima (limite superiore)
        min_mag: Magnitudine minima (limite inferiore)
        period_min: Periodo minimo in giorni
        period_max: Periodo massimo in giorni
        vartype: Tipo variabile (es: 'RRAB', 'EA', 'DSCT') - abbreviazione GCVS
        spec_type: Classe spettrale (es: 'G2V', 'M3III')

    Returns:
        Lista candidati VSX ranked per similarità
    """
    tol = tolerances or DEFAULT_TOLERANCES

    try:
        from astroquery.vizier import Vizier

        # Costruisci filtri per VizieR catalogo B/vsx
        # Colonne: Name, Type, max, min, Period, Sp, RAJ2000, DEJ2000
        column_filters = {}

        # Periodo: range
        p_min = period_min if period_min is not None else (periodo - periodo * tol['period_pct'] if periodo else None)
        p_max = period_max if period_max is not None else (periodo + periodo * tol['period_pct'] if periodo else None)
        if p_min is not None and p_max is not None:
            column_filters['Period'] = f'{p_min}..{p_max}'
        elif p_min is not None:
            column_filters['Period'] = f'>{p_min}'
        elif p_max is not None:
            column_filters['Period'] = f'<{p_max}'

        # Magnitudine (colonna 'max' = magnitudine al massimo della curva di luce)
        m_min = min_mag if min_mag is not None else (mag - tol['mag'] if mag else None)
        m_max = max_mag if max_mag is not None else (mag + tol['mag'] if mag else None)
        if m_min is not None and m_max is not None:
            column_filters['max'] = f'{m_min}..{m_max}'
        elif m_max is not None:
            column_filters['max'] = f'<{m_max}'

        # Tipo variabile e classe spettrale
        if vartype:
            column_filters['Type'] = vartype.strip()
        if spec_type:
            column_filters['Sp'] = spec_type.strip()

        logger.info(f"VSX/VizieR query: filters={column_filters}")

        v = Vizier(
            columns=['Name', 'Type', 'max', 'min', 'Period', 'Sp', 'RAJ2000', 'DEJ2000'],
            column_filters=column_filters,
            row_limit=MAX_CANDIDATES
        )

        catalogs = v.get_catalogs('B/vsx')
        table = catalogs[0] if catalogs else None

        if table is None or len(table) == 0:
            logger.warning("VSX/VizieR: nessun risultato")
            return []

        logger.info(f"VSX/VizieR: {len(table)} risultati dal catalogo")

        # Parametri centrali per similarità
        mag_central = mag or ((max_mag + min_mag) / 2 if max_mag and min_mag else None)
        periodo_central = periodo or ((p_min + p_max) / 2 if p_min and p_max else None)

        candidates = []
        for row in table:
            try:
                obj_name = str(row['Name']).strip()
                obj_type = str(row['Type']).strip()
                obj_spec = str(row['Sp']).strip() if row['Sp'] else ''

                obj_ra = float(row['RAJ2000']) if row['RAJ2000'] else ra
                obj_dec = float(row['DEJ2000']) if row['DEJ2000'] else dec

                obj_max_mag = float(row['max']) if row['max'] else None
                obj_min_mag = float(row['min']) if row['min'] else None
                obj_mag = obj_max_mag or obj_min_mag or (mag_central or 0)

                obj_period = float(row['Period']) if row['Period'] else None
                if obj_period == 0.0:
                    obj_period = None

                # Calcola similarità
                dist_components = []
                if mag_central is not None and obj_mag > 0:
                    dist_components.append(((obj_mag - mag_central) / tol['mag'])**2)
                if periodo_central is not None and obj_period is not None:
                    delta_p = periodo_central * tol['period_pct']
                    period_tolerance = delta_p if delta_p > 0 else 0.01
                    dist_components.append(((obj_period - periodo_central) / period_tolerance)**2)

                similarity = 1 / (1 + np.sqrt(sum(dist_components))) if dist_components else 0.5

                candidates.append({
                    'source_id': obj_name,
                    'catalog': 'VSX',
                    'name': obj_name,
                    'var_type': obj_type,
                    'spec_type': obj_spec,
                    'mag': obj_mag,
                    'mag_max': obj_max_mag,
                    'mag_min': obj_min_mag,
                    'period': obj_period,
                    'ra': obj_ra,
                    'dec': obj_dec,
                    'similarity_score': float(similarity)
                })
            except Exception as row_error:
                logger.warning(f"Error parsing VSX row: {row_error}")
                continue

        # Ordina per similarità decrescente
        candidates.sort(key=lambda x: x['similarity_score'], reverse=True)

        logger.info(f"VSX: trovati {len(candidates)} candidati")
        return candidates

    except Exception as e:
        logger.error(f"Errore query VSX/VizieR: {e}", exc_info=True)
        return []


def trova_stelle_analoghe(
    gaia_id: str,
    bp_rp: float,
    mag: float,
    ra: float,
    dec: float,
    periodi: List[float],
    teff: Optional[float] = None,
    top_n: int = 10,
    # Parametri VSX avanzati
    radius_deg: float = 5.0,
    max_mag: float = None,
    min_mag: float = None,
    period_min: float = None,
    period_max: float = None,
    vartype: str = None,
    spec_type: str = None
) -> List[Dict]:
    """
    Funzione principale: trova stelle variabili analoghe da VSX (AAVSO).

    Args:
        gaia_id: Gaia source_id stella target
        bp_rp: Colore BP-RP (non usato da VSX ma mantenuto per compatibilità)
        mag: Magnitudine G centrale (usato se max_mag/min_mag non specificati)
        ra, dec: Coordinate (per cone search VSX)
        periodi: Lista periodi candidati (da periodogramma, usato per period_min/max se non specificati)
        teff: Temperatura efficace (non usato da VSX)
        top_n: Numero massimo risultati
        radius_deg: Raggio cone search in gradi (default 5°)
        max_mag: Magnitudine massima per filtro VSX
        min_mag: Magnitudine minima per filtro VSX
        period_min: Periodo minimo in giorni
        period_max: Periodo massimo in giorni
        vartype: Tipo variabile GCVS (es: 'RRAB', 'EA', 'DSCT')
        spec_type: Classe spettrale (es: 'G2V', 'M3III')

    Returns:
        Lista stelle VSX analoghe ranked per similarity_score
    """
    all_candidates = []

    # Query VSX (AAVSO Variable Star Index) con parametri avanzati
    # Se period_min/max non specificati, usa periodo primario da periodogramma
    periodo_query = periodi[0] if periodi else None

    vsx_cands = query_vsx(
        ra=ra,
        dec=dec,
        mag=mag,
        periodo=periodo_query,
        radius_deg=radius_deg,
        max_mag=max_mag,
        min_mag=min_mag,
        period_min=period_min,
        period_max=period_max,
        vartype=vartype,
        spec_type=spec_type
    )
    all_candidates.extend(vsx_cands)

    # Sort per similarità e ritorna top_n
    sorted_cands = sorted(all_candidates, key=lambda x: x['similarity_score'], reverse=True)

    logger.info(f"Trovate {len(sorted_cands)} stelle VSX analoghe per Gaia {gaia_id}")
    return sorted_cands[:top_n]


# =============================================================================
# PHASED LIGHT CURVE E χ² FIT
# =============================================================================

def fourier_model(phase: np.ndarray, a1: float, phi1: float, a2: float, phi2: float) -> np.ndarray:
    """
    Modello Fourier 2nd order per fit LC phased.

    Args:
        phase: Array fase 0-1
        a1, phi1: Ampiezza e fase primo armonico
        a2, phi2: Ampiezza e fase secondo armonico

    Returns:
        Modello flux normalizzato
    """
    return 1 + a1 * np.sin(2 * np.pi * phase + phi1) + a2 * np.sin(4 * np.pi * phase + phi2)


def phase_fold_lightcurve(
    time: np.ndarray,
    flux: np.ndarray,
    flux_err: np.ndarray,
    periodo: float
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Phase-fold light curve con periodo dato.

    Args:
        time: Array tempi (HJD)
        flux: Array flussi (o magnitudini normalizzate)
        flux_err: Array errori
        periodo: Periodo in giorni

    Returns:
        Tuple (phase, flux, flux_err) sorted by phase
    """
    phase = (time % periodo) / periodo

    # Sort by phase
    sort_idx = np.argsort(phase)
    return phase[sort_idx], flux[sort_idx], flux_err[sort_idx]


def compute_chi2_fit(
    phase: np.ndarray,
    flux: np.ndarray,
    flux_err: np.ndarray
) -> Dict:
    """
    Calcola χ² fit con modello Fourier 2nd order.

    Args:
        phase: Fase 0-1
        flux: Flusso normalizzato
        flux_err: Errori

    Returns:
        Dict con chi2_reduced, model_params, residuals
    """
    try:
        # Normalizza flux (mean=1 per Fourier model)
        flux_mean = np.nanmean(flux)
        flux_norm = flux / flux_mean
        flux_err_norm = flux_err / flux_mean

        # Initial guess
        p0 = [0.1, 0, 0.05, 0]

        # Curve fit
        popt, pcov = curve_fit(
            fourier_model,
            phase,
            flux_norm,
            sigma=flux_err_norm,
            p0=p0,
            maxfev=5000
        )

        # Calcola modello e residui
        model = fourier_model(phase, *popt)
        residuals = flux_norm - model

        # χ² ridotto
        chi2 = np.sum((residuals / flux_err_norm)**2)
        dof = len(flux) - len(popt)
        chi2_reduced = chi2 / dof if dof > 0 else np.inf

        return {
            'chi2_reduced': float(chi2_reduced),
            'model_params': {
                'a1': float(popt[0]),
                'phi1': float(popt[1]),
                'a2': float(popt[2]),
                'phi2': float(popt[3])
            },
            'residuals_std': float(np.std(residuals)),
            'success': True
        }

    except Exception as e:
        logger.error(f"Errore χ² fit: {e}")
        return {
            'chi2_reduced': None,
            'success': False,
            'error': str(e)
        }


def generate_phased_comparison_plot(
    lightcurves_data: List[Dict],
    periodo: float,
    output_format: str = 'base64'
) -> Optional[str]:
    """
    Genera plot multi-panel di phased light curves confrontate.

    Args:
        lightcurves_data: Lista di dict con 'time', 'flux', 'flux_err', 'label'
        periodo: Periodo per folding
        output_format: 'base64' o 'file'

    Returns:
        Plot in formato base64 PNG o None se errore
    """
    try:
        n_lcs = len(lightcurves_data)
        if n_lcs == 0:
            return None

        fig, axs = plt.subplots(1, n_lcs, figsize=(5 * n_lcs, 4), squeeze=False)
        axs = axs.flatten()

        for i, lc_data in enumerate(lightcurves_data):
            time = np.array(lc_data['time'])
            flux = np.array(lc_data['flux'])
            flux_err = np.array(lc_data.get('flux_err', np.ones_like(flux) * 0.01))
            label = lc_data.get('label', f'LC {i+1}')

            # Phase fold
            phase, flux_phased, err_phased = phase_fold_lightcurve(time, flux, flux_err, periodo)

            # Compute χ² fit
            fit_result = compute_chi2_fit(phase, flux_phased, err_phased)

            # Plot
            axs[i].errorbar(phase, flux_phased, yerr=err_phased, fmt='o', markersize=3, alpha=0.6)

            # Overlay model se fit success
            if fit_result['success']:
                phase_model = np.linspace(0, 1, 200)
                params = fit_result['model_params']
                model_flux = fourier_model(phase_model, params['a1'], params['phi1'], params['a2'], params['phi2'])
                axs[i].plot(phase_model, model_flux, 'r-', linewidth=1.5, label='Fourier fit')

                chi2_str = f"χ²={fit_result['chi2_reduced']:.2f}"
            else:
                chi2_str = "Fit failed"

            axs[i].set_title(f"{label}\n{chi2_str}", fontsize=10)
            axs[i].set_xlabel('Phase')
            axs[i].set_ylabel('Normalized Flux')
            axs[i].invert_yaxis()  # Magnitudini invertite
            axs[i].grid(alpha=0.3)
            axs[i].legend(fontsize=8)

        plt.tight_layout()

        # Converti in base64 PNG
        if output_format == 'base64':
            buffer = BytesIO()
            plt.savefig(buffer, format='png', dpi=100)
            buffer.seek(0)
            img_base64 = base64.b64encode(buffer.read()).decode('utf-8')
            plt.close(fig)
            return img_base64
        else:
            # Save to file (opzionale)
            plt.savefig('/tmp/phased_comparison.png', dpi=100)
            plt.close(fig)
            return '/tmp/phased_comparison.png'

    except Exception as e:
        logger.error(f"Errore generazione plot: {e}", exc_info=True)
        plt.close('all')
        return None


# =============================================================================
# HELPER: RECUPERO LIGHTCURVE DA DATABASE
# =============================================================================

def get_lightcurve_from_db(db, gaia_id: str, catalog: str = None) -> Optional[Dict]:
    """
    Recupera lightcurve dal database Cataloghi_esterni.

    Args:
        db: SQLAlchemy session
        gaia_id: Gaia source_id
        catalog: Nome catalogo (es. 'ASAS-SN', 'TESS'), se None prende tutti

    Returns:
        Dict con time, flux (o mag), flux_err
    """
    from sqlalchemy import text

    try:
        # Converti gaia_id in intero (gestisci sia str che int)
        if isinstance(gaia_id, str):
            gaia_id_numeric = gaia_id.replace("Gaia DR3 ", "").strip()
            gaia_id_int = int(gaia_id_numeric)
        else:
            gaia_id_int = int(gaia_id)

        logger.info(f"Fetching lightcurve for Gaia {gaia_id_int}, catalog={catalog}")

        # Query SQL raw (Cataloghi_esterni non ha model SQLAlchemy)
        if catalog:
            sql = text("""
                SELECT hjd, Vmag
                FROM Cataloghi_esterni
                WHERE Source = :gaia_id AND catalogo = :catalog
                ORDER BY hjd
            """)
            result = db.execute(sql, {'gaia_id': gaia_id_int, 'catalog': catalog})
        else:
            sql = text("""
                SELECT hjd, Vmag
                FROM Cataloghi_esterni
                WHERE Source = :gaia_id
                ORDER BY hjd
            """)
            result = db.execute(sql, {'gaia_id': gaia_id_int})

        records = result.fetchall()

        if not records:
            logger.warning(f"No lightcurve data found for Gaia {gaia_id_int}" +
                          (f", catalog={catalog}" if catalog else " (all catalogs)"))
            return None

        # Converti in arrays
        times = []
        mags = []

        for row in records:
            hjd, vmag = row
            if hjd is not None and vmag is not None:
                times.append(float(hjd))
                mags.append(float(vmag))

        if len(times) == 0:
            logger.warning(f"No valid data points for Gaia {gaia_id}")
            return None

        # Converti mag → flux normalizzato (flip per plot)
        mags = np.array(mags)
        mag_mean = np.mean(mags)
        flux_norm = 10**(-(mags - mag_mean) / 2.5)  # Flux relativo

        # Errori fotometrici: stima da scatter se non disponibili
        mag_err = np.std(mags) if len(mags) > 5 else 0.01
        flux_err = np.full_like(flux_norm, mag_err * flux_norm[0] / 2.5)

        logger.info(f"Retrieved {len(times)} lightcurve points for Gaia {gaia_id}")

        return {
            'time': np.array(times),
            'flux': flux_norm,
            'flux_err': flux_err
        }

    except Exception as e:
        logger.error(f"Errore recupero LC da DB: {e}", exc_info=True)
        return None

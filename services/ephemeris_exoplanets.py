"""
services/ephemeris_exoplanets.py - Analisi Effemeridi Transiti Esopianeti

Gestisce:
- Calcolo tempi di transito (mid-transit times)
- Effemeridi lineari: T(E) = T0 + E × P
- Analisi O-C (Observed - Calculated)
- Export formato ExoClock

Riferimenti:
- Winn 2010, arXiv:1001.2010 (exoplanet transits)
- ExoClock: https://www.exoclock.space/

Autore: AGATA Project Team  
Data: 2026-01-03
"""

import numpy as np
import logging
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class TransitTime:
    """
    Singolo tempo di transito osservato.
    """
    epoch: int              # Numero epoca (0, 1, 2, ...)
    t_mid: float           # Tempo centro transito [JD]
    t_mid_err: float       # Errore su t_mid [giorni]
    depth: float           # Profondità transito osservata
    duration: float        # Durata transito [giorni]
    snr: float            # Signal-to-Noise Ratio
    is_valid: bool = True  # Flag validità


@dataclass
class Ephemeris:
    """
    Effemeridi lineari del pianeta.
    
    T(E) = T0 + E × P
    """
    t0: float              # Epoca zero (primo transito) [JD]
    t0_err: float          # Errore su T0 [giorni]
    period: float          # Periodo orbitale [giorni]
    period_err: float      # Errore su periodo [giorni]
    n_transits: int        # Numero transiti usati
    rms_oc: float          # RMS residui O-C [minuti]
    chi2_reduced: float    # Chi-quadro ridotto


# =============================================================================
# RILEVAMENTO TRANSITI INDIVIDUALI
# =============================================================================

def detect_individual_transits(
    jd: np.ndarray,
    flux: np.ndarray,
    period: float,
    t0: float,
    duration: float
) -> List[TransitTime]:
    """
    Rileva e misura transiti individuali nella curva di luce.
    
    Args:
        jd: Array Julian Dates
        flux: Array flussi relativi
        period: Periodo orbitale [giorni]
        t0: Epoca primo transito [JD]
        duration: Durata transito [giorni]
    
    Returns:
        Lista TransitTime con transiti rilevati
    """
    logger.info(f"Rilevamento transiti: P={period:.4f}d, T0={t0:.6f}")
    
    # Calcola baseline
    baseline = jd.max() - jd.min()
    n_expected = int(baseline / period) + 1
    
    logger.info(f"Baseline: {baseline:.1f}d, transiti attesi: {n_expected}")
    
    transits = []
    
    # Per ogni transito atteso
    for epoch in range(n_expected):
        # Tempo centro transito atteso
        t_center_expected = t0 + epoch * period
        
        # Finestra temporale attorno al transito
        t_start = t_center_expected - duration * 1.5
        t_end = t_center_expected + duration * 1.5
        
        # Seleziona dati in finestra
        mask = (jd >= t_start) & (jd <= t_end)
        
        if mask.sum() < 3:
            logger.debug(f"Epoca {epoch}: troppo pochi punti ({mask.sum()})")
            continue
        
        jd_transit = jd[mask]
        flux_transit = flux[mask]
        
        # =====================================================================
        # MISURA TEMPO CENTRO TRANSITO
        # =====================================================================
        
        # Metodo 1: Minimo flusso (semplice)
        idx_min = np.argmin(flux_transit)
        t_mid = jd_transit[idx_min]
        
        # Metodo 2: Fit parabola intorno al minimo (più accurato)
        # TODO: Implementare fit parabola per maggiore precisione
        
        # Errore stimato (approssimato)
        cadence = np.median(np.diff(np.sort(jd)))
        flux_std = np.std(flux)
        depth_measured = 1.0 - np.min(flux_transit)
        
        # Errore tempo ~ cadenza / SNR
        snr = depth_measured / flux_std if flux_std > 0 else 0
        t_mid_err = cadence / max(snr, 1.0)
        
        # =====================================================================
        # VALIDAZIONE TRANSITO
        # =====================================================================
        
        is_valid = True
        
        # Check 1: SNR minimo
        if snr < 3.0:
            logger.debug(f"Epoca {epoch}: SNR troppo basso ({snr:.2f})")
            is_valid = False
        
        # Check 2: Profondità consistente
        expected_depth = 1.0 - np.median(flux)  # Approssimazione
        if abs(depth_measured - expected_depth) > 3 * flux_std:
            logger.debug(f"Epoca {epoch}: profondità anomala")
            is_valid = False
        
        # =====================================================================
        # AGGIUNGI TRANSITO
        # =====================================================================
        
        transit = TransitTime(
            epoch=epoch,
            t_mid=t_mid,
            t_mid_err=t_mid_err,
            depth=depth_measured,
            duration=(jd_transit[-1] - jd_transit[0]),
            snr=snr,
            is_valid=is_valid
        )
        
        transits.append(transit)
        
        logger.debug(
            f"Epoca {epoch}: T_mid={t_mid:.6f} ± {t_mid_err*1440:.2f} min, "
            f"SNR={snr:.2f}, valid={is_valid}"
        )
    
    logger.info(f"Rilevati {len(transits)} transiti ({sum(t.is_valid for t in transits)} validi)")
    
    return transits


# =============================================================================
# CALCOLO EFFEMERIDI
# =============================================================================

def calculate_ephemeris(transits: List[TransitTime]) -> Ephemeris:
    """
    Calcola effemeridi lineari da transiti osservati.
    
    Fit lineare: T(E) = T0 + E × P
    
    Args:
        transits: Lista transiti osservati
    
    Returns:
        Ephemeris con parametri ottimali
    """
    # Filtra solo transiti validi
    valid_transits = [t for t in transits if t.is_valid]
    
    if len(valid_transits) < 2:
        raise ValueError("Servono almeno 2 transiti validi per effemeridi")
    
    logger.info(f"Calcolo effemeridi da {len(valid_transits)} transiti validi")
    
    # Estrai dati
    epochs = np.array([t.epoch for t in valid_transits])
    t_mids = np.array([t.t_mid for t in valid_transits])
    t_mid_errs = np.array([t.t_mid_err for t in valid_transits])
    
    # =========================================================================
    # FIT LINEARE PESATO
    # =========================================================================
    
    # Pesi = 1 / sigma^2
    weights = 1.0 / t_mid_errs**2
    
    # Fit pesato: T = a + b*E
    # a = T0, b = Period
    sum_w = np.sum(weights)
    sum_wx = np.sum(weights * epochs)
    sum_wy = np.sum(weights * t_mids)
    sum_wxx = np.sum(weights * epochs**2)
    sum_wxy = np.sum(weights * epochs * t_mids)
    
    # Soluzione sistema lineare
    delta = sum_w * sum_wxx - sum_wx**2
    
    t0 = (sum_wxx * sum_wy - sum_wx * sum_wxy) / delta
    period = (sum_w * sum_wxy - sum_wx * sum_wy) / delta
    
    # Errori
    t0_err = np.sqrt(sum_wxx / delta)
    period_err = np.sqrt(sum_w / delta)
    
    logger.info(
        f"Effemeridi:\n"
        f"  T0 = {t0:.6f} ± {t0_err*1440:.2f} min\n"
        f"  P  = {period:.6f} ± {period_err*86400:.2f} sec"
    )
    
    # =========================================================================
    # CALCOLA O-C E STATISTICHE
    # =========================================================================
    
    # Tempi calcolati
    t_calc = t0 + epochs * period
    
    # Residui O-C (Observed - Calculated)
    oc = t_mids - t_calc
    oc_minutes = oc * 1440  # giorni → minuti
    
    # RMS residui
    rms_oc = np.sqrt(np.mean(oc**2)) * 1440  # minuti
    
    # Chi-quadro ridotto
    chi2 = np.sum(((oc / t_mid_errs)**2))
    dof = len(valid_transits) - 2  # 2 parametri (T0, P)
    chi2_reduced = chi2 / dof if dof > 0 else np.inf
    
    logger.info(
        f"Qualità fit:\n"
        f"  RMS O-C: {rms_oc:.2f} min\n"
        f"  χ²_red: {chi2_reduced:.2f}"
    )
    
    # =========================================================================
    # RETURN
    # =========================================================================
    
    return Ephemeris(
        t0=t0,
        t0_err=t0_err,
        period=period,
        period_err=period_err,
        n_transits=len(valid_transits),
        rms_oc=rms_oc,
        chi2_reduced=chi2_reduced
    )


# =============================================================================
# CALCOLO O-C
# =============================================================================

def calculate_oc(
    transits: List[TransitTime],
    ephemeris: Ephemeris
) -> Dict:
    """
    Calcola residui O-C per tutti i transiti.
    
    Args:
        transits: Lista transiti osservati
        ephemeris: Effemeridi di riferimento
    
    Returns:
        Dict con dati O-C
    """
    epochs = []
    t_obs = []
    t_calc = []
    oc_values = []
    oc_err = []
    is_valid_list = []
    
    for transit in transits:
        epoch = transit.epoch
        
        # Tempo calcolato
        t_c = ephemeris.t0 + epoch * ephemeris.period
        
        # O-C
        oc = transit.t_mid - t_c
        
        epochs.append(epoch)
        t_obs.append(transit.t_mid)
        t_calc.append(t_c)
        oc_values.append(oc * 1440)  # minuti
        oc_err.append(transit.t_mid_err * 1440)  # minuti
        is_valid_list.append(transit.is_valid)
    
    return {
        "epochs": epochs,
        "t_observed": t_obs,
        "t_calculated": t_calc,
        "oc_minutes": oc_values,
        "oc_err_minutes": oc_err,
        "is_valid": is_valid_list
    }


# =============================================================================
# EXPORT EXOCLOCK
# =============================================================================

def export_exoclock_format(
    transits: List[TransitTime],
    ephemeris: Ephemeris,
    planet_name: str = "Test Planet",
    observer: str = "AGATA",
    filter_band: str = "Clear"
) -> str:
    """
    Esporta dati in formato ExoClock.
    
    Formato ExoClock CSV:
    Epoch,BJD_TDB,Error,O-C,Filter,Observer,Notes
    
    Args:
        transits: Lista transiti
        ephemeris: Effemeridi
        planet_name: Nome pianeta
        observer: Nome osservatore
        filter_band: Filtro usato
    
    Returns:
        String CSV formattato per ExoClock
    """
    lines = []
    
    # Header
    lines.append("# ExoClock Transit Times Export")
    lines.append(f"# Planet: {planet_name}")
    lines.append(f"# Observer: {observer}")
    lines.append(f"# Filter: {filter_band}")
    lines.append(f"# Ephemeris: T0={ephemeris.t0:.6f}, P={ephemeris.period:.6f}")
    lines.append("#")
    lines.append("Epoch,BJD_TDB,Error_days,O-C_min,Filter,Observer,Valid")
    
    # Dati
    for transit in transits:
        # Calcola O-C
        t_calc = ephemeris.t0 + transit.epoch * ephemeris.period
        oc = (transit.t_mid - t_calc) * 1440  # minuti
        
        # Formato riga
        line = (
            f"{transit.epoch},"
            f"{transit.t_mid:.6f},"
            f"{transit.t_mid_err:.6f},"
            f"{oc:.3f},"
            f"{filter_band},"
            f"{observer},"
            f"{transit.is_valid}"
        )
        lines.append(line)
    
    return "\n".join(lines)


# =============================================================================
# UTILITY: PREDIZIONE TRANSITI FUTURI
# =============================================================================

def predict_future_transits(
    ephemeris: Ephemeris,
    jd_start: float,
    jd_end: float
) -> List[Dict]:
    """
    Predice transiti futuri date le effemeridi.
    
    Args:
        ephemeris: Effemeridi pianeta
        jd_start: JD inizio intervallo
        jd_end: JD fine intervallo
    
    Returns:
        Lista dict con transiti predetti
    """
    # Calcola epoca iniziale
    epoch_start = int((jd_start - ephemeris.t0) / ephemeris.period)
    epoch_end = int((jd_end - ephemeris.t0) / ephemeris.period) + 1
    
    predictions = []
    
    for epoch in range(epoch_start, epoch_end + 1):
        t_mid = ephemeris.t0 + epoch * ephemeris.period
        
        # Solo transiti futuri nell'intervallo
        if t_mid < jd_start or t_mid > jd_end:
            continue
        
        # Errore propagato
        t_mid_err = np.sqrt(
            ephemeris.t0_err**2 + 
            (epoch * ephemeris.period_err)**2
        )
        
        predictions.append({
            "epoch": epoch,
            "t_mid": t_mid,
            "t_mid_err": t_mid_err,
            "t_mid_err_minutes": t_mid_err * 1440
        })
    
    return predictions


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    """
    Test modulo effemeridi.
    """
    logging.basicConfig(level=logging.INFO)
    
    print("="*60)
    print("TEST MODULO EFFEMERIDI ESOPIANETI")
    print("="*60)
    print()
    
    # Genera dati test
    period_true = 3.5
    t0_true = 2460000.5
    n_transits = 10
    
    # Simula transiti osservati con rumore
    transits = []
    for epoch in range(n_transits):
        t_mid = t0_true + epoch * period_true
        t_mid += np.random.normal(0, 0.0005)  # Rumore ~1 min
        
        transit = TransitTime(
            epoch=epoch,
            t_mid=t_mid,
            t_mid_err=0.0007,  # ~1 minuto errore
            depth=0.01,
            duration=0.1,
            snr=10.0,
            is_valid=True
        )
        transits.append(transit)
    
    # Calcola effemeridi
    print("Test 1: Calcolo Effemeridi")
    print("-"*60)
    ephemeris = calculate_ephemeris(transits)
    
    print(f"\nInput: T0={t0_true:.6f}, P={period_true:.6f}")
    print(f"Fit:   T0={ephemeris.t0:.6f} ± {ephemeris.t0_err*1440:.2f} min")
    print(f"       P ={ephemeris.period:.6f} ± {ephemeris.period_err*86400:.2f} sec")
    print(f"RMS O-C: {ephemeris.rms_oc:.2f} min")
    print()
    
    # Calcola O-C
    print("Test 2: Calcolo O-C")
    print("-"*60)
    oc_data = calculate_oc(transits, ephemeris)
    
    for i in range(min(5, len(oc_data["epochs"]))):
        print(
            f"Epoca {oc_data['epochs'][i]}: "
            f"O-C = {oc_data['oc_minutes'][i]:+.2f} ± {oc_data['oc_err_minutes'][i]:.2f} min"
        )
    print()
    
    # Export ExoClock
    print("Test 3: Export ExoClock")
    print("-"*60)
    csv_export = export_exoclock_format(transits, ephemeris, "WASP-12b")
    print(csv_export[:500] + "...")
    print()
    
    # Predizione
    print("Test 4: Predizione Transiti Futuri")
    print("-"*60)
    jd_start = t0_true + 11 * period_true
    jd_end = jd_start + 20
    
    predictions = predict_future_transits(ephemeris, jd_start, jd_end)
    
    for pred in predictions[:5]:
        print(
            f"Epoca {pred['epoch']}: "
            f"T_mid = {pred['t_mid']:.6f} ± {pred['t_mid_err_minutes']:.2f} min"
        )
    
    print()
    print("="*60)
    print("✓ Test completato")
    print("="*60)
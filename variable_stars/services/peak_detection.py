"""
peak_detection.py - Identificazione picchi e estremi in curve di luce

Wrapper attorno a scipy.signal.find_peaks con logica specifica per fotometria.
"""

import numpy as np
from scipy.signal import find_peaks
from typing import Tuple, Dict, List


def find_maxima(magnitudes: np.ndarray, prominence: float = 0.1, distance: int = 3) -> Tuple[np.ndarray, Dict]:
    """
    Trova massimi locali (stella più debole) in curva di luce.

    Args:
        magnitudes: Array magnitudini
        prominence: Prominenza minima picchi [mag]
        distance: Distanza minima tra picchi [punti]

    Returns:
        Tuple[np.ndarray, Dict]: (indici picchi, proprietà picchi)

    Nota:
        In astronomia: mag alta = stella debole
    """
    try:
        peaks_idx, properties = find_peaks(
            magnitudes,
            prominence=prominence,
            distance=distance
        )
        return peaks_idx, properties
    except Exception:
        # Se find_peaks fallisce, ritorna array vuoti
        return np.array([], dtype=int), {'prominences': np.array([])}


def find_minima(magnitudes: np.ndarray, prominence: float = 0.1, distance: int = 3) -> Tuple[np.ndarray, Dict]:
    """
    Trova minimi locali (stella più luminosa) in curva di luce.

    Args:
        magnitudes: Array magnitudini
        prominence: Prominenza minima picchi [mag]
        distance: Distanza minima tra picchi [punti]

    Returns:
        Tuple[np.ndarray, Dict]: (indici picchi, proprietà picchi)

    Nota:
        In astronomia: mag bassa = stella luminosa
        Invertiamo il segnale per trovare minimi come picchi
    """
    try:
        peaks_idx, properties = find_peaks(
            -magnitudes,  # Inverti segnale
            prominence=prominence,
            distance=distance
        )
        return peaks_idx, properties
    except Exception:
        return np.array([], dtype=int), {'prominences': np.array([])}


def compute_extrema_binned(
    jd: np.ndarray,
    mag: np.ndarray,
    bin_size: float = 0.05,
    prominence: float = 0.1
) -> Dict:
    """
    Calcola estremi usando binning mediano per ridurre rumore.

    Algoritmo:
        1. Dividi timeline in bin di dimensione fissa
        2. Calcola mediana per ogni bin (robusto a outlier)
        3. Identifica picchi su dati binned

    Args:
        jd: Julian Dates
        mag: Magnitudini
        bin_size: Dimensione bin [giorni]
        prominence: Prominenza minima per find_peaks

    Returns:
        Dict con:
            - binned_jd: JD binnati
            - binned_mag: Mag binned (mediane)
            - global_max_idx: Indice massimo globale
            - global_min_idx: Indice minimo globale
            - local_max_idx: Indici massimi locali
            - local_min_idx: Indici minimi locali
            - max_prominences: Prominenze massimi
            - min_prominences: Prominenze minimi
    """
    jd_min, jd_max = jd.min(), jd.max()
    duration = jd_max - jd_min

    # Se sessione troppo breve, usa punto singolo
    if duration < bin_size:
        binned_jd = np.array([np.median(jd)])
        binned_mag = np.array([np.median(mag)])
    else:
        bin_edges = np.arange(jd_min, jd_max + bin_size, bin_size)

        binned_jd = []
        binned_mag = []

        for i in range(len(bin_edges) - 1):
            in_bin = (jd >= bin_edges[i]) & (jd < bin_edges[i + 1])
            n_in_bin = np.sum(in_bin)

            if n_in_bin > 0:
                binned_jd.append(np.median(jd[in_bin]))
                binned_mag.append(np.median(mag[in_bin]))

        binned_jd = np.array(binned_jd)
        binned_mag = np.array(binned_mag)

    # Se troppo pochi bin, usa dati raw
    if len(binned_mag) < 3:
        binned_jd = jd
        binned_mag = mag

    # Estremi globali
    global_max_idx = np.argmax(binned_mag)
    global_min_idx = np.argmin(binned_mag)

    # Estremi locali
    local_max_idx, max_props = find_maxima(binned_mag, prominence=prominence, distance=3)
    local_min_idx, min_props = find_minima(binned_mag, prominence=prominence, distance=3)

    return {
        "binned_jd": binned_jd,
        "binned_mag": binned_mag,
        "global_max_idx": global_max_idx,
        "global_min_idx": global_min_idx,
        "local_max_idx": local_max_idx,
        "local_min_idx": local_min_idx,
        "max_prominences": max_props.get('prominences', np.array([])),
        "min_prominences": min_props.get('prominences', np.array([]))
    }

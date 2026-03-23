"""
statistics.py - Funzioni statistiche robuste per fotometria

Implementa statistiche robuste agli outlier per analisi fotometriche:
- MAD (Median Absolute Deviation)
- Sigma clipping
- Weighted median
"""

import numpy as np


def calculate_mad(data: np.ndarray) -> float:
    """
    Calcola Median Absolute Deviation (MAD).

    MAD è un stimatore robusto di dispersione, immune fino a 50%
    contaminazione da outlier.

    Formula:
        MAD = median(|X - median(X)|)

    Args:
        data: Array 1D di valori

    Returns:
        float: MAD

    Riferimento:
        Huber & Ronchetti 2009, "Robust Statistics"
    """
    median = np.median(data)
    deviations = np.abs(data - median)
    return np.median(deviations)


def mad_to_sigma(mad: float) -> float:
    """
    Converte MAD in σ equivalente per distribuzione Gaussiana.

    Fattore di conversione: σ = 1.4826 × MAD

    Derivazione:
        Per N(μ,σ), il 75° percentile è μ + 0.6745σ
        Quindi MAD = 0.6745σ
        Invertendo: σ = MAD / 0.6745 = 1.4826 × MAD

    Args:
        mad: Median Absolute Deviation

    Returns:
        float: Deviazione standard equivalente
    """
    return 1.4826 * mad


def weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    """
    Calcola mediana pesata.

    Algoritmo:
        1. Ordina valori per grandezza
        2. Accumula pesi
        3. Trova valore dove peso cumulativo = 50%

    Args:
        values: Array valori
        weights: Array pesi (stesso shape di values)

    Returns:
        float: Mediana pesata

    Nota:
        Più robusta di media pesata per distribuzioni non-Gaussiane
    """
    if len(values) != len(weights):
        raise ValueError("values e weights devono avere stessa lunghezza")

    sorted_idx = np.argsort(values)
    sorted_values = values[sorted_idx]
    sorted_weights = weights[sorted_idx]

    cumsum_weights = np.cumsum(sorted_weights)
    total_weight = cumsum_weights[-1]

    median_idx = np.searchsorted(cumsum_weights, total_weight / 2.0)

    return float(sorted_values[median_idx])


def sigma_clip_mask(data: np.ndarray, sigma: float = 3.0, center_func=np.median, std_func=None) -> np.ndarray:
    """
    Crea maschera booleana per sigma clipping.

    Args:
        data: Array da clippare
        sigma: Soglia in unità σ
        center_func: Funzione per calcolare centro (default: median)
        std_func: Funzione per calcolare dispersione (default: MAD → σ)

    Returns:
        np.ndarray: Maschera booleana (True = inlier, False = outlier)
    """
    if std_func is None:
        # Usa MAD come stimatore robusto di σ
        mad = calculate_mad(data)
        sigma_equiv = mad_to_sigma(mad)
        center = center_func(data)
    else:
        center = center_func(data)
        sigma_equiv = std_func(data)

    # Protezione MAD ≈ 0
    if sigma_equiv < 1e-6:
        # Tutti i punti identici, nessun outlier
        return np.ones_like(data, dtype=bool)

    lower = center - sigma * sigma_equiv
    upper = center + sigma * sigma_equiv

    return (data >= lower) & (data <= upper)

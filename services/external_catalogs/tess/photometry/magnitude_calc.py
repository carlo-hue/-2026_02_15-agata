# -*- coding: utf-8 -*-
"""
Created on Tue Jan 20 23:05:28 2026

@author: CarloMarino
"""

# agata/services/external_catalogs/tess/photometry/magnitude_calc.py
# Calcolo matematico della magnitudine da flusso.
# Implementa l'algoritmo VStar-like (REF-002), indipendente da FITS e AGATA.

from __future__ import annotations

import numpy as np


def compute_magnitude_curve(flux: np.ndarray, mag_reference: float) -> np.ndarray:
    """
    Converte una curva di flusso in magnitudine usando l'algoritmo VStar-like
    (rif. REF-002, plugin AAVSO VStar).

    Algoritmo:
      median_flux = median(flux)
      median_inst_mag = -2.5 * log10(median_flux)
      magShift = mag_reference - median_inst_mag
      mag = magShift - 2.5 * log10(flux)

    Parametri
    ---------
    flux:
        array numpy dei flussi (deve contenere solo valori > 0 e finiti).
    mag_reference:
        magnitudine di riferimento (es. TESSMAG).

    Ritorna
    -------
    np.ndarray
        array delle magnitudini, stessa lunghezza di flux.

    Note
    ----
    - richiede flux > 0 (il reader filtra già flux <= 0)
    - non applica alcun detrending o filtraggio
    """
    flux = np.asarray(flux, dtype=np.float64)

    if flux.size == 0:
        return np.array([], dtype=np.float64)

    # Controlli di sicurezza (difensivi)
    if not np.all(np.isfinite(flux)):
        raise ValueError("Flux array contains non-finite values.")
    if np.any(flux <= 0):
        raise ValueError("Flux array contains non-positive values.")

    median_flux = np.median(flux)
    if not np.isfinite(median_flux) or median_flux <= 0:
        raise ValueError("Median flux is not valid for magnitude conversion.")

    median_inst_mag = -2.5 * np.log10(median_flux)
    mag_shift = float(mag_reference) - median_inst_mag

    mag = mag_shift - 2.5 * np.log10(flux)
    return mag

# -*- coding: utf-8 -*-
"""
Created on Tue Jan 20 23:03:39 2026

@author: CarloMarino
"""

# agata/services/external_catalogs/tess/photometry/magnitude_policy.py
# Policy scientifica per la selezione della magnitudine di riferimento (SCI-002).
# Decide "cosa usare" (es. TESSMAG), senza effettuare calcoli numerici.

from __future__ import annotations

from typing import Any, Dict, Optional


def select_magnitude_reference(
    meta: Dict[str, Any],
    *,
    allow_fallback: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Seleziona la magnitudine di riferimento secondo le regole SCI-002 (Active).

    Regole:
      1) Usa la magnitudine nativa del prodotto QLP (TESSMAG) se presente e valida.
      2) Fallback consentito solo se allow_fallback=True (non implementato qui).

    Parametri
    ---------
    meta:
        dizionario metadata prodotto dal reader (PRIMARY header QLP).
    allow_fallback:
        abilita eventuali fallback futuri (cataloghi esterni), se True.

    Ritorna
    -------
    dict:
        {"value": float, "source": "TESSMAG"}
    oppure
    None:
        se non è disponibile una magnitudine di riferimento valida.
    """
    # 1) Preferenza assoluta: TESSMAG (QLP)
    tess_mag = meta.get("tess_mag")

    try:
        if tess_mag is not None:
            value = float(tess_mag)
            # sanity check molto largo
            if -5.0 < value < 35.0:
                return {
                    "value": value,
                    "source": "TESSMAG",
                }
    except (TypeError, ValueError):
        pass

    # 2) Fallback (solo se esplicitamente consentito)
    if allow_fallback:
        # Placeholder intenzionale:
        # qui in futuro potranno entrare cataloghi esterni (Gaia, APASS, ecc.)
        return None

    return None

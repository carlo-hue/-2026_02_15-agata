# -*- coding: utf-8 -*-
"""
Created on Tue Jan 20 22:58:00 2026

@author: CarloMarino
"""

# agata/services/external_catalogs/tess/qlp_core.py

# Punto di ingresso unico per AGATA: orchestration reader → policy → calcolo magnitudini,
# Core scientifico di ingestione QLP.
# produzione curve finali e report di tracciabilità.

from __future__ import annotations

from typing import Any, Dict, Tuple, Union

# from qlp_reader import read_qlp_fits
# from magnitude_policy import select_magnitude_reference
# from magnitude_calc import compute_magnitude_curve
from agata.services.external_catalogs.tess.qlp_reader import read_qlp_fits
from agata.services.external_catalogs.tess.photometry.magnitude_policy import select_magnitude_reference
from agata.services.external_catalogs.tess.photometry.magnitude_calc import compute_magnitude_curve


def ingest_qlp_core(
    source: Union[str, bytes],
    *,
    origin: str,
    compute_magnitude: bool = True,
    allow_mag_fallback: bool = False,
    require_author: str = "QLP",
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Core pipeline pura (standalone, Opzione A: dict).

    Flusso:
      1) read_qlp_fits (validazione origine QLP, normalizzazione tempi, SAP/KSPSAP)
      2) select_magnitude_reference (regole SCI-002)
      3) compute_magnitude_curve (algoritmo VStar-like) su raw/corrected
      4) costruzione report di tracciabilità

    Nessuna dipendenza da:
      - Flask / AGATA
      - DB
      - logging esterno
      - Lightkurve

    Ritorna:
      lc_set (dict)
      report (dict)
    """
    # ---- Lettura e normalizzazione FITS ----
    lc_set = read_qlp_fits(
        source,
        origin=origin,
        require_author=require_author,
    )

    # ---- Report base ----
    report: Dict[str, Any] = {
        "origin": origin,
        "validations": lc_set.get("validations", {}),
        "magnitude_reference": None,
        "curves_produced": list(lc_set.get("curves", {}).keys()),
        "warnings": [],
    }

    if not compute_magnitude:
        return lc_set, report

    # ---- Selezione magnitudine di riferimento ----
    meta = lc_set.get("meta", {})
    mag_ref = select_magnitude_reference(
        meta,
        allow_fallback=allow_mag_fallback,
    )
    report["magnitude_reference"] = mag_ref

    if mag_ref is None:
        report["warnings"].append(
            "No magnitude reference available; magnitude computation skipped."
        )
        return lc_set, report

    # ---- Calcolo magnitudine per ciascuna curva ----
    for curve_name, curve in lc_set["curves"].items():
        try:
            curve["mag"] = compute_magnitude_curve(
                curve["flux"],
                mag_ref["value"],
            )
        except Exception as exc:
            report["warnings"].append(
                f"Magnitude computation failed for curve '{curve_name}': {exc}"
            )

    return lc_set, report

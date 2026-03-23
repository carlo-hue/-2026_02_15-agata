# -*- coding: utf-8 -*-
"""
Created on Tue Jan 20 22:33:50 2026

@author: CarloMarino
"""

# agata/services/external_catalogs/tess/qlp_reader.py
# Reader FITS QLP: parsing, normalizzazione temporale, estrazione curve SAP/KSPSAP,
# validazione robusta dell'origine QLP. Nessuna logica scientifica o di persistenza.

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple, Union

import io
import numpy as np
from astropy.io import fits


def read_qlp_fits(
    source: Union[str, bytes],
    *,
    origin: str,
    require_author: str = "QLP",
) -> Dict[str, Any]:
    """
    Legge un FITS TESS QLP e restituisce un dict normalizzato (Opzione A: no classi).

    Parametri
    ---------
    source:
        - str: path del file FITS
        - bytes: contenuto FITS in memoria
    origin:
        stringa libera per tracciabilità (es. "agata_upload", "mast_qlp")
    require_author:
        se valorizzato, attiva validazione robusta dell'origine QLP:
          - accetta se AUTHOR==QLP (in PRIMARY o table HDU) OR ORIGIN contiene "QLP"
          - rifiuta se AUTHOR esiste (primary o table), non è QLP e ORIGIN non contiene "QLP"

    Output
    ------
    dict con struttura:
      {
        "curves": {
            "raw": {"time":..., "flux":..., "flux_err":..., "quality":...},
            "corrected": {...}   # solo se KSPSAP disponibile
        },
        "meta": {...},
        "validations": {...}
      }
    """
    hdul = _open_fits(source)
    try:
        primary_hdr = hdul[0].header

        # ---- Trova HDU tabellare con colonne tempo/flusso ----
        table_hdu = _find_table_hdu_with_columns(
            hdul,
            required_any=("TIME",),
            required_all=("SAP_FLUX",),
        )
        data = table_hdu.data
        table_hdr = table_hdu.header
        table_extname = table_hdr.get("EXTNAME")


        # ---- Validazione robusta origine QLP (AUTHOR / ORIGIN) ----
        author_primary = primary_hdr.get("AUTHOR")
        author_table = table_hdr.get("AUTHOR")
        origin_hdr = (primary_hdr.get("ORIGIN") or "").strip()

        def _contains_qlp(s: str) -> bool:
            return "QLP" in s.upper()

        author_matches = (author_primary == require_author) or (author_table == require_author)
        origin_matches = _contains_qlp(origin_hdr)

        author_exists = (author_primary is not None) or (author_table is not None)

        author_ok = True
        warning_author_mismatch = False

        if require_author is not None:
            # Caso forte di rifiuto: AUTHOR presente e non QLP, e ORIGIN non indica QLP
            if author_exists and (not author_matches) and (not origin_matches):
                author_ok = False
                raise ValueError(
                    f"FITS rejected: AUTHOR primary={author_primary!r}, table={author_table!r}, "
                    f"ORIGIN={origin_hdr!r} (expected QLP)."
                )

            # Caso non bloccante: AUTHOR presente ma diverso da QLP, però ORIGIN contiene QLP
            if author_exists and (not author_matches) and origin_matches:
                warning_author_mismatch = True

            # Caso comune: AUTHOR assente, ma ORIGIN contiene QLP -> ok
            # Caso comune: AUTHOR matcha -> ok

        # ---- Time base ----
        time = _col_as_float_array(data, "TIME")

        # Reference time: spesso BJDREFI + BJDREFF (o BJDREFR)
        bjdrefi = _get_first_number(primary_hdr, table_hdr, "BJDREFI")
        bjdrefr = _get_first_number(primary_hdr, table_hdr, "BJDREFR")  # spesso 0.0
        bjdreff = _get_first_number(primary_hdr, table_hdr, "BJDREFF", default=None)

        # Se BJDREFF è presente, preferiscilo. Altrimenti usa BJDREFR.
        if bjdreff is None:
            time_abs = time + (bjdrefi or 0.0) + (bjdrefr or 0.0)
            time_ref_used = "BJDREFI+BJDREFR"
        else:
            time_abs = time + (bjdrefi or 0.0) + bjdreff
            time_ref_used = "BJDREFI+BJDREFF"

        # ---- Raw (SAP) ----
        sap_flux = _col_as_float_array(data, "SAP_FLUX")
        sap_err = _try_col_as_float_array(data, "SAP_FLUX_ERR")

        quality = _try_col_as_float_array(data, "QUALITY")
        raw = {
            "time": time_abs,
            "flux": sap_flux,
            "flux_err": sap_err,
            "quality": quality,
        }

        # ---- Corrected (KSPSAP) se disponibile ----
        corrected = None
        if _has_column(data, "KSPSAP_FLUX"):
            ksp_flux = _col_as_float_array(data, "KSPSAP_FLUX")
            ksp_err = _try_col_as_float_array(data, "KSPSAP_FLUX_ERR")
            corrected = {
                "time": time_abs,
                "flux": ksp_flux,
                "flux_err": ksp_err,
                "quality": quality,
            }

        # ---- Pulizia minima: rimuove NaN/inf e flux<=0; ordina per tempo ----
        raw = _clean_curve(raw)
        curves: Dict[str, Dict[str, Any]] = {"raw": raw}
        has_corrected = False  # FIX: inizializza prima dell'if
        if corrected is not None:
            curves["corrected"] = _clean_curve(corrected)
            has_corrected = "corrected" in curves

        if curves["raw"]["time"].size == 0:
            raise ValueError("FITS rejected: empty dataset after cleaning (raw curve).")

        # ---- Metadata (best-effort) ----
        meta = _extract_meta(primary_hdr)
        meta.update(
            {
                "origin": origin,
                "origin_hdr": origin_hdr,
                "author_primary": author_primary,
                "author_table": author_table,
                "author_effective": author_primary or author_table,
                "time_ref_used": time_ref_used,
                "bjdrefi": bjdrefi,
                "bjdrefr": bjdrefr,
                "bjdreff": bjdreff,
                "n_points_raw": int(curves["raw"]["time"].size),
                "n_points_corrected": int(curves["corrected"]["time"].size) if "corrected" in curves else 0,
                "table_extname": table_extname,
                "has_corrected": has_corrected,
            }
        )

        validations = {
            "format_ok": True,
            "table_hdu": getattr(table_hdu, "name", None),
            "time_ref_used": time_ref_used,
            "author_primary": author_primary,
            "author_table": author_table,
            "author_effective": author_primary or author_table,
            "author_ok": author_ok,
            "origin_hdr": origin_hdr,
            "origin_contains_qlp": origin_matches,
            "warning_author_mismatch": warning_author_mismatch,
        }

        return {"curves": curves, "meta": meta, "validations": validations}

    finally:
        hdul.close()


# -----------------------------
# Helpers
# -----------------------------

def _open_fits(source: Union[str, bytes]) -> fits.HDUList:
    if isinstance(source, (bytes, bytearray)):
        return fits.open(io.BytesIO(source), memmap=False)
    if isinstance(source, str):
        return fits.open(source, memmap=False)
    raise TypeError("source must be a file path (str) or bytes.")


def _find_table_hdu_with_columns(
    hdul: fits.HDUList,
    *,
    required_any: Tuple[str, ...] = (),
    required_all: Tuple[str, ...] = (),
) -> fits.BinTableHDU:
    """
    Trova il primo BinTableHDU che contiene:
      - tutte le colonne in required_all
      - almeno una colonna in required_any (se specificato)
    """
    for hdu in hdul:
        if not isinstance(hdu, (fits.BinTableHDU, fits.TableHDU)):
            continue
        if hdu.data is None:
            continue

        colnames = set([c.upper() for c in hdu.columns.names or []])

        if required_all and not all(c.upper() in colnames for c in required_all):
            continue
        if required_any and not any(c.upper() in colnames for c in required_any):
            continue

        return hdu
    raise ValueError(
        f"No table HDU found with required columns. required_all={required_all}, required_any={required_any}"
    )


def _has_column(data, name: str) -> bool:
    try:
        return name in data.names
    except Exception:
        return False


def _col_as_float_array(data, name: str) -> np.ndarray:
    if not _has_column(data, name):
        raise ValueError(f"Missing required column: {name}")
    return np.array(data[name], dtype=np.float64)


def _try_col_as_float_array(data, name: str) -> Optional[np.ndarray]:
    if not _has_column(data, name):
        return None
    return np.array(data[name], dtype=np.float64)


def _get_first_number(h1, h2, key: str, default: Optional[float] = 0.0) -> Optional[float]:
    """
    Cerca key in due header (primary e table) e ritorna float o default.
    Se default=None, ritorna None se non trovato.
    """
    for hdr in (h1, h2):
        if hdr is None:
            continue
        if key in hdr:
            try:
                return float(hdr.get(key))
            except Exception:
                pass
    return default


def _extract_meta(hdr) -> Dict[str, Any]:
    """
    Estrae metadata QLP tipici in modalità best-effort dal PRIMARY header.
    """
    def g(k, default=None):
        return hdr.get(k, default)

    return {
        "origin_hdr_raw": g("ORIGIN"),
        "object": g("OBJECT"),
        "tic_id": g("TICID"),
        "sector": g("SECTOR"),
        "camera": g("CAMERA"),
        "ccd": g("CCD"),
        "tess_mag": g("TESSMAG"),
        "ra_obj": g("RA_OBJ"),
        "dec_obj": g("DEC_OBJ"),
        "mission": g("MISSION"),
        "instrument": g("INSTRUME"),
        "tstart": g("TSTART"),
        "tstop": g("TSTOP"),
        "flux_origin": g("FLUX_ORIGIN"),
        "calib": g("CALIB"),
        "ticver": g("TICVER"),
    }


def _clean_curve(curve: Dict[str, Any]) -> Dict[str, Any]:
    """
    Pulizia minima coerente:
    - rimuove NaN/inf su time e flux
    - rimuove flux <= 0 (perché log10 e/o qualità del dato)
    - applica la stessa maschera a flux_err e quality se presenti
    - ordina per tempo
    """
    time = np.asarray(curve["time"], dtype=np.float64)
    flux = np.asarray(curve["flux"], dtype=np.float64)

    mask = np.isfinite(time) & np.isfinite(flux) & (flux > 0)

    flux_err = curve.get("flux_err")
    if flux_err is not None:
        flux_err = np.asarray(flux_err, dtype=np.float64)
        mask = mask & np.isfinite(flux_err)

    quality = curve.get("quality")
    if quality is not None:
        quality = np.asarray(quality, dtype=np.float64)
        mask = mask & np.isfinite(quality)

    out = {
        "time": time[mask],
        "flux": flux[mask],
        "flux_err": flux_err[mask] if flux_err is not None else None,
        "quality": quality[mask] if quality is not None else None,
    }

    if out["time"].size > 1:
        idx = np.argsort(out["time"])
        out["time"] = out["time"][idx]
        out["flux"] = out["flux"][idx]
        if out["flux_err"] is not None:
            out["flux_err"] = out["flux_err"][idx]
        if out["quality"] is not None:
            out["quality"] = out["quality"][idx]

    return out

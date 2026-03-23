from __future__ import annotations

import logging
import math

from astroquery.gaia import Gaia
from astropy import units as u
from astropy.coordinates import SkyCoord

from .lightcurve_service import compute_lightcurve_stub
from .save_service import save_tpf_session_stub
from .utils import build_nearby_source_entry, rounded_or_none, validate_gaia_source_id

LOGGER = logging.getLogger(__name__)
PIXEL_SCALE_ARCSEC = 21.0
NEARBY_RADIUS_DEG = 0.02
PREVIEW_SIZE_PX = 11
MAX_NEARBY_SOURCES = 25


def _relative_flux_from_gmag(gmag: float | None, reference_gmag: float | None) -> float:
    if gmag is None:
        return 0.2
    ref = reference_gmag if reference_gmag is not None else gmag
    return max(0.05, math.pow(10.0, -0.4 * (float(gmag) - float(ref))))


def _fetch_gaia_dr3_target(gaia_source_id: str) -> dict:
    query = f"""
        SELECT source_id, ra, dec, phot_g_mean_mag AS gmag
        FROM gaiadr3.gaia_source
        WHERE source_id = {gaia_source_id}
    """
    job = Gaia.launch_job(query)
    results = job.get_results()
    if len(results) == 0:
        raise ValueError("gaia_source_id non trovato in Gaia DR3")
    row = results[0]
    return {
        "gaia_source_id": str(row["source_id"]),
        "ra_deg": rounded_or_none(row["ra"], 6),
        "dec_deg": rounded_or_none(row["dec"], 6),
        "gmag": rounded_or_none(row["gmag"], 4),
        "catalog": "Gaia DR3",
    }


def _fetch_nearby_gaia_sources(target_info: dict, radius_deg: float = NEARBY_RADIUS_DEG) -> list[dict]:
    ra = float(target_info["ra_deg"])
    dec = float(target_info["dec_deg"])
    center = SkyCoord(ra=ra * u.deg, dec=dec * u.deg, frame="icrs")
    cos_dec = math.cos(math.radians(dec)) or 1.0
    query = f"""
        SELECT TOP {MAX_NEARBY_SOURCES + 1} source_id, ra, dec, phot_g_mean_mag AS gmag
        FROM gaiadr3.gaia_source
        WHERE 1 = CONTAINS(
            POINT('ICRS', gaiadr3.gaia_source.ra, gaiadr3.gaia_source.dec),
            CIRCLE('ICRS', {ra}, {dec}, {radius_deg})
        )
    """
    job = Gaia.launch_job_async(query)
    results = job.get_results()
    entries = []
    for row in results:
        source_id = str(row["source_id"])
        if source_id == target_info["gaia_source_id"]:
            continue
        row_ra = float(row["ra"])
        row_dec = float(row["dec"])
        coord = SkyCoord(row_ra * u.deg, row_dec * u.deg, frame="icrs")
        dist_arcsec = center.separation(coord).arcsec
        offset_x_arcsec = (row_ra - ra) * 3600.0 * cos_dec
        offset_y_arcsec = (row_dec - dec) * 3600.0
        entries.append(
            build_nearby_source_entry(
                source_id=source_id,
                ra=row_ra,
                dec=row_dec,
                gmag=row["gmag"],
                dist_arcsec=dist_arcsec,
                pixel_scale_arcsec=PIXEL_SCALE_ARCSEC,
                offset_x_px=offset_x_arcsec / PIXEL_SCALE_ARCSEC,
                offset_y_px=offset_y_arcsec / PIXEL_SCALE_ARCSEC,
            )
        )
    entries.sort(key=lambda item: item.get("dist_arcsec") if item.get("dist_arcsec") is not None else float("inf"))
    return entries


def _build_flux_grid(target_info: dict, nearby_sources: list[dict]) -> list[list[float]]:
    size = PREVIEW_SIZE_PX
    center = size // 2
    sigma_px = 0.85
    target_weight = _relative_flux_from_gmag(target_info.get("gmag"), target_info.get("gmag"))
    sources = [{"x": 0.0, "y": 0.0, "weight": target_weight}]
    for source in nearby_sources:
        sources.append(
            {
                "x": float(source.get("offset_x_px") or 0.0),
                "y": float(source.get("offset_y_px") or 0.0),
                "weight": _relative_flux_from_gmag(source.get("gmag"), target_info.get("gmag")),
            }
        )

    grid = []
    peak = 0.0
    for row in range(size):
        row_values = []
        for col in range(size):
            x = col - center
            y = row - center
            value = 0.0
            for source in sources:
                dx = x - source["x"]
                dy = y - source["y"]
                value += source["weight"] * math.exp(-((dx * dx + dy * dy) / (2.0 * sigma_px * sigma_px)))
            peak = max(peak, value)
            row_values.append(value)
        grid.append(row_values)
    if peak <= 0:
        return [[0.0 for _ in range(size)] for _ in range(size)]
    return [[round((value / peak) * 100.0, 3) for value in row] for row in grid]


def _build_tpf_preview(target_info: dict, nearby_sources: list[dict]) -> dict:
    flux_grid = _build_flux_grid(target_info, nearby_sources)
    return {
        "status": "ok",
        "available": True,
        "mode": "preview",
        "message": "Preview TPF derivata da Gaia DR3: heatmap sintetica basata su target e stelle vicine.",
        "pixel_scale_arcsec": PIXEL_SCALE_ARCSEC,
        "suggested_cutout_size_px": PREVIEW_SIZE_PX,
        "target": target_info,
        "nearby_sources": nearby_sources,
        "flux_grid": flux_grid,
        "preview": {
            "center_pixel": {"x": PREVIEW_SIZE_PX // 2, "y": PREVIEW_SIZE_PX // 2},
            "neighbors_count": len(nearby_sources),
        },
    }


def run_tpf_pipeline(gaia_source_id: str) -> dict:
    normalized_gaia_source_id = validate_gaia_source_id(gaia_source_id)
    LOGGER.info("Starting TPF pipeline for gaia_source_id=%s", normalized_gaia_source_id)
    try:
        target_info = _fetch_gaia_dr3_target(normalized_gaia_source_id)
        nearby_sources = _fetch_nearby_gaia_sources(target_info)
        tpf_preview = _build_tpf_preview(target_info, nearby_sources)
        lightcurve = compute_lightcurve_stub(normalized_gaia_source_id, target_info)
        save_payload = {
            "input": {"gaia_source_id": normalized_gaia_source_id},
            "target": target_info,
            "tpf": {"available": bool(tpf_preview.get("available"))},
            "lightcurve": {"available": bool(lightcurve.get("available"))},
        }
        save_result = save_tpf_session_stub(save_payload)
        return {
            "status": "ok",
            "message": "Pipeline TPF completata correttamente.",
            "mode": "preview",
            "input": {"gaia_source_id": normalized_gaia_source_id},
            "target": target_info,
            "tpf": tpf_preview,
            "lightcurve": lightcurve,
            "save": save_result,
        }
    except Exception:
        LOGGER.exception("TPF pipeline failed for gaia_source_id=%s", normalized_gaia_source_id)
        raise

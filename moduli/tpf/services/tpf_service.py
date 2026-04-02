from __future__ import annotations

import logging
import math
from time import perf_counter

from astroquery.gaia import Gaia
from astroquery.mast import Catalogs
from astropy import units as u
from astropy.coordinates import SkyCoord

from ..config import settings
from .lightcurve_service import build_auto_masks, compute_lightcurve_stub, compute_real_lightcurve, normalize_manual_masks
from .save_service import save_tpf_session_stub
from .tpf_data_service import load_local_tpf, load_local_tpf_frames
from .utils import (
    build_nearby_source_entry,
    build_overlay_source_entry,
    point_is_inside_grid,
    rounded_or_none,
    validate_gaia_source_id,
    validate_sector,
)

LOGGER = logging.getLogger(__name__)
PIXEL_SCALE_ARCSEC = 21.0
NEARBY_RADIUS_DEG = 0.02
PREVIEW_SIZE_PX = 11
MAX_NEARBY_SOURCES = 25
MAX_OVERLAY_SOURCES = 50
AUTO_TARGET_THRESHOLD_SIGMA = 15.0
AUTO_BACKGROUND_THRESHOLD_SIGMA = 0.001
TIC_REFERENCE_RADIUS_ARCSEC = 5.0


def _empty_masks_payload(message: str) -> dict:
    return {
        "available": False,
        "mode": "not-available",
        "message": message,
        "target": [],
        "background": [],
        "summary": {
            "target_pixels": 0,
            "background_pixels": 0,
        },
    }


def _empty_overlay_payload(message: str) -> dict:
    return {
        "status": "not-available",
        "message": message,
        "target_position": None,
        "gaia_sources": [],
    }


def _empty_frames_payload(message: str) -> dict:
    return {
        "available": False,
        "count": 0,
        "time": [],
        "grids": [],
        "initial_index": 0,
        "message": message,
    }


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


def _resolve_reference_magnitude(target_info: dict, tpf_metadata: dict | None) -> dict:
    metadata = dict(tpf_metadata or {})
    header_tessmag = metadata.get("tessmag")
    header_tessmag_key = metadata.get("tessmag_key")
    if header_tessmag is not None:
        LOGGER.info(
            "Using TESS magnitude from TPF header for gaia_source_id=%s key=%s value=%s",
            target_info.get("gaia_source_id"),
            header_tessmag_key,
            header_tessmag,
        )
        metadata["reference_mag_value"] = header_tessmag
        metadata["reference_mag_band"] = "TESS"
        metadata["reference_mag_key"] = header_tessmag_key or "TESSMAG"
        metadata["reference_mag_source"] = "tpf_header"
        return metadata

    try:
        coord = SkyCoord(
            ra=float(target_info["ra_deg"]) * u.deg,
            dec=float(target_info["dec_deg"]) * u.deg,
            frame="icrs",
        )
        catalog = Catalogs.query_region(coord, radius=(TIC_REFERENCE_RADIUS_ARCSEC * u.arcsec), catalog="TIC")
        if catalog is not None and len(catalog) > 0:
            catalog_sorted = catalog
            if "dstArcSec" in catalog.colnames:
                catalog_sorted = catalog[np.argsort(catalog["dstArcSec"])]
            best_row = catalog_sorted[0]
            tmag_value = best_row["Tmag"] if "Tmag" in catalog.colnames else None
            if tmag_value is not None:
                tmag_numeric = rounded_or_none(tmag_value, 6)
                if tmag_numeric is not None and 0.0 < float(tmag_numeric) < 30.0:
                    LOGGER.info(
                        "Using TIC catalog Tmag for gaia_source_id=%s value=%s",
                        target_info.get("gaia_source_id"),
                        tmag_numeric,
                    )
                    metadata["reference_mag_value"] = float(tmag_numeric)
                    metadata["reference_mag_band"] = "TESS"
                    metadata["reference_mag_key"] = "Tmag"
                    metadata["reference_mag_source"] = "tic_catalog"
                    if "ID" in catalog.colnames:
                        metadata["reference_mag_catalog_id"] = str(best_row["ID"])
                    return metadata
    except Exception:
        LOGGER.exception("TIC reference magnitude lookup failed for gaia_source_id=%s", target_info.get("gaia_source_id"))

    gaia_gmag = target_info.get("gmag")
    if gaia_gmag is not None:
        LOGGER.info(
            "Falling back to Gaia G magnitude for gaia_source_id=%s value=%s",
            target_info.get("gaia_source_id"),
            gaia_gmag,
        )
        metadata["reference_mag_value"] = gaia_gmag
        metadata["reference_mag_band"] = "Gaia G"
        metadata["reference_mag_key"] = "phot_g_mean_mag"
        metadata["reference_mag_source"] = "gaia_catalog_fallback"
        return metadata

    LOGGER.info("No reference magnitude available for gaia_source_id=%s", target_info.get("gaia_source_id"))
    metadata["reference_mag_value"] = None
    metadata["reference_mag_band"] = None
    metadata["reference_mag_key"] = None
    metadata["reference_mag_source"] = None
    return metadata


def _estimate_overlay_radius_deg(shape: tuple[int, int] | list[int]) -> float:
    rows = int(shape[0])
    cols = int(shape[1])
    diagonal_px = math.sqrt((rows * rows) + (cols * cols))
    radius_arcsec = max(60.0, (diagonal_px * PIXEL_SCALE_ARCSEC * 0.6))
    return round(radius_arcsec / 3600.0, 5)


def _build_target_position(target_info: dict, shape: tuple[int, int] | list[int], wcs) -> dict:
    rows = int(shape[0])
    cols = int(shape[1])
    fallback = {
        "x": round((cols - 1) / 2.0, 3),
        "y": round((rows - 1) / 2.0, 3),
        "source": "fallback-center",
    }
    if wcs is None:
        LOGGER.warning("WCS not available: using center fallback for target position")
        return fallback

    try:
        x, y = wcs.all_world2pix(float(target_info["ra_deg"]), float(target_info["dec_deg"]), 0)
        if not point_is_inside_grid(x, y, shape):
            LOGGER.warning("Target world-to-pixel position fell outside TPF grid: x=%s y=%s", x, y)
            return fallback
        return {
            "x": rounded_or_none(x, 3),
            "y": rounded_or_none(y, 3),
            "source": "wcs",
        }
    except Exception:
        LOGGER.exception("Failed to convert target sky position to TPF pixel coordinates")
        return fallback


def _fetch_gaia_overlay_sources(target_info: dict, shape: tuple[int, int] | list[int], wcs) -> tuple[list[dict], str]:
    if wcs is None:
        return [], "Overlay Gaia non disponibile: WCS non disponibile."

    ra = float(target_info["ra_deg"])
    dec = float(target_info["dec_deg"])
    radius_deg = _estimate_overlay_radius_deg(shape)
    query = f"""
        SELECT TOP {MAX_OVERLAY_SOURCES + 1} source_id, ra, dec, phot_g_mean_mag AS gmag
        FROM gaiadr3.gaia_source
        WHERE 1 = CONTAINS(
            POINT('ICRS', gaiadr3.gaia_source.ra, gaiadr3.gaia_source.dec),
            CIRCLE('ICRS', {ra}, {dec}, {radius_deg})
        )
    """
    try:
        LOGGER.info("Querying Gaia overlay sources within radius_deg=%s", radius_deg)
        job = Gaia.launch_job_async(query)
        results = job.get_results()
        sources = []
        for row in results:
            source_id = str(row["source_id"])
            if source_id == target_info["gaia_source_id"]:
                continue
            row_ra = float(row["ra"])
            row_dec = float(row["dec"])
            x, y = wcs.all_world2pix(row_ra, row_dec, 0)
            if not point_is_inside_grid(x, y, shape):
                continue
            sources.append(build_overlay_source_entry(source_id, x, y, row["gmag"], row_ra, row_dec))
        sources.sort(key=lambda item: item.get("gmag") if item.get("gmag") is not None else float("inf"))
        return sources, f"Sorgenti Gaia overlay disponibili: {len(sources)} nel campo TPF."
    except Exception:
        LOGGER.exception("Gaia overlay query failed for gaia_source_id=%s", target_info["gaia_source_id"])
        return [], "Overlay Gaia non disponibile: query Gaia fallita."


def _build_real_tpf_overlay(target_info: dict, tpf_payload: dict, wcs) -> dict:
    shape = tuple(tpf_payload.get("shape") or (0, 0))
    target_position = _build_target_position(target_info, shape, wcs)
    gaia_sources, overlay_message = _fetch_gaia_overlay_sources(target_info, shape, wcs)
    return {
        "status": "ok",
        "message": overlay_message,
        "target_position": target_position,
        "gaia_sources": gaia_sources,
    }


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


def _build_tpf_preview(target_info: dict, sector: int, nearby_sources: list[dict]) -> dict:
    flux_grid = _build_flux_grid(target_info, nearby_sources)
    center = PREVIEW_SIZE_PX // 2
    return {
        "status": "ok",
        "available": True,
        "mode": "preview",
        "message": f"Preview TPF sintetica attiva: nessun file locale trovato per gaia_source_id={target_info['gaia_source_id']} e sector={sector}.",
        "pixel_scale_arcsec": PIXEL_SCALE_ARCSEC,
        "suggested_cutout_size_px": PREVIEW_SIZE_PX,
        "target": target_info,
        "nearby_sources": nearby_sources,
        "flux_grid": flux_grid,
        "source": {
            "type": "synthetic_preview",
            "path": None,
            "filename": None,
            "lookup_key": {
                "gaia_source_id": target_info["gaia_source_id"],
                "sector": sector,
            },
        },
        "metadata": {
            "sector": sector,
            "camera": None,
            "ccd": None,
            "tessmag": None,
            "ticid": None,
        },
        "masks": _empty_masks_payload("Maschere automatiche disponibili solo con TPF reale."),
        "frames": _empty_frames_payload("Navigazione frame disponibile solo con TPF reale."),
        "overlay": {
            "status": "preview",
            "message": "Overlay Gaia e target disponibile solo con TPF reale e WCS utilizzabile.",
            "target_position": {
                "x": center,
                "y": center,
                "source": "fallback-center",
            },
            "gaia_sources": [],
        },
        "preview": {
            "center_pixel": {"x": center, "y": center},
            "neighbors_count": len(nearby_sources),
        },
    }


def run_tpf_pipeline(gaia_source_id: str, sector, masks: dict | None = None) -> dict:
    normalized_gaia_source_id = validate_gaia_source_id(gaia_source_id)
    normalized_sector = validate_sector(sector)
    pipeline_started_at = perf_counter()
    LOGGER.info(
        "Starting TPF pipeline for gaia_source_id=%s sector=%s manual_masks=%s",
        normalized_gaia_source_id,
        normalized_sector,
        bool(masks),
    )
    try:
        target_fetch_started_at = perf_counter()
        target_info = _fetch_gaia_dr3_target(normalized_gaia_source_id)
        LOGGER.info(
            "TPF timing | gaia_source_id=%s sector=%s step=fetch_target elapsed_s=%.3f",
            normalized_gaia_source_id,
            normalized_sector,
            perf_counter() - target_fetch_started_at,
        )

        load_tpf_started_at = perf_counter()
        real_tpf = load_local_tpf(normalized_gaia_source_id, normalized_sector, settings.local_tpf_data_dir, include_frames=False)
        LOGGER.info(
            "TPF timing | gaia_source_id=%s sector=%s step=load_local_tpf elapsed_s=%.3f found=%s",
            normalized_gaia_source_id,
            normalized_sector,
            perf_counter() - load_tpf_started_at,
            bool(real_tpf),
        )
        if real_tpf is not None:
            LOGGER.info("Using real local TPF for gaia_source_id=%s sector=%s", normalized_gaia_source_id, normalized_sector)
            raw_time = real_tpf.pop("_time_values", None)
            raw_flux_cube = real_tpf.pop("_flux_cube", None)
            tpf_wcs = real_tpf.pop("_wcs", None)
            tpf_payload = real_tpf
            reference_mag_started_at = perf_counter()
            tpf_payload["metadata"] = _resolve_reference_magnitude(target_info, tpf_payload.get("metadata"))
            LOGGER.info(
                "TPF timing | gaia_source_id=%s sector=%s step=resolve_reference_magnitude elapsed_s=%.3f reference_band=%s reference_source=%s",
                normalized_gaia_source_id,
                normalized_sector,
                perf_counter() - reference_mag_started_at,
                tpf_payload["metadata"].get("reference_mag_band"),
                tpf_payload["metadata"].get("reference_mag_source"),
            )
            overlay_started_at = perf_counter()
            tpf_payload["overlay"] = _build_real_tpf_overlay(target_info, tpf_payload, tpf_wcs)
            LOGGER.info(
                "TPF timing | gaia_source_id=%s sector=%s step=build_overlay elapsed_s=%.3f sources=%s",
                normalized_gaia_source_id,
                normalized_sector,
                perf_counter() - overlay_started_at,
                len(tpf_payload["overlay"].get("gaia_sources") or []),
            )
            pipeline_mode = "real"
            tpf_payload["masks"] = _empty_masks_payload("Maschere non disponibili.")
            lightcurve = compute_lightcurve_stub(
                normalized_gaia_source_id,
                target_info,
                "Light curve reale non disponibile: errore nella costruzione iniziale.",
            )
            if raw_time is not None and raw_flux_cube is not None:
                if masks is not None:
                    manual_masks_started_at = perf_counter()
                    masks_payload, target_mask, background_mask = normalize_manual_masks(masks, tuple(raw_flux_cube.shape[1:]))
                    tpf_payload["masks"] = masks_payload
                    LOGGER.info(
                        "TPF timing | gaia_source_id=%s sector=%s step=normalize_manual_masks elapsed_s=%.3f",
                        normalized_gaia_source_id,
                        normalized_sector,
                        perf_counter() - manual_masks_started_at,
                    )
                    manual_lightcurve_started_at = perf_counter()
                    lightcurve = compute_real_lightcurve(
                        raw_time,
                        raw_flux_cube,
                        target_mask,
                        background_mask,
                            gaia_source_id=normalized_gaia_source_id,
                            tpf_source=tpf_payload.get("source"),
                            tpf_metadata=tpf_payload.get("metadata"),
                            extraction_metadata={
                                "mask_origin": "manual",
                                "target_threshold": None,
                                "background_threshold": None,
                                "sigma_clipping": None,
                            },
                        mode="real-manual-mask",
                        message="Light curve aggiornata con maschere modificate manualmente.",
                    )
                    LOGGER.info(
                        "TPF timing | gaia_source_id=%s sector=%s step=compute_real_lightcurve_manual elapsed_s=%.3f points=%s",
                        normalized_gaia_source_id,
                        normalized_sector,
                        perf_counter() - manual_lightcurve_started_at,
                        len(lightcurve.get("time") or []),
                    )
                else:
                    try:
                        auto_masks_started_at = perf_counter()
                        masks_payload, target_mask, background_mask = build_auto_masks(raw_flux_cube)
                        tpf_payload["masks"] = masks_payload
                        LOGGER.info(
                            "TPF timing | gaia_source_id=%s sector=%s step=build_auto_masks elapsed_s=%.3f",
                            normalized_gaia_source_id,
                            normalized_sector,
                            perf_counter() - auto_masks_started_at,
                        )
                        auto_lightcurve_started_at = perf_counter()
                        lightcurve = compute_real_lightcurve(
                            raw_time,
                            raw_flux_cube,
                            target_mask,
                            background_mask,
                            gaia_source_id=normalized_gaia_source_id,
                            tpf_source=tpf_payload.get("source"),
                            tpf_metadata=tpf_payload.get("metadata"),
                            extraction_metadata={
                                "mask_origin": "auto",
                                "target_threshold": f"median_grid > background + {AUTO_TARGET_THRESHOLD_SIGMA} * scatter",
                                "background_threshold": f"median_grid <= background + {AUTO_BACKGROUND_THRESHOLD_SIGMA} * scatter",
                                "sigma_clipping": None,
                            },
                        )
                        LOGGER.info(
                            "TPF timing | gaia_source_id=%s sector=%s step=compute_real_lightcurve_auto elapsed_s=%.3f points=%s",
                            normalized_gaia_source_id,
                            normalized_sector,
                            perf_counter() - auto_lightcurve_started_at,
                            len(lightcurve.get("time") or []),
                        )
                    except Exception as err:
                        LOGGER.exception(
                            "Automatic mask/light curve generation failed for gaia_source_id=%s sector=%s",
                            normalized_gaia_source_id,
                            normalized_sector,
                        )
                        lightcurve = compute_lightcurve_stub(
                            normalized_gaia_source_id,
                            target_info,
                            f"Light curve reale non disponibile: {err}",
                        )
            else:
                LOGGER.warning(
                    "Real TPF loaded without raw time/flux for gaia_source_id=%s sector=%s",
                    normalized_gaia_source_id,
                    normalized_sector,
                )
                lightcurve = compute_lightcurve_stub(
                    normalized_gaia_source_id,
                    target_info,
                    "Light curve reale non disponibile: dati temporali o cubo FLUX assenti.",
                )
        else:
            LOGGER.info("Falling back to synthetic TPF preview for gaia_source_id=%s sector=%s", normalized_gaia_source_id, normalized_sector)
            nearby_sources = _fetch_nearby_gaia_sources(target_info)
            tpf_payload = _build_tpf_preview(target_info, normalized_sector, nearby_sources)
            pipeline_mode = "preview"
            lightcurve = compute_lightcurve_stub(
                normalized_gaia_source_id,
                target_info,
                "Light curve non disponibile: il TPF reale non e' stato trovato, resta attivo il fallback sintetico.",
            )

        save_payload = {
            "input": {"gaia_source_id": normalized_gaia_source_id, "sector": normalized_sector},
            "target": target_info,
            "tpf": {
                "available": bool(tpf_payload.get("available")),
                "source": tpf_payload.get("source"),
                "metadata": tpf_payload.get("metadata"),
                "masks": tpf_payload.get("masks"),
            },
            "lightcurve": lightcurve,
        }
        save_started_at = perf_counter()
        save_result = save_tpf_session_stub(save_payload)
        LOGGER.info(
            "TPF timing | gaia_source_id=%s sector=%s step=save_stub elapsed_s=%.3f",
            normalized_gaia_source_id,
            normalized_sector,
            perf_counter() - save_started_at,
        )
        LOGGER.info(
            "TPF timing | gaia_source_id=%s sector=%s step=run_tpf_pipeline_total elapsed_s=%.3f mode=%s",
            normalized_gaia_source_id,
            normalized_sector,
            perf_counter() - pipeline_started_at,
            pipeline_mode,
        )
        return {
            "status": "ok",
            "message": "Pipeline TPF completata correttamente.",
            "mode": pipeline_mode,
            "input": {"gaia_source_id": normalized_gaia_source_id, "sector": normalized_sector},
            "target": target_info,
            "tpf": tpf_payload,
            "lightcurve": lightcurve,
            "save": save_result,
        }
    except ValueError:
        LOGGER.warning(
            "TPF pipeline validation failed for gaia_source_id=%s sector=%s",
            normalized_gaia_source_id,
            normalized_sector,
        )
        raise
    except Exception:
        LOGGER.exception("TPF pipeline failed for gaia_source_id=%s sector=%s", normalized_gaia_source_id, normalized_sector)
        raise


def load_tpf_frame_window(gaia_source_id: str, sector, frame_start: int, frame_end: int) -> dict:
    normalized_gaia_source_id = validate_gaia_source_id(gaia_source_id)
    normalized_sector = validate_sector(sector)
    safe_frame_start = int(frame_start)
    safe_frame_end = int(frame_end)
    if safe_frame_start < 0 or safe_frame_end < 0:
        raise ValueError("Intervallo frame non valido")
    if safe_frame_end < safe_frame_start:
        raise ValueError("Intervallo frame non valido")

    frames_payload = load_local_tpf_frames(
        normalized_gaia_source_id,
        normalized_sector,
        settings.local_tpf_data_dir,
        safe_frame_start,
        safe_frame_end,
    )
    if frames_payload is None:
        raise ValueError("Frame TPF reali non disponibili per il target richiesto")

    return {
        "status": "ok",
        "message": "Frame TPF caricati correttamente.",
        "input": {
            "gaia_source_id": normalized_gaia_source_id,
            "sector": normalized_sector,
            "frame_start": safe_frame_start,
            "frame_end": safe_frame_end,
        },
        "frames": frames_payload,
    }

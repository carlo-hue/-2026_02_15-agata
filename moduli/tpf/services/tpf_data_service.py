from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

from ..config import settings

LOGGER = logging.getLogger(__name__)


def _first_header_value(headers: list, keys: list[str]):
    for key in keys:
        for header in headers:
            value = header.get(key)
            if value is not None:
                return value, key
    return None, None


def _normalize_tessmag(value):
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(numeric):
        return None
    if numeric <= 0.0 or numeric >= 30.0:
        return None
    return numeric


def _build_expected_candidates(gaia_source_id: str, sector: int, data_dir: str) -> list[Path]:
    base_dir = Path(data_dir)
    stem = f"{gaia_source_id}_num_sett_TESS_{sector}"
    source_dir = base_dir / str(gaia_source_id)
    return [
        base_dir / f"{stem}.fit",
        base_dir / f"{stem}.fits",
        source_dir / f"{stem}.fit",
        source_dir / f"{stem}.fits",
    ]


def _build_downloaded_candidates(gaia_source_id: str, sector: int) -> list[Path]:
    download_dir = Path(settings.mast_tpf_download_dir)
    source_dir = download_dir / str(gaia_source_id)
    exact = [
        source_dir / f"tpf_gaia_{gaia_source_id}_s{sector}_cut{settings.default_cutout_size}.fits",
        source_dir / f"tpf_gaia_{gaia_source_id}_s{sector}_cut{settings.default_cutout_size}.fit",
    ]
    wildcard = sorted(source_dir.glob(f"tpf_gaia_{gaia_source_id}_s{sector}_cut*.fits"))
    return exact + wildcard


def _find_local_tpf_file(gaia_source_id: str, sector: int, data_dir: str) -> Path | None:
    base_dir = Path(data_dir)
    if base_dir.exists() and base_dir.is_dir():
        for candidate in _build_expected_candidates(gaia_source_id, sector, data_dir):
            if candidate.exists() and candidate.is_file():
                return candidate
    else:
        LOGGER.warning("Local legacy TPF data directory not available: %s", base_dir)

    download_dir = Path(settings.mast_tpf_download_dir)
    if download_dir.exists() and download_dir.is_dir():
        for candidate in _build_downloaded_candidates(gaia_source_id, sector):
            if candidate.exists() and candidate.is_file():
                return candidate
    return None


def _build_flux_grid_from_cube(flux_cube: np.ndarray) -> list[list[float]]:
    flux_cube = np.asarray(flux_cube, dtype=float)
    if flux_cube.ndim == 3:
        grid = np.nanmedian(flux_cube, axis=0)
    elif flux_cube.ndim == 2:
        grid = flux_cube
    else:
        raise ValueError("FLUX grid non compatibile")

    if not np.isfinite(grid).any():
        raise ValueError("FLUX grid priva di valori finiti")

    grid = np.nan_to_num(grid, nan=0.0, posinf=0.0, neginf=0.0)
    return np.round(grid, 3).tolist()


def _build_serialized_frames(flux_cube: np.ndarray, time_values: np.ndarray) -> dict:
    cube = np.asarray(flux_cube, dtype=float)
    times = np.asarray(time_values, dtype=float)
    if cube.ndim != 3:
        return {
            "available": False,
            "count": 0,
            "time": [],
            "grids": [],
            "initial_index": 0,
            "message": "Frame TPF non disponibili.",
        }

    serialized_grids: list[list[list[float]]] = []
    valid_indices: list[int] = []
    for index, frame in enumerate(cube):
        frame = np.nan_to_num(np.asarray(frame, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
        serialized_grids.append(np.round(frame, 3).tolist())
        if np.isfinite(np.asarray(cube[index], dtype=float)).any():
            valid_indices.append(index)

    initial_index = valid_indices[0] if valid_indices else 0
    return {
        "available": True,
        "loaded": True,
        "count": int(cube.shape[0]),
        "time": np.round(times, 6).tolist(),
        "grids": serialized_grids,
        "initial_index": int(initial_index),
        "start_index": 0,
        "end_index": int(cube.shape[0] - 1),
        "message": "Slider frame attivo: seleziona un cadence del TPF oppure clicca un punto della light curve.",
    }


def _build_frames_metadata_payload(flux_cube: np.ndarray) -> dict:
    cube = np.asarray(flux_cube, dtype=float)
    count = int(cube.shape[0]) if cube.ndim == 3 else 0
    return {
        "available": count > 0,
        "loaded": False,
        "count": count,
        "time": [],
        "grids": [],
        "initial_index": 0,
        "start_index": None,
        "end_index": None,
        "message": "Frame non ancora caricati. Fai zoom sulla light curve, poi usa il pulsante dedicato per caricare solo i cadence visibili.",
    }


def _build_pixel_world_payload(tpf_wcs, shape: list[int]) -> dict | None:
    if tpf_wcs is None:
        return None
    rows = int(shape[0]) if shape else 0
    cols = int(shape[1]) if len(shape) > 1 else 0
    if rows <= 0 or cols <= 0:
        return None
    try:
        ra_grid = []
        dec_grid = []
        for row in range(rows):
            row_ra = []
            row_dec = []
            for col in range(cols):
                ra_deg, dec_deg = tpf_wcs.all_pix2world([[float(col), float(row)]], 0)[0]
                row_ra.append(round(float(ra_deg), 5))
                row_dec.append(round(float(dec_deg), 5))
            ra_grid.append(row_ra)
            dec_grid.append(row_dec)
        return {
            "available": True,
            "ra_deg": ra_grid,
            "dec_deg": dec_grid,
        }
    except Exception:
        LOGGER.exception("Unable to build pixel world payload from TPF WCS")
        return None


def _build_serialized_frame_window(flux_cube: np.ndarray, time_values: np.ndarray, frame_start: int, frame_end: int) -> dict:
    cube = np.asarray(flux_cube, dtype=float)
    times = np.asarray(time_values, dtype=float)
    if cube.ndim != 3:
        raise ValueError("FLUX cube non compatibile")

    max_index = int(cube.shape[0] - 1)
    safe_start = max(0, min(int(frame_start), max_index))
    safe_end = max(safe_start, min(int(frame_end), max_index))
    subset_cube = cube[safe_start:safe_end + 1]
    subset_times = times[safe_start:safe_end + 1]
    serialized = _build_serialized_frames(subset_cube, subset_times)
    serialized["count"] = int(cube.shape[0])
    serialized["initial_index"] = safe_start
    serialized["start_index"] = safe_start
    serialized["end_index"] = safe_end
    serialized["message"] = "Slider frame attivo sulla finestra caricata. Clicca la light curve oppure sposta lo slider tra i cadence disponibili."
    return serialized


def _detect_source_info(file_path: Path) -> tuple[str, str]:
    download_dir = Path(settings.mast_tpf_download_dir)
    try:
        resolved_path = file_path.resolve()
        resolved_download_dir = download_dir.resolve()
        is_download = resolved_download_dir in resolved_path.parents
    except Exception:
        is_download = False
    if is_download:
        return "mast_download_local", "TPF reale caricato da file locale scaricato da MAST/TESS."
    return "local_test_data", "TPF reale caricato da file locale di prova."


def load_local_tpf(gaia_source_id: str, sector: int, data_dir: str, *, include_frames: bool = False) -> dict | None:
    LOGGER.info("Attempting local TPF load for gaia_source_id=%s sector=%s", gaia_source_id, sector)
    try:
        file_path = _find_local_tpf_file(gaia_source_id, sector, data_dir)
        if file_path is None:
            LOGGER.info("No local TPF file found for gaia_source_id=%s sector=%s", gaia_source_id, sector)
            return None

        with fits.open(file_path, memmap=True) as hdul:
            pixels_hdu = hdul["PIXELS"] if "PIXELS" in hdul else hdul[1]
            pixels_data = pixels_hdu.data
            if pixels_data is None or "FLUX" not in pixels_data.names:
                raise ValueError("Estensione PIXELS priva di colonna FLUX")

            flux_cube = np.asarray(pixels_data["FLUX"], dtype=float)
            flux_grid = _build_flux_grid_from_cube(flux_cube)
            time_values = np.asarray(pixels_data["TIME"], dtype=float) if "TIME" in pixels_data.names else np.arange(flux_cube.shape[0], dtype=float)
            frames_payload = _build_serialized_frames(flux_cube, time_values) if include_frames else _build_frames_metadata_payload(flux_cube)
            primary_header = hdul[0].header
            pixels_header = pixels_hdu.header
            headers = [pixels_header, primary_header]
            try:
                tpf_wcs = WCS(pixels_hdu.header, fobj=hdul, keysel=["binary"])
                if not tpf_wcs.has_celestial:
                    LOGGER.warning("Binary-table WCS is not celestial for gaia_source_id=%s sector=%s", gaia_source_id, sector)
                    tpf_wcs = None
            except Exception:
                LOGGER.exception("Unable to build WCS for gaia_source_id=%s sector=%s", gaia_source_id, sector)
                tpf_wcs = None
            header_sector = pixels_header.get("SECTOR") or primary_header.get("SECTOR")
            camera = pixels_header.get("CAMERA") or primary_header.get("CAMERA")
            ccd = pixels_header.get("CCD") or primary_header.get("CCD")
            tessmag, tessmag_key = _first_header_value(headers, ["TESSMAG", "TMAG", "MAG"])
            tessmag = _normalize_tessmag(tessmag)
            if tessmag is None:
                tessmag_key = None
            ticid = pixels_header.get("TICID") or primary_header.get("TICID")
            bjd_ref_i, bjd_ref_i_key = _first_header_value(headers, ["BJDREFI"])
            bjd_ref_f, bjd_ref_f_key = _first_header_value(headers, ["BJDREFF"])
            time_system, time_system_key = _first_header_value(headers, ["TIMESYS"])
            time_unit, time_unit_key = _first_header_value(headers, ["TIMEUNIT"])
            shape = [len(flux_grid), len(flux_grid[0]) if flux_grid else 0]
            pixel_world = _build_pixel_world_payload(tpf_wcs, shape)
            cadence_count = int(flux_cube.shape[0]) if flux_cube.ndim == 3 else 1
            source_type, message = _detect_source_info(file_path)
            bjd_ref = None
            if bjd_ref_i is not None or bjd_ref_f is not None:
                bjd_ref = float(bjd_ref_i or 0.0) + float(bjd_ref_f or 0.0)

            payload = {
                "status": "ok",
                "available": True,
                "mode": "real",
                "message": message,
                "shape": shape,
                "cadence_count": cadence_count,
                "flux_grid": flux_grid,
                "frames": frames_payload,
                "source": {
                    "type": source_type,
                    "path": str(file_path),
                    "filename": file_path.name,
                    "lookup_key": {
                        "gaia_source_id": gaia_source_id,
                        "sector": sector,
                    },
                },
                "metadata": {
                    "sector": int(header_sector) if header_sector is not None else None,
                    "camera": int(camera) if camera is not None else None,
                    "ccd": int(ccd) if ccd is not None else None,
                    "tessmag": tessmag,
                    "tessmag_key": tessmag_key,
                    "ticid": int(ticid) if ticid is not None else None,
                    "time_format": "BTJD",
                    "time_system": time_system or "TDB",
                    "time_system_key": time_system_key,
                    "time_unit": time_unit,
                    "time_unit_key": time_unit_key,
                    "bjd_ref_i": float(bjd_ref_i) if bjd_ref_i is not None else None,
                    "bjd_ref_i_key": bjd_ref_i_key,
                    "bjd_ref_f": float(bjd_ref_f) if bjd_ref_f is not None else None,
                    "bjd_ref_f_key": bjd_ref_f_key,
                    "bjd_ref": bjd_ref,
                    "pixel_world": pixel_world,
                },
                "_time_values": time_values,
                "_flux_cube": flux_cube,
                "_wcs": tpf_wcs,
            }
            LOGGER.info("Local TPF load succeeded for gaia_source_id=%s sector=%s using %s", gaia_source_id, sector, file_path.name)
            return payload
    except Exception:
        LOGGER.exception("Local TPF load failed for gaia_source_id=%s sector=%s", gaia_source_id, sector)
        return None


def load_local_tpf_frames(gaia_source_id: str, sector: int, data_dir: str, frame_start: int, frame_end: int) -> dict | None:
    LOGGER.info(
        "Attempting local TPF frame window load for gaia_source_id=%s sector=%s frame_start=%s frame_end=%s",
        gaia_source_id,
        sector,
        frame_start,
        frame_end,
    )
    try:
        file_path = _find_local_tpf_file(gaia_source_id, sector, data_dir)
        if file_path is None:
            LOGGER.info("No local TPF file found for gaia_source_id=%s sector=%s while loading frame window", gaia_source_id, sector)
            return None

        with fits.open(file_path, memmap=True) as hdul:
            pixels_hdu = hdul["PIXELS"] if "PIXELS" in hdul else hdul[1]
            pixels_data = pixels_hdu.data
            if pixels_data is None or "FLUX" not in pixels_data.names:
                raise ValueError("Estensione PIXELS priva di colonna FLUX")

            flux_cube = np.asarray(pixels_data["FLUX"], dtype=float)
            time_values = np.asarray(pixels_data["TIME"], dtype=float) if "TIME" in pixels_data.names else np.arange(flux_cube.shape[0], dtype=float)
            return _build_serialized_frame_window(flux_cube, time_values, frame_start, frame_end)
    except Exception:
        LOGGER.exception(
            "Local TPF frame window load failed for gaia_source_id=%s sector=%s frame_start=%s frame_end=%s",
            gaia_source_id,
            sector,
            frame_start,
            frame_end,
        )
        return None

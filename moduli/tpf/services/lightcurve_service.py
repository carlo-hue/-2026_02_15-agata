from __future__ import annotations

import logging
from collections import deque

import numpy as np

from .utils import rounded_or_none

LOGGER = logging.getLogger(__name__)


def compute_lightcurve_stub(gaia_source_id: str, target_info: dict | None = None, message: str | None = None) -> dict:
    return {
        "status": "ok",
        "available": False,
        "mode": "placeholder",
        "gaia_source_id": gaia_source_id,
        "message": message or "Light curve non ancora disponibile in questa fase.",
        "time": [],
        "flux": [],
        "corrected_flux": [],
        "target_flux": [],
        "background_flux_per_pixel": [],
        "summary": {
            "target_gmag": rounded_or_none((target_info or {}).get("gmag"), 4),
            "x_axis": "time",
            "y_axis": "corrected_flux",
            "target_pixels": 0,
            "background_pixels": 0,
        },
    }


def _serialize_mask(mask: np.ndarray) -> list[list[bool]]:
    return np.asarray(mask, dtype=bool).tolist()


def _build_masks_payload(target_mask: np.ndarray, background_mask: np.ndarray, mode: str, message: str) -> dict:
    target_pixels = int(np.count_nonzero(target_mask))
    background_pixels = int(np.count_nonzero(background_mask))
    return {
        "available": True,
        "mode": mode,
        "message": message,
        "target": _serialize_mask(target_mask),
        "background": _serialize_mask(background_mask),
        "summary": {
            "target_pixels": target_pixels,
            "background_pixels": background_pixels,
        },
    }


def _component_from_seed(mask: np.ndarray, seed: tuple[int, int]) -> np.ndarray:
    rows, cols = mask.shape
    result = np.zeros_like(mask, dtype=bool)
    queue: deque[tuple[int, int]] = deque([seed])
    while queue:
        row, col = queue.popleft()
        if row < 0 or row >= rows or col < 0 or col >= cols:
            continue
        if result[row, col] or not mask[row, col]:
            continue
        result[row, col] = True
        queue.append((row - 1, col))
        queue.append((row + 1, col))
        queue.append((row, col - 1))
        queue.append((row, col + 1))
    return result


def _select_seed(mask: np.ndarray, median_grid: np.ndarray) -> tuple[int, int]:
    rows, cols = mask.shape
    center = (rows // 2, cols // 2)
    if mask[center]:
        return center

    true_positions = np.argwhere(mask)
    if true_positions.size:
        center_arr = np.asarray(center)
        distances = np.sum((true_positions - center_arr) ** 2, axis=1)
        nearest = true_positions[int(np.argmin(distances))]
        return int(nearest[0]), int(nearest[1])

    row_start = max(0, center[0] - 1)
    row_end = min(rows, center[0] + 2)
    col_start = max(0, center[1] - 1)
    col_end = min(cols, center[1] + 2)
    local_grid = np.asarray(median_grid[row_start:row_end, col_start:col_end], dtype=float)
    if local_grid.size and np.isfinite(local_grid).any():
        local_pos = np.unravel_index(np.nanargmax(local_grid), local_grid.shape)
        return row_start + int(local_pos[0]), col_start + int(local_pos[1])

    finite = np.isfinite(median_grid)
    if finite.any():
        global_pos = np.unravel_index(np.nanargmax(np.where(finite, median_grid, -np.inf)), median_grid.shape)
        return int(global_pos[0]), int(global_pos[1])

    return center


def build_auto_masks(flux_cube: np.ndarray) -> tuple[dict, np.ndarray, np.ndarray]:
    cube = np.asarray(flux_cube, dtype=float)
    if cube.ndim != 3:
        raise ValueError("FLUX cube non compatibile per la costruzione delle maschere")

    median_grid = np.nanmedian(cube, axis=0)
    finite = np.isfinite(median_grid)
    if not finite.any():
        raise ValueError("Median grid priva di valori finiti")

    finite_values = median_grid[finite]
    background_level = float(np.nanmedian(finite_values))
    scatter = float(np.nanstd(finite_values))
    if not np.isfinite(scatter) or scatter <= 0:
        scatter = max(abs(background_level) * 1e-6, 1.0)

    target_candidate = finite & (median_grid > (background_level + 15.0 * scatter))
    if target_candidate.any():
        seed = _select_seed(target_candidate, median_grid)
        target_mask = _component_from_seed(target_candidate, seed)
    else:
        seed = _select_seed(np.zeros_like(finite, dtype=bool), median_grid)
        target_mask = np.zeros_like(finite, dtype=bool)
        target_mask[seed] = True

    broad_candidate = finite & (median_grid > (background_level + 0.001 * scatter))
    background_mask = finite & (~broad_candidate)
    background_mask &= ~target_mask
    if not background_mask.any():
        background_mask = finite & (~target_mask)

    target_pixels = int(np.count_nonzero(target_mask))
    background_pixels = int(np.count_nonzero(background_mask))
    if target_pixels <= 0:
        raise ValueError("Maschera target iniziale vuota")
    if background_pixels <= 0:
        raise ValueError("Maschera background iniziale vuota")

    LOGGER.info(
        "Built automatic masks: target_pixels=%s background_pixels=%s",
        target_pixels,
        background_pixels,
    )

    payload = _build_masks_payload(
        target_mask,
        background_mask,
        "auto-initial",
        "Selezione iniziale automatica foreground/background.",
    )
    return payload, target_mask, background_mask


def _normalize_mask_matrix(mask_data, expected_shape: tuple[int, int], label: str) -> np.ndarray:
    rows, cols = expected_shape
    if not isinstance(mask_data, list) or len(mask_data) != rows:
        raise ValueError(f"Maschera {label} non coerente con la shape del TPF")

    normalized_rows = []
    for row in mask_data:
        if not isinstance(row, list) or len(row) != cols:
            raise ValueError(f"Maschera {label} non coerente con la shape del TPF")
        normalized_row = []
        for value in row:
            if isinstance(value, bool):
                normalized_row.append(value)
            elif isinstance(value, int) and value in (0, 1):
                normalized_row.append(bool(value))
            else:
                raise ValueError(f"Valore non valido nella maschera {label}")
        normalized_rows.append(normalized_row)
    return np.asarray(normalized_rows, dtype=bool)


def normalize_manual_masks(masks_payload: dict, expected_shape: tuple[int, int]) -> tuple[dict, np.ndarray, np.ndarray]:
    if not isinstance(masks_payload, dict):
        raise ValueError("Maschere manuali non valide")

    target_mask = _normalize_mask_matrix(masks_payload.get("target"), expected_shape, "target")
    background_mask = _normalize_mask_matrix(masks_payload.get("background"), expected_shape, "background")

    if np.any(target_mask & background_mask):
        raise ValueError("Le maschere target e background devono essere mutuamente esclusive")

    target_pixels = int(np.count_nonzero(target_mask))
    background_pixels = int(np.count_nonzero(background_mask))
    if target_pixels <= 0:
        raise ValueError("La maschera target deve contenere almeno un pixel")
    if background_pixels <= 0:
        raise ValueError("La maschera background deve contenere almeno un pixel")

    LOGGER.info(
        "Validated manual masks: target_pixels=%s background_pixels=%s",
        target_pixels,
        background_pixels,
    )

    payload = _build_masks_payload(
        target_mask,
        background_mask,
        "manual",
        "Maschere modificate manualmente.",
    )
    return payload, target_mask, background_mask


def compute_real_lightcurve(
    time_values: np.ndarray,
    flux_cube: np.ndarray,
    target_mask: np.ndarray,
    background_mask: np.ndarray,
    *,
    mode: str = "real-auto-mask",
    message: str = "Light curve reale calcolata con maschere iniziali automatiche.",
) -> dict:
    time_arr = np.asarray(time_values, dtype=float)
    cube = np.asarray(flux_cube, dtype=float)
    target_mask = np.asarray(target_mask, dtype=bool)
    background_mask = np.asarray(background_mask, dtype=bool)

    if cube.ndim != 3:
        raise ValueError("FLUX cube non compatibile per la light curve")
    if target_mask.shape != cube.shape[1:] or background_mask.shape != cube.shape[1:]:
        raise ValueError("Shape delle maschere non coerente con il TPF")

    target_pixels = int(np.count_nonzero(target_mask))
    background_pixels = int(np.count_nonzero(background_mask))
    if target_pixels <= 0:
        raise ValueError("Nessun pixel target disponibile")
    if background_pixels <= 0:
        raise ValueError("Nessun pixel background disponibile")

    target_flux = np.nansum(cube[:, target_mask], axis=1)
    background_flux = np.nansum(cube[:, background_mask], axis=1)
    background_flux_per_pixel = background_flux / float(background_pixels)
    corrected_flux = target_flux - (background_flux_per_pixel * float(target_pixels))

    valid = (
        np.isfinite(time_arr)
        & np.isfinite(target_flux)
        & np.isfinite(background_flux_per_pixel)
        & np.isfinite(corrected_flux)
    )
    if not np.any(valid):
        raise ValueError("Nessun punto valido disponibile per la light curve")

    time_out = np.round(time_arr[valid], 6).tolist()
    target_flux_out = np.round(target_flux[valid], 6).tolist()
    background_out = np.round(background_flux_per_pixel[valid], 6).tolist()
    corrected_out = np.round(corrected_flux[valid], 6).tolist()

    LOGGER.info(
        "Computed real light curve with target_pixels=%s background_pixels=%s points=%s mode=%s",
        target_pixels,
        background_pixels,
        len(time_out),
        mode,
    )

    return {
        "status": "ok",
        "available": True,
        "mode": mode,
        "message": message,
        "time": time_out,
        "flux": corrected_out,
        "target_flux": target_flux_out,
        "background_flux_per_pixel": background_out,
        "corrected_flux": corrected_out,
        "summary": {
            "target_pixels": target_pixels,
            "background_pixels": background_pixels,
            "x_axis": "time",
            "y_axis": "corrected_flux",
        },
    }

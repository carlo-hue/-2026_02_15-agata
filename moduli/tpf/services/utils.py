from __future__ import annotations


def validate_gaia_source_id(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError("gaia_source_id mancante")
    if not normalized.isdigit():
        raise ValueError("gaia_source_id non valido")
    return normalized


def validate_sector(value) -> int:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError("sector mancante")
    if not normalized.isdigit():
        raise ValueError("sector non valido")
    return int(normalized)


def rounded_or_none(value, digits: int = 6):
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def point_is_inside_grid(x, y, shape: tuple[int, int] | list[int]) -> bool:
    try:
        rows = int(shape[0])
        cols = int(shape[1])
        px = float(x)
        py = float(y)
    except (TypeError, ValueError, IndexError):
        return False
    return -0.5 <= px <= (cols - 0.5) and -0.5 <= py <= (rows - 0.5)


def build_overlay_source_entry(source_id, x, y, gmag, ra=None, dec=None) -> dict:
    return {
        "source_id": str(source_id),
        "x": rounded_or_none(x, 3),
        "y": rounded_or_none(y, 3),
        "gmag": rounded_or_none(gmag, 4),
        "ra_deg": rounded_or_none(ra, 6),
        "dec_deg": rounded_or_none(dec, 6),
    }


def build_nearby_source_entry(
    source_id,
    ra,
    dec,
    gmag,
    dist_arcsec,
    pixel_scale_arcsec: float,
    offset_x_px,
    offset_y_px,
) -> dict:
    tess_pixel_distance = None
    if dist_arcsec is not None and pixel_scale_arcsec > 0:
        tess_pixel_distance = round(float(dist_arcsec) / pixel_scale_arcsec, 3)
    return {
        "gaia_source_id": str(source_id),
        "ra_deg": rounded_or_none(ra, 6),
        "dec_deg": rounded_or_none(dec, 6),
        "gmag": rounded_or_none(gmag, 4),
        "dist_arcsec": rounded_or_none(dist_arcsec, 3),
        "tess_pixel_distance": tess_pixel_distance,
        "offset_x_px": rounded_or_none(offset_x_px, 3),
        "offset_y_px": rounded_or_none(offset_y_px, 3),
    }

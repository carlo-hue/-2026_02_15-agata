from __future__ import annotations


def validate_gaia_source_id(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError("gaia_source_id mancante")
    if not normalized.isdigit():
        raise ValueError("gaia_source_id non valido")
    return normalized


def rounded_or_none(value, digits: int = 6):
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


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
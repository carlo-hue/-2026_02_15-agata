from __future__ import annotations

from .utils import rounded_or_none


def compute_lightcurve_stub(gaia_source_id: str, target_info: dict | None = None) -> dict:
    return {
        "status": "ok",
        "available": False,
        "mode": "placeholder",
        "gaia_source_id": gaia_source_id,
        "message": "Light curve non ancora disponibile in questa fase.",
        "time": [],
        "flux": [],
        "summary": {
            "target_gmag": rounded_or_none((target_info or {}).get("gmag"), 4),
            "x_axis": "cadence",
            "y_axis": "flux",
        },
    }
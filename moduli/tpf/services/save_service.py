from __future__ import annotations

import logging
from datetime import UTC, datetime

LOGGER = logging.getLogger(__name__)


def _extract_gaia_source_id(payload: dict) -> str:
    input_payload = payload.get("input") if isinstance(payload.get("input"), dict) else {}
    target_payload = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    gaia_source_id = str(
        input_payload.get("gaia_source_id")
        or target_payload.get("gaia_source_id")
        or ""
    ).strip()
    if not gaia_source_id:
        raise ValueError("gaia_source_id mancante nel payload di salvataggio")
    return gaia_source_id


def save_tpf_session_stub(payload: dict) -> dict:
    if not isinstance(payload, dict) or not payload:
        raise ValueError("payload di salvataggio non valido")

    gaia_source_id = _extract_gaia_source_id(payload)
    tpf_payload = payload.get("tpf") if isinstance(payload.get("tpf"), dict) else {}
    lightcurve_payload = payload.get("lightcurve") if isinstance(payload.get("lightcurve"), dict) else {}
    LOGGER.info("Executing stub save for gaia_source_id=%s", gaia_source_id)

    return {
        "status": "ok",
        "message": "Salvataggio stub eseguito correttamente.",
        "mode": "stub",
        "saved": True,
        "save_id": f"stub-{gaia_source_id}",
        "saved_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "summary": {
            "gaia_source_id": gaia_source_id,
            "tpf_available": bool(tpf_payload.get("available")),
            "lightcurve_available": bool(lightcurve_payload.get("available")),
        },
        "payload": payload,
    }

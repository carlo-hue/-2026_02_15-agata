from __future__ import annotations

import json
import logging
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text

try:
    from agata.db import SessionLocal
except ModuleNotFoundError:  # pragma: no cover - local runner fallback
    REPO_ROOT = Path(__file__).resolve().parents[3]
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from db import SessionLocal

LOGGER = logging.getLogger(__name__)

TPF_SESSION_TABLE = "agata_tpf_sessions"
TPF_PHOTOMETRY_TABLE = "agata_star_photometry"
TPF_STAR_TABLE = "agata_star"


def _extract_gaia_source_id(payload: dict) -> str:
    input_payload = payload.get("input") if isinstance(payload.get("input"), dict) else {}
    target_payload = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    gaia_source_id = str(
        input_payload.get("gaia_source_id")
        or target_payload.get("gaia_source_id")
        or ""
    ).strip()
    if not gaia_source_id or not gaia_source_id.isdigit():
        raise ValueError("gaia_source_id mancante nel payload di salvataggio")
    return gaia_source_id


def _extract_sector(payload: dict) -> int:
    input_payload = payload.get("input") if isinstance(payload.get("input"), dict) else {}
    sector_raw = input_payload.get("sector")
    try:
        return int(sector_raw)
    except (TypeError, ValueError):
        raise ValueError("sector mancante nel payload di salvataggio") from None


def _extract_mask_origin(payload: dict) -> str:
    lightcurve_payload = payload.get("lightcurve") if isinstance(payload.get("lightcurve"), dict) else {}
    metadata = lightcurve_payload.get("metadata") if isinstance(lightcurve_payload.get("metadata"), dict) else {}
    mask_origin = str(metadata.get("mask_origin") or "").strip().lower()
    if mask_origin in {"auto", "manual"}:
        return mask_origin

    mode = str(lightcurve_payload.get("mode") or "").strip().lower()
    if "manual" in mode:
        return "manual"
    if "auto" in mode:
        return "auto"
    raise ValueError("mask_origin mancante nel payload di salvataggio")


def _clean_float_series(time_bjd, mag_values) -> tuple[list[float], list[float], dict]:
    if not isinstance(time_bjd, list) or not isinstance(mag_values, list):
        raise ValueError("Serie time_bjd/mag_tess_anchored non valide")
    if len(time_bjd) != len(mag_values):
        raise ValueError("Array time_bjd e mag_tess_anchored di lunghezza diversa")

    cleaned: list[tuple[float, float]] = []
    skipped = 0
    for raw_time, raw_mag in zip(time_bjd, mag_values):
        try:
            time_value = float(raw_time)
            mag_value = float(raw_mag)
        except (TypeError, ValueError):
            skipped += 1
            continue
        if not math.isfinite(time_value) or not math.isfinite(mag_value):
            skipped += 1
            continue
        cleaned.append((time_value, mag_value))

    cleaned.sort(key=lambda item: item[0])
    return [item[0] for item in cleaned], [item[1] for item in cleaned], {
        "input_points": len(time_bjd),
        "valid_points": len(cleaned),
        "discarded_points": skipped,
    }


def _build_catalog_name(sector: int, mask_origin: str) -> str:
    return f"TPF-BJD_s{int(sector):04d}_{mask_origin}"


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _serialize_json(value) -> str:
    return json.dumps(value, ensure_ascii=True, default=_json_default)


def _table_exists(session, table_name: str) -> bool:
    result = session.execute(
        text(
            """
            SELECT COUNT(*) AS cnt
            FROM information_schema.tables
            WHERE table_schema = DATABASE() AND table_name = :table_name
            """
        ),
        {"table_name": table_name},
    ).scalar_one()
    return int(result or 0) > 0


def _session_record_from_payload(payload: dict, *, gaia_source_id: str, sector: int, mask_origin: str) -> dict:
    lightcurve_payload = payload.get("lightcurve") if isinstance(payload.get("lightcurve"), dict) else {}
    tpf_payload = payload.get("tpf") if isinstance(payload.get("tpf"), dict) else {}
    tpf_source = tpf_payload.get("source") if isinstance(tpf_payload.get("source"), dict) else {}
    tpf_metadata = dict(tpf_payload.get("metadata") if isinstance(tpf_payload.get("metadata"), dict) else {})
    lightcurve_metadata = dict(lightcurve_payload.get("metadata") if isinstance(lightcurve_payload.get("metadata"), dict) else {})
    masks = lightcurve_payload.get("masks") if isinstance(lightcurve_payload.get("masks"), dict) else {}

    metadata = {
        **tpf_metadata,
        **lightcurve_metadata,
        "time_system": "BJD_TDB",
        "time_note": "hjd contains BJD_TDB for TPF catalogs",
        "sector": sector,
        "mask_origin": mask_origin,
        "background_method": lightcurve_metadata.get("background_method"),
        "anchoring_method": lightcurve_metadata.get("anchoring_method"),
        "reference_mag_band": lightcurve_metadata.get("reference_mag_band"),
        "reference_mag_key": lightcurve_metadata.get("reference_mag_key"),
        "reference_mag_source": lightcurve_metadata.get("reference_mag_source"),
        "reference_mag_value": lightcurve_metadata.get("reference_mag_value"),
    }

    return {
        "gaia_source_id": int(gaia_source_id),
        "sector": sector,
        "catalog_name": _build_catalog_name(sector, mask_origin),
        "mode": str(lightcurve_payload.get("mode") or payload.get("mode") or "unknown"),
        "mask_origin": mask_origin,
        "tpf_filename": tpf_source.get("filename"),
        "tpf_path": tpf_source.get("path"),
        "target_mask_json": _serialize_json(masks.get("target_pixels") or []),
        "background_mask_json": _serialize_json(masks.get("background_pixels") or []),
        "lightcurve_json": _serialize_json(lightcurve_payload),
        "metadata_json": _serialize_json(metadata),
        "saved_by": None,
        "is_promoted": False,
        "promoted_points": 0,
    }


def _save_tpf_session_record(session_payload: dict) -> dict:
    session = SessionLocal()
    try:
        if not _table_exists(session, TPF_SESSION_TABLE):
            raise RuntimeError(f"Tabella {TPF_SESSION_TABLE} non disponibile")

        insert_sql = text(
            f"""
            INSERT INTO {TPF_SESSION_TABLE} (
                gaia_source_id,
                sector,
                catalog_name,
                mode,
                mask_origin,
                tpf_filename,
                tpf_path,
                target_mask_json,
                background_mask_json,
                lightcurve_json,
                metadata_json,
                saved_by,
                is_promoted,
                promoted_points
            ) VALUES (
                :gaia_source_id,
                :sector,
                :catalog_name,
                :mode,
                :mask_origin,
                :tpf_filename,
                :tpf_path,
                :target_mask_json,
                :background_mask_json,
                :lightcurve_json,
                :metadata_json,
                :saved_by,
                :is_promoted,
                :promoted_points
            )
            """
        )
        result = session.execute(insert_sql, session_payload)
        session.commit()
        session_id = int(result.lastrowid)
        LOGGER.info(
            "Saved TPF technical session in %s for gaia_source_id=%s sector=%s session_id=%s",
            TPF_SESSION_TABLE,
            session_payload["gaia_source_id"],
            session_payload["sector"],
            session_id,
        )
        return {"saved": True, "session_id": session_id, "table": TPF_SESSION_TABLE}
    finally:
        session.close()


def _update_tpf_session_promotion(session_id: int, *, promoted: bool, promoted_points: int) -> None:
    session = SessionLocal()
    try:
        with session.begin():
            session.execute(
                text(
                    f"""
                    UPDATE {TPF_SESSION_TABLE}
                    SET is_promoted = :is_promoted,
                        promoted_points = :promoted_points
                    WHERE id = :session_id
                    """
                ),
                {
                    "is_promoted": bool(promoted),
                    "promoted_points": int(promoted_points),
                    "session_id": int(session_id),
                },
            )
    finally:
        session.close()


def _promote_photometry_points(
    *,
    gaia_source_id: str,
    sector: int,
    mask_origin: str,
    cleaned_time_bjd: list[float],
    cleaned_mag: list[float],
) -> dict:
    catalog_name = _build_catalog_name(sector, mask_origin)
    rows = [
        {
            "hjd": time_value,
            "vmag": mag_value,
            "source": int(gaia_source_id),
            "catalogo": catalog_name,
            "catalog_import_id": None,
            "association_id_owner": None,
        }
        for time_value, mag_value in zip(cleaned_time_bjd, cleaned_mag)
    ]

    session = SessionLocal()
    try:
        with session.begin():
            delete_sql = text(
                f"""
                DELETE FROM {TPF_PHOTOMETRY_TABLE}
                WHERE Source = :source AND catalogo = :catalogo
                """
            )
            session.execute(delete_sql, {"source": int(gaia_source_id), "catalogo": catalog_name})

            insert_sql = text(
                f"""
                INSERT INTO {TPF_PHOTOMETRY_TABLE}
                    (hjd, Vmag, Source, catalogo, catalog_import_id, association_id_owner)
                VALUES
                    (:hjd, :vmag, :source, :catalogo, :catalog_import_id, :association_id_owner)
                """
            )
            session.execute(insert_sql, rows)

            catalogs_json = _serialize_json([catalog_name])
            upsert_sql = text(
                f"""
                INSERT INTO {TPF_STAR_TABLE}
                    (gaia_id, total_points, num_catalogs, catalogs, min_hjd, max_hjd, min_mag, max_mag)
                VALUES
                    (:gaia_id, :total_points, :num_catalogs, :catalogs, :min_hjd, :max_hjd, :min_mag, :max_mag)
                ON DUPLICATE KEY UPDATE
                    total_points = VALUES(total_points),
                    num_catalogs = VALUES(num_catalogs),
                    catalogs = VALUES(catalogs),
                    min_hjd = VALUES(min_hjd),
                    max_hjd = VALUES(max_hjd),
                    min_mag = VALUES(min_mag),
                    max_mag = VALUES(max_mag),
                    updated_at = CURRENT_TIMESTAMP
                """
            )
            session.execute(
                upsert_sql,
                {
                    "gaia_id": int(gaia_source_id),
                    "total_points": len(rows),
                    "num_catalogs": 1,
                    "catalogs": catalogs_json,
                    "min_hjd": min(cleaned_time_bjd),
                    "max_hjd": max(cleaned_time_bjd),
                    "min_mag": min(cleaned_mag),
                    "max_mag": max(cleaned_mag),
                },
            )

        LOGGER.info(
            "Promoted %s TPF photometry points for gaia_source_id=%s sector=%s mask_origin=%s catalog=%s",
            len(rows),
            gaia_source_id,
            sector,
            mask_origin,
            catalog_name,
        )
        return {
            "promoted": True,
            "catalog_name": catalog_name,
            "replaced_existing_catalog": True,
            "inserted_points": len(rows),
        }
    finally:
        session.close()


def save_tpf_session_stub(payload: dict) -> dict:
    if not isinstance(payload, dict) or not payload:
        raise ValueError("payload di salvataggio non valido")

    gaia_source_id = _extract_gaia_source_id(payload)
    sector = _extract_sector(payload)
    mask_origin = _extract_mask_origin(payload)
    lightcurve_payload = payload.get("lightcurve") if isinstance(payload.get("lightcurve"), dict) else {}

    session_record = _session_record_from_payload(
        payload,
        gaia_source_id=gaia_source_id,
        sector=sector,
        mask_origin=mask_origin,
    )
    session_result = _save_tpf_session_record(session_record)

    lightcurve_available = bool(lightcurve_payload.get("available"))
    time_bjd = lightcurve_payload.get("time_bjd")
    mag_tess_anchored = lightcurve_payload.get("mag_tess_anchored")

    promotion_result = {
        "promoted": False,
        "catalog_name": _build_catalog_name(sector, mask_origin),
        "inserted_points": 0,
        "reason": None,
    }

    if not lightcurve_available:
        promotion_result["reason"] = "lightcurve.available=false"
    elif not isinstance(time_bjd, list):
        raise ValueError("lightcurve.time_bjd mancante nel payload di salvataggio")
    elif not isinstance(mag_tess_anchored, list):
        raise ValueError("lightcurve.mag_tess_anchored mancante nel payload di salvataggio")
    else:
        cleaned_time_bjd, cleaned_mag, cleaning_summary = _clean_float_series(time_bjd, mag_tess_anchored)
        LOGGER.info(
            "Validated TPF promoted series for gaia_source_id=%s sector=%s: input_points=%s valid_points=%s discarded_points=%s",
            gaia_source_id,
            sector,
            cleaning_summary["input_points"],
            cleaning_summary["valid_points"],
            cleaning_summary["discarded_points"],
        )
        if cleaning_summary["valid_points"] < 2:
            promotion_result["reason"] = "meno di 2 punti validi con mag_tess_anchored"
        else:
            promotion_result = {
                **promotion_result,
                **_promote_photometry_points(
                    gaia_source_id=gaia_source_id,
                    sector=sector,
                    mask_origin=mask_origin,
                    cleaned_time_bjd=cleaned_time_bjd,
                    cleaned_mag=cleaned_mag,
                ),
                "cleaning_summary": cleaning_summary,
                "mapping": {
                    "time_bjd_to_hjd": True,
                    "mag_tess_anchored_to_Vmag": True,
                    "gaia_source_id_to_Source": True,
                    "time_system": "BJD_TDB",
                    "note": "hjd contains BJD_TDB for TPF catalogs",
                },
            }

    _update_tpf_session_promotion(
        session_result["session_id"],
        promoted=bool(promotion_result.get("promoted")),
        promoted_points=int(promotion_result.get("inserted_points") or 0),
    )

    saved_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return {
        "status": "ok",
        "message": "Salvataggio TPF eseguito.",
        "mode": "database",
        "saved": True,
        "save_id": f"tpf-{gaia_source_id}-{sector}-{mask_origin}",
        "saved_at_utc": saved_at,
        "summary": {
            "gaia_source_id": gaia_source_id,
            "sector": sector,
            "mask_origin": mask_origin,
            "tpf_available": bool((payload.get("tpf") or {}).get("available")),
            "lightcurve_available": lightcurve_available,
        },
        "session": session_result,
        "promotion": promotion_result,
        "payload": payload,
    }

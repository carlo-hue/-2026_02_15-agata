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


def _build_catalog_base_name(sector: int, mask_origin: str) -> str:
    return f"TPF-BJD_s{int(sector):04d}_{mask_origin}"


def _build_catalog_name(sector: int, mask_origin: str, *, session_id: int | None = None) -> str:
    base_name = _build_catalog_base_name(sector, mask_origin)
    if session_id is None:
        return base_name
    return f"{base_name}_sess{int(session_id)}"


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _serialize_json(value) -> str:
    return json.dumps(value, ensure_ascii=True, default=_json_default)


def _normalize_mask_pixels(mask_value) -> list[list[int]]:
    if not isinstance(mask_value, list):
        return []

    # Already in sparse coordinate form: [[row, col], ...]
    if mask_value and all(
        isinstance(item, list)
        and len(item) == 2
        and all(isinstance(coord, (int, float, bool)) for coord in item)
        for item in mask_value
    ):
        normalized_pixels: list[list[int]] = []
        for row_value, col_value in mask_value:
            normalized_pixels.append([int(row_value), int(col_value)])
        return normalized_pixels

    # Dense boolean matrix form: [[false, true, ...], ...]
    normalized_pixels = []
    for row_index, row in enumerate(mask_value):
        if not isinstance(row, list):
            continue
        for col_index, enabled in enumerate(row):
            if bool(enabled):
                normalized_pixels.append([row_index, col_index])
    return normalized_pixels


def _infer_mask_shape(metadata: dict, target_pixels: list[list[int]], background_pixels: list[list[int]]) -> tuple[int, int]:
    cutout_size = metadata.get("cutout_size")
    try:
        size_value = int(cutout_size)
        if size_value > 0:
            return size_value, size_value
    except (TypeError, ValueError):
        pass

    max_row = -1
    max_col = -1
    for pixels in (target_pixels, background_pixels):
        for pixel in pixels:
            if isinstance(pixel, list) and len(pixel) == 2:
                max_row = max(max_row, int(pixel[0]))
                max_col = max(max_col, int(pixel[1]))
    inferred_rows = max_row + 1 if max_row >= 0 else 0
    inferred_cols = max_col + 1 if max_col >= 0 else 0
    if inferred_rows > 0 and inferred_cols > 0:
        return inferred_rows, inferred_cols
    raise ValueError("Shape della maschera non ricostruibile dalla sessione TPF")


def _sparse_pixels_to_dense_mask(pixels: list[list[int]], shape: tuple[int, int]) -> list[list[bool]]:
    rows, cols = shape
    mask = [[False for _ in range(cols)] for _ in range(rows)]
    for pixel in pixels:
        if not isinstance(pixel, list) or len(pixel) != 2:
            continue
        row_index = int(pixel[0])
        col_index = int(pixel[1])
        if 0 <= row_index < rows and 0 <= col_index < cols:
            mask[row_index][col_index] = True
    return mask


def _build_session_metadata(
    *,
    tpf_metadata: dict,
    lightcurve_metadata: dict,
    gaia_source_id: str,
    sector: int,
    mask_origin: str,
) -> dict:
    bjd_ref = tpf_metadata.get("bjd_ref")
    if bjd_ref is None:
        bjd_ref_i = tpf_metadata.get("bjd_ref_i")
        bjd_ref_f = tpf_metadata.get("bjd_ref_f")
        if bjd_ref_i is not None or bjd_ref_f is not None:
            try:
                bjd_ref = float(bjd_ref_i or 0) + float(bjd_ref_f or 0)
            except (TypeError, ValueError):
                bjd_ref = None

    metadata = {
        "gaia_id": str(tpf_metadata.get("gaia_id") or gaia_source_id),
        "sector": sector,
        "camera": tpf_metadata.get("camera"),
        "ccd": tpf_metadata.get("ccd"),
        "tpf_filename": tpf_metadata.get("tpf_filename"),
        "tpf_path": tpf_metadata.get("tpf_path"),
        "cutout_size": tpf_metadata.get("cutout_size"),
        "time_system": "BJD_TDB",
        "time_note": "hjd contains BJD_TDB for TPF catalogs",
        "time_format": tpf_metadata.get("time_format"),
        "time_unit": tpf_metadata.get("time_unit"),
        "bjd_ref": bjd_ref,
        "mask_origin": mask_origin,
        "background_method": lightcurve_metadata.get("background_method"),
        "anchoring_method": lightcurve_metadata.get("anchoring_method"),
        "reference_mag_band": lightcurve_metadata.get("reference_mag_band"),
        "reference_mag_source": lightcurve_metadata.get("reference_mag_source"),
        "reference_mag_value": lightcurve_metadata.get("reference_mag_value"),
        "anchoring_applied": lightcurve_metadata.get("anchoring_applied"),
        "target_threshold": lightcurve_metadata.get("target_threshold"),
        "background_threshold": lightcurve_metadata.get("background_threshold"),
        "sigma_clipping": lightcurve_metadata.get("sigma_clipping"),
    }
    return {key: value for key, value in metadata.items() if value is not None}


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
    target_mask = masks.get("target_pixels")
    if not isinstance(target_mask, list):
        target_mask = masks.get("target") if isinstance(masks.get("target"), list) else []
    background_mask = masks.get("background_pixels")
    if not isinstance(background_mask, list):
        background_mask = masks.get("background") if isinstance(masks.get("background"), list) else []
    target_mask_pixels = _normalize_mask_pixels(target_mask)
    background_mask_pixels = _normalize_mask_pixels(background_mask)

    metadata = _build_session_metadata(
        tpf_metadata=tpf_metadata,
        lightcurve_metadata=lightcurve_metadata,
        gaia_source_id=gaia_source_id,
        sector=sector,
        mask_origin=mask_origin,
    )

    return {
        "gaia_source_id": int(gaia_source_id),
        "sector": sector,
        "catalog_name": _build_catalog_name(sector, mask_origin),
        "mode": str(lightcurve_payload.get("mode") or payload.get("mode") or "unknown"),
        "mask_origin": mask_origin,
        "tpf_filename": tpf_source.get("filename"),
        "tpf_path": tpf_source.get("path"),
        "target_mask_json": _serialize_json(target_mask_pixels),
        "background_mask_json": _serialize_json(background_mask_pixels),
        "lightcurve_json": _serialize_json({}),
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


def _update_tpf_session_record(session_id: int, session_payload: dict) -> dict:
    session = SessionLocal()
    try:
        if not _table_exists(session, TPF_SESSION_TABLE):
            raise RuntimeError(f"Tabella {TPF_SESSION_TABLE} non disponibile")

        existing = session.execute(
            text(
                f"""
                SELECT id
                FROM {TPF_SESSION_TABLE}
                WHERE id = :session_id
                """
            ),
            {"session_id": int(session_id)},
        ).scalar_one_or_none()
        if existing is None:
            raise ValueError(f"Sessione TPF {session_id} non trovata")

        session.execute(
            text(
                f"""
                UPDATE {TPF_SESSION_TABLE}
                SET gaia_source_id = :gaia_source_id,
                    sector = :sector,
                    catalog_name = :catalog_name,
                    mode = :mode,
                    mask_origin = :mask_origin,
                    tpf_filename = :tpf_filename,
                    tpf_path = :tpf_path,
                    target_mask_json = :target_mask_json,
                    background_mask_json = :background_mask_json,
                    lightcurve_json = :lightcurve_json,
                    metadata_json = :metadata_json,
                    saved_by = :saved_by,
                    is_promoted = :is_promoted,
                    promoted_points = :promoted_points,
                    saved_at = CURRENT_TIMESTAMP
                WHERE id = :session_id
                """
            ),
            {
                **session_payload,
                "session_id": int(session_id),
            },
        )
        session.commit()
        LOGGER.info(
            "Updated TPF technical session in %s for gaia_source_id=%s sector=%s session_id=%s",
            TPF_SESSION_TABLE,
            session_payload["gaia_source_id"],
            session_payload["sector"],
            int(session_id),
        )
        return {"saved": True, "session_id": int(session_id), "table": TPF_SESSION_TABLE, "updated": True}
    finally:
        session.close()


def list_tpf_sessions(*, gaia_source_id: str, sector: int | None = None, limit: int = 20) -> dict:
    session = SessionLocal()
    try:
        if not _table_exists(session, TPF_SESSION_TABLE):
            raise RuntimeError(f"Tabella {TPF_SESSION_TABLE} non disponibile")

        query_sql = text(
            f"""
            SELECT
                id,
                gaia_source_id,
                sector,
                catalog_name,
                mode,
                mask_origin,
                tpf_filename,
                saved_at,
                is_promoted,
                promoted_points
            FROM {TPF_SESSION_TABLE}
            WHERE gaia_source_id = :gaia_source_id
              AND (:sector IS NULL OR sector = :sector)
            ORDER BY saved_at DESC, id DESC
            LIMIT :limit_value
            """
        )
        rows = session.execute(
            query_sql,
            {
                "gaia_source_id": int(gaia_source_id),
                "sector": int(sector) if sector is not None else None,
                "limit_value": int(limit),
            },
        ).mappings().all()
        sessions = []
        for row in rows:
            saved_at = row.get("saved_at")
            sessions.append({
                "session_id": int(row["id"]),
                "gaia_source_id": str(row["gaia_source_id"]),
                "sector": int(row["sector"]),
                "catalog_name": row.get("catalog_name"),
                "mode": row.get("mode"),
                "mask_origin": row.get("mask_origin"),
                "tpf_filename": row.get("tpf_filename"),
                "saved_at": saved_at.isoformat() if saved_at is not None else None,
                "is_promoted": bool(row.get("is_promoted")),
                "promoted_points": int(row.get("promoted_points") or 0),
            })
        return {
            "status": "ok",
            "sessions": sessions,
            "gaia_source_id": str(gaia_source_id),
            "sector": sector,
        }
    finally:
        session.close()


def restore_tpf_session(session_id: int) -> dict:
    session = SessionLocal()
    try:
        if not _table_exists(session, TPF_SESSION_TABLE):
            raise RuntimeError(f"Tabella {TPF_SESSION_TABLE} non disponibile")

        row = session.execute(
            text(
                f"""
                SELECT
                    id,
                    gaia_source_id,
                    sector,
                    mask_origin,
                    target_mask_json,
                    background_mask_json,
                    metadata_json
                FROM {TPF_SESSION_TABLE}
                WHERE id = :session_id
                """
            ),
            {"session_id": int(session_id)},
        ).mappings().first()
        if row is None:
            raise ValueError(f"Sessione TPF {session_id} non trovata")

        metadata = json.loads(row.get("metadata_json") or "{}")
        target_pixels = _normalize_mask_pixels(json.loads(row.get("target_mask_json") or "[]"))
        background_pixels = _normalize_mask_pixels(json.loads(row.get("background_mask_json") or "[]"))
        mask_shape = _infer_mask_shape(metadata, target_pixels, background_pixels)
        manual_masks = {
            "target": _sparse_pixels_to_dense_mask(target_pixels, mask_shape),
            "background": _sparse_pixels_to_dense_mask(background_pixels, mask_shape),
        }
        gaia_source_id = str(row["gaia_source_id"])
        sector = int(row["sector"])
    finally:
        session.close()

    from .tpf_service import run_tpf_pipeline

    result = run_tpf_pipeline(gaia_source_id, sector, masks=manual_masks)
    result["restored_session"] = {
        "session_id": int(session_id),
        "gaia_source_id": gaia_source_id,
        "sector": sector,
        "mask_origin": row.get("mask_origin"),
    }
    result["message"] = f"Sessione TPF {session_id} ripristinata."
    return result


def delete_tpf_session(session_id: int) -> dict:
    session = SessionLocal()
    try:
        if not _table_exists(session, TPF_SESSION_TABLE):
            raise RuntimeError(f"Tabella {TPF_SESSION_TABLE} non disponibile")

        row = session.execute(
            text(
                f"""
                SELECT id, gaia_source_id, sector
                FROM {TPF_SESSION_TABLE}
                WHERE id = :session_id
                """
            ),
            {"session_id": int(session_id)},
        ).mappings().first()
        if row is None:
            raise ValueError(f"Sessione TPF {session_id} non trovata")

        session.execute(
            text(
                f"""
                DELETE FROM {TPF_SESSION_TABLE}
                WHERE id = :session_id
                """
            ),
            {"session_id": int(session_id)},
        )
        session.commit()

        return {
            "status": "ok",
            "deleted": True,
            "session_id": int(session_id),
            "gaia_source_id": str(row["gaia_source_id"]),
            "sector": int(row["sector"]),
            "message": f"Sessione TPF {session_id} eliminata.",
        }
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


def _update_tpf_session_catalog_name(session_id: int, catalog_name: str) -> None:
    session = SessionLocal()
    try:
        with session.begin():
            session.execute(
                text(
                    f"""
                    UPDATE {TPF_SESSION_TABLE}
                    SET catalog_name = :catalog_name
                    WHERE id = :session_id
                    """
                ),
                {
                    "catalog_name": str(catalog_name),
                    "session_id": int(session_id),
                },
            )
    finally:
        session.close()


def _promote_photometry_points(
    *,
    session_id: int,
    gaia_source_id: str,
    sector: int,
    mask_origin: str,
    cleaned_time_bjd: list[float],
    cleaned_mag: list[float],
) -> dict:
    catalog_base_name = _build_catalog_base_name(sector, mask_origin)
    catalog_name = _build_catalog_name(sector, mask_origin, session_id=session_id)
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
                WHERE Source = :source AND catalogo LIKE :catalogo_pattern
                """
            )
            session.execute(
                delete_sql,
                {
                    "source": int(gaia_source_id),
                    "catalogo_pattern": f"{catalog_base_name}%",
                },
            )

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
    technical_session_payload = payload.get("technical_session") if isinstance(payload.get("technical_session"), dict) else {}
    update_session_id = technical_session_payload.get("update_session_id")
    if update_session_id in (None, ""):
        session_result = _save_tpf_session_record(session_record)
    else:
        try:
            session_result = _update_tpf_session_record(int(update_session_id), session_record)
        except (TypeError, ValueError):
            raise ValueError("update_session_id non valido per il salvataggio tecnico") from None
    saved_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    return {
        "status": "ok",
        "message": "Sessione tecnica TPF aggiornata." if session_result.get("updated") else "Sessione tecnica TPF salvata.",
        "mode": "database",
        "saved": True,
        "save_id": f"tpf-session-{gaia_source_id}-{sector}-{mask_origin}-{session_result['session_id']}",
        "saved_at_utc": saved_at,
        "summary": {
            "gaia_source_id": gaia_source_id,
            "sector": sector,
            "mask_origin": mask_origin,
            "tpf_available": bool((payload.get("tpf") or {}).get("available")),
            "lightcurve_available": bool(lightcurve_payload.get("available")),
        },
        "session": session_result,
        "payload": payload,
    }


def promote_tpf_curve(payload: dict) -> dict:
    if not isinstance(payload, dict) or not payload:
        raise ValueError("payload di promozione non valido")

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
        promotion_result["reason"] = "lightcurve.time_bjd mancante nel payload di promozione"
    elif not isinstance(mag_tess_anchored, list):
        promotion_result["reason"] = "lightcurve.mag_tess_anchored mancante nel payload di promozione"
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
                    session_id=session_result["session_id"],
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
            _update_tpf_session_catalog_name(
                session_result["session_id"],
                promotion_result["catalog_name"],
            )

    if promotion_result.get("promoted"):
        message = "Promozione curva TPF completata."
        status = "ok"
    else:
        message = promotion_result.get("reason") or "Promozione curva TPF non eseguita."
        status = "error"

    _update_tpf_session_promotion(
        session_result["session_id"],
        promoted=bool(promotion_result.get("promoted")),
        promoted_points=int(promotion_result.get("inserted_points") or 0),
    )

    saved_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return {
        "status": status,
        "message": message,
        "mode": "database",
        "saved": True,
        "save_id": f"tpf-promotion-{gaia_source_id}-{sector}-{mask_origin}-{session_result['session_id']}",
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

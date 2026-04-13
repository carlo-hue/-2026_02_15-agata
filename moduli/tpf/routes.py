from __future__ import annotations

import logging

from flask import Blueprint, current_app, jsonify, render_template, request, url_for

from .config import settings
from .services import delete_tpf_session, download_tpf_from_mast, get_local_tpf_sectors_for_gaia, get_mast_sectors_for_gaia, list_tpf_sessions, load_tpf_frame_window, promote_tpf_curve, restore_tpf_session, run_tpf_pipeline, save_tpf_session_stub
from .services.utils import validate_cutout_size, validate_gaia_source_id, validate_sector

LOGGER = logging.getLogger(__name__)


def _json_error(message: str, status_code: int = 400):
    return jsonify({"status": "error", "message": message}), status_code


def _mast_json_error(message: str, status_code: int = 400, **extra):
    payload = {"ok": False, "status": "error", "message": message}
    payload.update(extra)
    return jsonify(payload), status_code


def _build_page_context(args, entrypoint: str = "editor") -> dict:
    gaia_source_id = str(args.get("gaia_source_id", "")).strip()
    sector_raw = str(args.get("sector", "")).strip()
    source_context = str(args.get("source_context", "")).strip()
    mode = "integrated" if source_context else "standalone"
    return {
        "mode": mode,
        "gaia_source_id": gaia_source_id,
        "sector": sector_raw,
        "source_context": source_context,
        "entrypoint": entrypoint,
    }


def _optional_url(endpoint: str, fallback: str = "#") -> str:
    if endpoint not in current_app.view_functions:
        return fallback
    try:
        return url_for(endpoint)
    except Exception:
        return fallback


def create_blueprint() -> Blueprint:
    bp = Blueprint(
        "tpf",
        __name__,
        template_folder="templates",
        static_folder="static",
        url_prefix="/tpf",
    )

    @bp.get("/")
    def index():
        page_context = _build_page_context(request.args, entrypoint="editor")
        return render_template(
            "tpf/index.html",
            module_title=settings.module_title,
            scaffold_message=settings.placeholder_message,
            page_context=page_context,
            default_cutout_size=settings.default_cutout_size,
            module_links={
                "admin": _optional_url("admin.list_projects"),
                "variable_stars": _optional_url("variable_stars.index"),
                "exoplanets": _optional_url("exoplanets.index"),
                "field_star_map": _optional_url("field_star_map.index"),
                "galassie_nane": _optional_url("galassie_nane.index"),
                "tess_tce": _optional_url("tess_tce.index"),
                "tpf": url_for("tpf.index"),
            },
        )

    @bp.get("/overview")
    def overview():
        page_context = _build_page_context(request.args, entrypoint="overview")
        return render_template(
            "tpf/index.html",
            module_title=settings.module_title,
            scaffold_message=settings.placeholder_message,
            page_context=page_context,
            default_cutout_size=settings.default_cutout_size,
            module_links={
                "admin": _optional_url("admin.list_projects"),
                "variable_stars": _optional_url("variable_stars.index"),
                "exoplanets": _optional_url("exoplanets.index"),
                "field_star_map": _optional_url("field_star_map.index"),
                "galassie_nane": _optional_url("galassie_nane.index"),
                "tess_tce": _optional_url("tess_tce.index"),
                "tpf": url_for("tpf.index"),
            },
        )

    @bp.get("/health")
    def health():
        return jsonify({
            "status": "ok",
            "message": "TPF component healthy",
            "component": "tpf",
        })

    @bp.post("/api/run")
    def run_api():
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return _json_error("payload JSON non valido", 400)

        gaia_source_id = str(payload.get("gaia_source_id", "")).strip()
        sector_raw = payload.get("sector", "")
        masks = payload.get("masks") if isinstance(payload.get("masks"), dict) else None
        if not gaia_source_id:
            return _json_error("gaia_source_id mancante", 400)

        try:
            sector = validate_sector(sector_raw)
        except ValueError as err:
            return _json_error(str(err), 400)

        LOGGER.info(
            "TPF pipeline requested for gaia_source_id=%s sector=%s manual_masks=%s",
            gaia_source_id,
            sector,
            bool(masks),
        )
        try:
            result = run_tpf_pipeline(gaia_source_id, sector, masks=masks)
        except ValueError as err:
            LOGGER.warning("TPF pipeline validation error for %s sector=%s: %s", gaia_source_id, sector, err)
            return _json_error(str(err), 400)
        except Exception as err:
            LOGGER.exception("TPF pipeline failed for gaia_source_id=%s sector=%s", gaia_source_id, sector)
            return _json_error(str(err), 502)
        return jsonify(result)

    @bp.post("/api/frames")
    def frames_api():
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return _json_error("payload JSON non valido", 400)

        gaia_source_id = str(payload.get("gaia_source_id", "")).strip()
        sector_raw = payload.get("sector", "")
        frame_start_raw = payload.get("frame_start")
        frame_end_raw = payload.get("frame_end")
        if not gaia_source_id:
            return _json_error("gaia_source_id mancante", 400)

        try:
            sector = validate_sector(sector_raw)
            frame_start = int(frame_start_raw)
            frame_end = int(frame_end_raw)
        except (TypeError, ValueError):
            return _json_error("Intervallo frame non valido", 400)

        LOGGER.info(
            "TPF frame window requested for gaia_source_id=%s sector=%s frame_start=%s frame_end=%s",
            gaia_source_id,
            sector,
            frame_start,
            frame_end,
        )
        try:
            result = load_tpf_frame_window(gaia_source_id, sector, frame_start, frame_end)
        except ValueError as err:
            LOGGER.warning(
                "TPF frame window validation error for %s sector=%s frame_start=%s frame_end=%s: %s",
                gaia_source_id,
                sector,
                frame_start,
                frame_end,
                err,
            )
            return _json_error(str(err), 400)
        except Exception as err:
            LOGGER.exception(
                "TPF frame window failed for gaia_source_id=%s sector=%s frame_start=%s frame_end=%s",
                gaia_source_id,
                sector,
                frame_start,
                frame_end,
            )
            return _json_error(str(err), 502)
        return jsonify(result)

    @bp.post("/api/mast/sectors")
    def mast_sectors_api():
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return _mast_json_error("payload JSON non valido", 400)

        gaia_id_raw = payload.get("gaia_id", "")
        cutout_size_raw = payload.get("cutout_size", settings.default_cutout_size)
        try:
            gaia_id = validate_gaia_source_id(gaia_id_raw)
            cutout_size = validate_cutout_size(cutout_size_raw, settings.default_cutout_size)
        except ValueError as err:
            return _mast_json_error(str(err), 400)

        LOGGER.info("MAST sector listing requested for gaia_id=%s cutout_size=%s", gaia_id, cutout_size)
        try:
            result = get_mast_sectors_for_gaia(gaia_id, cutout_size=cutout_size)
        except ValueError as err:
            LOGGER.warning("MAST sector listing validation error for gaia_id=%s: %s", gaia_id, err)
            return _mast_json_error(str(err), 400, gaia_id=gaia_id)
        except Exception as err:
            LOGGER.exception("MAST sector listing failed for gaia_id=%s", gaia_id)
            return _mast_json_error(str(err), 502, gaia_id=gaia_id)
        return jsonify(result)

    @bp.post("/api/mast/local-sectors")
    def mast_local_sectors_api():
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return _mast_json_error("payload JSON non valido", 400)

        gaia_id_raw = payload.get("gaia_id", "")
        cutout_size_raw = payload.get("cutout_size", settings.default_cutout_size)
        try:
            gaia_id = validate_gaia_source_id(gaia_id_raw)
            cutout_size = validate_cutout_size(cutout_size_raw, settings.default_cutout_size)
        except ValueError as err:
            return _mast_json_error(str(err), 400)

        LOGGER.info("Local TPF sector listing requested for gaia_id=%s cutout_size=%s", gaia_id, cutout_size)
        try:
            result = get_local_tpf_sectors_for_gaia(gaia_id, cutout_size=cutout_size)
        except ValueError as err:
            LOGGER.warning("Local TPF sector listing validation error for gaia_id=%s: %s", gaia_id, err)
            return _mast_json_error(str(err), 400, gaia_id=gaia_id)
        except Exception as err:
            LOGGER.exception("Local TPF sector listing failed for gaia_id=%s", gaia_id)
            return _mast_json_error(str(err), 502, gaia_id=gaia_id)
        return jsonify(result)

    @bp.post("/api/mast/download")
    def mast_download_api():
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return _mast_json_error("payload JSON non valido", 400)

        gaia_id_raw = payload.get("gaia_id", "")
        sector_raw = payload.get("sector", "")
        cutout_size_raw = payload.get("cutout_size", settings.default_cutout_size)
        try:
            gaia_id = validate_gaia_source_id(gaia_id_raw)
            sector = validate_sector(sector_raw)
            cutout_size = validate_cutout_size(cutout_size_raw, settings.default_cutout_size)
        except ValueError as err:
            return _mast_json_error(str(err), 400)

        LOGGER.info(
            "MAST TPF download requested for gaia_id=%s sector=%s cutout_size=%s",
            gaia_id,
            sector,
            cutout_size,
        )
        try:
            result = download_tpf_from_mast(gaia_id, sector, cutout_size=cutout_size)
        except ValueError as err:
            LOGGER.warning("MAST TPF download validation error for gaia_id=%s sector=%s: %s", gaia_id, sector, err)
            return _mast_json_error(str(err), 400, gaia_id=gaia_id, sector=sector, cutout_size=cutout_size)
        except Exception as err:
            LOGGER.exception("MAST TPF download failed for gaia_id=%s sector=%s", gaia_id, sector)
            return _mast_json_error(str(err), 502, gaia_id=gaia_id, sector=sector, cutout_size=cutout_size)
        return jsonify(result)

    @bp.post("/api/save")
    def save_api():
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict) or not payload:
            return _json_error("payload di salvataggio mancante", 400)

        gaia_source_id = "-"
        sector = "-"
        if isinstance(payload.get("input"), dict):
            gaia_source_id = str(payload["input"].get("gaia_source_id") or "-")
            sector = str(payload["input"].get("sector") or "-")
        LOGGER.info("TPF save requested for gaia_source_id=%s sector=%s", gaia_source_id, sector)

        try:
            result = save_tpf_session_stub(payload)
        except ValueError as err:
            LOGGER.warning("TPF save validation error for %s sector=%s: %s", gaia_source_id, sector, err)
            return _json_error(str(err), 400)
        except Exception as err:
            LOGGER.exception("TPF save failed for gaia_source_id=%s sector=%s", gaia_source_id, sector)
            return _json_error(str(err), 502)
        return jsonify(result)

    @bp.post("/api/sessions")
    def sessions_api():
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return _json_error("payload JSON non valido", 400)

        gaia_source_id = str(payload.get("gaia_source_id", "")).strip()
        sector_raw = payload.get("sector")
        if not gaia_source_id:
            return _json_error("gaia_source_id mancante", 400)

        sector = None
        if sector_raw not in (None, ""):
            try:
                sector = validate_sector(sector_raw)
            except ValueError as err:
                return _json_error(str(err), 400)

        try:
            result = list_tpf_sessions(gaia_source_id=gaia_source_id, sector=sector)
        except ValueError as err:
            return _json_error(str(err), 400)
        except Exception as err:
            LOGGER.exception("TPF sessions listing failed for gaia_source_id=%s sector=%s", gaia_source_id, sector or "-")
            return _json_error(str(err), 502)
        return jsonify(result)

    @bp.post("/api/restore-session")
    def restore_session_api():
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return _json_error("payload JSON non valido", 400)

        session_id_raw = payload.get("session_id")
        try:
            session_id = int(session_id_raw)
        except (TypeError, ValueError):
            return _json_error("session_id non valido", 400)

        try:
            result = restore_tpf_session(session_id)
        except ValueError as err:
            return _json_error(str(err), 400)
        except Exception as err:
            LOGGER.exception("TPF restore failed for session_id=%s", session_id)
            return _json_error(str(err), 502)
        return jsonify(result)

    @bp.post("/api/delete-session")
    def delete_session_api():
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return _json_error("payload JSON non valido", 400)

        session_id_raw = payload.get("session_id")
        try:
            session_id = int(session_id_raw)
        except (TypeError, ValueError):
            return _json_error("session_id non valido", 400)

        try:
            result = delete_tpf_session(session_id)
        except ValueError as err:
            return _json_error(str(err), 400)
        except Exception as err:
            LOGGER.exception("TPF delete failed for session_id=%s", session_id)
            return _json_error(str(err), 502)
        return jsonify(result)

    @bp.post("/api/promote")
    def promote_api():
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict) or not payload:
            return _json_error("payload di promozione mancante", 400)

        gaia_source_id = "-"
        sector = "-"
        if isinstance(payload.get("input"), dict):
            gaia_source_id = str(payload["input"].get("gaia_source_id") or "-")
            sector = str(payload["input"].get("sector") or "-")
        LOGGER.info("TPF promotion requested for gaia_source_id=%s sector=%s", gaia_source_id, sector)

        try:
            result = promote_tpf_curve(payload)
        except ValueError as err:
            LOGGER.warning("TPF promotion validation error for %s sector=%s: %s", gaia_source_id, sector, err)
            return _json_error(str(err), 400)
        except Exception as err:
            LOGGER.exception("TPF promotion failed for gaia_source_id=%s sector=%s", gaia_source_id, sector)
            return _json_error(str(err), 502)
        return jsonify(result)

    return bp

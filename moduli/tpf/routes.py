from __future__ import annotations

import logging

from flask import Blueprint, current_app, jsonify, render_template, request, url_for

from .config import settings
from .services import run_tpf_pipeline, save_tpf_session_stub
from .services.utils import validate_sector

LOGGER = logging.getLogger(__name__)


def _json_error(message: str, status_code: int = 400):
    return jsonify({"status": "error", "message": message}), status_code


def _build_page_context(args) -> dict:
    gaia_source_id = str(args.get("gaia_source_id", "")).strip()
    sector_raw = str(args.get("sector", "")).strip()
    source_context = str(args.get("source_context", "")).strip()
    mode = "integrated" if source_context else "standalone"
    return {
        "mode": mode,
        "gaia_source_id": gaia_source_id,
        "sector": sector_raw,
        "source_context": source_context,
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
        page_context = _build_page_context(request.args)
        return render_template(
            "tpf/index.html",
            module_title=settings.module_title,
            scaffold_message=settings.placeholder_message,
            page_context=page_context,
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

    return bp

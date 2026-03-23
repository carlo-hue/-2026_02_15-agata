"""
field_star_map - Modulo Mappa Stelle Gaia

UI AGATA (template Jinja + static JS/CSS) per visualizzare:
- mappa stelle nel campo
- cerchi concentrici fotometrici
- top contaminanti con ordinamento/selezione

L'API scientifica resta quella del backend dedicato:
- GET /health
- GET /field-star-map
"""

from __future__ import annotations

import os

from flask import Blueprint, current_app, request
from flask_login import current_user

AGATA_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

field_star_map_bp = Blueprint(
    "field_star_map",
    __name__,
    url_prefix="/agata/field-star-map",
    template_folder=os.path.join(AGATA_DIR, "templates"),
    static_folder=os.path.join(AGATA_DIR, "static"),
)


@field_star_map_bp.before_request
def require_analyst_role():
    """
    Accesso consentito a ruoli analyst o superiori.
    """
    if current_app.config.get("LOCAL_DEV_BYPASS_AUTH", False):
        return None

    if request.endpoint and "static" in request.endpoint:
        return None

    if not current_user.is_authenticated or not current_user.is_active:
        return "Access denied", 403

    allowed_roles = {"analyst", "reviewer", "admin", "superuser"}
    if current_user.role not in allowed_roles:
        return "Access denied", 403

    return None


from . import routes  # noqa: E402,F401

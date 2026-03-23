from __future__ import annotations

import os

from flask import render_template

from . import field_star_map_bp


@field_star_map_bp.get("/")
def index():
    api_base_url = os.getenv("FIELD_STAR_MAP_API_BASE_URL", "http://localhost:8000")
    return render_template("field_star_map/index.html", api_base_url=api_base_url)


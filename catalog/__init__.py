"""
Catalog Blueprint - Interrogazione cataloghi esterni via Gaia ID

Fornisce API per interrogare cataloghi astronomici (Gaia, Vizier, VSX, etc.)
partendo da un Gaia source ID.

Routes:
- POST /agata/catalog/api/query - Query catalogs by Gaia ID
"""
from flask import Blueprint

catalog_bp = Blueprint(
    'catalog',
    __name__,
    url_prefix='/agata/catalog'
)

# Import routes (auto-register decorators)
from . import flask_routes

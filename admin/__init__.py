"""
AGATA Admin Blueprint

Interfaccia di amministrazione autoritativa per AGATA:
- Dashboard overview con metriche chiave
- Gestione associazioni (multi-tenant)
- Gestione utenti con RBAC per associazione
- Catalogo progetti con workflow management
- Integrazione Slack (canali, thread, errori)
- Audit log completo
- Policy e configurazioni di sistema

Ruoli supportati:
- superuser: AstroGen governance (accesso globale)
- admin: gestione associazione (scope associazione)
- reviewer: review scientifica (scope associazione)
- analyst: analisi (scope associazione, accesso limitato)
- viewer: sola lettura (audit)

AGATA è autoritativo, Slack è riflesso.
"""

from flask import Blueprint

# Blueprint principale
admin_bp = Blueprint(
    'admin',
    __name__,
    url_prefix='/agata/admin',
    template_folder='../templates/admin',
    static_folder='../static'
)

# Import routes (dopo definizione blueprint per evitare circular imports)
from agata.admin.routes import (
    overview,
    associations,
    users,
    projects,
    workflow,
    slack_integration,
    audit,
    config,
    project_detail,
    external_catalogs,
    stars_catalog,
    vast_automation
)

# Import e registra blueprint cataloghi (endpoint dedicati per ogni catalogo)
from agata.admin.routes.catalogs import catalogs_bp
admin_bp.register_blueprint(catalogs_bp)

# Import e registra blueprint project_detail (API per dettaglio progetti)
from agata.admin.routes.project_detail import project_detail_bp
admin_bp.register_blueprint(project_detail_bp)

__all__ = ['admin_bp', 'catalogs_bp', 'project_detail_bp']

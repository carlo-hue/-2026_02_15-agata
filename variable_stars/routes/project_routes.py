"""
project_routes.py - Endpoint per progetti utente

Permette di ottenere la lista dei progetti assegnati all'utente corrente
per selezionarli direttamente nell'interfaccia delle stelle variabili.
"""

import logging
from flask import jsonify
from flask_login import current_user, login_required
from sqlalchemy.orm import Session

from agata.variable_stars import variable_stars_bp
from agata.db import SessionLocal
from agata.auth_models.project import Project

logger = logging.getLogger(__name__)


@variable_stars_bp.get("/api/my-projects")
@login_required
def api_my_projects():
    """
    Ottiene i progetti assegnati all'utente corrente.

    Restituisce solo progetti in stato 'assigned' o 'in_review' che
    l'utente può analizzare attivamente.

    Returns:
        JSON con lista progetti:
        [
            {
                "id": 1,
                "project_code": "AGATA-2024-001",
                "gaia_id": "1868255974288176128",
                "title": "RR Lyrae candidate",
                "state": "assigned",
                "magnitude": 12.5,
                "source": "ZTF"
            },
            ...
        ]
    """
    db: Session = SessionLocal()
    try:
        # Query progetti assegnati all'utente corrente
        # Stati attivi per l'analisi: assigned, in_review
        projects = db.query(Project).filter(
            Project.assigned_to == current_user.id,
            Project.state.in_(['assigned', 'in_review'])
        ).order_by(Project.assigned_at.desc()).all()

        result = []
        for p in projects:
            result.append({
                "id": p.id,
                "project_code": p.project_code,
                "gaia_id": p.gaia_id,
                "title": p.title or f"Progetto {p.project_code}",
                "state": p.state,
                "magnitude": p.magnitude,
                "source": p.source,
                "ra": p.ra,
                "dec": p.dec_deg
            })

        logger.info(f"Utente {current_user.email} ha {len(result)} progetti assegnati")
        return jsonify(result)

    except Exception as e:
        logger.error(f"Errore caricamento progetti utente: {e}", exc_info=True)
        return jsonify({"error": "Errore caricamento progetti"}), 500

    finally:
        db.close()

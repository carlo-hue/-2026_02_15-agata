"""
views.py - Rendering template homepage

Gestisce solo la visualizzazione della pagina principale.
"""

import logging
from flask import render_template, request, abort
from flask_login import current_user, login_required
from sqlalchemy.orm import Session
from agata.variable_stars import variable_stars_bp
from agata.auth_models import Project
from agata.db import SessionLocal

logger = logging.getLogger(__name__)


@variable_stars_bp.get("/")
@login_required
def index():
    """
    Homepage dell'applicazione Variable Stars Editor.

    Query Parameters:
        project_id (int, optional): ID del progetto da caricare

    Logica:
    - Se viene passato project_id, verifica che sia assegnato all'utente corrente
    - Superuser possono accedere a qualsiasi progetto
    - Altri utenti possono accedere solo ai progetti assegnati a loro
    - Se non viene passato project_id, l'utente parte da una vista vuota

    Returns:
        str: HTML template renderizzato
    """
    project_id = request.args.get('project_id', type=int)
    gaia_id = request.args.get('gaia_id', type=str)
    project = None
    error_message = None

    if project_id:
        db: Session = SessionLocal()
        try:
            project = db.query(Project).filter(Project.id == project_id).first()

            if not project:
                logger.warning(f"Progetto {project_id} non trovato per user {current_user.id}")
                error_message = f"Progetto #{project_id} non trovato. Verifica l'ID e riprova."
                return render_template(
                    "variable_stars/index.html",
                    project=None,
                    is_superuser=(current_user.role == 'superuser'),
                    error_message=error_message,
                    error_type="not_found"
                ), 404

            # Verifica permessi
            if current_user.role != 'superuser':
                # Verifica associazione
                if project.association_id != current_user.association_id:
                    logger.warning(f"User {current_user.id} ({current_user.email}) tentò di accedere a progetto {project_id} ({project.project_code}) di altra associazione")
                    error_message = f"❌ Non sei autorizzato ad accedere al progetto {project.project_code}. Questo progetto appartiene a un'altra associazione."
                    return render_template(
                        "variable_stars/index.html",
                        project=None,
                        is_superuser=False,
                        error_message=error_message,
                        error_type="forbidden_association"
                    ), 403

                # Verifica assegnazione: solo analyst/reviewer devono essere assegnati
                # Admin della stessa associazione possono sempre accedere
                if current_user.role in ['analyst', 'reviewer']:
                    # Confronto robusto: converti entrambi a string per evitare problemi di tipo
                    assigned_to_str = str(project.assigned_to) if project.assigned_to else None
                    current_user_id_str = str(current_user.id)

                    if assigned_to_str != current_user_id_str:
                        assigned_user_name = project.assigned_user.full_name if project.assigned_user else "Un altro analista"
                        logger.warning(f"User {current_user.id} ({current_user.email}) tentò di accedere a progetto {project_id} ({project.project_code}) non assegnato a loro (assegnato a {project.assigned_to})")
                        error_message = f"❌ Il progetto {project.project_code} non è assegnato a te. È assegnato a: {assigned_user_name}. Contatta l'amministratore se ritieni si tratti di un errore."
                        return render_template(
                            "variable_stars/index.html",
                            project=None,
                            is_superuser=False,
                            error_message=error_message,
                            error_type="forbidden_not_assigned"
                        ), 403

            logger.info(f"User {current_user.id} ({current_user.email}) accede al progetto {project_id} ({project.project_code})")
        finally:
            db.close()
    else:
        logger.info(f"User {current_user.id} ({current_user.email}) accede all'editor senza progetto")

    return render_template(
        "variable_stars/index.html",
        project=project,
        gaia_id=gaia_id,
        is_superuser=(current_user.role == 'superuser'),
        is_admin=(current_user.role == 'admin'),
        project_state=project.state if project else None,
        user_role=current_user.role,
        error_message=None,
        error_type=None
    )

# agata/admin/services/project_service.py
"""
Project Service

Business logic per operazioni amministrative su progetti:
- Cambio stato (con validazione workflow)
- Assegnazione/riassegnazione analyst
- Invio in review
- Cancellazione
- Promozione a canale Slack

AGATA è autoritativo: tutti i cambi stato avvengono qui.
Slack viene aggiornato di conseguenza (non viceversa).
"""
from datetime import datetime
from typing import Optional, Tuple
from sqlalchemy.orm import Session

from agata.auth_models import Project, User, Association, ProjectSlackThread
from agata.db import SessionLocal
from agata.admin.services.audit_service import log_audit
from agata.admin.services.slack_service import get_slack_service

import logging
logger = logging.getLogger(__name__)


# Workflow states validi
VALID_STATES = [
    'incoming', 'available', 'assigned', 'in_review',
    'submitted_aavso', 'accepted_aavso', 'rejected_aavso', 'cancelled'
]

# Transizioni stato valide (from_state -> [allowed_to_states])
STATE_TRANSITIONS = {
    'incoming': ['available', 'cancelled'],
    'available': ['assigned', 'cancelled'],
    'assigned': ['available', 'in_review', 'cancelled'],  # Può tornare available se de-assegnato
    'in_review': ['assigned', 'submitted_aavso', 'cancelled'],  # Può tornare assigned se respinto
    'submitted_aavso': ['accepted_aavso', 'rejected_aavso', 'cancelled'],
    'accepted_aavso': [],  # Stato finale
    'rejected_aavso': ['assigned'],  # Può essere riassegnato dopo rifiuto AAVSO
    'cancelled': []  # Stato finale
}


def validate_state_transition(from_state: str, to_state: str) -> Tuple[bool, Optional[str]]:
    """
    Valida se una transizione di stato è permessa

    Args:
        from_state: stato attuale
        to_state: stato target

    Returns:
        (is_valid, error_message)
    """
    if to_state not in VALID_STATES:
        return False, f"Invalid target state: {to_state}"

    allowed_transitions = STATE_TRANSITIONS.get(from_state, [])
    if to_state not in allowed_transitions:
        return False, f"Transition from '{from_state}' to '{to_state}' not allowed"

    return True, None


def change_project_state(
    project_id: int,
    new_state: str,
    user_id: str,
    reason: Optional[str] = None
) -> Tuple[bool, Optional[str], Optional[Project]]:
    """
    Cambia stato di un progetto (con validazione workflow)

    Args:
        project_id: ID progetto
        new_state: nuovo stato
        user_id: ID utente che esegue il cambio
        reason: motivazione (opzionale)

    Returns:
        (success, error_message, project)
    """
    db: Session = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return False, "Project not found", None

        # Valida transizione
        is_valid, error = validate_state_transition(project.state, new_state)
        if not is_valid:
            return False, error, None

        old_state = project.state
        project.state = new_state
        project.updated_at = datetime.utcnow()

        # Gestione campi specifici per stato
        if new_state == 'cancelled':
            project.cancelled_at = datetime.utcnow()
            project.cancelled_by = user_id
            if reason:
                project.cancellation_reason = reason

        db.commit()
        db.refresh(project)

        # Log audit
        log_audit(
            user_id=user_id,
            user_email=None,  # TODO: fetch from user_id
            association_id=project.association_id,
            action='project_state_changed',
            entity_type='project',
            entity_id=str(project.id),
            old_value=old_state,
            new_value=new_state,
            description=f"Project {project.project_code} state changed from {old_state} to {new_state}" +
                       (f" - Reason: {reason}" if reason else "")
        )

        return True, None, project

    except Exception as e:
        db.rollback()
        return False, str(e), None
    finally:
        db.close()


def assign_project(
    project_id: int,
    analyst_user_id: str,
    assigned_by_user_id: str
) -> Tuple[bool, Optional[str], Optional[Project]]:
    """
    Assegna progetto ad analyst

    Args:
        project_id: ID progetto
        analyst_user_id: ID analyst da assegnare
        assigned_by_user_id: ID utente che esegue l'assegnazione

    Returns:
        (success, error_message, project)
    """
    db: Session = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return False, "Project not found", None

        # Verifica che progetto sia in stato 'available'
        if project.state != 'available':
            return False, f"Project must be in 'available' state (current: {project.state})", None

        # Verifica che analyst esista
        analyst = db.query(User).filter(User.id == analyst_user_id).first()
        if not analyst:
            return False, "Analyst user not found", None

        # Verifica che analyst appartenga alla stessa associazione
        if analyst.association_id != project.association_id:
            return False, "Analyst must belong to the same association as project", None

        # Assegna
        old_assigned = project.assigned_to
        project.assigned_to = analyst_user_id
        project.assigned_at = datetime.utcnow()
        project.state = 'assigned'
        project.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(project)

        # Log audit
        log_audit(
            user_id=assigned_by_user_id,
            user_email=None,
            association_id=project.association_id,
            action='project_assigned',
            entity_type='project',
            entity_id=str(project.id),
            old_value=old_assigned,
            new_value=analyst_user_id,
            description=f"Project {project.project_code} assigned to {analyst.full_name}"
        )

        # Notifica Slack (best-effort, non blocca il successo)
        try:
            assigned_by = db.query(User).filter(User.id == assigned_by_user_id).first()
            slack_service = get_slack_service()
            slack_service.notify_project_assigned(db, project, analyst, assigned_by)
        except Exception as slack_error:
            logger.warning(f"Notifica Slack assegnazione fallita per {project.project_code}: {slack_error}")

        return True, None, project

    except Exception as e:
        db.rollback()
        return False, str(e), None
    finally:
        db.close()


def reassign_project(
    project_id: int,
    new_analyst_user_id: str,
    reassigned_by_user_id: str,
    reason: Optional[str] = None
) -> Tuple[bool, Optional[str], Optional[Project]]:
    """
    Riassegna progetto ad altro analyst

    Args:
        project_id: ID progetto
        new_analyst_user_id: ID nuovo analyst
        reassigned_by_user_id: ID utente che esegue riassegnazione
        reason: motivazione (opzionale)

    Returns:
        (success, error_message, project)
    """
    db: Session = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return False, "Project not found", None

        # Verifica stato
        if project.state not in ['assigned', 'in_review']:
            return False, f"Project must be in 'assigned' or 'in_review' state (current: {project.state})", None

        # Verifica nuovo analyst
        new_analyst = db.query(User).filter(User.id == new_analyst_user_id).first()
        if not new_analyst:
            return False, "New analyst user not found", None

        if new_analyst.association_id != project.association_id:
            return False, "New analyst must belong to the same association", None

        # Riassegna
        old_analyst_id = project.assigned_to
        project.assigned_to = new_analyst_user_id
        project.assigned_at = datetime.utcnow()
        project.state = 'assigned'  # Ritorna a assigned anche se era in_review
        project.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(project)

        # Log audit
        log_audit(
            user_id=reassigned_by_user_id,
            user_email=None,
            association_id=project.association_id,
            action='project_reassigned',
            entity_type='project',
            entity_id=str(project.id),
            old_value=old_analyst_id,
            new_value=new_analyst_user_id,
            description=f"Project {project.project_code} reassigned to {new_analyst.full_name}" +
                       (f" - Reason: {reason}" if reason else "")
        )

        # Notifica Slack riassegnazione (best-effort)
        try:
            reassigned_by = db.query(User).filter(User.id == reassigned_by_user_id).first()
            slack_service = get_slack_service()
            slack_service.notify_project_assigned(db, project, new_analyst, reassigned_by, is_reassignment=True)
        except Exception as slack_error:
            logger.warning(f"Notifica Slack riassegnazione fallita per {project.project_code}: {slack_error}")

        return True, None, project

    except Exception as e:
        db.rollback()
        return False, str(e), None
    finally:
        db.close()


def send_to_review(
    project_id: int,
    sent_by_user_id: str
) -> Tuple[bool, Optional[str], Optional[Project]]:
    """
    Invia progetto in review

    Args:
        project_id: ID progetto
        sent_by_user_id: ID utente che invia

    Returns:
        (success, error_message, project)
    """
    db: Session = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return False, "Project not found", None

        # Verifica stato
        if project.state != 'assigned':
            return False, f"Project must be in 'assigned' state (current: {project.state})", None

        # Cambia stato
        project.state = 'in_review'
        project.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(project)

        # Log audit
        log_audit(
            user_id=sent_by_user_id,
            user_email=None,
            association_id=project.association_id,
            action='project_sent_to_review',
            entity_type='project',
            entity_id=str(project.id),
            old_value='assigned',
            new_value='in_review',
            description=f"Project {project.project_code} sent to review"
        )

        return True, None, project

    except Exception as e:
        db.rollback()
        return False, str(e), None
    finally:
        db.close()


def cancel_project(
    project_id: int,
    cancelled_by_user_id: str,
    reason: str
) -> Tuple[bool, Optional[str], Optional[Project]]:
    """
    Cancella progetto

    Args:
        project_id: ID progetto
        cancelled_by_user_id: ID utente che cancella
        reason: motivazione cancellazione (obbligatoria)

    Returns:
        (success, error_message, project)
    """
    if not reason or not reason.strip():
        return False, "Cancellation reason is required", None

    return change_project_state(
        project_id=project_id,
        new_state='cancelled',
        user_id=cancelled_by_user_id,
        reason=reason
    )


def self_assign_project(
    project_id: int,
    analyst_user_id: str
) -> Tuple[bool, Optional[str], Optional[Project]]:
    """
    Auto-assegnazione progetto da parte dell'analyst stesso.

    L'analyst può assegnarsi un progetto in stato 'available'
    della propria associazione.

    Args:
        project_id: ID progetto
        analyst_user_id: ID analyst che si auto-assegna

    Returns:
        (success, error_message, project)
    """
    db: Session = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return False, "Progetto non trovato", None

        # Verifica che progetto sia in stato 'available'
        if project.state != 'available':
            return False, f"Il progetto deve essere in stato 'available' (attuale: {project.state})", None

        # Verifica che analyst esista e sia attivo
        analyst = db.query(User).filter(User.id == analyst_user_id).first()
        if not analyst:
            return False, "Utente non trovato", None

        if not analyst.is_active:
            return False, "Utente non attivo", None

        # Verifica ruolo (solo analyst, reviewer, admin possono assegnarsi)
        if analyst.role not in ['analyst', 'reviewer', 'admin']:
            return False, "Solo analyst, reviewer o admin possono auto-assegnarsi progetti", None

        # Verifica che analyst appartenga alla stessa associazione
        if analyst.association_id != project.association_id:
            return False, "L'utente deve appartenere alla stessa associazione del progetto", None

        # Auto-assegna
        project.assigned_to = analyst_user_id
        project.assigned_at = datetime.utcnow()
        project.state = 'assigned'
        project.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(project)

        # Log audit
        log_audit(
            user_id=analyst_user_id,
            user_email=analyst.email,
            association_id=project.association_id,
            action='project_self_assigned',
            entity_type='project',
            entity_id=str(project.id),
            old_value=None,
            new_value=analyst_user_id,
            description=f"Progetto {project.project_code} auto-assegnato da {analyst.full_name}"
        )

        # Notifica Slack (best-effort, non blocca il successo)
        try:
            slack_service = get_slack_service()
            slack_service.notify_project_assigned(db, project, analyst, analyst, is_self_assignment=True)
        except Exception as slack_error:
            logger.warning(f"Notifica Slack auto-assegnazione fallita per {project.project_code}: {slack_error}")

        return True, None, project

    except Exception as e:
        db.rollback()
        return False, str(e), None
    finally:
        db.close()

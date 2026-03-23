# agata/admin/services/stats_service.py
"""
Stats Service

Calcolo statistiche e metriche per dashboard amministrativa:
- Conteggi progetti per stato
- Progetti per associazione
- Backlog review
- Progetti bloccati
- Errori integrazione
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy import func, and_, or_
from sqlalchemy.orm import Session

from agata.auth_models import Project, Association, User, AuditLog, ProjectSlackThread
from agata.db import SessionLocal


def get_dashboard_stats(association_id: Optional[int] = None) -> Dict:
    """
    Statistiche principali per dashboard overview

    Args:
        association_id: Se specificato, filtra per associazione (per admin)
                       Se None, statistiche globali (per superuser)

    Returns:
        Dict con statistiche chiave
    """
    db: Session = SessionLocal()
    try:
        # Base query
        query = db.query(Project)
        if association_id:
            query = query.filter(Project.association_id == association_id)

        # Conteggio per stato
        projects_by_state = {}
        for state in ['incoming', 'available', 'assigned', 'in_review', 'submitted_aavso',
                     'accepted_aavso', 'rejected_aavso', 'cancelled']:
            count = query.filter(Project.state == state).count()
            projects_by_state[state] = count

        # Progetti attivi (escludendo completed/cancelled)
        active_projects = query.filter(
            Project.state.in_(['incoming', 'available', 'assigned', 'in_review', 'submitted_aavso'])
        ).count()

        # Progetti in review (backlog)
        in_review_count = projects_by_state.get('in_review', 0)

        # Progetti bloccati (assigned da > 7 giorni)
        blocked_threshold = datetime.utcnow() - timedelta(days=7)
        blocked_projects = query.filter(
            and_(
                Project.state == 'assigned',
                Project.assigned_at < blocked_threshold
            )
        ).count()

        # Ultimi progetti creati
        recent_projects = query.order_by(Project.created_at.desc()).limit(5).all()

        # === OPTIMIZATION: Aggregate project counts per association in single query ===
        projects_by_association = []
        if not association_id:
            from sqlalchemy import func

            associations = db.query(Association).filter(Association.is_active == True).all()

            # Single aggregation query instead of N separate count() calls
            assoc_project_counts = db.query(
                Project.association_id,
                func.count(Project.id).label('count')
            ).filter(
                Project.state.in_(['incoming', 'available', 'assigned', 'in_review'])
            ).group_by(Project.association_id).all()

            # Build lookup map for O(1) access
            counts_map = {apc.association_id: apc.count for apc in assoc_project_counts}

            # Populate results from cache (no queries!)
            for assoc in associations:
                projects_by_association.append({
                    'id': assoc.id,
                    'name': assoc.name,
                    'slug': assoc.slug,
                    'active_projects': counts_map.get(assoc.id, 0)
                })

        return {
            'projects_by_state': projects_by_state,
            'active_projects': active_projects,
            'in_review_count': in_review_count,
            'blocked_projects': blocked_projects,
            'recent_projects': [
                {
                    'id': p.id,
                    'project_code': p.project_code,
                    'gaia_id': p.gaia_id,
                    'state': p.state,
                    'created_at': p.created_at.isoformat() if p.created_at else None
                }
                for p in recent_projects
            ],
            'projects_by_association': projects_by_association
        }
    finally:
        db.close()


def get_blocked_projects(days_threshold: int = 7, association_id: Optional[int] = None) -> List[Dict]:
    """
    Ottieni progetti bloccati in stato 'assigned' da troppo tempo

    Args:
        days_threshold: numero giorni di inattività per considerare bloccato
        association_id: filtra per associazione

    Returns:
        Lista progetti bloccati con dettagli
    """
    db: Session = SessionLocal()
    try:
        threshold_date = datetime.utcnow() - timedelta(days=days_threshold)

        query = db.query(Project).filter(
            and_(
                Project.state == 'assigned',
                Project.assigned_at < threshold_date
            )
        )

        if association_id:
            query = query.filter(Project.association_id == association_id)

        projects = query.all()

        result = []
        for p in projects:
            days_assigned = (datetime.utcnow() - p.assigned_at).days if p.assigned_at else 0
            result.append({
                'id': p.id,
                'project_code': p.project_code,
                'gaia_id': p.gaia_id,
                'association_id': p.association_id,
                'association_name': p.association.name if p.association else None,
                'assigned_to': p.assigned_to,
                'assigned_user_name': p.assigned_user.full_name if p.assigned_user else None,
                'assigned_at': p.assigned_at.isoformat() if p.assigned_at else None,
                'days_assigned': days_assigned
            })

        return result
    finally:
        db.close()


def get_review_backlog(association_id: Optional[int] = None) -> List[Dict]:
    """
    Ottieni progetti in attesa di review

    Args:
        association_id: filtra per associazione

    Returns:
        Lista progetti in_review
    """
    db: Session = SessionLocal()
    try:
        query = db.query(Project).filter(Project.state == 'in_review')

        if association_id:
            query = query.filter(Project.association_id == association_id)

        projects = query.order_by(Project.updated_at.asc()).all()

        result = []
        for p in projects:
            result.append({
                'id': p.id,
                'project_code': p.project_code,
                'gaia_id': p.gaia_id,
                'association_id': p.association_id,
                'association_name': p.association.name if p.association else None,
                'assigned_to': p.assigned_to,
                'assigned_user_name': p.assigned_user.full_name if p.assigned_user else None,
                'updated_at': p.updated_at.isoformat() if p.updated_at else None
            })

        return result
    finally:
        db.close()


def get_association_stats(association_id: int) -> Dict:
    """
    Statistiche dettagliate per una singola associazione

    Args:
        association_id: ID associazione

    Returns:
        Dict con statistiche associazione
    """
    db: Session = SessionLocal()
    try:
        # Associazione
        association = db.query(Association).filter(Association.id == association_id).first()
        if not association:
            return {}

        # Progetti
        total_projects = db.query(Project).filter(Project.association_id == association_id).count()
        active_projects = db.query(Project).filter(
            and_(
                Project.association_id == association_id,
                Project.state.in_(['incoming', 'available', 'assigned', 'in_review'])
            )
        ).count()

        # Utenti
        total_users = db.query(User).filter(
            and_(
                User.association_id == association_id,
                User.is_active == True
            )
        ).count()

        # Canali Slack
        from agata.auth_models import SlackChannel
        slack_channels = db.query(SlackChannel).filter(
            SlackChannel.association_id == association_id
        ).all()

        return {
            'association': {
                'id': association.id,
                'name': association.name,
                'slug': association.slug,
                'type': association.type,
                'is_active': association.is_active
            },
            'total_projects': total_projects,
            'active_projects': active_projects,
            'total_users': total_users,
            'slack_channels': [
                {
                    'id': ch.id,
                    'name': ch.channel_name,
                    'type': ch.channel_type,
                    'channel_id': ch.channel_id
                }
                for ch in slack_channels
            ]
        }
    finally:
        db.close()


def get_recent_audit_events(
    limit: int = 20,
    association_id: Optional[int] = None
) -> List[Dict]:
    """
    Ultimi eventi audit log

    Args:
        limit: numero max eventi
        association_id: filtra per associazione

    Returns:
        Lista eventi recenti
    """
    db: Session = SessionLocal()
    try:
        query = db.query(AuditLog)

        if association_id:
            query = query.filter(AuditLog.association_id == association_id)

        events = query.order_by(AuditLog.created_at.desc()).limit(limit).all()

        return [
            {
                'id': e.id,
                'user_email': e.user_email,
                'action': e.action,
                'entity_type': e.entity_type,
                'entity_id': e.entity_id,
                'description': e.description,
                'created_at': e.created_at.isoformat() if e.created_at else None
            }
            for e in events
        ]
    finally:
        db.close()

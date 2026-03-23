# agata/admin/services/audit_service.py
"""
Audit Service

Gestione completa audit log:
- Registrazione azioni
- Query con filtri avanzati
- Export per compliance
"""
from datetime import datetime
from typing import Optional, List
from sqlalchemy import desc, and_, or_
from sqlalchemy.orm import Session

from agata.auth_models import AuditLog
from agata.db import SessionLocal


def log_audit(
    user_id: Optional[str],
    user_email: Optional[str],
    association_id: Optional[int],
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
    description: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    request_id: Optional[str] = None
) -> AuditLog:
    """
    Registra un'azione in audit log

    Args:
        user_id: ID utente che ha eseguito l'azione
        user_email: Email utente
        association_id: ID associazione (context)
        action: Tipo azione (es: 'project_assigned', 'user_created')
        entity_type: Tipo entità (es: 'project', 'user')
        entity_id: ID entità
        old_value: Valore precedente (JSON string)
        new_value: Nuovo valore (JSON string)
        description: Descrizione leggibile
        ip_address: IP richiedente
        user_agent: User agent browser
        request_id: Request ID per tracing

    Returns:
        AuditLog entry creato
    """
    db: Session = SessionLocal()
    try:
        audit = AuditLog(
            user_id=user_id,
            user_email=user_email,
            association_id=association_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_value=old_value,
            new_value=new_value,
            description=description,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            created_at=datetime.utcnow()
        )
        db.add(audit)
        db.commit()
        db.refresh(audit)
        return audit
    finally:
        db.close()


def query_audit_log(
    association_id: Optional[int] = None,
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0
) -> List[AuditLog]:
    """
    Query audit log con filtri

    Args:
        association_id: filtra per associazione
        user_id: filtra per utente
        action: filtra per tipo azione
        entity_type: filtra per tipo entità
        entity_id: filtra per ID entità
        from_date: data inizio
        to_date: data fine
        limit: numero max risultati
        offset: offset per paginazione

    Returns:
        Lista AuditLog entries
    """
    db: Session = SessionLocal()
    try:
        query = db.query(AuditLog)

        # Filtri
        if association_id is not None:
            query = query.filter(AuditLog.association_id == association_id)
        if user_id:
            query = query.filter(AuditLog.user_id == user_id)
        if action:
            query = query.filter(AuditLog.action == action)
        if entity_type:
            query = query.filter(AuditLog.entity_type == entity_type)
        if entity_id:
            query = query.filter(AuditLog.entity_id == entity_id)
        if from_date:
            query = query.filter(AuditLog.created_at >= from_date)
        if to_date:
            query = query.filter(AuditLog.created_at <= to_date)

        # Ordina per data decrescente (più recenti prima)
        query = query.order_by(desc(AuditLog.created_at))

        # Paginazione
        query = query.limit(limit).offset(offset)

        return query.all()
    finally:
        db.close()


def get_project_audit_trail(project_id: int) -> List[AuditLog]:
    """
    Ottieni audit trail completo di un progetto

    Include:
    - Cambio stati
    - Assegnazioni
    - Review
    - Invii Slack
    - Cancellazioni

    Args:
        project_id: ID progetto

    Returns:
        Lista completa audit log ordinata cronologicamente
    """
    return query_audit_log(
        entity_type='project',
        entity_id=str(project_id),
        limit=1000  # Assumiamo max 1000 eventi per progetto
    )


def get_user_activity(user_id: str, days: int = 30) -> List[AuditLog]:
    """
    Ottieni attività di un utente negli ultimi N giorni

    Args:
        user_id: ID utente
        days: numero giorni passati

    Returns:
        Lista audit log utente
    """
    from datetime import timedelta
    from_date = datetime.utcnow() - timedelta(days=days)

    return query_audit_log(
        user_id=user_id,
        from_date=from_date,
        limit=500
    )


def count_audit_entries(
    association_id: Optional[int] = None,
    action: Optional[str] = None,
    from_date: Optional[datetime] = None
) -> int:
    """
    Conta entries audit log con filtri

    Args:
        association_id: filtra per associazione
        action: filtra per azione
        from_date: data inizio

    Returns:
        Numero entries
    """
    db: Session = SessionLocal()
    try:
        query = db.query(AuditLog)

        if association_id is not None:
            query = query.filter(AuditLog.association_id == association_id)
        if action:
            query = query.filter(AuditLog.action == action)
        if from_date:
            query = query.filter(AuditLog.created_at >= from_date)

        return query.count()
    finally:
        db.close()

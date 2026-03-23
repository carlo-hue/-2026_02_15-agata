# agata/admin/routes/audit.py
"""
Audit Log Viewer Routes

Visualizzazione audit log:
- Query con filtri avanzati
- Export per compliance
- Timeline eventi
"""
from flask import render_template, jsonify, request
from flask_login import login_required, current_user
from datetime import datetime, timedelta

from agata.admin import admin_bp
from agata.admin.decorators import admin_required
from agata.admin.services.audit_service import query_audit_log, count_audit_entries


@admin_bp.route('/audit')
@login_required
@admin_required('admin')
def audit_log():
    """
    Visualizzatore audit log con filtri

    Query params:
    - action: filtra per tipo azione
    - entity_type: filtra per tipo entità
    - user_id: filtra per utente
    - from_date: data inizio (ISO format)
    - to_date: data fine (ISO format)
    - page: paginazione
    """
    # Filtri
    action = request.args.get('action')
    entity_type = request.args.get('entity_type')
    user_id = request.args.get('user_id')

    # Date parsing
    from_date = None
    to_date = None
    if request.args.get('from_date'):
        try:
            from_date = datetime.fromisoformat(request.args.get('from_date'))
        except:
            pass
    if request.args.get('to_date'):
        try:
            to_date = datetime.fromisoformat(request.args.get('to_date'))
        except:
            pass

    # Default: ultimi 7 giorni
    if not from_date:
        from_date = datetime.utcnow() - timedelta(days=7)

    # Scope per associazione
    association_id = None if current_user.role == 'superuser' else current_user.association_id

    # Paginazione
    page = request.args.get('page', 1, type=int)
    per_page = 100

    # Query
    entries = query_audit_log(
        association_id=association_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        from_date=from_date,
        to_date=to_date,
        limit=per_page,
        offset=(page - 1) * per_page
    )

    # Count totale
    total = count_audit_entries(
        association_id=association_id,
        action=action,
        from_date=from_date
    )

    return render_template(
        'admin/audit/log.html',
        entries=entries,
        total=total,
        page=page,
        per_page=per_page,
        filters={
            'action': action,
            'entity_type': entity_type,
            'user_id': user_id,
            'from_date': from_date.isoformat() if from_date else None,
            'to_date': to_date.isoformat() if to_date else None
        }
    )


@admin_bp.route('/api/audit')
@login_required
@admin_required('admin')
def api_audit_log():
    """
    API: query audit log (JSON)
    """
    # Filtri
    action = request.args.get('action')
    entity_type = request.args.get('entity_type')
    user_id = request.args.get('user_id')

    # Date
    from_date = None
    to_date = None
    if request.args.get('from_date'):
        try:
            from_date = datetime.fromisoformat(request.args.get('from_date'))
        except:
            pass
    if request.args.get('to_date'):
        try:
            to_date = datetime.fromisoformat(request.args.get('to_date'))
        except:
            pass

    # Scope
    association_id = None if current_user.role == 'superuser' else current_user.association_id

    # Limit
    limit = request.args.get('limit', 100, type=int)
    if limit > 1000:
        limit = 1000

    # Query
    entries = query_audit_log(
        association_id=association_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        from_date=from_date,
        to_date=to_date,
        limit=limit
    )

    return jsonify([
        {
            'id': e.id,
            'user_email': e.user_email,
            'association_id': e.association_id,
            'action': e.action,
            'entity_type': e.entity_type,
            'entity_id': e.entity_id,
            'old_value': e.old_value,
            'new_value': e.new_value,
            'description': e.description,
            'ip_address': e.ip_address,
            'created_at': e.created_at.isoformat() if e.created_at else None
        }
        for e in entries
    ])

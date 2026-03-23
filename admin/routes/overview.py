# agata/admin/routes/overview.py
"""
Admin Overview Routes

Dashboard principale con:
- Statistiche progetti per stato
- Progetti attivi per associazione
- Backlog review
- Progetti bloccati
- Ultimi eventi audit
"""
from flask import render_template, jsonify, request, redirect, url_for
from flask_login import login_required, current_user

from agata.admin import admin_bp
from agata.admin.decorators import admin_required
from agata.admin.services.stats_service import (
    get_dashboard_stats,
    get_blocked_projects,
    get_review_backlog,
    get_recent_audit_events
)


@admin_bp.route('/')
@login_required
@admin_required('analyst')
def admin_index():
    """
    Entry point per l'area admin.

    Redirect intelligente in base al ruolo:
    - Admin/Superuser: va alla dashboard
    - Analyst/Reviewer: va alla lista progetti
    """
    if current_user.role in ['admin', 'superuser']:
        return redirect(url_for('admin.dashboard'))
    else:
        # Analyst e reviewer vanno direttamente ai progetti
        return redirect(url_for('admin.list_projects'))


@admin_bp.route('/dashboard')
@login_required
@admin_required('admin')
def dashboard():
    """
    Dashboard amministrativa principale

    - Superuser: vede statistiche globali
    - Admin: vede solo la propria associazione
    """
    # Determina scope
    association_id = None if current_user.role == 'superuser' else current_user.association_id

    # Ottieni statistiche
    stats = get_dashboard_stats(association_id=association_id)
    blocked = get_blocked_projects(days_threshold=7, association_id=association_id)
    review_backlog = get_review_backlog(association_id=association_id)
    recent_events = get_recent_audit_events(limit=10, association_id=association_id)

    return render_template(
        'admin/dashboard.html',
        stats=stats,
        blocked_projects=blocked,
        review_backlog=review_backlog,
        recent_events=recent_events,
        is_superuser=current_user.role == 'superuser'
    )


@admin_bp.route('/api/stats')
@login_required
@admin_required('admin')
def api_stats():
    """
    API: statistiche dashboard (JSON)
    """
    association_id = None if current_user.role == 'superuser' else current_user.association_id
    stats = get_dashboard_stats(association_id=association_id)
    return jsonify(stats)


@admin_bp.route('/api/blocked-projects')
@login_required
@admin_required('admin')
def api_blocked_projects():
    """
    API: progetti bloccati (JSON)
    """
    days_threshold = request.args.get('days', 7, type=int)
    association_id = None if current_user.role == 'superuser' else current_user.association_id

    blocked = get_blocked_projects(days_threshold=days_threshold, association_id=association_id)
    return jsonify(blocked)


@admin_bp.route('/api/review-backlog')
@login_required
@admin_required('admin')
def api_review_backlog():
    """
    API: backlog review (JSON)
    """
    association_id = None if current_user.role == 'superuser' else current_user.association_id
    backlog = get_review_backlog(association_id=association_id)
    return jsonify(backlog)

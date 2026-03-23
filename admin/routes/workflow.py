# agata/admin/routes/workflow.py
"""
Workflow Management Routes

Vista globale stati workflow:
- Matrice stato × associazione
- Individua colli di bottiglia
- Backlog review per associazione
- Progetti dormienti
"""
from flask import render_template, jsonify
from flask_login import login_required, current_user
from sqlalchemy.orm import Session
from sqlalchemy import func

from agata.admin import admin_bp
from agata.admin.decorators import admin_required
from agata.auth_models import Project, Association
from agata.db import SessionLocal


@admin_bp.route('/workflow')
@login_required
@admin_required('admin')
def workflow_overview():
    """
    Vista workflow globale: matrice stato × associazione
    """
    db: Session = SessionLocal()
    try:
        # Query base
        query = db.query(
            Project.state,
            Project.association_id,
            func.count(Project.id).label('count')
        )

        # Scope per non-superuser
        if current_user.role != 'superuser':
            query = query.filter(Project.association_id == current_user.association_id)

        # Group by stato e associazione
        results = query.group_by(Project.state, Project.association_id).all()

        # Organizza dati in matrice
        associations = db.query(Association).filter(Association.is_active == True).order_by(Association.name).all()
        if current_user.role != 'superuser':
            associations = [a for a in associations if a.id == current_user.association_id]

        states = ['incoming', 'available', 'assigned', 'in_review', 'submitted_aavso',
                 'accepted_aavso', 'rejected_aavso', 'cancelled']

        # Matrice: association_id -> state -> count
        matrix = {}
        for assoc in associations:
            matrix[assoc.id] = {state: 0 for state in states}

        for state, assoc_id, count in results:
            if assoc_id in matrix:
                matrix[assoc_id][state] = count

        return render_template(
            'admin/workflow/overview.html',
            associations=associations,
            states=states,
            matrix=matrix
        )

    finally:
        db.close()


@admin_bp.route('/api/workflow/stats')
@login_required
@admin_required('admin')
def api_workflow_stats():
    """
    API: statistiche workflow (JSON)
    """
    db: Session = SessionLocal()
    try:
        query = db.query(
            Project.state,
            Project.association_id,
            func.count(Project.id).label('count')
        )

        if current_user.role != 'superuser':
            query = query.filter(Project.association_id == current_user.association_id)

        results = query.group_by(Project.state, Project.association_id).all()

        # Formato: [{state, association_id, count}]
        return jsonify([
            {
                'state': r[0],
                'association_id': r[1],
                'count': r[2]
            }
            for r in results
        ])

    finally:
        db.close()

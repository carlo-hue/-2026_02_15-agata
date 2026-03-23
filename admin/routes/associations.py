# agata/admin/routes/associations.py
"""
Association Management Routes

Gestione associazioni:
- Lista associazioni
- Dettaglio associazione
- Creazione/modifica (solo superuser)
- Configurazione Slack
- Statistiche associazione
"""
from flask import render_template, jsonify, request, abort
from flask_login import login_required, current_user
from sqlalchemy.orm import Session

from agata.admin import admin_bp
from agata.admin.decorators import admin_required, superuser_required, can_manage_association
from agata.admin.services.stats_service import get_association_stats
from agata.admin.services.audit_service import log_audit
from agata.admin.services.slack_service import get_slack_service
from agata.auth_models import Association, SlackChannel, Project, User
from agata.db import SessionLocal


@admin_bp.route('/associations')
@login_required
@admin_required('admin')
def list_associations():
    """
    Lista associazioni

    - Superuser: vede tutte
    - Admin: vede solo la propria
    """
    db: Session = SessionLocal()
    try:
        query = db.query(Association)

        # Filtro per admin non-superuser
        if current_user.role != 'superuser':
            query = query.filter(Association.id == current_user.association_id)

        associations = query.order_by(Association.name).all()

        # === OPTIMIZATION: Aggregate all counts in batch queries instead of N×3 count() calls ===
        from sqlalchemy import func

        assoc_ids = [a.id for a in associations]

        # Batch query 1: Aggregate active projects per association
        project_counts = db.query(
            Project.association_id,
            func.count(Project.id).label('count')
        ).filter(
            Project.association_id.in_(assoc_ids),
            Project.state.in_(['incoming', 'available', 'assigned', 'in_review'])
        ).group_by(Project.association_id).all()
        project_counts_map = {pc.association_id: pc.count for pc in project_counts}

        # Batch query 2: Aggregate users per association
        user_counts = db.query(
            User.association_id,
            func.count(User.id).label('count')
        ).filter(
            User.association_id.in_(assoc_ids),
            User.is_active == True
        ).group_by(User.association_id).all()
        user_counts_map = {uc.association_id: uc.count for uc in user_counts}

        # Batch query 3: Aggregate slack channels per association
        slack_counts = db.query(
            SlackChannel.association_id,
            func.count(SlackChannel.id).label('count')
        ).filter(
            SlackChannel.association_id.in_(assoc_ids),
            SlackChannel.is_active == True
        ).group_by(SlackChannel.association_id).all()
        slack_counts_map = {sc.association_id: sc.count for sc in slack_counts}

        # Arricchisci con dati da cache (no queries!)
        result = []
        for assoc in associations:
            result.append({
                'id': assoc.id,
                'name': assoc.name,
                'slug': assoc.slug,
                'type': assoc.type,
                'is_active': assoc.is_active,
                'active_projects': project_counts_map.get(assoc.id, 0),
                'total_users': user_counts_map.get(assoc.id, 0),
                'slack_channels': slack_counts_map.get(assoc.id, 0),
                'slack_enabled': getattr(assoc, 'slack_enabled', True),
                'referente_name': assoc.referente_name,
                'referente_email': assoc.referente_email
            })

        return render_template('admin/associations/list.html', associations=result)

    finally:
        db.close()


@admin_bp.route('/associations/<int:association_id>')
@login_required
@admin_required('admin')
def association_detail(association_id):
    """
    Dettaglio associazione

    Mostra:
    - Dati base
    - Configurazione Slack
    - Canali attivi
    - Statistiche
    - Utenti
    """
    # Verifica permessi
    if not can_manage_association(association_id) and current_user.role != 'superuser':
        if current_user.association_id != association_id:
            abort(403, "Access denied to this association")

    db: Session = SessionLocal()
    try:
        association = db.query(Association).filter(Association.id == association_id).first()
        if not association:
            abort(404, "Association not found")

        # Statistiche
        stats = get_association_stats(association_id)

        # Canali Slack
        slack_channels = db.query(SlackChannel).filter(
            SlackChannel.association_id == association_id
        ).all()

        # Utenti
        users = db.query(User).filter(
            User.association_id == association_id,
            User.is_active == True
        ).order_by(User.name).all()

        return render_template(
            'admin/associations/detail.html',
            association=association,
            stats=stats,
            slack_channels=slack_channels,
            users=users,
            can_edit=can_manage_association(association_id) or current_user.role == 'superuser'
        )

    finally:
        db.close()


@admin_bp.route('/api/associations', methods=['GET'])
@login_required
@admin_required('admin')
def api_list_associations():
    """
    API: lista associazioni (JSON)
    """
    db: Session = SessionLocal()
    try:
        query = db.query(Association)

        if current_user.role != 'superuser':
            query = query.filter(Association.id == current_user.association_id)

        associations = query.order_by(Association.name).all()

        return jsonify([
            {
                'id': a.id,
                'name': a.name,
                'slug': a.slug,
                'type': a.type,
                'is_active': a.is_active,
                'slack_namespace': a.slack_namespace,
                'referente_name': a.referente_name,
                'referente_email': a.referente_email,
                'created_at': a.created_at.isoformat() if a.created_at else None
            }
            for a in associations
        ])

    finally:
        db.close()


@admin_bp.route('/api/associations/<int:association_id>', methods=['GET'])
@login_required
@admin_required('admin')
def api_association_detail(association_id):
    """
    API: dettaglio associazione (JSON)
    """
    # Check permissions
    if current_user.role != 'superuser' and current_user.association_id != association_id:
        return jsonify({"error": "Access denied"}), 403

    stats = get_association_stats(association_id)
    return jsonify(stats)


@admin_bp.route('/api/associations', methods=['POST'])
@login_required
@superuser_required
def api_create_association():
    """
    API: crea nuova associazione (solo superuser)

    Supporta creazione automatica canali Slack con parametro:
    - create_slack_channels: bool (default: False)
    """
    data = request.json
    if not data:
        return jsonify({"error": "Invalid request"}), 400

    # Validazioni
    required_fields = ['name', 'slug', 'type']
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    db: Session = SessionLocal()
    try:
        # Check slug univoco
        existing = db.query(Association).filter(Association.slug == data['slug']).first()
        if existing:
            return jsonify({"error": f"Slug '{data['slug']}' already exists"}), 400

        # Crea associazione
        association = Association(
            name=data['name'],
            slug=data['slug'],
            type=data['type'],
            is_active=data.get('is_active', True),
            referente_name=data.get('referente_name'),
            referente_email=data.get('referente_email'),
            slack_namespace=data.get('slack_namespace', data['slug'])
        )

        db.add(association)
        db.commit()
        db.refresh(association)

        # Log audit
        log_audit(
            user_id=current_user.id,
            user_email=current_user.email,
            association_id=None,
            action='association_created',
            entity_type='association',
            entity_id=str(association.id),
            new_value=data['name'],
            description=f"Association '{data['name']}' created"
        )

        # Crea canali Slack se richiesto
        slack_channels = []
        if data.get('create_slack_channels', False):
            try:
                slack_service = get_slack_service()
                slack_channels = slack_service.create_association_channels(
                    db=db,
                    association=association,
                    user_id=current_user.id,
                    user_email=current_user.email
                )
            except Exception as e:
                # Non fallire se la creazione canali Slack fallisce
                # Log l'errore ma continua
                log_audit(
                    user_id=current_user.id,
                    user_email=current_user.email,
                    association_id=association.id,
                    action='slack_channels_creation_failed',
                    entity_type='association',
                    entity_id=str(association.id),
                    description=f"Failed to create Slack channels: {str(e)}"
                )

        return jsonify({
            'id': association.id,
            'name': association.name,
            'slug': association.slug,
            'type': association.type,
            'slack_channels_created': len(slack_channels),
            'slack_channels': [
                {
                    'id': ch.id,
                    'channel_name': ch.channel_name,
                    'channel_type': ch.channel_type,
                    'channel_id': ch.channel_id
                }
                for ch in slack_channels
            ]
        }), 201

    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@admin_bp.route('/api/associations/<int:association_id>', methods=['PATCH'])
@login_required
@admin_required('admin')
def api_update_association(association_id):
    """
    API: aggiorna associazione

    Superuser: può modificare tutto
    Admin: può modificare solo referente e settings della propria associazione
    """
    # Check permissions
    if not can_manage_association(association_id):
        return jsonify({"error": "Access denied"}), 403

    data = request.json
    if not data:
        return jsonify({"error": "Invalid request"}), 400

    db: Session = SessionLocal()
    try:
        association = db.query(Association).filter(Association.id == association_id).first()
        if not association:
            return jsonify({"error": "Association not found"}), 404

        # Admin non-superuser può modificare solo certi campi
        if current_user.role != 'superuser':
            allowed_fields = {'referente_name', 'referente_email', 'settings'}
            for key in data.keys():
                if key not in allowed_fields:
                    return jsonify({"error": f"Field '{key}' cannot be modified by non-superuser"}), 403

        # Aggiorna campi
        updatable_fields = ['name', 'type', 'is_active', 'referente_name',
                           'referente_email', 'slack_namespace', 'settings']

        for field in updatable_fields:
            if field in data:
                setattr(association, field, data[field])

        db.commit()
        db.refresh(association)

        # Log audit
        log_audit(
            user_id=current_user.id,
            user_email=current_user.email,
            association_id=association.id,
            action='association_updated',
            entity_type='association',
            entity_id=str(association.id),
            description=f"Association '{association.name}' updated"
        )

        return jsonify({
            'id': association.id,
            'name': association.name,
            'slug': association.slug,
            'type': association.type,
            'is_active': association.is_active
        })

    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@admin_bp.route('/api/associations/<int:association_id>/slack-channels', methods=['POST'])
@login_required
@superuser_required
def api_create_slack_channels(association_id):
    """
    API: crea canali Slack per un'associazione esistente (solo superuser)

    Crea tutti e 3 i canali AGATA:
    - ag-<slug>-coord
    - ag-<slug>-lavori
    - ag-<slug>-review
    """
    db: Session = SessionLocal()
    try:
        # Verifica associazione esista
        association = db.query(Association).filter(Association.id == association_id).first()
        if not association:
            return jsonify({"error": "Association not found"}), 404

        # Verifica che non esistano già canali
        existing_channels = db.query(SlackChannel).filter(
            SlackChannel.association_id == association_id,
            SlackChannel.is_active == True
        ).count()

        if existing_channels > 0:
            return jsonify({
                "error": f"Association already has {existing_channels} Slack channels",
                "hint": "Delete existing channels first or use PATCH to update them"
            }), 400

        # Crea canali Slack
        try:
            slack_service = get_slack_service()
            slack_channels = slack_service.create_association_channels(
                db=db,
                association=association,
                user_id=current_user.id,
                user_email=current_user.email
            )

            return jsonify({
                'association_id': association.id,
                'association_name': association.name,
                'channels_created': len(slack_channels),
                'channels': [
                    {
                        'id': ch.id,
                        'channel_name': ch.channel_name,
                        'channel_type': ch.channel_type,
                        'channel_id': ch.channel_id
                    }
                    for ch in slack_channels
                ]
            }), 201

        except Exception as e:
            db.rollback()
            return jsonify({
                "error": "Failed to create Slack channels",
                "details": str(e)
            }), 500

    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@admin_bp.route('/api/associations/<int:association_id>/slack-toggle', methods=['POST'])
@login_required
@superuser_required
def api_toggle_slack(association_id):
    """
    API: abilita/disabilita integrazione Slack per un'associazione (solo superuser)

    Quando disabilitato:
    - Non vengono creati nuovi canali Slack
    - Non vengono creati thread per i progetti
    - Non vengono inviate notifiche Slack

    Body JSON:
    - slack_enabled: bool (required)
    """
    data = request.json
    if not data or 'slack_enabled' not in data:
        return jsonify({"error": "Missing required field: slack_enabled"}), 400

    slack_enabled = bool(data['slack_enabled'])

    db: Session = SessionLocal()
    try:
        association = db.query(Association).filter(Association.id == association_id).first()
        if not association:
            return jsonify({"error": "Association not found"}), 404

        old_value = association.slack_enabled
        association.slack_enabled = slack_enabled
        db.commit()

        # Log audit
        action_desc = "abilitata" if slack_enabled else "disabilitata"
        log_audit(
            user_id=current_user.id,
            user_email=current_user.email,
            association_id=association.id,
            action='slack_integration_toggled',
            entity_type='association',
            entity_id=str(association.id),
            old_value=str(old_value),
            new_value=str(slack_enabled),
            description=f"Integrazione Slack {action_desc} per '{association.name}'"
        )

        return jsonify({
            'success': True,
            'association_id': association.id,
            'association_name': association.name,
            'slack_enabled': slack_enabled,
            'message': f"Integrazione Slack {action_desc}"
        })

    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@admin_bp.route('/api/associations/<int:association_id>', methods=['DELETE'])
@login_required
@superuser_required
def api_delete_association(association_id):
    """
    API: elimina associazione (solo superuser)

    Elimina anche:
    - Canali Slack associati (solo dal DB, non da Slack)
    - Progetti associati
    - Utenti associati
    """
    db: Session = SessionLocal()
    try:
        association = db.query(Association).filter(Association.id == association_id).first()
        if not association:
            return jsonify({"error": "Association not found"}), 404

        assoc_name = association.name
        assoc_slug = association.slug

        # Conta elementi da eliminare
        slack_channels_count = db.query(SlackChannel).filter(
            SlackChannel.association_id == association_id
        ).count()

        projects_count = db.query(Project).filter(
            Project.association_id == association_id
        ).count()

        users_count = db.query(User).filter(
            User.association_id == association_id
        ).count()

        # Log audit prima di eliminare
        log_audit(
            user_id=current_user.id,
            user_email=current_user.email,
            association_id=association_id,
            action='association_deleted',
            entity_type='association',
            entity_id=str(association_id),
            old_value=assoc_name,
            description=f"Association '{assoc_name}' deleted (channels: {slack_channels_count}, projects: {projects_count}, users: {users_count})"
        )

        # Elimina esplicitamente le dipendenze prima dell'associazione
        # (il CASCADE nel DB potrebbe non funzionare correttamente)

        # 1. Elimina canali Slack
        db.query(SlackChannel).filter(
            SlackChannel.association_id == association_id
        ).delete(synchronize_session=False)

        # 2. Elimina progetti
        db.query(Project).filter(
            Project.association_id == association_id
        ).delete(synchronize_session=False)

        # 3. Elimina utenti
        db.query(User).filter(
            User.association_id == association_id
        ).delete(synchronize_session=False)

        # 4. Elimina associazione
        db.delete(association)
        db.commit()

        return jsonify({
            'success': True,
            'deleted': {
                'association_id': association_id,
                'association_name': assoc_name,
                'association_slug': assoc_slug,
                'slack_channels': slack_channels_count,
                'projects': projects_count,
                'users': users_count
            },
            'note': 'Canali Slack rimangono su Slack, eliminali manualmente se necessario'
        }), 200

    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()

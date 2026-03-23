# agata/admin/routes/config.py
"""
System Configuration Routes

Gestione policy e configurazioni di sistema:
- Timeout stati workflow
- Soglie promozione canale
- Ruoli minimi richiesti
- Notifiche automatiche

Queste sono regole di sistema, non codice hardcoded.
Solo superuser può modificarle.
"""
from flask import render_template, jsonify, request
from flask_login import login_required

from agata.admin import admin_bp
from agata.admin.decorators import superuser_required
from agata.admin.services.audit_service import log_audit
from agata.auth_models import SystemConfig
from agata.db import SessionLocal
from sqlalchemy.orm import Session


@admin_bp.route('/config')
@login_required
@superuser_required
def system_config():
    """
    Visualizza configurazioni di sistema

    Solo superuser
    """
    db: Session = SessionLocal()
    try:
        configs = db.query(SystemConfig).order_by(SystemConfig.config_key).all()

        # Group by category (se implementato)
        configs_dict = {c.config_key: c for c in configs}

        return render_template(
            'admin/config/system.html',
            configs=configs_dict
        )

    finally:
        db.close()


@admin_bp.route('/api/config', methods=['GET'])
@login_required
@superuser_required
def api_get_config():
    """
    API: ottieni tutte le configurazioni (JSON)
    """
    db: Session = SessionLocal()
    try:
        configs = db.query(SystemConfig).all()

        return jsonify([
            {
                'key': c.config_key,
                'value': c.config_value,
                'description': c.description,
                'updated_at': c.updated_at.isoformat() if c.updated_at else None
            }
            for c in configs
        ])

    finally:
        db.close()


@admin_bp.route('/api/config/<string:key>', methods=['GET'])
@login_required
@superuser_required
def api_get_config_key(key):
    """
    API: ottieni configurazione specifica
    """
    db: Session = SessionLocal()
    try:
        config = db.query(SystemConfig).filter(SystemConfig.config_key == key).first()
        if not config:
            return jsonify({"error": "Config key not found"}), 404

        return jsonify({
            'key': config.config_key,
            'value': config.config_value,
            'description': config.description
        })

    finally:
        db.close()


@admin_bp.route('/api/config/<string:key>', methods=['PUT'])
@login_required
@superuser_required
def api_update_config(key):
    """
    API: aggiorna configurazione

    Body: {"value": "new_value"}
    """
    from flask_login import current_user
    from datetime import datetime

    data = request.json
    if not data or 'value' not in data:
        return jsonify({"error": "Missing value"}), 400

    db: Session = SessionLocal()
    try:
        config = db.query(SystemConfig).filter(SystemConfig.config_key == key).first()

        if not config:
            # Crea nuova config
            config = SystemConfig(
                config_key=key,
                config_value=data['value'],
                description=data.get('description', ''),
                updated_at=datetime.utcnow()
            )
            db.add(config)
            action = 'config_created'
            old_value = None
        else:
            # Aggiorna esistente
            old_value = config.config_value
            config.config_value = data['value']
            config.updated_at = datetime.utcnow()
            action = 'config_updated'

        db.commit()
        db.refresh(config)

        # Log audit
        log_audit(
            user_id=current_user.id,
            user_email=current_user.email,
            association_id=None,
            action=action,
            entity_type='system_config',
            entity_id=key,
            old_value=old_value,
            new_value=data['value'],
            description=f"System config '{key}' {action.split('_')[1]}"
        )

        return jsonify({
            'success': True,
            'key': config.config_key,
            'value': config.config_value
        })

    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()

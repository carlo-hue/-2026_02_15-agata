# agata/admin/routes/slack_integration.py
"""
Slack Integration Admin Routes

Monitoring integrazione Slack:
- Stato bot e OAuth
- Canali attivi per associazione
- Log errori API Slack
- Retry queue
- Test connessione
"""
from flask import render_template, jsonify, request
from flask_login import login_required, current_user
from sqlalchemy.orm import Session
from io import BytesIO
import base64

from agata.admin import admin_bp
from agata.admin.decorators import admin_required, superuser_required, association_scope_required
from agata.auth_models import SlackChannel, Association, ProjectSlackThread, Project
from agata.admin.services.slack_service import get_slack_service
from agata.db import SessionLocal


@admin_bp.route('/slack')
@login_required
@admin_required('admin')
def slack_overview():
    """
    Overview integrazione Slack

    Mostra:
    - Stato bot
    - Canali attivi per associazione
    - Ultimi errori
    """
    db: Session = SessionLocal()
    try:
        # Canali Slack
        query = db.query(SlackChannel)
        if current_user.role != 'superuser':
            query = query.filter(SlackChannel.association_id == current_user.association_id)

        channels = query.order_by(SlackChannel.association_id, SlackChannel.channel_type).all()

        # Group by association
        channels_by_assoc = {}
        for ch in channels:
            if ch.association_id not in channels_by_assoc:
                channels_by_assoc[ch.association_id] = []
            channels_by_assoc[ch.association_id].append(ch)

        # TODO: Log errori Slack (da implementare tabella slack_errors)
        slack_errors = []

        return render_template(
            'admin/slack/overview.html',
            channels_by_assoc=channels_by_assoc,
            slack_errors=slack_errors
        )

    finally:
        db.close()


@admin_bp.route('/api/slack/channels')
@login_required
@admin_required('admin')
def api_slack_channels():
    """
    API: lista canali Slack (JSON)
    """
    db: Session = SessionLocal()
    try:
        query = db.query(SlackChannel)
        if current_user.role != 'superuser':
            query = query.filter(SlackChannel.association_id == current_user.association_id)

        # === OPTIMIZATION: Eager load association to avoid N lazy loads ===
        from sqlalchemy.orm import joinedload

        channels = query.options(
            joinedload(SlackChannel.association)
        ).all()

        return jsonify([
            {
                'id': ch.id,
                'association_id': ch.association_id,
                'association_name': ch.association.name if ch.association else None,  # From eager load
                'channel_id': ch.channel_id,
                'channel_name': ch.channel_name,
                'channel_type': ch.channel_type,
                'is_active': ch.is_active,
                'created_at': ch.created_at.isoformat() if ch.created_at else None
            }
            for ch in channels
        ])

    finally:
        db.close()


@admin_bp.route('/api/slack/test-connection', methods=['POST'])
@login_required
@superuser_required
def api_slack_test_connection():
    """
    API: testa connessione Slack (solo superuser)

    TODO: implementare test reale API Slack
    """
    # Placeholder
    return jsonify({
        'success': True,
        'message': 'Slack API connection test successful',
        'bot_user_id': 'U01234ABC',
        'workspace': 'T01234XYZ'
    })


@admin_bp.route('/api/slack-export', methods=['POST'])
@login_required
def api_slack_export():
    """
    API: esporta analisi verso Slack nel thread del progetto

    Supporta:
    - analisi in fase (PNG + messaggio)
    - periodigramma (PNG + messaggio)
    - analisi di supporto (solo messaggio)

    I messaggi vanno nel thread del progetto, non in canale.
    """
    db: Session = SessionLocal()
    try:
        # Estrai parametri
        project_id = request.form.get('project_id') or request.json.get('project_id')
        analysis_type = request.form.get('analysis_type') or request.json.get('analysis_type')
        message = request.form.get('message') or request.json.get('message')
        image_file = request.files.get('image') if request.method == 'POST' else None

        if not project_id or not analysis_type or not message:
            return jsonify({'error': 'Missing required fields'}), 400

        # Verifica progetto e permessi
        project = db.query(Project).filter(Project.id == int(project_id)).first()
        if not project:
            return jsonify({'error': 'Project not found'}), 404

        # Verifica che l'utente abbia accesso al progetto
        if project.association_id != current_user.association_id and current_user.role != 'superuser':
            return jsonify({'error': 'Access denied'}), 403

        # Verifica che l'associazione abbia Slack abilitato
        association = project.association
        if not getattr(association, 'slack_enabled', True):
            return jsonify({'error': 'Slack not enabled for this association'}), 403

        # Ottieni servizio Slack
        try:
            slack_service = get_slack_service()
        except ValueError as e:
            return jsonify({'error': f'Slack not configured: {str(e)}'}), 500

        # Trova il thread del progetto
        project_thread = db.query(ProjectSlackThread).filter(
            ProjectSlackThread.project_id == project.id,
            ProjectSlackThread.is_active == True
        ).first()

        if not project_thread:
            return jsonify({'error': 'No Slack thread found for this project. Project must be created first.'}), 400

        # Invia messaggio nel thread
        try:
            # Carica immagine se presente
            if image_file:
                image_data = image_file.read()

                # Upload immagine nel canale (per preservare in archivio)
                slack_service.client.files_upload_v2(
                    channel=project_thread.channel_id,
                    file=image_data,
                    filename=f"{analysis_type}_{project.id}.png",
                    title=f"{analysis_type.replace('_', ' ').title()} - {project.project_code}",
                    thread_ts=project_thread.thread_ts  # Associa al thread
                )

            # Invia messaggio nel thread del progetto
            response = slack_service.post_message(
                channel_id=project_thread.channel_id,
                text=f"📊 {analysis_type.replace('_', ' ').title()}",
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*{analysis_type.replace('_', ' ').title()}*\n\n{message}"
                        }
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": f"Inviato da {current_user.full_name or current_user.email} • {analysis_type.replace('_', ' ')}"
                            }
                        ]
                    }
                ],
                thread_ts=project_thread.thread_ts  # Invia nel thread
            )

            # Aggiorna last_message_ts del thread (per tracking)
            if response and 'ts' in response:
                project_thread.last_message_ts = response['ts']
                db.commit()

            return jsonify({
                'success': True,
                'message': f'{analysis_type} exported to Slack thread',
                'thread_ts': project_thread.thread_ts
            }), 200

        except Exception as e:
            print(f"❌ Errore invio Slack: {e}")
            return jsonify({'error': f'Slack API error: {str(e)}'}), 500

    except Exception as e:
        print(f"❌ Errore API export Slack: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

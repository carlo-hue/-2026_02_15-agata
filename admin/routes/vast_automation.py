# agata/admin/routes/vast_automation.py
"""
VAST Automation Routes (Superuser Only)
"""
import logging
import threading
from flask import render_template, jsonify, request
from flask_login import login_required, current_user

from agata.admin import admin_bp
from agata.admin.decorators import superuser_required, audit_action
from agata.db import SessionLocal
from agata.auth_models import VastJob, Association

logger = logging.getLogger(__name__)

# Lazy-load service (avoid initialization errors if files missing)
_vast_service = None

def get_vast_service():
    global _vast_service
    if _vast_service is None:
        from agata.admin.services.vast_service import VastService
        _vast_service = VastService()
    return _vast_service


@admin_bp.route('/vast')
@login_required
@superuser_required
def vast_automation_page():
    """Pagina gestione job VAST."""
    db = SessionLocal()

    try:
        # Carica job recenti
        jobs = db.query(VastJob).order_by(VastJob.created_at.desc()).limit(50).all()

        return render_template(
            'admin/vast/jobs.html',
            jobs=jobs,
            page_title='VAST Automation'
        )
    except Exception as e:
        logger.error(f"Error loading VAST page: {e}", exc_info=True)
        return render_template('error.html', error=str(e)), 500
    finally:
        db.close()


@admin_bp.route('/api/vast/jobs', methods=['POST'])
@login_required
@superuser_required
@audit_action('vast_job_created', 'vast_job')
def api_create_vast_job():
    """Crea nuovo job VAST."""
    data = request.json

    try:
        # Validazione input
        if not data.get('target_name'):
            return jsonify({'success': False, 'error': 'target_name is required'}), 400
        if not data.get('source_type'):
            return jsonify({'success': False, 'error': 'source_type is required'}), 400
        if not data.get('source_location'):
            return jsonify({'success': False, 'error': 'source_location is required'}), 400

        # Crea job
        vast_service = get_vast_service()
        job = vast_service.create_job(
            target_name=data['target_name'],
            source_type=data['source_type'],
            source_location=data['source_location'],
            processing_params=data.get('processing_params', {}),
            user_id=current_user.id,
            user_email=current_user.email
        )

        # Avvia job in background thread
        thread = threading.Thread(
            target=vast_service.execute_job,
            args=(job.id,),
            daemon=True
        )
        thread.start()
        logger.info(f"Started background thread for job {job.job_code}")

        return jsonify({
            'success': True,
            'job_id': job.id,
            'job_code': job.job_code
        }), 201

    except Exception as e:
        logger.error(f"Failed to create VAST job: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400


@admin_bp.route('/api/vast/jobs/<int:job_id>')
@login_required
@superuser_required
def api_get_vast_job(job_id):
    """Get job status (per polling)."""
    try:
        vast_service = get_vast_service()
        status = vast_service.get_job_status(job_id)
        return jsonify(status), 200
    except ValueError:
        return jsonify({'error': 'Job not found'}), 404
    except Exception as e:
        logger.error(f"Error getting job status: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/api/vast/jobs')
@login_required
@superuser_required
def api_list_vast_jobs():
    """Elenca job VAST."""
    try:
        state = request.args.get('state')
        limit = int(request.args.get('limit', 50))

        vast_service = get_vast_service()
        jobs = vast_service.list_jobs(limit=limit, state=state)
        return jsonify({'jobs': jobs}), 200

    except Exception as e:
        logger.error(f"Error listing VAST jobs: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/api/vast/analysis-folders')
@login_required
@superuser_required
def api_list_analysis_folders():
    """Elenca sottocartelle analisi da VAST_DRIVE_FOLDER_ID in .env"""
    try:
        import os
        from agata.admin.services.google_drive_service import GoogleDriveService

        # Leggi folder ID da .env
        parent_folder_id = os.getenv('VAST_DRIVE_FOLDER_ID')
        if not parent_folder_id:
            return jsonify({
                'success': False,
                'error': 'VAST_DRIVE_FOLDER_ID not configured in .env'
            }), 400

        drive_service = GoogleDriveService()
        subfolders = drive_service.list_subfolders(parent_folder_id=parent_folder_id)

        logger.info(f"Listing {len(subfolders)} analysis folders in {parent_folder_id}")

        return jsonify({
            'success': True,
            'subfolders': subfolders
        }), 200

    except Exception as e:
        logger.error(f"Error listing analysis folders: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/vast/jobs/<int:job_id>')
@login_required
@superuser_required
def vast_job_detail(job_id):
    """Pagina dettaglio job con risultati."""
    db = SessionLocal()

    try:
        job = db.query(VastJob).get(job_id)
        if not job:
            return render_template('error.html', error='Job not found'), 404

        # Carica associazioni attive per la promozione
        associations = db.query(Association).filter(
            Association.is_active == True
        ).order_by(Association.name).all()

        # Verifica se il job è già stato promosso
        is_promoted = bool(
            job.output_files
            and job.output_files.get('promotion')
        )

        return render_template(
            'admin/vast/job_detail.html',
            job=job,
            associations=associations,
            is_promoted=is_promoted,
            page_title=f'VAST Job {job.job_code}'
        )

    except Exception as e:
        logger.error(f"Error loading job detail: {e}", exc_info=True)
        return render_template('error.html', error=str(e)), 500
    finally:
        db.close()


@admin_bp.route('/api/vast/jobs/<int:job_id>/promote', methods=['POST'])
@login_required
@superuser_required
@audit_action('vast_results_promoted', 'vast_job')
def api_promote_vast_job(job_id):
    """
    Promuove i risultati VAST a Cataloghi_esterni (import bulk).

    NON crea progetti automaticamente. I dati vengono inseriti come
    "bacino centrale" e le associazioni possono assegnarli a se stesse
    quando creano progetti.

    Body JSON:
        exclude_known_variables: bool (optional) - Esclude variabili note
    """
    data = request.json or {}

    try:
        exclude_known = data.get('exclude_known_variables', False)

        vast_service = get_vast_service()
        stats = vast_service.promote_job_results(
            job_id=job_id,
            association_id=None,  # Non serve, legacy parameter
            user_id=current_user.id,
            user_email=current_user.email,
            only_known_variables=exclude_known,  # Se True, esclude note (skip in loop)
            only_candidates=True  # Sempre True: promuoviamo solo VAST candidates
        )

        return jsonify({
            'success': True,
            'stats': stats
        }), 200

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except FileNotFoundError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404
    except Exception as e:
        logger.error(f"Failed to promote VAST job: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

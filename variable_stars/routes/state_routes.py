"""
state_routes.py - Persistenza stato utente

Gestisce salvataggio/caricamento stato applicazione:
- Parametri analisi
- Selezioni punti
- Preferenze UI

Storage: MariaDB (tabella user_states)
"""

import json
import uuid
import logging
from flask import request, jsonify, session as flask_session
from sqlalchemy.exc import SQLAlchemyError

from agata.variable_stars import variable_stars_bp
from agata.db import SessionLocal
from agata.models import UserState

logger = logging.getLogger(__name__)


def _get_state_id():
    """
    Ottieni o genera ID stato per sessione corrente.

    Usa Flask session (cookie-based) per tracking utente.
    Ogni utente ha un UUID univoco per salvare/caricare stato.

    Returns:
        str: UUID hex (32 caratteri)
    """
    if "state_id" not in flask_session:
        # Genera nuovo UUID
        flask_session["state_id"] = uuid.uuid4().hex
        logger.info(f"Nuovo state_id generato: {flask_session['state_id']}")

    return flask_session["state_id"]


@variable_stars_bp.post("/api/state/save")
def api_state_save():
    """
    Salva stato applicazione per utente corrente.

    Permette persistenza:
    - Parametri analisi (periodo, sigma, etc.)
    - Selezioni punti
    - Preferenze UI

    Request Body (JSON):
        Qualsiasi oggetto JSON serializzabile.
        Tipicamente:
        {
            "period": float,
            "epoch": float,
            "removed_indices": [int...],
            "view": str,
            ...
        }

    Returns:
        JSON: {"ok": true}

    Storage:
        MariaDB table `user_states`:
        - state_id (PK): UUID utente
        - payload_json: Stato serializzato
        - updated_at: Timestamp
    """
    try:
        payload = request.get_json(force=True)
        state_id = _get_state_id()

        logger.info(f"Salvataggio stato per {state_id}")

        db = SessionLocal()
        try:
            # Cerca riga esistente
            row = db.get(UserState, state_id)

            if row is None:
                # Crea nuova riga
                row = UserState(
                    state_id=state_id,
                    payload_json=json.dumps(payload)
                )
                db.add(row)
                logger.info(f"Creato nuovo stato per {state_id}")
            else:
                # Aggiorna esistente
                row.payload_json = json.dumps(payload)
                logger.info(f"Aggiornato stato per {state_id}")

            db.commit()

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Errore DB save state: {e}", exc_info=True)
            return jsonify({"ok": False, "error": "Errore database"}), 500
        finally:
            db.close()

        return jsonify({"ok": True})

    except Exception as e:
        logger.error(f"Errore save state: {e}", exc_info=True)
        return jsonify({"ok": False, "error": "Errore interno"}), 500


@variable_stars_bp.get("/api/state/load")
def api_state_load():
    """
    Carica stato salvato per utente corrente.

    Returns:
        JSON:
        {
            "ok": true,
            "state": {...} | null
        }

        state è null se:
        - Utente nuovo (nessun cookie)
        - Stato mai salvato
    """
    try:
        state_id = flask_session.get("state_id")

        if not state_id:
            # Utente nuovo, nessuno stato
            logger.info("Nessun state_id in sessione, ritorno null")
            return jsonify({"ok": True, "state": None})

        logger.info(f"Caricamento stato per {state_id}")

        db = SessionLocal()
        try:
            row = db.get(UserState, state_id)

            if row is None:
                # State_id esiste ma nessun salvataggio DB
                logger.info(f"Nessuno stato salvato per {state_id}")
                return jsonify({"ok": True, "state": None})

            # Deserializza JSON
            state = json.loads(row.payload_json)
            logger.info(f"Stato caricato per {state_id}")

            return jsonify({"ok": True, "state": state})

        except SQLAlchemyError as e:
            logger.error(f"Errore DB load state: {e}", exc_info=True)
            return jsonify({"ok": False, "error": "Errore database"}), 500
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Errore load state: {e}", exc_info=True)
        return jsonify({"ok": False, "error": "Errore interno"}), 500

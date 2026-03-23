"""
data_routes.py - Caricamento dati (sintetic/DB)

Endpoint per caricamento curve di luce da:
- Database (GAIA DR3)
- Generatore sintetico (testing/demo)
"""

import logging
import numpy as np
import pyarrow as pa
from flask import request, jsonify, Response
from flask_login import current_user
from sqlalchemy.orm import Session

from agata.variable_stars import variable_stars_bp
from agata.variable_stars.constants import MAX_SESSIONS, ALLOWED_SYNTHETIC_KINDS
from agata.services.data_loader import get_lightcurve
from agata.variable_stars.services.arrow_parser import create_arrow_response
from agata.auth_models import Project
from agata.db import SessionLocal

logger = logging.getLogger(__name__)


@variable_stars_bp.get("/api/lightcurve.arrow")
def api_lightcurve_arrow():
    """
    Carica curva di luce da database o genera sintetica.

    Restituisce dati in formato Apache Arrow IPC stream per efficienza.
    Arrow permette zero-copy transfer e parsing velocissimo in JavaScript.

    Query Parameters:
        project_id (int, optional): ID progetto per dati reali
        gaia_id (str, optional): GAIA ID stella per dati reali (se non specificato project_id)
        kind (str, optional): Tipo stella sintetica se no project_id/gaia_id
            - "rrlyrae": RR Lyrae tipo ab
            - "delta_scuti": Delta Scuti multiperiodica
            - "eclipsing": Binaria eclissante
            - "cepheid": Cepheide classica
            - "irregular": Variabile irregolare
        seed (int, optional): Seed RNG per riproducibilità
        sessions (int, optional): Numero sessioni sintetiche (1-50)

    Returns:
        Response: Arrow IPC stream con tabella contenente:
            - point_id: int32 - ID univoco punto
            - session_id: int32 - ID sessione osservativa
            - session_name: string - Nome sessione (da DB o "S{id}")
            - jd: float64 - Julian Date
            - mag: float32 - Magnitudine

    Errors:
        403: Progetto non autorizzato
        404: Progetto non trovato o nessun dato disponibile
        500: Errore database o generazione

    Note:
        Arrow stream è compatto (~10x più piccolo di JSON) e veloce.
        Frontend usa arrow-js per parsing diretto in JS.
    """

    try:
        # ------------------------------------
        # VALIDAZIONE E SANITIZZAZIONE INPUT
        # ------------------------------------

        project_id = request.args.get("project_id", type=int)
        gaia_id = request.args.get("gaia_id", type=str)

        # Tipo stella sintetica (default: RR Lyrae)
        kind = request.args.get("kind", "rrlyrae")
        if kind not in ALLOWED_SYNTHETIC_KINDS:
            logger.warning(f"Tipo stella non valido: {kind}")
            kind = "rrlyrae"

        # Seed RNG (default: 1)
        try:
            seed = int(request.args.get("seed", "1"))
            if seed < 0:
                logger.warning(f"Seed negativo: {seed}, uso 1")
                seed = 1
        except ValueError:
            logger.warning("Seed non valido, uso default 1")
            seed = 1

        # Numero sessioni (validato 1-50 per evitare sovraccarico server)
        try:
            n_sessions = int(request.args.get("sessions", "6"))
            n_sessions = max(1, min(n_sessions, MAX_SESSIONS))
        except ValueError:
            logger.warning("Numero sessioni non valido, uso default 6")
            n_sessions = 6

        # ------------------------------------
        # CARICAMENTO DATI
        # ------------------------------------

        if project_id:
            # Dati reali da database tramite progetto
            logger.info(f"Caricamento dati per project_id: {project_id}")

            db: Session = SessionLocal()
            try:
                # Recupera il progetto
                project = db.query(Project).filter(Project.id == project_id).first()

                if not project:
                    logger.warning(f"Progetto {project_id} non trovato")
                    return jsonify({"error": "Progetto non trovato"}), 404

                # Verifica permessi
                if current_user.role != 'superuser':
                    # Verifica associazione
                    if project.association_id != current_user.association_id:
                        logger.warning(f"User {current_user.id} tentò di accedere a progetto {project_id} di altra associazione")
                        return jsonify({"error": "Non autorizzato ad accedere a questo progetto"}), 403

                    # Verifica assegnazione:
                    # - Admin della stessa associazione possono sempre accedere
                    # - Analyst/Reviewer solo se assegnati
                    if current_user.role in ['analyst', 'reviewer']:
                        # Confronto robusto: converti entrambi a string per evitare problemi di tipo
                        assigned_to_str = str(project.assigned_to) if project.assigned_to else None
                        current_user_id_str = str(current_user.id)

                        if assigned_to_str != current_user_id_str:
                            logger.warning(f"User {current_user.id} tentò di caricare dati per progetto {project_id} non assegnato a loro (assegnato a {project.assigned_to})")
                            return jsonify({"error": "Progetto non assegnato a te"}), 403

                loaded_gaia_id = project.gaia_id
                logger.info(f"Caricamento dati DB per GAIA ID: {loaded_gaia_id} (progetto {project.project_code})")

                sessions = get_lightcurve(
                    source="db",
                    gaia_id=loaded_gaia_id
                )
            finally:
                db.close()
        elif gaia_id:
            # Dati reali da database tramite GAIA ID (per admin che esaminano stelle)
            logger.info(f"Caricamento dati per gaia_id: {gaia_id}")

            # Verifica permessi - solo admin e superuser possono accedere
            if current_user.role not in ['admin', 'superuser']:
                logger.warning(f"User {current_user.id} (role: {current_user.role}) tentò di accedere a stella {gaia_id}")
                return jsonify({"error": "Non autorizzato ad accedere a questa stella"}), 403

            # Carica i dati dal database
            # I dati possono provenire da:
            # 1. dati_stelle (progetto locale)
            # 2. Cataloghi_esterni (catalogo esterno)
            # La funzione load_lightcurve_from_db() interroga entrambi
            sessions = get_lightcurve(
                source="db",
                gaia_id=gaia_id
            )

            if not sessions:
                logger.warning(f"Nessun dato trovato per gaia_id: {gaia_id}")
                return jsonify({"error": "Stella non trovata"}), 404

            logger.info(f"Caricamento dati DB per GAIA ID: {gaia_id} ({len(sessions)} sessioni)")
        else:
            # Dati sintetici per testing/demo
            logger.info(f"Generazione dati sintetici: kind={kind}, sessions={n_sessions}, seed={seed}")
            sessions = get_lightcurve(
                source="synthetic",
                kind=kind,
                n_sessions=n_sessions,
                seed=seed,
                realism=4  # Realism fisso a 4 (buon compromesso)
            )

        # Verifica presenza dati
        if not sessions:
            if project_id:
                logger.warning(f"Nessun dato trovato per project_id: {project_id}")
            return jsonify({"error": "Nessun dato disponibile"}), 404

        # ------------------------------------
        # CONVERSIONE IN FORMATO ARROW
        # ------------------------------------
        # Flatten: lista di sessioni → array unici

        jd_all = []       # Julian Dates
        mag_all = []      # Magnitudini
        sid_all = []      # Session IDs
        sname_all = []    # Session names

        for s in sessions:
            n = len(s["jd"])  # Numero punti in questa sessione

            # Accumula array per ogni colonna
            jd_all.append(s["jd"])
            mag_all.append(s["mag"].astype(np.float32))  # float32 sufficiente, risparmia RAM
            sid_all.append(np.full(n, s["session_id"], dtype=np.int32))

            # Nome sessione: da DB se presente, altrimenti "S{id}"
            session_name_val = s.get("session_name", f"S{s['session_id']}")
            sname_all.append(np.full(n, session_name_val, dtype=object))

        # Concatena tutti gli array
        jd = np.concatenate(jd_all).astype(np.float64)
        mag = np.concatenate(mag_all).astype(np.float32)
        session_id = np.concatenate(sid_all).astype(np.int32)
        session_name = np.concatenate(sname_all)

        # ID univoco per ogni punto (utile per selezioni/rimozioni)
        point_id = np.arange(jd.size, dtype=np.int32)

        logger.info(f"Dati preparati: {jd.size} punti totali, {len(sessions)} sessioni")

        # Crea tabella Arrow
        table = pa.table({
            "point_id": pa.array(point_id),
            "session_id": pa.array(session_id),
            "session_name": pa.array(session_name),
            "jd": pa.array(jd),
            "mag": pa.array(mag),
        })

        # Serializza a IPC stream
        buf = create_arrow_response(table)

        logger.info(f"Arrow stream generato: {len(buf)} bytes")

        # Restituisci stream binario
        return Response(
            buf,
            mimetype="application/vnd.apache.arrow.stream",
            headers={"Cache-Control": "no-store"},  # No caching (dati dinamici)
        )

    except Exception as e:
        logger.error(f"Errore caricamento lightcurve: {e}", exc_info=True)
        return jsonify({"error": "Errore interno server"}), 500

"""
phase_routes.py - Phase folding delle curve di luce

Endpoint per folding in fase dato un periodo.
Supporta sia JSON che Arrow IPC stream.
"""

import logging
import numpy as np
import pyarrow as pa
from flask import request, jsonify, Response

from agata.variable_stars import variable_stars_bp
from agata.variable_stars.constants import MIN_PERIOD, MAX_PERIOD
from agata.variable_stars.services.arrow_parser import read_arrow_table_from_request, create_arrow_response

logger = logging.getLogger(__name__)


@variable_stars_bp.post("/api/phase")
def api_phase_json():
    """
    Fold curva di luce in fase (endpoint JSON - backward compatible).

    Request Body (JSON):
        {
            "jd": [float...],
            "mag": [float...],
            "period": float,         // Periodo folding [giorni]
            "phase_shift": float     // Shift fase opzionale [0-1]
        }

    Returns:
        JSON:
        {
            "phase": [float...],  // Fase [0-1] ordinata
            "mag": [float...]     // Mag riordinata per fase crescente
        }
    """
    try:
        data = request.get_json(force=True)
        jd = np.asarray(data["jd"], dtype=float)
        mag = np.asarray(data["mag"], dtype=float)
        period = float(data["period"])
        phase_shift = float(data.get("phase_shift", 0.0))

        # Validazione
        if period <= 0:
            return jsonify({"error": "Periodo deve essere > 0"}), 400

        logger.info(f"Phase folding JSON: P={period:.4f}d, shift={phase_shift:.3f}")

        # Calcola fase
        phase = ((jd / period) + phase_shift) % 1.0

        # Ordina per fase crescente (importante per plot connessi)
        order = np.argsort(phase)

        return jsonify({
            "phase": phase[order].tolist(),
            "mag": mag[order].tolist()
        })

    except (KeyError, ValueError) as e:
        logger.error(f"Errore input phase folding: {e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Errore phase folding: {e}", exc_info=True)
        return jsonify({"error": "Errore interno"}), 500


@variable_stars_bp.post("/api/phase.arrow")
def api_phase_arrow():
    """
    Fold curva di luce in fase (endpoint Arrow - raccomandato).

    Questo endpoint preserva session_id per permettere
    colorazione punti per sessione nel plot fase.

    Request:
        Body: Arrow stream (jd, mag, session_id)
        Query params:
            - period: float (obbligatorio)
            - phase_shift: float (default: 0.0)

    Returns:
        Arrow stream con:
            - phase: float32 [0-1]
            - mag: float32
            - session_id: int32

        Ordinato per fase crescente.
    """
    try:
        # Parametri da query
        period_str = request.args.get("period")
        if not period_str:
            return jsonify({"error": "Parametro 'period' obbligatorio"}), 400

        period = float(period_str)
        phase_shift = float(request.args.get("phase_shift", 0.0))

        # Validazione
        if period <= 0:
            return jsonify({"error": "Periodo deve essere > 0"}), 400
        if not (MIN_PERIOD <= period <= MAX_PERIOD):
            logger.warning(f"Periodo fuori range raccomandato: {period}d")

        logger.info(f"Phase folding Arrow: P={period:.4f}d, shift={phase_shift:.3f}")

        # Leggi tabella
        table = read_arrow_table_from_request()

        jd = np.asarray(table["jd"].to_numpy(zero_copy_only=False), dtype=float)
        mag = np.asarray(table["mag"].to_numpy(zero_copy_only=False), dtype=float)
        session_id = np.asarray(table["session_id"].to_numpy(zero_copy_only=False), dtype=np.int32)

        # Calcola fase
        # Formula: φ = (JD/P + shift) mod 1
        # dove φ ∈ [0,1]
        phase = ((jd / period) + phase_shift) % 1.0

        # Ordina per fase crescente
        order = np.argsort(phase)

        # Crea tabella output
        out_table = pa.table({
            "phase": pa.array(phase[order].astype(np.float32)),
            "mag": pa.array(mag[order].astype(np.float32)),
            "session_id": pa.array(session_id[order]),
        })

        # Serializza
        buf = create_arrow_response(out_table)

        logger.info(f"Phase folded: {len(phase)} punti → {len(buf)} bytes")

        return Response(
            buf,
            mimetype="application/vnd.apache.arrow.stream",
            headers={"Cache-Control": "no-store"},
        )

    except ValueError as e:
        logger.error(f"Errore validazione phase: {e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Errore phase Arrow: {e}", exc_info=True)
        return jsonify({"error": "Errore interno"}), 500

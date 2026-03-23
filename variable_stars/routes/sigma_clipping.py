"""
sigma_clipping.py - Sigma clipping per identificazione outlier fotometrici

Identifica outlier usando MAD (Median Absolute Deviation) sigma clipping
applicato PER SESSIONE per rispettare differenze strumentali.
"""

import logging
import numpy as np
from flask import request, jsonify

from agata.variable_stars import variable_stars_bp
from agata.variable_stars.constants import DEFAULT_SIGMA_THRESHOLD, MIN_POINTS_PER_SESSION
from agata.variable_stars.services.arrow_parser import read_arrow_table_from_request
from agata.variable_stars.services.statistics import calculate_mad, mad_to_sigma

logger = logging.getLogger(__name__)


@variable_stars_bp.post("/api/sigma_clip.arrow")
def api_sigma_clip_arrow():
    """
    Identifica outlier fotometrici usando MAD sigma clipping PER SESSIONE.

    Perché PER SESSIONE?
    Ogni sessione osservativa ha caratteristiche uniche:
    - Offset strumentale (diversa calibrazione)
    - Condizioni meteo (seeing, trasparenza)
    - Rumore fotometrico variabile

    Analizzare tutte le sessioni insieme contaminerebbe statistiche!

    Request:
        Body: Arrow stream (jd, mag, session_id)
        Query params:
            - sigma: float (default: 3.0)
                Soglia clipping in unità σ
                - 2.0 = aggressivo (rimuove ~5% dati normali)
                - 3.0 = standard (rimuove ~0.3% dati normali)
                - 5.0 = conservativo (solo outlier estremi)

    Returns:
        JSON con statistiche dettagliate:
        {
            "outlier_indices": [int...],     // Indici globali outlier
            "n_outliers_total": int,
            "n_sessions": int,
            "sigma_used": float,
            "session_stats": {               // Statistiche per sessione
                "0": {
                    "n_total": int,
                    "n_outliers": int,
                    "median": float,         // Mag mediana [mag]
                    "mad": float,            // MAD [mag]
                    "sigma_equiv": float,    // σ equivalente [mag]
                    "bounds": [float, float], // [lower, upper] bounds
                    "outlier_percentage": float,
                    "skipped": bool,         // True se troppo pochi punti
                    "reason": str            // Se skipped, perché
                },
                ...
            },
            "algorithm": "MAD (Median Absolute Deviation)",
            "note": "..."
        }

    Algoritmo:
        MAD (Median Absolute Deviation) - Robusto agli outlier

        1. Per ogni sessione:
           median = mediana(mag)
           MAD = mediana(|mag - median|)

        2. Conversione MAD → σ:
           σ_equiv = 1.4826 × MAD

           Fattore 1.4826 deriva da:
           - Per distribuzione Gaussiana: MAD = 0.6745 × σ
           - Quindi: σ = MAD / 0.6745 = 1.4826 × MAD

           Questo rende MAD confrontabile con deviazione standard
           ma MAD resta robusta anche con 50% outlier!

        3. Bounds:
           lower = median - k × σ_equiv
           upper = median + k × σ_equiv
           dove k = sigma (parametro input)

        4. Outlier: punti fuori bounds

    Riferimento:
        - Stetson 1996, PASP 108, 851 (uso MAD in fotometria)
        - Huber & Ronchetti 2009 "Robust Statistics" (teoria MAD)

    Note:
        - MAD immune a ~50% contaminazione outlier
        - Median immune a ~50% contaminazione
        - Standard deviation collassa con anche solo 1% outlier!
    """
    try:
        # Parametro sigma da query
        sigma_threshold = float(request.args.get("sigma", DEFAULT_SIGMA_THRESHOLD))

        # Validazione
        if not (0.5 <= sigma_threshold <= 10.0):
            logger.warning(f"Sigma fuori range raccomandato: {sigma_threshold}, uso {DEFAULT_SIGMA_THRESHOLD}")
            sigma_threshold = DEFAULT_SIGMA_THRESHOLD

        logger.info(f"Sigma clipping: σ={sigma_threshold}")

        # Leggi dati
        table = read_arrow_table_from_request()

        jd = np.asarray(table["jd"].to_numpy(zero_copy_only=False), dtype=float)
        mag = np.asarray(table["mag"].to_numpy(zero_copy_only=False), dtype=float)
        session_id = np.asarray(table["session_id"].to_numpy(zero_copy_only=False), dtype=np.int32)

        # Container risultati
        outlier_indices = []
        session_stats = {}

        # Analizza ogni sessione indipendentemente
        unique_sessions = np.unique(session_id)

        logger.info(f"Analizzando {len(unique_sessions)} sessioni")

        for sid in unique_sessions:
            # ===== ISOLAMENTO SESSIONE =====
            # Maschera booleana per punti di questa sessione
            mask = (session_id == sid)
            session_mags = mag[mask]
            session_jd = jd[mask]  # Non usato, ma disponibile se serve
            session_indices = np.where(mask)[0]  # Indici globali

            n_points = len(session_mags)

            # ===== CHECK MINIMO PUNTI =====
            # Con <5 punti, statistiche inaffidabili
            if n_points < MIN_POINTS_PER_SESSION:
                session_stats[int(sid)] = {
                    "n_total": n_points,
                    "n_outliers": 0,
                    "median": None,
                    "mad": None,
                    "sigma_equiv": None,
                    "bounds": None,
                    "skipped": True,
                    "reason": f"Meno di {MIN_POINTS_PER_SESSION} punti"
                }
                logger.warning(f"Sessione {sid}: troppo pochi punti ({n_points}), skip")
                continue

            # ===== STATISTICHE ROBUSTE =====

            # Mediana: valore centrale, immune a outlier
            median = np.median(session_mags)

            # MAD (Median Absolute Deviation)
            mad = calculate_mad(session_mags)

            # ===== PROTEZIONE MAD = 0 =====
            # Se MAD ≈ 0, tutti i punti sono identici (es: saturazione)
            # Non possiamo calcolare sigma, skip sessione
            if mad < 1e-6:
                session_stats[int(sid)] = {
                    "n_total": n_points,
                    "n_outliers": 0,
                    "median": float(median),
                    "mad": float(mad),
                    "sigma_equiv": 0.0,
                    "bounds": [float(median), float(median)],
                    "skipped": True,
                    "reason": "Varianza nulla (MAD≈0)"
                }
                logger.warning(f"Sessione {sid}: MAD≈0, tutti punti identici")
                continue

            # ===== CONVERSIONE MAD → SIGMA =====
            sigma_equiv = mad_to_sigma(mad)

            # ===== SOGLIE CLIPPING =====
            lower_bound = median - sigma_threshold * sigma_equiv
            upper_bound = median + sigma_threshold * sigma_equiv

            logger.debug(f"Sessione {sid}: median={median:.3f}, MAD={mad:.4f}, σ={sigma_equiv:.4f}")
            logger.debug(f"  Bounds: [{lower_bound:.3f}, {upper_bound:.3f}]")

            # ===== IDENTIFICA OUTLIER =====
            # Outlier = punti fuori bounds
            outliers_mask = (session_mags < lower_bound) | (session_mags > upper_bound)
            outlier_session_indices = session_indices[outliers_mask]

            n_outliers = len(outlier_session_indices)
            outlier_pct = 100.0 * n_outliers / n_points

            logger.info(f"Sessione {sid}: {n_outliers}/{n_points} outlier ({outlier_pct:.1f}%)")

            # ===== SALVA STATISTICHE =====
            session_stats[int(sid)] = {
                "n_total": n_points,
                "n_outliers": n_outliers,
                "median": float(median),
                "mad": float(mad),
                "sigma_equiv": float(sigma_equiv),
                "bounds": [float(lower_bound), float(upper_bound)],
                "skipped": False,
                "outlier_percentage": float(outlier_pct)
            }

            # Aggiungi a lista globale outlier
            outlier_indices.extend(outlier_session_indices.tolist())

        # ===== RISPOSTA =====
        n_outliers_total = len(outlier_indices)
        logger.info(f"Totale: {n_outliers_total} outlier identificati su {len(jd)} punti")

        return jsonify({
            "outlier_indices": outlier_indices,
            "n_outliers_total": n_outliers_total,
            "n_sessions": len(unique_sessions),
            "sigma_used": sigma_threshold,
            "session_stats": session_stats,
            "algorithm": "MAD (Median Absolute Deviation)",
            "note": "Clipping eseguito indipendentemente per ogni sessione"
        })

    except ValueError as e:
        logger.error(f"Errore validazione sigma clip: {e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Errore sigma clipping: {e}", exc_info=True)
        return jsonify({"error": "Errore interno"}), 500

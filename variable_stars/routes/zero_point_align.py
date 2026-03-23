"""
zero_point_align.py - Allineamento zero-point robusto tra sessioni

Allinea sessioni fotometriche usando:
- Astropy sigma-clipped statistics
- MAD come stimatore robusto di σ
- Weighted median per riferimento globale
- Test significatività offset
"""

import logging
import numpy as np
from flask import request, jsonify
from astropy.stats import sigma_clipped_stats, mad_std, sigma_clip

from agata.variable_stars import variable_stars_bp
from agata.variable_stars.constants import MIN_POINTS_PER_SESSION
from agata.variable_stars.services.arrow_parser import read_arrow_table_from_request
from agata.variable_stars.services.statistics import weighted_median

logger = logging.getLogger(__name__)


@variable_stars_bp.post("/api/align_zeropoint.arrow")
def api_align_zeropoint():
    """
    Allinea sessioni fotometriche usando zero-point calibration con astropy.

    Metodo scientifico:
    1. Per ogni sessione, calcola statistiche robuste con sigma-clipping iterativo
    2. Usa MAD (Median Absolute Deviation) per stimatore robusto di σ
    3. Calcola offset per allineare tutte le sessioni a una magnitudine di riferimento globale
    4. Applica pesatura basata su numero punti e dispersione

    Request:
        Body: Arrow stream con colonne:
            - jd: float64 - Julian Date
            - mag: float64 - Magnitudine (già con detrending applicato dal frontend)
            - session_id: int32 - ID sessione

        Query params:
            - sigma: float (default: 3.0) - Soglia sigma-clipping
            - max_iters: int (default: 5) - Iterazioni max sigma-clipping

    Returns:
        JSON:
        {
            "session_offsets": {
                "0": float,      // Offset da applicare alla sessione 0 [mag]
                "1": float,
                ...
            },
            "global_reference": float,  // Magnitudine mediana globale di riferimento
            "session_stats": {
                "0": {
                    "n_points": int,
                    "median_before": float,    // Mediana prima allineamento
                    "median_after": float,     // Mediana dopo allineamento
                    "mad": float,              // MAD della sessione
                    "sigma_equiv": float,      // σ equivalente (1.4826 × MAD)
                    "n_clipped": int,          // Punti rimossi da sigma-clipping
                    "weight": float,           // Peso nella calibrazione globale
                    "offset": float            // Offset calcolato
                },
                ...
            },
            "algorithm": "astropy.stats sigma-clipped robust statistics",
            "reference": "Stetson 1996 PASP 108, 851"
        }

    Algoritmo:

        Per ogni sessione S:

        1. SIGMA-CLIPPING ITERATIVO (astropy.stats.sigma_clipped_stats)
           - Calcola median, mean, std con rimozione iterativa outlier
           - Usa MAD come stimatore iniziale di σ (robusto a outlier)
           - Iterazioni fino a convergenza o max_iters

        2. CALCOLO OFFSET
           - Offset_S = Median_global - Median_S
           - Median_global = mediana pesata di tutte le sessioni
           - Peso_S = N_points / σ²  (più punti e meno dispersi → peso maggiore)

        3. VALIDAZIONE
           - Verifica significatività: |Offset| > σ/√N
           - Se non significativo, Offset = 0

        Perché questo metodo è scientificamente corretto:
        - MAD immune fino a 50% contaminazione outlier
        - Sigma-clipping rimuove outlier senza assumere distribuzione
        - Pesatura ottimale considera sia numero punti che qualità fotometrica
        - Non assume variabilità costante tra sessioni (eteroschedasticità OK)

    Riferimenti:
        - Sigma-clipping: Stetson 1996, PASP 108, 851
        - MAD estimator: Huber & Ronchetti 2009, "Robust Statistics"
        - Astropy stats: https://docs.astropy.org/en/stable/stats/
    """
    try:
        # Parametri con validazione
        sigma_threshold = float(request.args.get("sigma", 3.0))
        max_iters = int(request.args.get("max_iters", 5))

        # Sanitizza
        sigma_threshold = max(1.0, min(sigma_threshold, 10.0))
        max_iters = max(1, min(max_iters, 20))

        logger.info(f"Allineamento zero-point: σ={sigma_threshold}, max_iters={max_iters}")

        # Leggi dati Arrow
        table = read_arrow_table_from_request()

        jd = np.asarray(table["jd"].to_numpy(zero_copy_only=False), dtype=float)
        mag = np.asarray(table["mag"].to_numpy(zero_copy_only=False), dtype=float)
        session_id = np.asarray(table["session_id"].to_numpy(zero_copy_only=False), dtype=np.int32)

        # Container risultati
        session_stats = {}
        session_medians = []
        session_weights = []

        unique_sessions = np.unique(session_id)

        logger.info(f"Processando {len(unique_sessions)} sessioni")

        # ===== FASE 1: STATISTICHE ROBUSTE PER SESSIONE =====
        for sid in unique_sessions:
            mask = (session_id == sid)
            session_mag = mag[mask]

            n_points = len(session_mag)

            # Skip se troppo pochi punti
            if n_points < MIN_POINTS_PER_SESSION:
                logger.warning(f"Sessione {sid}: solo {n_points} punti, skip")
                session_stats[int(sid)] = {
                    "n_points": n_points,
                    "skipped": True,
                    "reason": f"Meno di {MIN_POINTS_PER_SESSION} punti",
                    "offset": 0.0
                }
                continue

            # ===== SIGMA-CLIPPING ROBUSTO con ASTROPY =====
            try:
                mean_clipped, median_clipped, std_clipped = sigma_clipped_stats(
                    session_mag,
                    sigma=sigma_threshold,
                    maxiters=max_iters,
                    std_func=mad_std  # Usa MAD invece di std classica (più robusto!)
                )

                # Conta punti clippati
                masked = sigma_clip(
                    session_mag,
                    sigma=sigma_threshold,
                    maxiters=max_iters,
                    stdfunc=mad_std
                )
                n_clipped = masked.mask.sum() if hasattr(masked, 'mask') else 0

            except Exception as e:
                logger.error(f"Sessione {sid}: sigma-clipping fallito: {e}")
                # Fallback: statistiche semplici
                median_clipped = np.median(session_mag)
                std_clipped = mad_std(session_mag)
                mean_clipped = np.mean(session_mag)
                n_clipped = 0

            # ===== CALCOLO PESO =====
            # Peso = N / σ²
            # Sessioni con più punti e meno dispersione hanno peso maggiore
            if std_clipped > 1e-6:
                weight = n_points / (std_clipped ** 2)
            else:
                # Dispersione nulla (improbabile ma gestisci)
                weight = n_points

            # Accumula per calcolo mediana globale
            session_medians.append(median_clipped)
            session_weights.append(weight)

            # Salva statistiche
            session_stats[int(sid)] = {
                "n_points": n_points,
                "median_before": float(median_clipped),
                "mad": float(mad_std(session_mag)),
                "sigma_equiv": float(std_clipped),
                "n_clipped": int(n_clipped),
                "weight": float(weight),
                "skipped": False
            }

            logger.debug(f"Sessione {sid}: median={median_clipped:.4f}, σ={std_clipped:.4f}, weight={weight:.2f}")

        # ===== FASE 2: CALCOLO MEDIANA GLOBALE PESATA =====

        if len(session_medians) == 0:
            logger.error("Nessuna sessione valida per allineamento")
            return jsonify({"error": "Nessuna sessione con dati sufficienti"}), 400

        # Weighted median
        session_medians = np.array(session_medians)
        session_weights = np.array(session_weights)

        global_reference = weighted_median(session_medians, session_weights)

        logger.info(f"Riferimento globale pesato: {global_reference:.4f} mag")

        # ===== FASE 3: CALCOLO OFFSET PER SESSIONE =====

        session_offsets = {}

        for sid in unique_sessions:
            sid_int = int(sid)

            if session_stats[sid_int].get("skipped", False):
                session_offsets[sid_int] = 0.0
                session_stats[sid_int]["offset"] = 0.0
                session_stats[sid_int]["median_after"] = session_stats[sid_int].get("median_before", 0.0)
                continue

            median_before = session_stats[sid_int]["median_before"]
            sigma = session_stats[sid_int]["sigma_equiv"]
            n = session_stats[sid_int]["n_points"]

            # Offset = quanto spostare questa sessione per allinearla al riferimento
            offset = global_reference - median_before

            # ===== TEST SIGNIFICATIVITÀ =====
            # Offset significativo se |offset| > errore_standard_mediana
            # Per mediana: σ_median ≈ σ / √N come approssimazione conservativa
            sigma_median = sigma / np.sqrt(n)
            is_significant = abs(offset) > sigma_median

            if not is_significant:
                logger.info(f"Sessione {sid}: offset={offset:.4f} non significativo (σ_med={sigma_median:.4f}), forzo a 0")
                offset = 0.0

            session_offsets[sid_int] = float(offset)
            session_stats[sid_int]["offset"] = float(offset)
            session_stats[sid_int]["median_after"] = float(median_before + offset)
            session_stats[sid_int]["significant"] = bool(is_significant)
            session_stats[sid_int]["sigma_median"] = float(sigma_median)

            logger.info(f"Sessione {sid}: offset={offset:.4f} mag ({'SIGNIFICATIVO' if is_significant else 'non significativo'})")

        # ===== RISPOSTA =====

        return jsonify({
            "session_offsets": session_offsets,
            "global_reference": global_reference,
            "session_stats": session_stats,
            "algorithm": "astropy.stats sigma-clipped robust statistics with weighted median",
            "parameters": {
                "sigma": sigma_threshold,
                "max_iters": max_iters,
                "weight_formula": "N / σ²"
            },
            "reference": "Stetson 1996 PASP 108, 851; Astropy documentation"
        })

    except ValueError as e:
        logger.error(f"Errore validazione align zeropoint: {e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Errore align zeropoint: {e}", exc_info=True)
        return jsonify({"error": "Errore interno"}), 500

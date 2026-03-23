"""
ai_routes.py - AI Advisor con LLM per analisi curve di luce

Analizza sessioni fotometriche usando LLM (Cerebras/Claude/OpenAI) per:
- Qualità delle sessioni (noise, gaps, outliers)
- Suggerimenti pre-processing
- Range ottimale periodigramma
- Classificazione tipo variabile
"""

import json
import logging
import numpy as np
from flask import request, jsonify
from astropy.stats import mad_std

from agata.variable_stars import variable_stars_bp
from agata.variable_stars.constants import MIN_POINTS_PER_SESSION
from agata.variable_stars.services.arrow_parser import read_arrow_table_from_request
from agata.variable_stars.services.llm_client import LLMClient

logger = logging.getLogger(__name__)


@variable_stars_bp.post("/api/analyze_with_llm.arrow")
def api_analyze_with_llm():
    """
    Analizza sessioni fotometriche usando Claude AI per suggerimenti intelligenti.

    Questo endpoint usa LLM per analizzare:
    1. Qualità delle sessioni (noise, gaps, outliers)
    2. Suggerimenti pre-processing (zero-align, detrending, sigma-clipping)
    3. Range ottimale per periodigramma
    4. Classificazione tipo di variabile (se periodigramma disponibile)

    Request:
        Body: Arrow IPC stream con colonne:
            - jd: float64 - Julian Date
            - mag: float64 - Magnitudine
            - session_id: int32 - ID sessione

        Query params (opzionali):
            - has_periodogram: bool - Se true, include analisi periodigramma
            - periods: str - JSON array con periodi trovati (es: "[0.5, 1.0]")
            - amplitudes: str - JSON array con ampiezze (es: "[0.3, 0.1]")

    Returns:
        JSON: Analisi strutturata con suggerimenti e classificazione

    Note:
        - Richiede API key configurata (CEREBRAS_API_KEY/ANTHROPIC_API_KEY/OPENAI_API_KEY)
        - Provider selezionabile via env AI_PROVIDER (default: cerebras)
        - Timeout 30s per chiamata API
    """
    try:
        # ===== INIZIALIZZA CLIENT LLM =====
        try:
            llm_client = LLMClient()
        except ValueError as e:
            logger.error(f"Errore configurazione AI: {e}")
            return jsonify({"error": str(e)}), 500

        # Leggi dati Arrow
        table = read_arrow_table_from_request()

        jd = np.asarray(table["jd"].to_numpy(zero_copy_only=False), dtype=float)
        mag = np.asarray(table["mag"].to_numpy(zero_copy_only=False), dtype=float)
        session_id = np.asarray(table["session_id"].to_numpy(zero_copy_only=False), dtype=np.int32)

        # Parametri opzionali
        has_periodogram = request.args.get("has_periodogram", "false").lower() == "true"
        periods_str = request.args.get("periods", "[]")
        amplitudes_str = request.args.get("amplitudes", "[]")

        try:
            periods = json.loads(periods_str) if periods_str else []
            amplitudes = json.loads(amplitudes_str) if amplitudes_str else []
        except json.JSONDecodeError:
            periods = []
            amplitudes = []

        logger.info(f"AI Advisor: analizzando {len(np.unique(session_id))} sessioni, {len(jd)} punti totali")

        # ===== FASE 1: CALCOLA STATISTICHE PER SESSIONE =====
        session_stats = _compute_session_statistics(jd, mag, session_id)

        # ===== ANALISI OMOGENEITÀ TRA SESSIONI =====
        session_homogeneity = _analyze_session_homogeneity(
            jd, mag, session_id, session_stats, has_periodogram, periods
        )

        # ===== FASE 2: COSTRUISCI PROMPT PER LLM =====
        prompt = _build_llm_prompt(
            jd, mag, session_stats, session_homogeneity,
            has_periodogram, periods, amplitudes
        )

        # ===== FASE 3: CHIAMA LLM API =====
        logger.info("Chiamata LLM API...")

        try:
            llm_response = llm_client.generate(prompt, max_tokens=4096, temperature=0.3)
            response_text = llm_response["response_text"]
            model_used = llm_response["model_used"]
            provider = llm_response["provider"]

            logger.info(f"Risposta AI ricevuta: {len(response_text)} caratteri")

            # Parse JSON
            analysis = _parse_llm_response(response_text)

        except Exception as e:
            logger.error(f"Errore chiamata LLM: {e}", exc_info=True)
            return jsonify({"error": f"Errore comunicazione con AI: {str(e)}"}), 500

        # ===== FASE 4: NORMALIZZA E ARRICCHISCI RISPOSTA =====
        analysis = _normalize_llm_response(analysis)

        result = {
            "analysis": analysis,
            "summary": _generate_summary(analysis),
            "warnings": _extract_warnings(session_stats),
            "homogeneity": session_homogeneity,
            "llm_model": model_used,
            "ai_provider": provider,
            "timestamp": jd.max()
        }

        logger.info("AI Advisor completato con successo")

        return jsonify(result)

    except ValueError as e:
        logger.error(f"Errore validazione AI advisor: {e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Errore AI advisor: {e}", exc_info=True)
        return jsonify({"error": "Errore interno"}), 500


# ==========================================================
# FUNZIONI HELPER INTERNE
# ==========================================================

def _compute_session_statistics(jd, mag, session_id):
    """Calcola statistiche per ogni sessione."""
    session_stats = {}
    unique_sessions = np.unique(session_id)

    for sid in unique_sessions:
        mask = (session_id == sid)
        session_jd = jd[mask]
        session_mag = mag[mask]

        n_points = len(session_mag)

        if n_points < 3:
            session_stats[int(sid)] = {
                "n_points": n_points,
                "quality_score": 0,
                "issues": ["Troppo pochi punti (<3)"]
            }
            continue

        # Statistiche robuste
        median = float(np.median(session_mag))
        mad = float(mad_std(session_mag))
        amplitude = float(np.max(session_mag) - np.min(session_mag))

        # Gaps temporali
        jd_sorted = np.sort(session_jd)
        gaps = np.diff(jd_sorted)
        max_gap = float(np.max(gaps)) if len(gaps) > 0 else 0
        median_gap = float(np.median(gaps)) if len(gaps) > 0 else 0

        # Durata sessione
        duration = float(jd_sorted[-1] - jd_sorted[0])

        # Stima qualità (0-10)
        quality = 10.0
        issues = []

        if n_points < MIN_POINTS_PER_SESSION:
            quality -= 3
            issues.append(f"Pochi punti ({n_points})")

        if mad > 0.2:
            quality -= 2
            issues.append(f"Alto rumore fotometrico (MAD={mad:.3f})")

        if max_gap > 0.5 and max_gap > 3 * median_gap:
            quality -= 1
            issues.append(f"Gap temporali significativi ({max_gap:.2f}d)")

        if duration < 0.1:
            quality -= 1
            issues.append("Sessione molto breve")

        quality = max(0, quality)

        session_stats[int(sid)] = {
            "n_points": n_points,
            "median_mag": median,
            "mad": mad,
            "amplitude": amplitude,
            "duration_days": duration,
            "max_gap_days": max_gap,
            "median_gap_days": median_gap,
            "quality_score": quality,
            "issues": issues
        }

    return session_stats


def _analyze_session_homogeneity(jd, mag, session_id, session_stats, has_periodogram, periods):
    """Analizza omogeneità tra sessioni."""
    unique_sessions = np.unique(session_id)

    if len(unique_sessions) <= 1:
        return {}

    session_medians = {}
    session_mads = {}

    for sid in unique_sessions:
        mask = (session_id == sid)
        session_mag = mag[mask]
        session_medians[int(sid)] = float(np.median(session_mag))
        session_mads[int(sid)] = float(mad_std(session_mag))

    median_values = list(session_medians.values())
    offset_range = float(np.max(median_values) - np.min(median_values))
    offset_std = float(np.std(median_values))

    mad_values = list(session_mads.values())
    mad_ratio = float(np.max(mad_values) / np.min(mad_values)) if np.min(mad_values) > 0 else 0

    # Controllo periodi spurii
    spurious_period_warnings = []
    if has_periodogram and periods:
        for sid in unique_sessions:
            sess_duration = session_stats[int(sid)]["duration_days"]
            for i, period in enumerate(periods[:3]):
                if 0.8 * sess_duration <= period <= 1.2 * sess_duration:
                    spurious_period_warnings.append({
                        "session_id": int(sid),
                        "session_duration": sess_duration,
                        "period": float(period),
                        "period_rank": i + 1,
                        "warning": f"Period {period:.2f}d is suspiciously close to session {sid} duration ({sess_duration:.2f}d)"
                    })

    # Outlier dominanti
    outlier_analysis = {}
    global_mad = float(mad_std(mag))
    for sid in unique_sessions:
        mask = (session_id == sid)
        session_mag = mag[mask]
        session_median = np.median(session_mag)
        outliers = np.abs(session_mag - session_median) > 3 * global_mad
        outlier_fraction = float(np.sum(outliers) / len(session_mag))
        if outlier_fraction > 0.1:
            outlier_analysis[int(sid)] = {
                "outlier_fraction": outlier_fraction,
                "outlier_count": int(np.sum(outliers))
            }

    return {
        "offset_range": offset_range,
        "offset_std": offset_std,
        "mad_ratio": mad_ratio,
        "session_medians": session_medians,
        "session_mads": session_mads,
        "spurious_period_warnings": spurious_period_warnings,
        "outlier_analysis": outlier_analysis
    }


def _build_llm_prompt(jd, mag, session_stats, session_homogeneity, has_periodogram, periods, amplitudes):
    """Costruisce prompt strutturato per LLM."""
    global_median = float(np.median(mag))
    global_amplitude = float(np.max(mag) - np.min(mag))
    total_duration = float(jd.max() - jd.min())

    prompt = f"""You are an expert astronomer analyzing photometric data of a variable star. Provide detailed scientific analysis.

**GLOBAL DATA:**
- Total points: {len(jd)}
- Number of sessions: {len(session_stats)}
- Total duration: {total_duration:.2f} days
- Variation amplitude: {global_amplitude:.3f} mag
- Median magnitude: {global_median:.2f}

**PER-SESSION STATISTICS:**
{json.dumps(session_stats, indent=2)}

**SESSION HOMOGENEITY ANALYSIS:**
{json.dumps(session_homogeneity, indent=2)}
"""

    if has_periodogram and periods:
        prompt += f"""

**PERIODOGRAM ANALYSIS:**
- Found periods (days): {periods[:5]}
- Amplitudes (mag): {amplitudes[:5]}
- Amplitude ratios: {[round(amplitudes[0]/a, 2) if a > 0 else 0 for a in amplitudes[1:3]] if len(amplitudes) > 1 else []}
- Period ratios: {[round(periods[0]/p, 2) if p > 0 else 0 for p in periods[1:3]] if len(periods) > 1 else []}
"""

    prompt += """

**YOUR TASK:**
Provide expert analysis as valid JSON with this EXACT structure:

{
  "session_quality": {
    "overall_score": <float 0-10>,
    "sessions": {
      "0": {
        "score": <float 0-10>,
        "issues": [<list of specific problems>],
        "recommendations": [<list of specific actions>]
      }
    }
  },
  "preprocessing_suggestions": [
    {
      "action": "<zero_align|detrending|sigma_clip|remove_session>",
      "priority": "<high|medium|low>",
      "reason": "<detailed scientific explanation>",
      "parameters": {<suggested parameters>}
    }
  ],
  "periodogram_recommendations": {
    "min_period": <float in days>,
    "max_period": <float in days>,
    "reasoning": "<scientific explanation based on session duration and gaps>"
  }"""

    if has_periodogram and periods:
        prompt += """,
  "variable_classification": {
    "type": "<specific variable star type>",
    "confidence": "<high|medium|low>",
    "reasoning": "<detailed scientific explanation>",
    "alternative_types": [<other possible types>]
  }"""

    prompt += """
}

**CRITICAL GUIDELINES:**
- Analyze EACH session individually with specific numeric scores
- Identify real issues (high MAD, gaps, low points, short duration)
- CHECK SESSION HOMOGENEITY: Look at offset_range, mad_ratio, spurious period warnings
- Suggest actions ONLY if needed (don't suggest if data is good)
- For periodogram range: consider session duration (Nyquist limit ~duration/2)
- Be specific with numbers and thresholds
- FLAG INHOMOGENEOUS SESSIONS: If sessions are not homogeneous, explicitly mention which ones and why

RESPOND ONLY WITH VALID JSON. NO OTHER TEXT BEFORE OR AFTER."""

    return prompt


def _parse_llm_response(response_text):
    """Parse risposta JSON dal LLM."""
    # Rimuovi markdown code blocks
    response_text = response_text.strip()
    if response_text.startswith("```json"):
        response_text = response_text[7:]
    if response_text.startswith("```"):
        response_text = response_text[3:]
    if response_text.endswith("```"):
        response_text = response_text[:-3]
    response_text = response_text.strip()

    return json.loads(response_text)


def _normalize_llm_response(analysis):
    """Normalizza risposta LLM a formato standard."""
    # Normalizza session_quality
    if "session_quality" in analysis:
        sq = analysis["session_quality"]
        if "sessions" not in sq:
            sessions_dict = {}
            overall_scores = []
            for key, value in sq.items():
                if isinstance(value, dict) and "score" in value:
                    sessions_dict[str(key)] = value
                    overall_scores.append(value.get("score", 5))
            analysis["session_quality"] = {
                "overall_score": sum(overall_scores) / len(overall_scores) if overall_scores else 5.0,
                "sessions": sessions_dict
            }

    # Normalizza periodogram_recommendations
    if "periodogram_recommendations" in analysis:
        pr = analysis["periodogram_recommendations"]
        if "period_range" in pr and "min_period" not in pr:
            period_range = pr["period_range"]
            if isinstance(period_range, list) and len(period_range) >= 2:
                pr["min_period"] = float(period_range[0])
                pr["max_period"] = float(period_range[1])
        if "suggestions" in pr and "reasoning" not in pr:
            pr["reasoning"] = pr["suggestions"]
        if "min_period" not in pr:
            pr["min_period"] = 0.1
        if "max_period" not in pr:
            pr["max_period"] = 10.0
        if "reasoning" not in pr:
            pr["reasoning"] = "Range basato sulla durata delle sessioni osservative"

    return analysis


def _generate_summary(analysis):
    """Genera riassunto testuale."""
    try:
        parts = []
        if "session_quality" in analysis:
            sq = analysis["session_quality"]
            if "overall_score" in sq:
                parts.append(f"Qualità globale: {sq['overall_score']:.1f}/10")
        if "preprocessing_suggestions" in analysis:
            high_priority = [s for s in analysis["preprocessing_suggestions"]
                           if s.get("priority") == "high"]
            if high_priority:
                parts.append(f"{len(high_priority)} azioni prioritarie raccomandate")
        if "variable_classification" in analysis:
            vc = analysis["variable_classification"]
            if "type" in vc:
                parts.append(f"Possibile {vc['type']}")
        return " • ".join(parts) if parts else "Analisi completata"
    except Exception as e:
        logger.warning(f"Errore generazione summary: {e}")
        return "Analisi completata"


def _extract_warnings(session_stats):
    """Estrai warning critici."""
    warnings = []
    for sid, stats in session_stats.items():
        if stats.get("quality_score", 10) < 3:
            warnings.append(f"Sessione {sid}: qualità molto bassa")
        if stats.get("n_points", 0) < MIN_POINTS_PER_SESSION:
            warnings.append(f"Sessione {sid}: troppo pochi punti per analisi affidabile")
    return warnings

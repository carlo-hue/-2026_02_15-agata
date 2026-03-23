"""
Regole di Validazione per Variabili Stellari

Contiene:
- Requisiti identificatori per tipo variabile
- Cataloghi raccomandati per tipo variabile
- Requisiti precisione periodo
- Quality checks per campi specifici

Usate come fallback quando KB non disponibile o vuoto.
Aggiornate periodicamente da email/documenti nel KB.
"""

import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# =============================================================================
# REQUISITI IDENTIFICATORI
# =============================================================================

IDENTIFIER_REQUIREMENTS: Dict[str, Dict[str, List[str]]] = {
    "RR Lyrae": {
        "required": ["gaia_id"],
        "recommended": ["vsx_id", "aavso_id"],
        "optional": ["2mass_id", "gcvs_name"]
    },
    "Cepheid": {
        "required": ["gaia_id"],
        "recommended": ["vsx_id", "gcvs_name", "aavso_id"],
        "optional": ["2mass_id", "hipparcos_id"]
    },
    "Eclipsing Binary": {
        "required": ["gaia_id"],
        "recommended": ["vsx_id", "aavso_id"],
        "optional": ["2mass_id"]
    },
    "Mira": {
        "required": ["gaia_id"],
        "recommended": ["vsx_id", "gcvs_name", "aavso_id"],
        "optional": ["hipparcos_id", "tycho_id"]
    },
    "Semi-Detached": {
        "required": ["gaia_id"],
        "recommended": ["vsx_id", "aavso_id"],
        "optional": ["2mass_id"]
    },
    "LPV": {
        "required": ["gaia_id"],
        "recommended": ["vsx_id", "aavso_id"],
        "optional": ["2mass_id"]
    },
    "Delta Cephei": {
        "required": ["gaia_id"],
        "recommended": ["vsx_id", "gcvs_name"],
        "optional": ["aavso_id", "hipparcos_id"]
    },
    "Beta Lyrae": {
        "required": ["gaia_id"],
        "recommended": ["vsx_id", "aavso_id"],
        "optional": ["hipparcos_id", "tycho_id"]
    }
}

# =============================================================================
# CATALOGHI RACCOMANDATI PER TIPO VARIABILE
# =============================================================================

CATALOG_RECOMMENDATIONS: Dict[str, List[Dict[str, Any]]] = {
    "RR Lyrae": [
        {
            "catalog": "ZTF",
            "priority": "high",
            "reason": "ZTF fornisce curve di luce multi-banda (g, r, i) per RR Lyrae con cadenza ottimale (~3 giorni)",
            "notes": "Coverage: interi cielo settentrionale, declinazione > -30°"
        },
        {
            "catalog": "OGLE",
            "priority": "high",
            "reason": "OGLE ha survey specifici in bulge galattico e Magellanic Clouds con cadenza giornaliera",
            "notes": "Survey: LMC, SMC, Bulge, Magellanic Stream"
        },
        {
            "catalog": "ASAS-SN",
            "priority": "medium",
            "reason": "ASAS-SN fornisce dati long-term per verificare la stabilità del periodo",
            "notes": "Visibilità nord/sud dell'equatore"
        },
        {
            "catalog": "Gaia",
            "priority": "medium",
            "reason": "Gaia fornisce coordinate precise e magnitudini di riferimento",
            "notes": "Already consulted for most cases"
        }
    ],
    "Cepheid": [
        {
            "catalog": "HST",
            "priority": "high",
            "reason": "HST fornisce fotometria ad alta risoluzione spaziale per Cefeidi in galaxie esterne",
            "notes": "Specifico per Cefeidi extragalattiche"
        },
        {
            "catalog": "ZTF",
            "priority": "high",
            "reason": "ZTF ha buona cobertura temporale per periodi Cepheid (1-100 giorni)",
            "notes": "Multi-banda per studi di colore"
        },
        {
            "catalog": "OGLE",
            "priority": "medium",
            "reason": "OGLE survey contiene Cefeidi nel Magellanic Clouds",
            "notes": "Survey LMC/SMC"
        },
        {
            "catalog": "Gaia",
            "priority": "medium",
            "reason": "Parallassi per Cefeidi galattiche per calibrazione periodo-luminosità",
            "notes": "Essenziale per Cefeidi galattiche"
        }
    ],
    "Eclipsing Binary": [
        {
            "catalog": "TESS",
            "priority": "high",
            "reason": "TESS fornisce fotometria ad alta precisione con cadenza 30-min per eclissi",
            "notes": "Coverage: 85% del cielo, magn. limite ~16 in banda TESS"
        },
        {
            "catalog": "ASAS-SN",
            "priority": "high",
            "reason": "ASAS-SN ha buona cadenza (1-4 giorni) per eclissi",
            "notes": "Coverage universale nord/sud"
        },
        {
            "catalog": "ZTF",
            "priority": "medium",
            "reason": "ZTF fornisce dati supplementari per eclissi con periodo > 2 giorni",
            "notes": "Multi-banda per classificazione spettrale"
        }
    ],
    "Mira": [
        {
            "catalog": "OGLE",
            "priority": "high",
            "reason": "OGLE ha eccellente cobertura per Mire con periodi lunghi (100-500 giorni)",
            "notes": "Survey Bulge e Magellanic Clouds"
        },
        {
            "catalog": "ASAS-SN",
            "priority": "high",
            "reason": "ASAS-SN ha buona cobertura temporale per monitoraggio Mire",
            "notes": "Coverage universale"
        },
        {
            "catalog": "Gaia",
            "priority": "medium",
            "reason": "Gaia coordinate e magnitudini riferimento",
            "notes": "Parallassi disponibili per alcune Mire"
        }
    ],
    "LPV": [
        {
            "catalog": "OGLE",
            "priority": "high",
            "reason": "OGLE eccellente per LPV (periodi lunghi e variabilità complessa)",
            "notes": "Survey dedicate nei survey principali"
        },
        {
            "catalog": "ASAS-SN",
            "priority": "high",
            "reason": "ASAS-SN fornisce dati long-term",
            "notes": "Coverage universale"
        },
        {
            "catalog": "Gaia",
            "priority": "medium",
            "reason": "Coordinate e magnitudini",
            "notes": "Parallassi per some LPV"
        }
    ],
    "Delta Cephei": [
        {
            "catalog": "ZTF",
            "priority": "high",
            "reason": "ZTF ottimo per Delta Cephei (periodi 1-10 giorni)",
            "notes": "Multi-banda fondamentale"
        },
        {
            "catalog": "ASAS-SN",
            "priority": "medium",
            "reason": "ASAS-SN verifica stabilità",
            "notes": "Coverage universale"
        },
        {
            "catalog": "Gaia",
            "priority": "medium",
            "reason": "Coordinate precise",
            "notes": "Parallassi per calibrazione P-L"
        }
    ],
    "Eclipsing Binary": [
        {
            "catalog": "TESS",
            "priority": "high",
            "reason": "TESS fotometria ad alta precisione per eclissi",
            "notes": "Coverage 85% cielo"
        },
        {
            "catalog": "ASAS-SN",
            "priority": "high",
            "reason": "ASAS-SN monitoraggio long-term",
            "notes": "Coverage universale"
        }
    ],
    "Beta Lyrae": [
        {
            "catalog": "TESS",
            "priority": "high",
            "reason": "TESS ad alta precisione per eclissi",
            "notes": "Coverage e sensibilità ottimali"
        },
        {
            "catalog": "ZTF",
            "priority": "medium",
            "reason": "ZTF supplementari",
            "notes": "Multi-banda"
        }
    ]
}

# =============================================================================
# REQUISITI PRECISIONE PERIODO
# =============================================================================

PERIOD_PRECISION_REQUIREMENTS: Dict[str, Dict[str, Any]] = {
    "RR Lyrae": {
        "required_precision_days": 0.00001,  # ~1 secondo
        "notes": "AAVSO richiede ±0.00001 d per accuratezza sottomissione",
        "source": "AAVSO RR Lyrae Guidelines"
    },
    "Cepheid": {
        "required_precision_days": 0.0001,  # ~10 secondi
        "notes": "Precisione per calibrazione P-L",
        "source": "AAVSO Cepheid Guidelines"
    },
    "Eclipsing Binary": {
        "required_precision_days": 0.000001,  # ~0.1 secondi
        "notes": "Essenziale per predizioni eclissi",
        "source": "AAVSO EB Guidelines"
    },
    "Mira": {
        "required_precision_days": 1.0,  # 1 giorno OK
        "notes": "Periodi lunghi consentono bassa precisione relativa",
        "source": "AAVSO Mira Guidelines"
    },
    "LPV": {
        "required_precision_days": 1.0,
        "notes": "Variabilità complessa, precisione meno critica",
        "source": "AAVSO LPV Guidelines"
    },
    "Delta Cephei": {
        "required_precision_days": 0.0001,
        "notes": "Come Cepheid clasico",
        "source": "AAVSO Delta Cephei Guidelines"
    },
    "Semi-Detached": {
        "required_precision_days": 0.000001,
        "notes": "Simile a eclissi",
        "source": "AAVSO Semi-Detached Guidelines"
    },
    "Beta Lyrae": {
        "required_precision_days": 0.000001,
        "notes": "Sistema continuo",
        "source": "AAVSO Beta Lyrae Guidelines"
    }
}

# =============================================================================
# QUALITY CHECKS PER CAMPI SPECIFICI
# =============================================================================

AMPLITUDE_RANGES: Dict[str, Dict[str, float]] = {
    "RR Lyrae": {
        "min": 0.3,
        "max": 2.0,
        "typical": 1.0,
        "notes": "Ampiezza in bande V, tipicamente 0.5-1.5 mag"
    },
    "Cepheid": {
        "min": 0.2,
        "max": 2.0,
        "typical": 1.0,
        "notes": "Ampiezza cresce con periodo"
    },
    "Eclipsing Binary": {
        "min": 0.01,
        "max": 5.0,
        "typical": 1.0,
        "notes": "Dipende da rapporto luminosità"
    },
    "Mira": {
        "min": 2.5,
        "max": 11.0,
        "typical": 6.0,
        "notes": "Mire hanno ampiezze molto grandi"
    },
    "LPV": {
        "min": 0.5,
        "max": 5.0,
        "typical": 2.0,
        "notes": "Semi-variabili e LPV"
    }
}

# =============================================================================
# FUNZIONI DI UTILITÀ
# =============================================================================

def get_identifiers_for_type(variable_type: str) -> Optional[Dict[str, List[str]]]:
    """Restituisce requisiti identificatori per tipo variabile"""
    return IDENTIFIER_REQUIREMENTS.get(variable_type)


def get_catalogs_for_type(variable_type: str) -> List[Dict[str, Any]]:
    """Restituisce cataloghi raccomandati per tipo variabile"""
    return CATALOG_RECOMMENDATIONS.get(variable_type, [])


def get_period_precision_for_type(variable_type: str) -> Optional[Dict[str, Any]]:
    """Restituisce requisiti precisione periodo per tipo variabile"""
    return PERIOD_PRECISION_REQUIREMENTS.get(variable_type)


def get_amplitude_range_for_type(variable_type: str) -> Optional[Dict[str, float]]:
    """Restituisce range ampiezza atteso per tipo variabile"""
    return AMPLITUDE_RANGES.get(variable_type)


def check_amplitude_ok(variable_type: str, amplitude: float) -> tuple[bool, str]:
    """
    Valida se ampiezza è nel range atteso

    Returns:
        (valid: bool, message: str)
    """
    amplitude_info = get_amplitude_range_for_type(variable_type)
    if not amplitude_info:
        return True, "Nessun requisito ampiezza noto per questo tipo"

    if amplitude < amplitude_info["min"]:
        return False, f"Ampiezza {amplitude} mag è inferiore al minimo atteso ({amplitude_info['min']} mag) per {variable_type}"

    if amplitude > amplitude_info["max"]:
        return False, f"Ampiezza {amplitude} mag è superiore al massimo atteso ({amplitude_info['max']} mag) per {variable_type}"

    return True, f"Ampiezza {amplitude} mag compatibile con {variable_type}"


def missing_identifiers_for_type(variable_type: str, provided_ids: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Identifica quali identificatori mancano

    Args:
        variable_type: tipo variabile
        provided_ids: dict con valori attuali di identificatori

    Returns:
        Lista di identificatori mancanti con severity
    """
    reqs = get_identifiers_for_type(variable_type)
    if not reqs:
        return []

    missing = []

    # Check required identifiers
    for id_field in reqs.get("required", []):
        if not provided_ids.get(id_field):
            missing.append({
                "field": id_field,
                "severity": "error",
                "message": f"{id_field} è OBBLIGATORIO per {variable_type}",
                "how_to_find": _get_how_to_find_id(id_field),
                "source": "Requisiti AAVSO/VSX"
            })

    # Check recommended identifiers
    for id_field in reqs.get("recommended", []):
        if not provided_ids.get(id_field):
            missing.append({
                "field": id_field,
                "severity": "warning",
                "message": f"{id_field} mancante - fortemente raccomandato per pubblicazione",
                "how_to_find": _get_how_to_find_id(id_field),
                "source": "Best practices AAVSO"
            })

    return missing


def recommended_catalogs_not_consulted(
    variable_type: str,
    catalogs_already_consulted: List[str]
) -> List[Dict[str, Any]]:
    """
    Filtra cataloghi raccomandati escludendo quelli già consultati

    Args:
        variable_type: tipo variabile
        catalogs_already_consulted: lista cataloghi già usati

    Returns:
        Lista cataloghi raccomandati non ancora consultati
    """
    recommendations = get_catalogs_for_type(variable_type)
    result = []

    for rec in recommendations:
        if rec["catalog"] not in catalogs_already_consulted:
            result.append(rec)

    return result


def validate_period_precision(
    variable_type: str,
    period: float,
    period_precision: float
) -> Dict[str, Any]:
    """
    Valida se precisione periodo è adeguata per tipo variabile

    Args:
        variable_type: tipo variabile
        period: periodo in giorni
        period_precision: incertezza periodo in giorni

    Returns:
        Dict con validità e dettagli
    """
    reqs = get_period_precision_for_type(variable_type)

    if not reqs:
        return {
            "valid": True,
            "message": "Nessun requisito precisione noto per questo tipo",
            "source": "Unknown"
        }

    required = reqs["required_precision_days"]

    if period_precision > required:
        return {
            "valid": False,
            "message": f"Precisione periodo ({period_precision:.2e} d) insufficiente per {variable_type}. Richiesto: ≤{required:.2e} d",
            "required_precision": required,
            "current_precision": period_precision,
            "relative_error": (period_precision / period) * 100,
            "source": reqs.get("source", "AAVSO Guidelines"),
            "suggested_action": _suggest_period_improvement(variable_type, period, period_precision, required)
        }

    return {
        "valid": True,
        "message": f"Precisione periodo ({period_precision:.2e} d) adeguata per {variable_type}",
        "required_precision": required,
        "current_precision": period_precision,
        "relative_error": (period_precision / period) * 100,
        "source": reqs.get("source", "AAVSO Guidelines")
    }


# =============================================================================
# FUNZIONI HELPER PRIVATE
# =============================================================================

def _get_how_to_find_id(id_field: str) -> str:
    """Suggerimenti su come trovare identificatore"""
    tips = {
        "vsx_id": "Cerca in VSX (https://www.aavso.org/vsx) usando coordinate RA/Dec",
        "aavso_id": "Contatta AAVSO o cerca in database AAVSO International Database",
        "gaia_id": "Usa Gaia DR3 Query (ESA) con coordinate RA/Dec. Dovrebbe essere già presente.",
        "2mass_id": "Cerca nel 2MASS All-Sky Data Release Catalog usando coordinate",
        "gcvs_name": "Cerca nel GCVS (General Catalogue of Variable Stars) per nome o coordinate",
        "hipparcos_id": "Per stelle brillanti, controlla catalogo Hipparcos (ESA)",
        "tycho_id": "Catalogo Tycho-2 per stelle brillanti"
    }
    return tips.get(id_field, "Contatta l'assistenza")


def _suggest_period_improvement(
    variable_type: str,
    period: float,
    current_precision: float,
    required_precision: float
) -> str:
    """Suggerisce come migliorare la precisione del periodo"""

    improvement_needed = current_precision / required_precision

    if improvement_needed < 10:
        return (
            f"La precisione deve migliorare di ~{improvement_needed:.0f}x. "
            f"Prova: (1) analisi con più epoche, (2) fitting polinomiale, (3) algoritmi avanzati (phase fitting, template matching)"
        )
    elif improvement_needed < 100:
        return (
            f"Miglioramento significativo necessario (~{improvement_needed:.0f}x). "
            f"Consigliato: usare software specializzato (MOPEX, Period04, Fourier) con dati a cadenza elevata"
        )
    else:
        return (
            f"Precisione attuale è {improvement_needed:.0f}x peggiore del richiesto. "
            f"Raccomandata ranalisi completa con metodi avanzati e data set espanso"
        )


# =============================================================================
# CALCOLO SCORE VALIDAZIONE
# =============================================================================

def calculate_validation_score(
    variable_type: str,
    missing_identifiers: List[Dict[str, Any]],
    missing_catalogs: List[Dict[str, Any]],
    period_precision_valid: bool,
    amplitude_valid: bool = True
) -> int:
    """
    Calcola score complessivo validazione (0-100)

    Scoring:
    - Base: 100
    - Missing required ID: -20 points each
    - Missing recommended ID: -5 points each
    - Missing high-priority catalog: -10 points each
    - Missing medium-priority catalog: -5 points each
    - Period precision invalid: -20 points
    - Amplitude invalid: -10 points
    """
    score = 100

    for missing_id in missing_identifiers:
        if missing_id["severity"] == "error":
            score -= 20
        elif missing_id["severity"] == "warning":
            score -= 5

    for missing_cat in missing_catalogs:
        if missing_cat["priority"] == "high":
            score -= 10
        elif missing_cat["priority"] == "medium":
            score -= 5

    if not period_precision_valid:
        score -= 20

    if not amplitude_valid:
        score -= 10

    return max(0, score)  # Minimum 0

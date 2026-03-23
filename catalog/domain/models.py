from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from .enums import CatalogStatus, Context, EventType, MatchStrategy


# -----------------------------
# Registry (configurazione)
# -----------------------------

@dataclass(frozen=True)
class CatalogDefinition:
    """
    Definizione tecnica di un catalogo interrogabile.
    """
    catalog_id: str                     # es. "I/355/gaiaedr3"
    provider: str                       # es. "vizier"
    label: str                          # es. "Gaia EDR3"
    match_strategy: MatchStrategy       # source_id / ra_dec_cone
    default_radius_arcsec: Optional[float] = None
    enabled: bool = True


@dataclass(frozen=True)
class ContextCatalogConfig:
    """
    Configurazione del catalogo nel contesto (mapping catalogo↔contesto).
    """
    context: Context
    catalog_id: str
    enabled_in_context: bool = True
    condition_of_use: Optional[str] = None
    priority: int = 100


@dataclass(frozen=True)
class AttributeConfig:
    """
    Attributo selezionato per (contesto, catalogo).
    """
    context: Context
    catalog_id: str
    attribute_name: str                 # nome colonna su Vizier (o virtual)
    label: Optional[str] = None
    description: Optional[str] = None
    unit: Optional[str] = None
    recommended: bool = True
    position: int = 100
    transform: Optional[str] = None     # es. "Vmag_calc" o espressione futura
    virtual: bool = False               # True se derivato/non presente nel catalogo


# -----------------------------
# Cache (risultati)
# -----------------------------

@dataclass(frozen=True)
class CacheEntry:
    """
    Cache per (gaia_id, context, catalog_id).
    payload: risultato normalizzato della query per quel catalogo nel contesto.
    """
    gaia_id: str
    context: Context
    catalog_id: str

    match_strategy: MatchStrategy
    resolved_ra_deg: Optional[float] = None
    resolved_dec_deg: Optional[float] = None
    radius_arcsec: Optional[float] = None

    status: CatalogStatus = CatalogStatus.OK
    matches_count: int = 0
    selected_index: Optional[int] = None
    d2d_arcsec: Optional[List[float]] = None

    payload: Dict[str, Any] = field(default_factory=dict)

    fetched_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


# -----------------------------
# Event log (audit/diagnostica)
# -----------------------------

@dataclass(frozen=True)
class QueryEvent:
    """
    Evento di audit/diagnostica. Non contiene i dati scientifici (solo log).
    """
    request_id: str
    event_type: EventType

    gaia_id: Optional[str] = None
    context: Optional[Context] = None
    catalog_id: Optional[str] = None

    duration_ms: Optional[int] = None
    http_status: Optional[int] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    created_at: datetime = field(default_factory=datetime.utcnow)


# -----------------------------
# Utility per svuota cache
# -----------------------------

@dataclass(frozen=True)
class CacheClearFilters:
    """
    Filtri per la cancellazione/invalidation della cache.
    Se tutti i campi sono None e wipe_all=True => wipe globale.
    """
    gaia_id: Optional[str] = None
    context: Optional[Context] = None
    catalog_id: Optional[str] = None
    expired_only: bool = False
    wipe_all: bool = False

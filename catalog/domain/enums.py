from enum import Enum


class Context(str, Enum):
    """
    Contesti informativi supportati dal sistema.
    """
    IDENTIFICATIVI = "identificativi"
    PARAMETRI_FISICI = "parametri_fisici"
    MAGNITUDINE = "magnitudine"
    TIPO_SPETTRALE = "tipo_spettrale"
    VARIABILITA_NOTA = "variabilita_nota"
    ALL = "all"


class MatchStrategy(str, Enum):
    """
    Strategia di match per il catalogo.
    """
    SOURCE_ID = "source_id"
    RA_DEC_CONE = "ra_dec_cone"


class CatalogStatus(str, Enum):
    """
    Stato del risultato per un singolo catalogo.
    """
    OK = "ok"
    NO_MATCH = "no_match"
    MULTI_MATCH = "multi_match"
    AMBIGUOUS_MATCH = "ambiguous_match"
    TIMEOUT = "timeout"
    ERROR = "error"
    SKIPPED = "skipped"
    STALE_CACHE = "stale_cache"


class RequestStatus(str, Enum):
    """
    Stato complessivo della richiesta.
    """
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class EventType(str, Enum):
    """
    Tipologia di evento per audit e diagnostica.
    """
    FETCH_OK = "fetch_ok"
    FETCH_NO_MATCH = "fetch_no_match"
    FETCH_TIMEOUT = "fetch_timeout"
    FETCH_ERROR = "fetch_error"

    USED_CACHE = "used_cache"
    USED_STALE_CACHE = "used_stale_cache"

    REFRESH_FORCED = "refresh_forced"
    SKIPPED_POLICY = "skipped_policy"
    SKIPPED_GLOBAL_TIMEOUT = "skipped_global_timeout"


class UserRole(str, Enum):
    """
    Ruoli applicativi.
    """
    SUPERUSER = "superuser"
    ADMIN = "admin"
    USER = "user"

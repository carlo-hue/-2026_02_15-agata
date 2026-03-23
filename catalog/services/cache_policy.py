from datetime import datetime, timedelta

from agata.catalog.domain.enums import CatalogStatus
from agata.catalog.domain.models import CacheEntry


# TTL default (giorni)
TTL_OK_DAYS = 180
TTL_NO_MATCH_DAYS = 365


def compute_expiration(entry: CacheEntry, now: datetime | None = None) -> CacheEntry:
    """
    Calcola expires_at in base allo stato del risultato.
    """
    now = now or datetime.utcnow()

    if entry.status == CatalogStatus.NO_MATCH:
        expires = now + timedelta(days=TTL_NO_MATCH_DAYS)
    else:
        expires = now + timedelta(days=TTL_OK_DAYS)

    return CacheEntry(
        **{**entry.__dict__, "fetched_at": now, "expires_at": expires}
    )


def is_expired(entry: CacheEntry, now: datetime | None = None) -> bool:
    """
    True se la cache è scaduta.
    """
    if entry.expires_at is None:
        return True
    now = now or datetime.utcnow()
    return entry.expires_at < now


def should_overwrite(existing: CacheEntry, incoming: CacheEntry) -> bool:
    """
    Decide se una nuova entry può sovrascrivere una cache esistente.
    Regola chiave: error/timeout NON sovrascrivono una cache buona.
    """
    if incoming.status in (CatalogStatus.ERROR, CatalogStatus.TIMEOUT):
        return False
    return True

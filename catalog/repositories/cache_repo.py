from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from agata.catalog.domain.enums import Context
from agata.catalog.domain.models import CacheClearFilters, CacheEntry


class InMemoryCacheRepo:
    """
    Stub in-memory per cache (tabella catalog_query_cache).
    Chiave logica: (gaia_id, context, catalog_id)
    """

    def __init__(self) -> None:
        self._store: Dict[tuple[str, str, str], CacheEntry] = {}

    def get_cache(self, gaia_id: str, context: Context, catalog_id: str) -> Optional[CacheEntry]:
        return self._store.get((gaia_id, context.value, catalog_id))

    def upsert_cache(self, entry: CacheEntry) -> None:
        self._store[(entry.gaia_id, entry.context.value, entry.catalog_id)] = entry

    def delete_cache(self, filters: CacheClearFilters, now: Optional[datetime] = None) -> int:
        """
        Cancella cache secondo filtri. Supporta wipe globale.
        expired_only=True cancella solo record con expires_at < now.
        """
        now = now or datetime.utcnow()

        if filters.wipe_all:
            keys = list(self._store.keys())
            if filters.expired_only:
                keys = [
                    k for k in keys
                    if (self._store[k].expires_at is not None and self._store[k].expires_at < now)
                ]
            for k in keys:
                del self._store[k]
            return len(keys)

        to_delete = []
        for (gaia_id, ctx, cat_id), entry in self._store.items():
            if filters.gaia_id is not None and gaia_id != filters.gaia_id:
                continue
            if filters.context is not None and ctx != filters.context.value:
                continue
            if filters.catalog_id is not None and cat_id != filters.catalog_id:
                continue
            if filters.expired_only:
                if entry.expires_at is None or entry.expires_at >= now:
                    continue
            to_delete.append((gaia_id, ctx, cat_id))

        for k in to_delete:
            del self._store[k]
        return len(to_delete)

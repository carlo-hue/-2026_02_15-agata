from __future__ import annotations

from dataclasses import replace
from typing import Dict, List, Optional

from agata.catalog.domain.enums import Context
from agata.catalog.domain.models import (
    AttributeConfig,
    CatalogDefinition,
    ContextCatalogConfig,
)


class InMemoryRegistryRepo:
    """
    Stub in-memory per registry (cataloghi, mapping contesti, attributi).
    In fase 2 verrà sostituito dall'implementazione su DB AGATA.
    """

    def __init__(self) -> None:
        self._catalogs: Dict[str, CatalogDefinition] = {}
        self._context_catalog: Dict[tuple[str, str], ContextCatalogConfig] = {}
        self._attributes: Dict[tuple[str, str], List[AttributeConfig]] = {}

    # ----------------------------
    # Read
    # ----------------------------

    def list_contexts(self) -> List[Context]:
        contexts = {cfg.context for cfg in self._context_catalog.values()}
        # includo solo quelli realmente presenti
        return sorted(contexts, key=lambda c: c.value)

    def get_catalog_definition(self, catalog_id: str) -> Optional[CatalogDefinition]:
        return self._catalogs.get(catalog_id)

    def get_catalogs_for_context(self, context: Context, include_disabled: bool = False) -> List[ContextCatalogConfig]:
        items = [
            cfg for (ctx, _), cfg in self._context_catalog.items()
            if ctx == context.value
        ]
        if not include_disabled:
            items = [cfg for cfg in items if cfg.enabled_in_context]
        return sorted(items, key=lambda x: x.priority)

    def get_attributes_for_context_catalog(self, context: Context, catalog_id: str) -> List[AttributeConfig]:
        attrs = self._attributes.get((context.value, catalog_id), [])
        return sorted(attrs, key=lambda a: a.position)

    # ----------------------------
    # Write (superuser)
    # ----------------------------

    def upsert_catalog_definition(self, defn: CatalogDefinition) -> None:
        self._catalogs[defn.catalog_id] = defn

    def set_catalog_in_context(self, cfg: ContextCatalogConfig) -> None:
        self._context_catalog[(cfg.context.value, cfg.catalog_id)] = cfg

    def set_attributes_for_context_catalog(self, context: Context, catalog_id: str, attrs: List[AttributeConfig]) -> None:
        # Normalizza: forza context/catalog_id coerenti
        normalized: List[AttributeConfig] = []
        for a in attrs:
            if a.context != context or a.catalog_id != catalog_id:
                normalized.append(replace(a, context=context, catalog_id=catalog_id))
            else:
                normalized.append(a)
        self._attributes[(context.value, catalog_id)] = normalized

    # ----------------------------
    # Seed helper (facoltativo)
    # ----------------------------

    def seed_minimal(self) -> None:
        """
        Carica un minimo di configurazione per fare smoke test.
        Modifica liberamente o rimuovi.
        """
        # Esempio: Gaia DR3 come catalogo "source_id" in identificativi
        gaia = CatalogDefinition(
            catalog_id="I/355/gaiadr3",
            provider="vizier",
            label="Gaia DR3",
            match_strategy="source_id",  # accetta anche str, ma consigliato usare Enum nel seed se preferisci
            default_radius_arcsec=None,
            enabled=True,
        )
        # Nota: se vuoi evitare stringhe, crea usando MatchStrategy.SOURCE_ID.
        self.upsert_catalog_definition(gaia)  # type: ignore[arg-type]

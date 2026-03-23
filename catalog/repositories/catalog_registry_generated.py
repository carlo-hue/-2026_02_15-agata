from __future__ import annotations

import csv
import os
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Tuple

from agata.catalog.domain.enums import Context, MatchStrategy
from agata.catalog.domain.models import AttributeConfig, CatalogDefinition, ContextCatalogConfig


CSV_FILENAME = "cataloghi_gvt.csv"
CSV_PATH = Path(
    os.getenv("CATALOGS_CSV_PATH", str(Path(__file__).resolve().parents[1] / CSV_FILENAME))
)


def _read_csv_rows(path: Path) -> List[Dict[str, str]]:
    encodings = ("utf-8-sig", "utf-8", "cp1252")
    last_exc: Exception | None = None

    for encoding in encodings:
        try:
            with path.open("r", encoding=encoding, newline="") as f:
                reader = csv.DictReader(f, delimiter=";")
                return [dict(row) for row in reader]
        except Exception as exc:  # pragma: no cover - fallback chain
            last_exc = exc
            continue

    raise RuntimeError(f"Cannot read CSV file: {path}") from last_exc


def _clean(value: str | None) -> str:
    if value is None:
        return ""
    return value.strip().strip('"').strip()


def _normalize_col_name(name: str) -> str:
    return (
        (name or "")
        .lower()
        .replace("\u2019", "'")
        .replace("â€™", "'")
        .strip()
    )


def _get_field(raw: Dict[str, str], *candidate_names: str) -> str:
    normalized_candidates = {_normalize_col_name(name) for name in candidate_names}
    for key, value in raw.items():
        if _normalize_col_name(key) in normalized_candidates:
            return _clean(value)
    return ""


def _to_match_strategy(match_key: str) -> MatchStrategy:
    lowered = match_key.lower()
    if "ra/dec" in lowered or "cone" in lowered:
        return MatchStrategy.RA_DEC_CONE
    return MatchStrategy.SOURCE_ID


def _build_registry(rows: List[Dict[str, str]]) -> tuple[Dict[str, Dict[str, Any]], Dict[str, List[str]]]:
    catalog_registry: Dict[str, Dict[str, Any]] = {}
    context_rows: Dict[str, List[Tuple[int, str]]] = {}

    for idx, raw in enumerate(rows, start=1):
        context = _get_field(raw, "contesto")
        catalog_id = _get_field(raw, "catalogo")
        attribute = _get_field(raw, "attributi")
        reference = _get_field(raw, "reference")
        comment = _get_field(raw, "commento")
        source = _get_field(raw, "fonte")
        usage = _get_field(raw, "condizione d'uso", "condizione d\u2019uso")
        match_key = _get_field(raw, "chiave_match")

        if not context or not catalog_id:
            continue

        catalog = catalog_registry.setdefault(
            catalog_id,
            {
                "enabled": True,
                "source": source or "tab_validi",
                "match_key": match_key or "RA/DEC cone",
                "contexts": {},
            },
        )

        if source and not catalog.get("source"):
            catalog["source"] = source
        if match_key and not catalog.get("match_key"):
            catalog["match_key"] = match_key

        contexts = catalog["contexts"]
        context_def = contexts.setdefault(
            context,
            {
                "attributes": [],
                "references": [],
                "comments": [],
                "usage_conditions": [],
                "order": idx,
            },
        )

        if attribute and attribute not in context_def["attributes"]:
            context_def["attributes"].append(attribute)
        if reference and reference not in context_def["references"]:
            context_def["references"].append(reference)
        if comment and comment not in context_def["comments"]:
            context_def["comments"].append(comment)
        if usage and usage not in context_def["usage_conditions"]:
            context_def["usage_conditions"].append(usage)

        context_rows.setdefault(context, []).append((int(context_def["order"]), catalog_id))

    context_to_catalogs: Dict[str, List[str]] = {}
    for context, rows_for_context in context_rows.items():
        rows_sorted = sorted(rows_for_context, key=lambda r: r[0])
        ordered_unique = OrderedDict((catalog_id, None) for _, catalog_id in rows_sorted)
        context_to_catalogs[context] = list(ordered_unique.keys())

    all_ids = OrderedDict()
    for context in sorted(context_to_catalogs.keys()):
        for catalog_id in context_to_catalogs[context]:
            all_ids[catalog_id] = None
    context_to_catalogs["all"] = list(all_ids.keys())

    return catalog_registry, context_to_catalogs


if CSV_PATH.exists():
    _ROWS = _read_csv_rows(CSV_PATH)
else:
    _ROWS = []

CATALOG_REGISTRY, CONTEXT_TO_CATALOGS = _build_registry(_ROWS)


def get_catalog_ids_for_context(context: str) -> List[str]:
    return list(CONTEXT_TO_CATALOGS.get(context, []))


def iter_catalog_defs_for_context(context: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for catalog_id in get_catalog_ids_for_context(context):
        catalog = CATALOG_REGISTRY.get(catalog_id)
        if not catalog:
            continue
        out.append({"catalog_id": catalog_id, **catalog})
    return out


def reload_catalog_registry() -> Dict[str, int]:
    """
    Reload CSV data from disk and rebuild in-memory registry maps.
    """
    global _ROWS, CATALOG_REGISTRY, CONTEXT_TO_CATALOGS

    if CSV_PATH.exists():
        _ROWS = _read_csv_rows(CSV_PATH)
    else:
        _ROWS = []

    CATALOG_REGISTRY, CONTEXT_TO_CATALOGS = _build_registry(_ROWS)

    return {
        "rows": len(_ROWS),
        "catalogs": len(CATALOG_REGISTRY),
        "contexts": len([c for c in CONTEXT_TO_CATALOGS.keys() if c != "all"]),
        "all_catalogs": len(CONTEXT_TO_CATALOGS.get("all", [])),
    }


def apply_registry_to_repo(registry_repo: Any) -> int:
    """
    Load catalog/context/attribute configuration into an InMemoryRegistryRepo-like object.
    Returns the number of configured (context, catalog) pairs.
    """
    loaded = 0

    for catalog_id, catalog_def in CATALOG_REGISTRY.items():
        match_strategy = _to_match_strategy(str(catalog_def.get("match_key", "")))
        registry_repo.upsert_catalog_definition(
            CatalogDefinition(
                catalog_id=catalog_id,
                provider=str(catalog_def.get("source") or "vizier").lower(),
                label=catalog_id,
                match_strategy=match_strategy,
                enabled=bool(catalog_def.get("enabled", True)),
            )
        )

        contexts = catalog_def.get("contexts", {})
        for context_name, context_def in contexts.items():
            try:
                context_enum = Context(context_name)
            except ValueError:
                continue

            registry_repo.set_catalog_in_context(
                ContextCatalogConfig(
                    context=context_enum,
                    catalog_id=catalog_id,
                    enabled_in_context=bool(catalog_def.get("enabled", True)),
                    condition_of_use="; ".join(context_def.get("usage_conditions", [])) or None,
                    priority=int(context_def.get("order", 100)),
                )
            )

            attrs = [
                AttributeConfig(
                    context=context_enum,
                    catalog_id=catalog_id,
                    attribute_name=attr_name,
                    position=pos,
                )
                for pos, attr_name in enumerate(context_def.get("attributes", []), start=1)
            ]
            registry_repo.set_attributes_for_context_catalog(context_enum, catalog_id, attrs)
            loaded += 1

    return loaded

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from agata.catalog.domain.enums import CatalogStatus, Context, EventType, MatchStrategy, RequestStatus, UserRole
from agata.catalog.domain.models import CacheEntry, QueryEvent
from agata.catalog.repositories.cache_repo import InMemoryCacheRepo
from agata.catalog.repositories.events_repo import InMemoryEventsRepo
from agata.catalog.repositories.registry_repo import InMemoryRegistryRepo
from agata.catalog.repositories.catalog_registry_generated import get_catalog_ids_for_context
from agata.catalog.services.cache_policy import compute_expiration, is_expired, should_overwrite

from agata.catalog.services.vizier_client import VizierClient
from astroquery.gaia import Gaia
from astropy.coordinates import SkyCoord
import astropy.units as u

Gaia.TIMEOUT = 5


@dataclass(frozen=True)
class ResolvedTarget:
    gaia_id: str
    gaia_release_used: str  # "dr3" | "dr2"
    ra_deg: float
    dec_deg: float


@dataclass(frozen=True)
class CatalogResult:
    catalog_id: str
    context: Context
    status: CatalogStatus
    from_cache: bool
    needs_attention: bool
    matches_count: int = 0
    payload: Dict[str, Any] = None
    fetched_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    error_message: Optional[str] = None
    configured_attributes: List[str] = None  # Attributi configurati nel CSV per questo catalogo/contesto


@dataclass(frozen=True)
class QueryResponse:
    request_id: str
    request_status: RequestStatus
    context: Context
    resolved_target: ResolvedTarget
    results_by_context: Dict[str, List[CatalogResult]]


class QueryService:
    def __init__(
        self,
        registry_repo: InMemoryRegistryRepo,
        cache_repo: InMemoryCacheRepo,
        events_repo: InMemoryEventsRepo,
        db_cache_repo=None,  # Optional: persistent DB cache

    ) -> None:
        self.registry = registry_repo
        self.cache = cache_repo
        self.db_cache = db_cache_repo  # Will be used for persistent storage
        self.events = events_repo
        self.vizier = VizierClient(timeout_s=20)

    # ----------------------------
    # Public API
    # ----------------------------

    def query(
        self,
        gaia_id: str,
        context: Context,
        role: UserRole,
        catalogs: Optional[List[str]] = None,
        refresh: bool = False,
        max_matches: int = 3,
        cone_radius: Optional[float] = None,
    ) -> QueryResponse:
        request_id = str(uuid4())

        # Role gating: refresh solo superuser
        if refresh and role != UserRole.SUPERUSER:
            refresh = False

        # 1) resolve target
        resolved = self._resolve_target_or_fail(gaia_id)

        # 2) determinare contesti da eseguire
        contexts_to_run = self._expand_context(context)

        results_by_context: Dict[str, List[CatalogResult]] = {}
        overall_status = RequestStatus.COMPLETE

        for ctx in contexts_to_run:
            results: List[CatalogResult] = []
            ctx_catalogs = self.registry.get_catalogs_for_context(ctx)
            generated_catalog_ids = get_catalog_ids_for_context(ctx.value)

            if generated_catalog_ids:
                order_by_id = {catalog_id: idx for idx, catalog_id in enumerate(generated_catalog_ids)}
                ctx_catalogs = [c for c in ctx_catalogs if c.catalog_id in order_by_id]
                ctx_catalogs.sort(key=lambda c: order_by_id[c.catalog_id])

            # filtro per subset richiesta
            if catalogs:
                ctx_catalogs = [c for c in ctx_catalogs if c.catalog_id in catalogs]

            for cfg in ctx_catalogs:
                r = self._query_single_catalog(
                    request_id=request_id,
                    resolved=resolved,
                    context=ctx,
                    catalog_id=cfg.catalog_id,
                    refresh=refresh,
                    max_matches=max_matches,
                    cone_radius=cone_radius,
                )
                results.append(r)

                if r.status in (CatalogStatus.ERROR, CatalogStatus.TIMEOUT):
                    overall_status = RequestStatus.PARTIAL

            results_by_context[ctx.value] = results

        return QueryResponse(
            request_id=request_id,
            request_status=overall_status,
            context=context,
            resolved_target=resolved,
            results_by_context=results_by_context,
        )

    # ----------------------------
    # Internals
    # ----------------------------

    def _expand_context(self, context: Context) -> List[Context]:
        if context == Context.ALL:
            # esegui solo i contesti presenti nel registry
            ctxs = self.registry.list_contexts()
            # se vuoto, fallback ai contesti standard (evita "all" che torna vuoto)
            return ctxs or [
                Context.IDENTIFICATIVI,
                Context.PARAMETRI_FISICI,
                Context.MAGNITUDINE,
                Context.TIPO_SPETTRALE,
                Context.VARIABILITA_NOTA,
            ]
        return [context]

    def _resolve_target_or_fail(self, gaia_id: str) -> ResolvedTarget:
        if not gaia_id or not gaia_id.isdigit():
            raise ValueError("TARGET_ID_INVALID")

        source_id = int(gaia_id)

        dr3 = self._query_gaia_source("gaiadr3.gaia_source", source_id)
        if dr3 is not None:
            return ResolvedTarget(
                gaia_id=gaia_id,
                gaia_release_used="dr3",
                ra_deg=dr3[0],
                dec_deg=dr3[1],
            )

        dr2 = self._query_gaia_source("gaiadr2.gaia_source", source_id)
        if dr2 is not None:
            return ResolvedTarget(
                gaia_id=gaia_id,
                gaia_release_used="dr2",
                ra_deg=dr2[0],
                dec_deg=dr2[1],
            )

        raise ValueError("TARGET_NOT_FOUND")

    def _query_gaia_source(self, table_name: str, source_id: int) -> Optional[tuple[float, float]]:
        query = (
            "SELECT source_id, ra, dec "
            f"FROM {table_name} "
            f"WHERE source_id = {source_id}"
        )

        try:
            job = Gaia.launch_job(query)
            result = job.get_results()
        except Exception:
            return None

        if len(result) == 0:
            return None

        row = result[0]
        try:
            return float(row["ra"]), float(row["dec"])
        except Exception:
            return None

    def _query_single_catalog(
        self,
        request_id: str,
        resolved: ResolvedTarget,
        context: Context,
        catalog_id: str,
        refresh: bool,
        max_matches: int,
        cone_radius: Optional[float] = None,
    ) -> CatalogResult:
        # Get configured attributes from CSV (needed for both cache and live fetch)
        attrs = self.registry.get_attributes_for_context_catalog(context, catalog_id)
        configured_attrs = [a.attribute_name for a in attrs] if attrs else []

        # 1) Try in-memory cache first
        cached = self.cache.get_cache(resolved.gaia_id, context, catalog_id)
        if cached and (not refresh) and (not is_expired(cached)):
            self.events.log_event(QueryEvent(
                request_id=request_id,
                event_type=EventType.USED_CACHE,
                gaia_id=resolved.gaia_id,
                context=context,
                catalog_id=catalog_id,
            ))
            return CatalogResult(
                catalog_id=catalog_id,
                context=context,
                status=cached.status,
                from_cache=True,
                needs_attention=(
                cached.status in (
                    CatalogStatus.MULTI_MATCH,
                    CatalogStatus.AMBIGUOUS_MATCH,
                    CatalogStatus.STALE_CACHE,
                    )
                ),

                matches_count=cached.matches_count,
                payload=cached.payload,
                fetched_at=cached.fetched_at,
                expires_at=cached.expires_at,
                configured_attributes=configured_attrs,
            )

        # 1b) Try persistent DB cache second (if in-memory miss and no refresh)
        if (not refresh) and self.db_cache:
            db_attributes = self.db_cache.get_all_attributes(resolved.gaia_id, catalog_id)
            if db_attributes:
                # Found in DB cache - payload is directly the attributes dict
                db_payload = db_attributes
                # Determine status based on whether we found all configured attributes
                found_count = len([a for a in configured_attrs if a in db_attributes])
                status = CatalogStatus.OK if found_count == len(configured_attrs) else (
                    CatalogStatus.MULTI_MATCH if found_count > 0 else CatalogStatus.NO_MATCH
                )

                self.events.log_event(QueryEvent(
                    request_id=request_id,
                    event_type=EventType.USED_CACHE,
                    gaia_id=resolved.gaia_id,
                    context=context,
                    catalog_id=catalog_id,
                ))
                return CatalogResult(
                    catalog_id=catalog_id,
                    context=context,
                    status=status,
                    from_cache=True,
                    needs_attention=(
                        status in (
                            CatalogStatus.MULTI_MATCH,
                            CatalogStatus.AMBIGUOUS_MATCH,
                            CatalogStatus.STALE_CACHE,
                        )
                    ),
                    matches_count=len(db_attributes),
                    payload=db_payload,
                    fetched_at=None,  # DB cache doesn't track fetch time separately
                    expires_at=None,
                    configured_attributes=configured_attrs,
                )

        # 2) live fetch (stub)
        live_entry = self._fetch_catalog_stub(
            resolved=resolved,
            context=context,
            catalog_id=catalog_id,
            max_matches=max_matches,
            cone_radius=cone_radius,
        )

        # 3) TTL compute
        live_entry = compute_expiration(live_entry)

        # 4) write cache (no overwrite on error/timeout)
        if cached is None or should_overwrite(cached, live_entry):
            self.cache.upsert_cache(live_entry)

            # 4b) Save filtered results to persistent DB cache
            self._save_to_db_cache(
                gaia_id=resolved.gaia_id,
                context=context,
                catalog_id=catalog_id,
                live_entry=live_entry,
                configured_attrs=configured_attrs,
                resolved_ra=resolved.ra_deg,
                resolved_dec=resolved.dec_deg,
            )

        # 5) event
        self.events.log_event(QueryEvent(
            request_id=request_id,
            event_type=EventType.FETCH_OK if live_entry.status in (
                CatalogStatus.OK, CatalogStatus.MULTI_MATCH, CatalogStatus.AMBIGUOUS_MATCH
            ) else (
                EventType.FETCH_NO_MATCH if live_entry.status == CatalogStatus.NO_MATCH else EventType.FETCH_ERROR
            ),
            gaia_id=resolved.gaia_id,
            context=context,
            catalog_id=catalog_id,
        ))

        return CatalogResult(
            catalog_id=catalog_id,
            context=context,
            status=live_entry.status,
            from_cache=False,
            needs_attention=(
                live_entry.status in (
                    CatalogStatus.MULTI_MATCH,
                    CatalogStatus.AMBIGUOUS_MATCH,
                    CatalogStatus.STALE_CACHE,
                )
            ),
            matches_count=live_entry.matches_count,
            payload=live_entry.payload,
            fetched_at=live_entry.fetched_at,
            expires_at=live_entry.expires_at,
            error_message=None,
            configured_attributes=configured_attrs,
        )


    def _fetch_catalog_stub(
        self,
        resolved: ResolvedTarget,
        context: Context,
        catalog_id: str,
        max_matches: int,
        cone_radius: Optional[float] = None,
    ) -> CacheEntry:
        # 1) attributi configurati (se vuoti: "*")
        attrs = self.registry.get_attributes_for_context_catalog(context, catalog_id)
        columns = [a.attribute_name for a in attrs] if attrs else ["*"]

        # Always include coordinate columns for distance calculation (will be filtered out in frontend)
        if columns != ["*"]:
            if "_RAJ2000" not in columns:
                columns.append("_RAJ2000")
            if "_DEJ2000" not in columns:
                columns.append("_DEJ2000")

        # 2) cone search radius: priority order
        # a) User-provided override (from frontend)
        # b) Catalog definition default
        # c) Global fallback: 5.0 arcsec (default)
        if cone_radius is not None:
            radius = cone_radius
        else:
            catalog_def = self.registry.get_catalog_definition(catalog_id)
            if catalog_def and catalog_def.default_radius_arcsec:
                radius = catalog_def.default_radius_arcsec
            else:
                radius = 5.0
        rows = self.vizier.query_cone(
            catalog_id=catalog_id,
            ra_deg=resolved.ra_deg,
            dec_deg=resolved.dec_deg,
            radius_arcsec=radius,
            columns=columns,
        )

        if not rows:
            return CacheEntry(
                gaia_id=resolved.gaia_id,
                context=context,
                catalog_id=catalog_id,
                match_strategy=MatchStrategy.RA_DEC_CONE,
                resolved_ra_deg=resolved.ra_deg,
                resolved_dec_deg=resolved.dec_deg,
                radius_arcsec=radius,
                status=CatalogStatus.NO_MATCH,
                matches_count=0,
                payload={},
            )

        # Calculate distance for each match and sort by distance
        target_coord = SkyCoord(ra=resolved.ra_deg * u.deg, dec=resolved.dec_deg * u.deg, frame='icrs')
        candidates_with_distance = []

        for row in rows:
            candidate = dict(row.values)

            # Try to get RA/Dec from common column names (expanded list)
            ra_col = None
            dec_col = None

            # RA column variants (ordered by priority)
            ra_variants = ['_RAJ2000', 'RAJ2000', 'RA', 'ra', 'RAdeg', 'RAhour', 'RA_ICRS', 'ra_epoch2000']
            for key in candidate.keys():
                if key in ra_variants:
                    ra_col = key
                    break

            # Dec column variants (ordered by priority)
            dec_variants = ['_DEJ2000', 'DEJ2000', 'DEC', 'Dec', 'dec', 'DEdeg', 'DE_ICRS', 'dec_epoch2000']
            for key in candidate.keys():
                if key in dec_variants:
                    dec_col = key
                    break

            if ra_col and dec_col and candidate.get(ra_col) is not None and candidate.get(dec_col) is not None:
                try:
                    match_coord = SkyCoord(ra=float(candidate[ra_col]) * u.deg,
                                          dec=float(candidate[dec_col]) * u.deg,
                                          frame='icrs')
                    distance_arcsec = target_coord.separation(match_coord).arcsec
                    candidate['_distance_arcsec'] = round(distance_arcsec, 2)
                except (ValueError, TypeError):
                    candidate['_distance_arcsec'] = None
            else:
                candidate['_distance_arcsec'] = None

            candidates_with_distance.append(candidate)

        # Sort by distance (closest first), putting None distances at the end
        # Convert numpy float64 to Python float for proper sorting
        candidates_with_distance.sort(key=lambda x: (x['_distance_arcsec'] is None, float(x['_distance_arcsec']) if x['_distance_arcsec'] is not None else 999999))

        # Count total matches BEFORE selecting closest
        total_matches = len(candidates_with_distance)

        # Take only the closest match
        selected = dict(candidates_with_distance[0])  # copia separata del match più vicino

        return CacheEntry(
            gaia_id=resolved.gaia_id,
            context=context,
            catalog_id=catalog_id,
            match_strategy=MatchStrategy.RA_DEC_CONE,
            resolved_ra_deg=resolved.ra_deg,
            resolved_dec_deg=resolved.dec_deg,
            radius_arcsec=radius,
            status=CatalogStatus.OK if total_matches == 1 else CatalogStatus.MULTI_MATCH,
            matches_count=total_matches,
            selected_index=0,
            payload=selected,
        )

    def _save_to_db_cache(
        self,
        gaia_id: str,
        context: Context,
        catalog_id: str,
        live_entry: CacheEntry,
        configured_attrs: List[str],
        resolved_ra: float,
        resolved_dec: float,
    ) -> None:
        """
        Save filtered query results to persistent DB cache.

        Saves only the configured attributes (those from CSV) to avoid
        storing unnecessary columns. Respects the user's filtered display.

        Note: Uses UPSERT logic - if a record already exists, it's updated
        with the new value. This automatically handles refresh=true queries.

        Args:
            gaia_id: Gaia source ID
            context: Catalog context
            catalog_id: Catalog identifier
            live_entry: CacheEntry with payload from Vizier
            configured_attrs: List of attribute names to save (from CSV)
            resolved_ra: Target RA for reference
            resolved_dec: Target Dec for reference
        """
        if not self.db_cache or live_entry.status not in (
            CatalogStatus.OK, CatalogStatus.MULTI_MATCH, CatalogStatus.AMBIGUOUS_MATCH
        ):
            # Don't save errors, timeouts, or if no DB cache available
            return

        try:
            payload = live_entry.payload or {}
            attrs = self.registry.get_attributes_for_context_catalog(context, catalog_id)

            # Collect attributes to save
            entries_to_save = []

            if configured_attrs:
                # Save only configured attributes
                for attr_config in attrs:
                    attr_name = attr_config.attribute_name

                    if attr_name not in configured_attrs:
                        continue

                    # Get value from payload
                    value = payload.get(attr_name)
                    if value is None:
                        continue

                    entries_to_save.append({
                        'gaia_id': gaia_id,
                        'catalog_id': catalog_id,
                        'attribute_name': attr_name,
                        'value': str(value) if value is not None else None,
                        'context': context.value,
                        'reference': getattr(attr_config, 'reference', None),
                        'ra_deg': resolved_ra,
                        'dec_deg': resolved_dec,
                        'distance_arcsec': None,  # Not part of cache key - all attributes for this gaia_id/catalog
                        'ttl_days': 180,  # Standard TTL
                    })
            else:
                # Fallback: save all non-metadata fields from payload
                exclude_fields = {'_candidates', '_RAJ2000', '_DEJ2000', '_r', '_distance_arcsec', 'recno'}
                for key, value in payload.items():
                    if key.startswith('_') or key in exclude_fields:
                        continue

                    entries_to_save.append({
                        'gaia_id': gaia_id,
                        'catalog_id': catalog_id,
                        'attribute_name': key,
                        'value': str(value) if value is not None else None,
                        'context': context.value,
                        'reference': None,
                        'ra_deg': resolved_ra,
                        'dec_deg': resolved_dec,
                        'distance_arcsec': None,  # Not part of cache key - all attributes for this gaia_id/catalog
                        'ttl_days': 180,
                    })

            # Batch save to DB (upsert handles both insert and update)
            if entries_to_save:
                count = self.db_cache.save_batch(entries_to_save)
                # Optionally log: print(f"[Catalog] Saved {count} attributes to DB cache for {gaia_id} / {catalog_id}")

        except Exception:
            # Silently fail - don't interrupt the query if DB save fails
            pass


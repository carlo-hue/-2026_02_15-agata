from __future__ import annotations

from typing import Any, Dict, List, Optional

from agata.catalog.domain.enums import Context, UserRole
from agata.catalog.services.query_service import QueryService


def post_query(
    service: QueryService,
    gaia_id: str,
    context: str,
    role: str,
    catalogs: Optional[List[str]] = None,
    refresh: bool = False,
    max_matches: int = 3,
    cone_radius: Optional[float] = None,
) -> Dict[str, Any]:
    ctx = Context(context)
    user_role = UserRole(role)

    resp = service.query(
        gaia_id=gaia_id,
        context=ctx,
        role=user_role,
        catalogs=catalogs,
        refresh=refresh,
        max_matches=max_matches,
        cone_radius=cone_radius,
    )

    # JSON-friendly
    out: Dict[str, Any] = {
        "request_id": resp.request_id,
        "request_status": resp.request_status.value,
        "context": resp.context.value,
        "resolved_target": {
            "gaia_id": resp.resolved_target.gaia_id,
            "gaia_release_used": resp.resolved_target.gaia_release_used,
            "ra_deg": resp.resolved_target.ra_deg,
            "dec_deg": resp.resolved_target.dec_deg,
        },
        "results_by_context": {},
    }

    for ctx_key, results in resp.results_by_context.items():
        out["results_by_context"][ctx_key] = [
            {
                "catalog_id": r.catalog_id,
                "status": r.status.value,
                "from_cache": r.from_cache,
                "needs_attention": r.needs_attention,
                "matches_count": r.matches_count,
                "payload": {k: str(v) if v is not None else v for k, v in (r.payload or {}).items()},
                "fetched_at": r.fetched_at.isoformat() if r.fetched_at else None,
                "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                "error_message": r.error_message,
                "configured_attributes": r.configured_attributes or [],
            }
            for r in results
        ]

    return out

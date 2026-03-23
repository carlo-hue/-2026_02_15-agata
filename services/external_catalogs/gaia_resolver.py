# agata/services/external_catalogs/gaia_resolver.py
"""
DEPRECATED: Gaia ID resolver.

La nuova implementazione e' in agata/admin/routes/catalogs/common.py
Questo file e' mantenuto per compatibilita' con vecchio codice.
"""
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)


def resolve_gaia_id(ra: float, dec: float, radius_arcsec: float = 5.0) -> Optional[Dict]:
    """
    Risolve Gaia DR3 ID da coordinate.

    NOTA: Questa funzione e' deprecata.
    Usa agata.admin.routes.catalogs.common.resolve_gaia_id

    Args:
        ra: Right Ascension in gradi
        dec: Declination in gradi
        radius_arcsec: Raggio di ricerca in arcsec

    Returns:
        Dict con gaia_id, ra, dec, distance_arcsec o None
    """
    # Import dalla nuova location
    try:
        from agata.admin.routes.catalogs.common import resolve_gaia_id as new_resolve
        return new_resolve(ra, dec, radius_arcsec)
    except ImportError:
        logger.warning("Impossibile importare nuovo resolve_gaia_id")
        return None

# agata/services/external_catalogs/__init__.py
"""
DEPRECATED: Modulo di compatibilita' per vecchia architettura.

La nuova architettura usa endpoint dedicati in:
- agata/admin/routes/catalogs/tess.py
- agata/admin/routes/catalogs/ztf.py
- agata/admin/routes/catalogs/asassn.py
- agata/admin/routes/catalogs/ogle.py
- agata/admin/routes/catalogs/file_upload.py

Questo modulo fornisce classi stub per evitare errori di import
nel vecchio codice non ancora migrato.
"""




from dataclasses import dataclass
from typing import Optional, List
import pandas as pd


@dataclass
class SearchQuery:
    """Query di ricerca per cataloghi esterni."""
    ra: float
    dec: float
    radius_arcsec: float = 5.0
    gaia_id: Optional[str] = None


@dataclass
class CatalogSearchResult:
    """Risultato ricerca catalogo."""
    catalog_name: str
    success: bool
    point_count: int = 0
    data: Optional[pd.DataFrame] = None
    band: Optional[str] = None
    time_range: Optional[tuple] = None
    mag_range: Optional[tuple] = None
    error_message: Optional[str] = None
    extra_info: Optional[dict] = None


class BaseCatalogClient:
    """Client base deprecato."""

    def search(self, query: SearchQuery) -> CatalogSearchResult:
        raise NotImplementedError("Usa i nuovi endpoint in agata/admin/routes/catalogs/")


class TESSClient(BaseCatalogClient):
    """TESS client deprecato. Usa /api/catalogs/tess/search"""
    pass


class ZTFClient(BaseCatalogClient):
    """ZTF client deprecato. Usa /api/catalogs/ztf/search"""
    pass


class ASASSNClient(BaseCatalogClient):
    """ASAS-SN client deprecato. Usa /api/catalogs/asassn/search"""
    pass


class OGLEClient(BaseCatalogClient):
    """OGLE client deprecato. Usa /api/catalogs/ogle/search"""
    pass


class FileClient(BaseCatalogClient):
    """File client deprecato. Usa /api/catalogs/file/upload"""
    pass


__all__ = [
    'SearchQuery',
    'CatalogSearchResult',
    'BaseCatalogClient',
    'TESSClient',
    'ZTFClient',
    'ASASSNClient',
    'OGLEClient',
    'FileClient',
]

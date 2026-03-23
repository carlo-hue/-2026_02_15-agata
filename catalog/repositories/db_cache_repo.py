"""
Database-backed cache repository for catalog attributes.

Replaces in-memory stub with persistent MySQL storage.
Implements intelligent caching: check DB first, fetch from Vizier only for missing.
"""
from typing import Dict, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_

from agata.auth_models import CatalogAttribute
from agata.db import SessionLocal
from agata.catalog.domain.enums import CatalogStatus


class DBCacheRepo:
    """
    Persistent cache repository using agata_catalog_attributes table.

    Interface:
    - get(gaia_id, catalog_id, attribute_name) -> str | None
    - get_all_attributes(gaia_id, catalog_id) -> Dict[str, str]
    - save(gaia_id, catalog_id, attribute_name, value, context, reference, ra, dec, distance)
    - save_batch(entries_list)
    - invalidate(gaia_id, catalog_id=None)
    """

    def __init__(self, session: Optional[Session] = None):
        """
        Args:
            session: SQLAlchemy Session. If None, creates new session per operation.
        """
        self._session = session
        self._own_session = session is None

    def _get_session(self) -> Session:
        """Get or create session."""
        if self._session is not None:
            return self._session
        return SessionLocal()

    def _close_session(self, session: Session):
        """Close session if we created it."""
        if self._own_session and session is not None:
            session.close()

    def get(
        self,
        gaia_id: str,
        catalog_id: str,
        attribute_name: str
    ) -> Optional[str]:
        """
        Get single attribute value from cache.

        Args:
            gaia_id: Gaia source ID
            catalog_id: Catalog identifier (e.g., 'I/305/out')
            attribute_name: Attribute name (e.g., 'GSC2.3')

        Returns:
            Attribute value as string, or None if not found or expired.
        """
        session = self._get_session()
        try:
            record = session.query(CatalogAttribute).filter(
                and_(
                    CatalogAttribute.gaia_id == gaia_id,
                    CatalogAttribute.catalog_id == catalog_id,
                    CatalogAttribute.attribute_name == attribute_name
                )
            ).first()

            if record is None:
                return None

            # Check expiry
            if record.is_expired:
                return None

            return record.value

        finally:
            self._close_session(session)

    def get_all_attributes(
        self,
        gaia_id: str,
        catalog_id: str
    ) -> Dict[str, str]:
        """
        Get all attributes for a star/catalog combination.

        Cache key is (gaia_id, catalog_id, attribute_name) - one value per attribute.

        Args:
            gaia_id: Gaia source ID
            catalog_id: Catalog identifier

        Returns:
            Dict mapping attribute_name -> value (excludes expired).
        """
        session = self._get_session()
        try:
            records = session.query(CatalogAttribute).filter(
                and_(
                    CatalogAttribute.gaia_id == gaia_id,
                    CatalogAttribute.catalog_id == catalog_id
                )
            ).all()

            result = {}
            for record in records:
                if not record.is_expired:
                    result[record.attribute_name] = record.value

            return result

        finally:
            self._close_session(session)

    def save(
        self,
        gaia_id: str,
        catalog_id: str,
        attribute_name: str,
        value: Optional[str],
        context: Optional[str] = None,
        reference: Optional[str] = None,
        ra_deg: Optional[float] = None,
        dec_deg: Optional[float] = None,
        distance_arcsec: Optional[float] = None,
        ttl_days: int = 180
    ) -> bool:
        """
        Save attribute to cache.

        Args:
            gaia_id: Gaia source ID
            catalog_id: Catalog identifier
            attribute_name: Attribute name
            value: Attribute value (can be None for no_match)
            context: Catalog context (from CSV)
            reference: Reference biblio (from CSV)
            ra_deg: Star RA for validation
            dec_deg: Star Dec for validation
            distance_arcsec: Match distance for quality assessment
            ttl_days: Cache lifetime (180 = 6 months)

        Returns:
            True if saved successfully, False on error.
        """
        session = self._get_session()
        try:
            # Check if already exists
            existing = session.query(CatalogAttribute).filter(
                and_(
                    CatalogAttribute.gaia_id == gaia_id,
                    CatalogAttribute.catalog_id == catalog_id,
                    CatalogAttribute.attribute_name == attribute_name
                )
            ).first()

            if existing:
                # Update existing
                existing.value = value
                existing.contesto = context
                existing.reference = reference
                existing.ra_deg = ra_deg
                existing.dec_deg = dec_deg
                existing.distance_arcsec = distance_arcsec
                existing.fetched_at = datetime.utcnow()
                existing.set_expiry(ttl_days)
            else:
                # Create new
                record = CatalogAttribute(
                    gaia_id=gaia_id,
                    catalog_id=catalog_id,
                    attribute_name=attribute_name,
                    value=value,
                    contesto=context,
                    reference=reference,
                    ra_deg=ra_deg,
                    dec_deg=dec_deg,
                    distance_arcsec=distance_arcsec,
                    fetched_at=datetime.utcnow()
                )
                record.set_expiry(ttl_days)
                session.add(record)

            session.commit()
            return True

        except Exception as e:
            session.rollback()
            print(f"Error saving catalog attribute: {e}")
            return False
        finally:
            self._close_session(session)

    def save_batch(
        self,
        entries: List[Dict]
    ) -> int:
        """
        Save multiple attributes in batch.

        Args:
            entries: List of dicts with keys:
                - gaia_id, catalog_id, attribute_name, value
                - context, reference, ra_deg, dec_deg, distance_arcsec (optional)

        Returns:
            Number of records saved.
        """
        session = self._get_session()
        count = 0
        try:
            for entry in entries:
                try:
                    existing = session.query(CatalogAttribute).filter(
                        and_(
                            CatalogAttribute.gaia_id == entry['gaia_id'],
                            CatalogAttribute.catalog_id == entry['catalog_id'],
                            CatalogAttribute.attribute_name == entry['attribute_name']
                        )
                    ).first()

                    if existing:
                        existing.value = entry.get('value')
                        existing.contesto = entry.get('context')
                        existing.reference = entry.get('reference')
                        existing.ra_deg = entry.get('ra_deg')
                        existing.dec_deg = entry.get('dec_deg')
                        existing.distance_arcsec = entry.get('distance_arcsec')
                        existing.fetched_at = datetime.utcnow()
                        existing.set_expiry(entry.get('ttl_days', 180))
                    else:
                        record = CatalogAttribute(
                            gaia_id=entry['gaia_id'],
                            catalog_id=entry['catalog_id'],
                            attribute_name=entry['attribute_name'],
                            value=entry.get('value'),
                            contesto=entry.get('context'),
                            reference=entry.get('reference'),
                            ra_deg=entry.get('ra_deg'),
                            dec_deg=entry.get('dec_deg'),
                            distance_arcsec=entry.get('distance_arcsec'),
                            fetched_at=datetime.utcnow()
                        )
                        record.set_expiry(entry.get('ttl_days', 180))
                        session.add(record)
                    count += 1
                except Exception as e:
                    print(f"Error in batch entry: {e}")

            session.commit()
            return count

        except Exception as e:
            session.rollback()
            print(f"Error in batch save: {e}")
            return 0
        finally:
            self._close_session(session)

    def invalidate(
        self,
        gaia_id: str,
        catalog_id: Optional[str] = None
    ) -> int:
        """
        Mark entries as expired (force refetch from Vizier).

        Args:
            gaia_id: Gaia source ID
            catalog_id: Optional catalog ID. If None, invalidates all for gaia_id.

        Returns:
            Number of records invalidated.
        """
        session = self._get_session()
        try:
            query = session.query(CatalogAttribute).filter(
                CatalogAttribute.gaia_id == gaia_id
            )

            if catalog_id:
                query = query.filter(CatalogAttribute.catalog_id == catalog_id)

            records = query.all()
            for record in records:
                record.invalidate()

            session.commit()
            return len(records)

        except Exception as e:
            session.rollback()
            print(f"Error invalidating cache: {e}")
            return 0
        finally:
            self._close_session(session)

    def get_stats(self, gaia_id: str) -> Dict:
        """
        Get cache statistics for a star.

        Args:
            gaia_id: Gaia source ID

        Returns:
            Dict with total, expired, active counts.
        """
        session = self._get_session()
        try:
            all_records = session.query(CatalogAttribute).filter(
                CatalogAttribute.gaia_id == gaia_id
            ).all()

            total = len(all_records)
            expired = sum(1 for r in all_records if r.is_expired)
            active = total - expired

            return {
                'total': total,
                'active': active,
                'expired': expired,
                'catalogs': len(set(r.catalog_id for r in all_records))
            }

        finally:
            self._close_session(session)

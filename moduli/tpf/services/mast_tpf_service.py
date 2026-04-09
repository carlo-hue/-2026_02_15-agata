from __future__ import annotations

import importlib.util
import logging
from functools import lru_cache
from pathlib import Path

from astropy.coordinates import SkyCoord
from astroquery.gaia import Gaia
from astroquery.mast import Tesscut

from ..config import settings
from .utils import rounded_or_none, validate_cutout_size, validate_gaia_source_id, validate_sector

LOGGER = logging.getLogger(__name__)


class MastTpfServiceError(ValueError):
    pass


def _normalize_remote_error_message(error: Exception) -> str:
    raw_message = str(error or "").strip()
    lowered = raw_message.lower()

    if "remotedisconnected" in lowered or "remote end closed connection without response" in lowered:
        return "Il servizio remoto MAST/TESS ha chiuso la connessione senza rispondere. Riprova tra poco."
    if "connection aborted" in lowered:
        return "La connessione verso MAST/TESS e' stata interrotta prima della risposta. Riprova tra poco."
    if "timed out" in lowered or "timeout" in lowered:
        return "Il servizio remoto MAST/TESS non ha risposto nei tempi attesi. Riprova tra poco."
    if "connection reset" in lowered or "connection broken" in lowered:
        return "La connessione verso MAST/TESS e' stata chiusa in modo anomalo. Riprova tra poco."
    if "name resolution" in lowered or "temporary failure in name resolution" in lowered:
        return "Impossibile risolvere il servizio remoto MAST/TESS dalla rete locale."
    return raw_message or "Errore remoto non previsto durante la comunicazione con MAST/TESS."


def _get_internal_lightkurve():
    try:
        import lightkurve as lightkurve_module

        return lightkurve_module
    except ModuleNotFoundError as err:
        raise MastTpfServiceError(f"lightkurve non disponibile nell'ambiente locale: {err}") from err


@lru_cache(maxsize=1)
def _load_legacy_util_module():
    util_path = Path(settings.legacy_tpf_util_path)
    if not util_path.exists() or not util_path.is_file():
        raise MastTpfServiceError(f"util.py legacy non trovato: {util_path}")

    spec = importlib.util.spec_from_file_location("agata_tpf_legacy_util", util_path)
    if spec is None or spec.loader is None:
        raise MastTpfServiceError(f"Impossibile caricare util.py legacy: {util_path}")

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except ModuleNotFoundError as err:
        LOGGER.warning("Legacy util import failed because dependency is missing: %s", err)
        raise MastTpfServiceError(f"Legacy util non importabile: {err}") from err
    except Exception as err:
        LOGGER.warning("Legacy util import failed, falling back to internal resolvers: %s", err)
        raise MastTpfServiceError(f"Legacy util non importabile: {err}") from err
    return module


def _ensure_download_dir() -> Path:
    download_dir = Path(settings.mast_tpf_download_dir)
    download_dir.mkdir(parents=True, exist_ok=True)
    return download_dir


def _ensure_gaia_download_dir(gaia_id: str) -> Path:
    base_dir = _ensure_download_dir()
    source_dir = base_dir / str(gaia_id)
    source_dir.mkdir(parents=True, exist_ok=True)
    return source_dir


def build_local_tpf_filename(gaia_id: str, sector: int, cutout_size: int) -> str:
    return f"tpf_gaia_{gaia_id}_s{int(sector)}_cut{int(cutout_size)}.fits"


def build_local_tpf_path(gaia_id: str, sector: int, cutout_size: int) -> Path:
    return _ensure_gaia_download_dir(gaia_id) / build_local_tpf_filename(gaia_id, sector, cutout_size)


def list_downloaded_tpf_sectors(gaia_id: str, cutout_size: int = 10) -> dict[int, dict]:
    validated_gaia_id = validate_gaia_source_id(gaia_id)
    validated_cutout_size = validate_cutout_size(cutout_size, settings.default_cutout_size)
    download_dir = _ensure_gaia_download_dir(validated_gaia_id)
    downloaded: dict[int, dict] = {}

    new_pattern = f"tpf_gaia_{validated_gaia_id}_s*_cut{validated_cutout_size}.fits"
    for file_path in sorted(download_dir.glob(new_pattern)):
        parts = file_path.stem.split("_")
        sector_part = next((part for part in parts if part.startswith("s") and part[1:].isdigit()), None)
        if sector_part is None:
            continue
        sector = int(sector_part[1:])
        downloaded[sector] = {
            "sector": sector,
            "downloaded": True,
            "filename": file_path.name,
            "file_path": str(file_path),
        }

    legacy_patterns = [
        f"{validated_gaia_id}_num_sett_TESS_*.fit",
        f"{validated_gaia_id}_num_sett_TESS_*.fits",
    ]
    for pattern in legacy_patterns:
        for file_path in sorted(download_dir.glob(pattern)):
            suffix = file_path.stem.replace(f"{validated_gaia_id}_num_sett_TESS_", "", 1)
            if not suffix.isdigit():
                continue
            sector = int(suffix)
            downloaded[sector] = {
                "sector": sector,
                "downloaded": True,
                "filename": file_path.name,
                "file_path": str(file_path),
            }
    return downloaded


def get_local_tpf_sectors_for_gaia(gaia_id: str, cutout_size: int = 10) -> dict:
    validated_gaia_id = validate_gaia_source_id(gaia_id)
    validated_cutout_size = validate_cutout_size(cutout_size, settings.default_cutout_size)
    downloaded_map = list_downloaded_tpf_sectors(validated_gaia_id, validated_cutout_size)
    sectors = [downloaded_map[key] for key in sorted(downloaded_map)]
    return {
        "ok": True,
        "status": "ok",
        "gaia_id": validated_gaia_id,
        "cutout_size": validated_cutout_size,
        "sectors": sectors,
        "message": f"TPF locali trovati: {len(sectors)}",
    }


def _resolve_gaia_coordinates_via_legacy_util(gaia_id: str) -> tuple[float, float, float | None, str]:
    util = _load_legacy_util_module()
    last_error = None

    if hasattr(util, "ra_dec_mag_da_idgaiaDA_DB_o_GAIA"):
        try:
            cod_ret, cod_ret_desc, ra, dec, mag = util.ra_dec_mag_da_idgaiaDA_DB_o_GAIA(gaia_id)
            if cod_ret == "ok":
                return float(ra), float(dec), None if mag is None else float(mag), str(cod_ret_desc)
            last_error = str(cod_ret_desc)
        except Exception as err:
            LOGGER.exception("Legacy util Gaia resolver failed for gaia_id=%s", gaia_id)
            last_error = str(err)

    if hasattr(util, "get_gaia_dr2_or_dr3_ra_dec_gmag"):
        try:
            ra, dec, mag = util.get_gaia_dr2_or_dr3_ra_dec_gmag(gaia_id)
            return float(ra), float(dec), None if mag is None else float(mag), "Coordinate risolte via util.py legacy."
        except Exception as err:
            LOGGER.exception("Legacy util Gaia fallback failed for gaia_id=%s", gaia_id)
            last_error = str(err)

    raise MastTpfServiceError(last_error or "gaia_id non risolto")


def _resolve_gaia_coordinates_direct(gaia_id: str) -> tuple[float, float, float | None, str]:
    query = f"""
        SELECT source_id, ra, dec, phot_g_mean_mag AS gmag
        FROM gaiadr3.gaia_source
        WHERE source_id = {gaia_id}
    """
    job = Gaia.launch_job(query)
    results = job.get_results()
    if len(results) == 0:
        raise MastTpfServiceError("gaia_id non risolto")
    row = results[0]
    gmag = row["gmag"]
    return float(row["ra"]), float(row["dec"]), None if gmag is None else float(gmag), "Coordinate risolte via fallback Gaia DR3."


def _resolve_gaia_coordinates(gaia_id: str) -> tuple[float, float, float | None, str]:
    try:
        return _resolve_gaia_coordinates_via_legacy_util(gaia_id)
    except MastTpfServiceError as err:
        LOGGER.warning("Falling back to internal Gaia resolver for gaia_id=%s: %s", gaia_id, err)
        return _resolve_gaia_coordinates_direct(gaia_id)


def _get_sector_numbers_for_coordinates(ra: float, dec: float) -> list[int]:
    try:
        util = _load_legacy_util_module()
        coord_builder = getattr(util, "SkyCoord", SkyCoord)
        tesscut = getattr(util, "Tesscut", Tesscut)
    except MastTpfServiceError as err:
        LOGGER.warning("Falling back to internal Tesscut sector lookup: %s", err)
        coord_builder = SkyCoord
        tesscut = Tesscut

    coord = coord_builder(ra, dec, unit="deg")
    try:
        sector_table = tesscut.get_sectors(coordinates=coord)
    except Exception as err:
        LOGGER.exception("MAST/TESS sector lookup failed for ra=%s dec=%s", ra, dec)
        raise MastTpfServiceError(_normalize_remote_error_message(err)) from err
    if sector_table is None or len(sector_table) == 0:
        raise MastTpfServiceError("Nessun settore TESS disponibile")

    sectors: list[int] = []
    for row in sector_table:
        try:
            if hasattr(sector_table, "colnames") and "sector" in sector_table.colnames:
                sector_value = row["sector"]
            else:
                sector_value = row[1]
            sectors.append(int(sector_value))
        except Exception:
            continue
    if not sectors:
        raise MastTpfServiceError("Nessun settore TESS disponibile")
    return sorted(set(sectors))


def get_mast_sectors_for_gaia(gaia_id: str, cutout_size: int = 10) -> dict:
    validated_gaia_id = validate_gaia_source_id(gaia_id)
    validated_cutout_size = validate_cutout_size(cutout_size, settings.default_cutout_size)
    LOGGER.info("Listing TESS sectors from MAST for gaia_id=%s cutout_size=%s", validated_gaia_id, validated_cutout_size)

    ra, dec, gmag, resolution_message = _resolve_gaia_coordinates(validated_gaia_id)
    sectors = _get_sector_numbers_for_coordinates(ra, dec)
    downloaded_map = list_downloaded_tpf_sectors(validated_gaia_id, validated_cutout_size)

    sector_entries = []
    for sector in sectors:
        downloaded_entry = downloaded_map.get(sector)
        sector_entries.append({
            "sector": sector,
            "downloaded": bool(downloaded_entry),
            "filename": downloaded_entry["filename"] if downloaded_entry else None,
        })

    return {
        "ok": True,
        "status": "ok",
        "gaia_id": validated_gaia_id,
        "cutout_size": validated_cutout_size,
        "ra": rounded_or_none(ra, 6),
        "dec": rounded_or_none(dec, 6),
        "gmag": rounded_or_none(gmag, 4),
        "sectors": sector_entries,
        "message": resolution_message,
    }


def download_tpf_from_mast(gaia_id: str, sector, cutout_size: int = 10, *, reuse_existing: bool = True) -> dict:
    validated_gaia_id = validate_gaia_source_id(gaia_id)
    validated_sector = validate_sector(sector)
    validated_cutout_size = validate_cutout_size(cutout_size, settings.default_cutout_size)
    target_path = build_local_tpf_path(validated_gaia_id, validated_sector, validated_cutout_size)

    if reuse_existing and target_path.exists() and target_path.is_file():
        LOGGER.info(
            "Reusing existing downloaded TPF for gaia_id=%s sector=%s cutout_size=%s",
            validated_gaia_id,
            validated_sector,
            validated_cutout_size,
        )
        return {
            "ok": True,
            "status": "ok",
            "gaia_id": validated_gaia_id,
            "sector": validated_sector,
            "cutout_size": validated_cutout_size,
            "filename": target_path.name,
            "file_path": str(target_path),
            "downloaded": False,
            "reused_existing": True,
            "message": "TPF gia' presente localmente, file riusato.",
        }

    ra, dec, gmag, resolution_message = _resolve_gaia_coordinates(validated_gaia_id)
    try:
        util = _load_legacy_util_module()
        lightkurve_module = getattr(util, "lk", None) or _get_internal_lightkurve()
    except MastTpfServiceError as err:
        LOGGER.warning("Falling back to internal lightkurve download for gaia_id=%s: %s", validated_gaia_id, err)
        lightkurve_module = _get_internal_lightkurve()

    try:
        search_result = lightkurve_module.search_tesscut(f"{ra} {dec}", sector=int(validated_sector))
        if search_result is None or len(search_result) == 0:
            raise MastTpfServiceError("TPF non disponibile su MAST/TESS per il settore richiesto")
        tpf = search_result.download(cutout_size=int(validated_cutout_size))
        if tpf is None:
            raise MastTpfServiceError("Download TPF non riuscito")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        tpf.to_fits(str(target_path), overwrite=True)
    except MastTpfServiceError:
        raise
    except Exception as err:
        LOGGER.exception(
            "MAST/TESS TPF download failed for gaia_id=%s sector=%s cutout_size=%s",
            validated_gaia_id,
            validated_sector,
            validated_cutout_size,
        )
        raise MastTpfServiceError(_normalize_remote_error_message(err)) from err

    LOGGER.info(
        "TPF downloaded successfully from MAST for gaia_id=%s sector=%s cutout_size=%s file=%s",
        validated_gaia_id,
        validated_sector,
        validated_cutout_size,
        target_path.name,
    )
    return {
        "ok": True,
        "status": "ok",
        "gaia_id": validated_gaia_id,
        "sector": validated_sector,
        "cutout_size": validated_cutout_size,
        "ra": rounded_or_none(ra, 6),
        "dec": rounded_or_none(dec, 6),
        "gmag": rounded_or_none(gmag, 4),
        "filename": target_path.name,
        "file_path": str(target_path),
        "downloaded": True,
        "reused_existing": False,
        "message": f"TPF scaricato con successo. {resolution_message}",
    }

import os
import logging
from tempfile import NamedTemporaryFile
from typing import Optional, Tuple, Dict, Any

import numpy as np
import pandas as pd
from flask import request, jsonify
from flask_login import login_required, current_user

from . import catalogs_bp
from .common import (
    get_db_session,
    create_import_record,
    update_import_with_results,
    insert_catalog_data,
)
from agata.admin.decorators import admin_required

from agata.services.external_catalogs.tess.qlp_core import ingest_qlp_core

logger = logging.getLogger(__name__)


# =============================================================================
# HELPERS
# =============================================================================

def _choose_curve(curves: Dict[str, Dict[str, Any]], preferred: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """
    Sceglie la curva da salvare:
      1) preferred se esiste
      2) 'corrected' se esiste
      3) 'raw'
      4) prima disponibile
    """
    if not curves:
        return None, "Nessuna curva disponibile in lc_set['curves']"

    if preferred and preferred in curves:
        return preferred, None

    if "corrected" in curves:
        return "corrected", None
    if "raw" in curves:
        return "raw", None

    return next(iter(curves.keys())), None


def _build_df_from_curve(curve: Dict[str, Any]) -> Tuple[Optional[pd.DataFrame], Optional[str], str]:
    """
    Converte una curva QLP (dict) in DataFrame standard:
      - hjd: tempo assoluto (BJD-like) già normalizzato da read_qlp_fits()
      - mag: magnitudine se presente (curve['mag']) altrimenti flux
    Ritorna anche 'kind' = 'mag' oppure 'flux'
    """
    time = curve.get("time")
    flux = curve.get("flux")

    if time is None or flux is None:
        return None, "Curva non valida: mancano 'time' e/o 'flux'", "unknown"

    time = np.asarray(time, dtype=np.float64)
    flux = np.asarray(flux, dtype=np.float64)

    # decide cosa salvare in colonna 'mag'
    if curve.get("mag") is not None:
        mag = np.asarray(curve["mag"], dtype=np.float64)
        kind = "mag"
        df = pd.DataFrame({"hjd": time, "mag": mag})
    else:
        kind = "flux"
        df = pd.DataFrame({"hjd": time, "mag": flux})

    # pulizia base
    df["hjd"] = pd.to_numeric(df["hjd"], errors="coerce")
    df["mag"] = pd.to_numeric(df["mag"], errors="coerce")
    df = df.dropna(subset=["hjd", "mag"]).sort_values("hjd").reset_index(drop=True)

    if df.empty:
        return None, "Nessun punto valido dopo conversione/pulizia", kind

    return df, None, kind


# =============================================================================
# ENDPOINT
# =============================================================================

@catalogs_bp.route('/api/catalogs/qlp/upload', methods=['POST'])
@login_required
@admin_required('analyst')
def upload_qlp_file():
    # --- Verifica file ---
    if 'file' not in request.files:
        return jsonify({'error': 'Nessun file caricato'}), 400

    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'error': 'Nessun file selezionato'}), 400

    # --- Parametri ---
    gaia_id = request.form.get('gaia_id')
    if not gaia_id:
        return jsonify({'error': 'gaia_id è obbligatorio'}), 400

    catalog_name = request.form.get('catalog_name') or 'TESS-QLP'
    sector = request.form.get('sector') or None

    # Aggiungi sector al nome del catalogo se presente
    if sector:
        catalog_name = f"{catalog_name}_Sector{sector}"

    db = get_db_session()
    tmp_path = None

    try:
        logger.info(f"QLP upload: filename={file.filename}, gaia_id={gaia_id}, sector={sector}")

        # Step 0: crea record import SUBITO (tracking), FIX search_type
        import_record = create_import_record(
            db=db,
            catalog_name=catalog_name,
            search_type='file',          # ✅ compatibile con ENUM/VARCHAR
            search_value=file.filename,
            ra=None,
            dec=None,
            radius_arcsec=0,
            gaia_id=gaia_id,
            user_id=current_user.id,
            state='importing'
        )

        # Step 1: salva temporaneo
        with NamedTemporaryFile(suffix=".fits", delete=False) as tmp:
            tmp_path = tmp.name
            file.save(tmp_path)

        # Step 2: ingest core (reader→policy→mag)
        lc_set, report = ingest_qlp_core(
            str(tmp_path),
            origin="local_upload",
            compute_magnitude=True,
            allow_mag_fallback=False,
            require_author="QLP",
        )

        curves = lc_set.get("curves") or {}
        curve_name, curve_err = _choose_curve(curves)
        if curve_name is None:
            import_record.state = 'failed'
            import_record.error_message = curve_err or "Nessuna curva disponibile"
            db.commit()
            return jsonify({'success': False, 'error': import_record.error_message, 'import_id': import_record.id}), 400

        curve = curves[curve_name]

        # Step 3: build DF standard
        df, parse_error, kind = _build_df_from_curve(curve)
        if df is None:
            import_record.state = 'failed'
            import_record.error_message = parse_error or "Errore parsing QLP"
            db.commit()
            return jsonify({'success': False, 'error': import_record.error_message, 'import_id': import_record.id}), 400

        # Step 4: persistenza
        logger.info(
            "QLP DF: rows=%s cols=%s head=%s",
            len(df), list(df.columns), df.head(3).to_dict(orient="records")
        )
        logger.info(
            "QLP DF ranges: hjd=[%s,%s] mag=[%s,%s] nulls=%s",
            df["hjd"].min(), df["hjd"].max(),
            df["mag"].min(), df["mag"].max(),
            df.isna().sum().to_dict()
        )
        logger.info("insert_catalog_data inputs: gaia_id=%s catalog_name=%s sector=%s", gaia_id, catalog_name, sector)

        # Determina proprietario dei dati
        # - superuser: association_id_owner = None (dati centrali, bacino principale)
        # - admin/analyst: association_id_owner = current_user.association_id (dati dell'associazione)
        association_id_owner = None
        if current_user.role != 'superuser':
            association_id_owner = current_user.association_id

        points_imported = insert_catalog_data(
            db, gaia_id, catalog_name, df,
            association_id_owner=association_id_owner,
            catalog_import_id=import_record.id
        )
        if points_imported == 0:
            import_record.state = 'failed'
            import_record.error_message = "Nessun punto importato"
            db.commit()
            return jsonify({'success': False, 'error': import_record.error_message, 'import_id': import_record.id}), 400

        # Step 5: statistiche + update import
        time_range = (float(df['hjd'].min()), float(df['hjd'].max()))
        mag_range = (float(df['mag'].min()), float(df['mag'].max()))

        # band: se kind=mag, allora è davvero magnitudine; se flux, segnalo chiaramente
        band_value = 'tess' if kind == 'mag' else 'tess_qlp_flux'

        update_import_with_results(
            db=db,
            import_record=import_record,
            catalog_name=catalog_name,
            success=True,
            point_count=points_imported,
            band=band_value,
            time_range=time_range,
            mag_range=mag_range
        )

        meta = lc_set.get("meta") or {}

        response = {
            'success': True,
            'import_id': import_record.id,
            'points_imported': points_imported,
            'source_name': catalog_name,
            'gaia_id': gaia_id,
            'sector': sector or meta.get("sector"),
            'curve_used': curve_name,
            'data_kind': kind,
            'message': f"Importati {points_imported} punti QLP da {file.filename}"
        }

        return jsonify(response)

    except Exception as e:
        db.rollback()
        logger.error(f"QLP upload error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

    finally:
        try:
            db.close()
        except Exception:
            pass

        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                logger.warning(f"Impossibile cancellare tmp FITS: {tmp_path}")

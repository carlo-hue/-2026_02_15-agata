"""
services/data_loader_exoplanets.py - Caricamento Dati Osservazioni Reali

Supporta upload e parsing di dati da:
- File CSV/TXT (JD, mag, flux, errori)
- File FITS (tabelle binarie)
- Formati comuni osservatori (AstroImageJ, IRAF, DAOPHOT)

Autore: AGATA Project Team
Data: 2026-01-04
"""

import numpy as np
import logging
from typing import Dict, List, Optional, Tuple
import io

logger = logging.getLogger(__name__)


# =============================================================================
# PARSER CSV/TXT
# =============================================================================

def parse_csv_file(
    file_content: str,
    delimiter: str = None,
    skip_lines: int = 0,
    column_names: Optional[List[str]] = None
) -> Dict:
    """
    Parse file CSV/TXT generico.
    
    Args:
        file_content: Contenuto file come stringa
        delimiter: Separatore colonne (auto-detect se None)
        skip_lines: Righe da saltare (header/commenti)
        column_names: Nomi colonne ['jd', 'flux', 'flux_err'] o None per auto
    
    Returns:
        Dict con dati parsati e metadata
    """
    logger.info("Parsing CSV/TXT file")
    
    # =========================================================================
    # AUTO-DETECT DELIMITER
    # =========================================================================
    
    if delimiter is None:
        # Prova separatori comuni
        lines = file_content.strip().split('\n')
        test_line = lines[skip_lines] if len(lines) > skip_lines else lines[0]
        
        for sep in [',', '\t', ' ', ';', '|']:
            if sep in test_line:
                parts = test_line.split(sep)
                # Valido se almeno 2 colonne numeriche
                try:
                    floats = [float(p.strip()) for p in parts if p.strip()]
                    if len(floats) >= 2:
                        delimiter = sep
                        logger.info(f"Delimiter auto-detected: '{delimiter}'")
                        break
                except ValueError:
                    continue
        
        if delimiter is None:
            delimiter = ','  # Default
            logger.warning("Delimiter not detected, using default: ','")
    
    # =========================================================================
    # PARSE DATA
    # =========================================================================
    
    lines = file_content.strip().split('\n')
    
    # Skip header/comment lines
    data_lines = []
    for i, line in enumerate(lines):
        if i < skip_lines:
            continue
        
        # Skip comment lines (starting with #)
        if line.strip().startswith('#'):
            continue
        
        # Skip empty lines
        if not line.strip():
            continue
        
        data_lines.append(line)
    
    if not data_lines:
        raise ValueError("No data lines found in file")
    
    logger.info(f"Found {len(data_lines)} data lines")
    
    # Parse lines
    data_rows = []
    for line in data_lines:
        parts = line.split(delimiter)
        
        # Convert to floats
        try:
            row = [float(p.strip()) for p in parts if p.strip()]
            if row:  # Solo righe non vuote
                data_rows.append(row)
        except ValueError as e:
            logger.warning(f"Skipping invalid line: {line[:50]}... ({e})")
            continue
    
    if not data_rows:
        raise ValueError("No valid numeric data found")
    
    # Convert to numpy array
    data_array = np.array(data_rows)
    
    logger.info(f"Parsed data shape: {data_array.shape}")
    
    # =========================================================================
    # DETECT COLUMNS
    # =========================================================================
    
    n_cols = data_array.shape[1]
    
    if column_names is None:
        # Auto-detect based on number of columns
        if n_cols == 2:
            column_names = ['jd', 'mag']
            logger.info("Detected 2 columns: JD, mag")
        elif n_cols == 3:
            # Could be: JD, mag, mag_err OR JD, flux, flux_err
            # Check if values are < 0 (mag) or > 0 (flux)
            if np.median(data_array[:, 1]) < 0:
                column_names = ['jd', 'mag', 'mag_err']
                logger.info("Detected 3 columns: JD, mag, mag_err")
            else:
                column_names = ['jd', 'flux', 'flux_err']
                logger.info("Detected 3 columns: JD, flux, flux_err")
        elif n_cols == 4:
            column_names = ['jd', 'mag', 'mag_err', 'flux']
            logger.info("Detected 4 columns: JD, mag, mag_err, flux")
        elif n_cols >= 5:
            column_names = ['jd', 'mag', 'mag_err', 'flux', 'flux_err']
            logger.info("Detected 5+ columns: JD, mag, mag_err, flux, flux_err")
        else:
            raise ValueError(f"Unexpected number of columns: {n_cols}")
    
    # =========================================================================
    # EXTRACT DATA
    # =========================================================================
    
    result = {}
    
    for i, col_name in enumerate(column_names):
        if i < n_cols:
            result[col_name] = data_array[:, i]
    
    # Convert mag to flux if needed
    if 'mag' in result and 'flux' not in result:
        # flux = 10^(-mag/2.5)
        result['flux'] = 10 ** (-result['mag'] / 2.5)
        logger.info("Converted mag to flux")
    
    # Ensure JD is present
    if 'jd' not in result:
        raise ValueError("JD (Julian Date) column not found")
    
    # =========================================================================
    # VALIDATION
    # =========================================================================
    
    jd = result['jd']
    
    # Check JD range (should be > 2400000 for modern dates)
    if np.min(jd) < 2400000:
        logger.warning(
            f"JD values seem too small (min={np.min(jd)}). "
            f"Are you sure these are Julian Dates?"
        )
    
    # Check for NaN/Inf
    for key, values in result.items():
        n_bad = np.sum(~np.isfinite(values))
        if n_bad > 0:
            logger.warning(f"Found {n_bad} NaN/Inf values in {key}")
            # Remove bad values
            mask = np.isfinite(values)
            for k in result.keys():
                result[k] = result[k][mask]
    
    # Sort by JD
    sort_idx = np.argsort(result['jd'])
    for key in result.keys():
        result[key] = result[key][sort_idx]
    
    logger.info(f"Final data points: {len(result['jd'])}")
    
    # =========================================================================
    # METADATA
    # =========================================================================
    
    result['metadata'] = {
        'n_points': len(result['jd']),
        'jd_min': float(np.min(result['jd'])),
        'jd_max': float(np.max(result['jd'])),
        'baseline_days': float(np.max(result['jd']) - np.min(result['jd'])),
        'median_cadence_minutes': float(np.median(np.diff(result['jd'])) * 1440),
        'columns': list(result.keys() - {'metadata'}),
        'delimiter': delimiter,
        'n_cols': n_cols
    }
    
    return result


# =============================================================================
# PARSER FITS
# =============================================================================

def parse_fits_file(file_bytes: bytes) -> Dict:
    """
    Parse file FITS con tabella dati fotometrici.
    
    Args:
        file_bytes: Contenuto file FITS come bytes
    
    Returns:
        Dict con dati parsati
    """
    try:
        from astropy.io import fits
    except ImportError:
        raise ImportError(
            "astropy required for FITS support. "
            "Install with: pip install astropy"
        )
    
    logger.info("Parsing FITS file")
    
    # Apri FITS da bytes
    hdul = fits.open(io.BytesIO(file_bytes))
    
    # Cerca tabella dati (di solito HDU 1 o 2)
    table_hdu = None
    for i, hdu in enumerate(hdul):
        if isinstance(hdu, (fits.BinTableHDU, fits.TableHDU)):
            table_hdu = hdu
            logger.info(f"Found table in HDU {i}")
            break
    
    if table_hdu is None:
        raise ValueError("No table found in FITS file")
    
    # Estrai dati
    data = table_hdu.data
    
    # Log colonne disponibili
    logger.info(f"Available columns: {data.columns.names}")
    
    # =========================================================================
    # DETECT COLUMNS
    # =========================================================================
    
    result = {}
    
    # Cerca colonne comuni
    jd_cols = ['JD', 'BJD', 'TIME', 'MJD', 'HJD', 'BJD_TDB']
    flux_cols = ['FLUX', 'FLUX_RAW', 'SAP_FLUX', 'PDCSAP_FLUX']
    flux_err_cols = ['FLUX_ERR', 'FLUXERR', 'SAP_FLUX_ERR']
    mag_cols = ['MAG', 'MAGNITUDE', 'INST_MAG']
    mag_err_cols = ['MAG_ERR', 'MAGERR', 'MERR']
    
    # JD
    for col in jd_cols:
        if col in data.columns.names:
            result['jd'] = np.array(data[col])
            logger.info(f"Found JD column: {col}")
            break
    
    # Flux
    for col in flux_cols:
        if col in data.columns.names:
            result['flux'] = np.array(data[col])
            logger.info(f"Found flux column: {col}")
            break
    
    # Flux error
    for col in flux_err_cols:
        if col in data.columns.names:
            result['flux_err'] = np.array(data[col])
            logger.info(f"Found flux_err column: {col}")
            break
    
    # Magnitude
    for col in mag_cols:
        if col in data.columns.names:
            result['mag'] = np.array(data[col])
            logger.info(f"Found mag column: {col}")
            break
    
    # Mag error
    for col in mag_err_cols:
        if col in data.columns.names:
            result['mag_err'] = np.array(data[col])
            logger.info(f"Found mag_err column: {col}")
            break
    
    # Check if we have minimum required data
    if 'jd' not in result:
        raise ValueError("JD column not found in FITS table")
    
    if 'flux' not in result and 'mag' not in result:
        raise ValueError("Neither flux nor magnitude column found")
    
    # Convert mag to flux if needed
    if 'mag' in result and 'flux' not in result:
        result['flux'] = 10 ** (-result['mag'] / 2.5)
        logger.info("Converted mag to flux")
    
    # =========================================================================
    # VALIDATION
    # =========================================================================
    
    # Remove NaN/Inf
    mask = np.isfinite(result['jd']) & np.isfinite(result['flux'])
    for key in result.keys():
        result[key] = result[key][mask]
    
    # Sort by JD
    sort_idx = np.argsort(result['jd'])
    for key in result.keys():
        result[key] = result[key][sort_idx]
    
    logger.info(f"Final data points: {len(result['jd'])}")
    
    # Metadata
    result['metadata'] = {
        'n_points': len(result['jd']),
        'jd_min': float(np.min(result['jd'])),
        'jd_max': float(np.max(result['jd'])),
        'baseline_days': float(np.max(result['jd']) - np.min(result['jd'])),
        'median_cadence_minutes': float(np.median(np.diff(result['jd'])) * 1440),
        'columns': list(result.keys() - {'metadata'})
    }
    
    hdul.close()
    
    return result


# =============================================================================
# VALIDAZIONE DATI
# =============================================================================

def validate_lightcurve_data(data: Dict) -> Tuple[bool, List[str]]:
    """
    Valida dati curva di luce caricati.
    
    Args:
        data: Dict con dati caricati
    
    Returns:
        (is_valid, warnings_list)
    """
    warnings = []
    is_valid = True
    
    # Check 1: Dati minimi
    if 'jd' not in data or 'flux' not in data:
        warnings.append("ERROR: Missing required columns (jd, flux)")
        return False, warnings
    
    n_points = len(data['jd'])
    
    # Check 2: Numero punti
    if n_points < 100:
        warnings.append(f"WARNING: Very few points ({n_points}), recommend > 100")
        if n_points < 50:
            is_valid = False
            warnings.append("ERROR: Too few points for reliable analysis")
    
    # Check 3: Baseline
    baseline = data['metadata']['baseline_days']
    if baseline < 1:
        warnings.append(f"WARNING: Very short baseline ({baseline:.2f}d)")
    
    # Check 4: Cadenza
    cadence = data['metadata']['median_cadence_minutes']
    if cadence > 60:
        warnings.append(
            f"WARNING: Large cadence ({cadence:.0f} min), "
            f"may miss short transits"
        )
    
    # Check 5: Outlier
    flux = data['flux']
    flux_median = np.median(flux)
    flux_std = np.std(flux)
    
    outliers = np.abs(flux - flux_median) > 5 * flux_std
    n_outliers = np.sum(outliers)
    
    if n_outliers > 0:
        outlier_frac = n_outliers / n_points
        warnings.append(
            f"WARNING: {n_outliers} outliers detected "
            f"({outlier_frac*100:.1f}%)"
        )
        
        if outlier_frac > 0.1:
            warnings.append("WARNING: High outlier fraction, consider cleaning")
    
    # Check 6: Flux range
    flux_min = np.min(flux)
    flux_max = np.max(flux)
    flux_range = flux_max - flux_min
    
    if flux_range / flux_median < 0.001:
        warnings.append(
            "WARNING: Very small flux variations, "
            "transits may be hard to detect"
        )
    
    # Check 7: Gaps temporali
    time_diffs = np.diff(data['jd'])
    median_diff = np.median(time_diffs)
    large_gaps = time_diffs > 10 * median_diff
    n_gaps = np.sum(large_gaps)
    
    if n_gaps > 0:
        warnings.append(f"INFO: {n_gaps} large gaps in time series")
    
    return is_valid, warnings


# =============================================================================
# FUNZIONE PRINCIPALE
# =============================================================================

def load_observation_file(
    file_content: bytes,
    filename: str,
    file_format: str = 'auto'
) -> Dict:
    """
    Carica file osservazioni (auto-detect formato).
    
    Args:
        file_content: Contenuto file come bytes
        filename: Nome file
        file_format: 'auto', 'csv', 'txt', 'fits'
    
    Returns:
        Dict con dati parsati e validati
    """
    logger.info(f"Loading observation file: {filename}")
    
    # =========================================================================
    # AUTO-DETECT FORMAT
    # =========================================================================
    
    if file_format == 'auto':
        ext = filename.lower().split('.')[-1]
        
        if ext in ['fits', 'fit']:
            file_format = 'fits'
        elif ext in ['csv', 'txt', 'dat', 'asc']:
            file_format = 'csv'
        else:
            # Try FITS first, then CSV
            try:
                return load_observation_file(file_content, filename, 'fits')
            except:
                file_format = 'csv'
    
    logger.info(f"File format: {file_format}")
    
    # =========================================================================
    # PARSE FILE
    # =========================================================================
    
    if file_format == 'fits':
        data = parse_fits_file(file_content)
    
    elif file_format == 'csv':
        # Decode bytes to string
        try:
            content_str = file_content.decode('utf-8')
        except UnicodeDecodeError:
            content_str = file_content.decode('latin-1')
        
        data = parse_csv_file(content_str)
    
    else:
        raise ValueError(f"Unsupported file format: {file_format}")
    
    # =========================================================================
    # VALIDATE
    # =========================================================================
    
    is_valid, warnings = validate_lightcurve_data(data)
    
    data['validation'] = {
        'is_valid': is_valid,
        'warnings': warnings
    }
    
    logger.info(f"Validation: valid={is_valid}, warnings={len(warnings)}")
    
    return data


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    """
    Test parser con dati sintetici.
    """
    logging.basicConfig(level=logging.INFO)
    
    print("="*60)
    print("TEST DATA LOADER")
    print("="*60)
    print()
    
    # =========================================================================
    # Test 1: CSV semplice
    # =========================================================================
    
    print("Test 1: CSV semplice (JD, flux)")
    print("-"*60)
    
    csv_content = """# Test data
2460001.5, 1.0000
2460001.6, 0.9900
2460001.7, 0.9850
2460001.8, 0.9900
2460001.9, 1.0000
"""
    
    data = parse_csv_file(csv_content, delimiter=',', skip_lines=1)
    
    print(f"Points: {len(data['jd'])}")
    print(f"JD range: {data['jd'][0]:.1f} - {data['jd'][-1]:.1f}")
    print(f"Flux range: {np.min(data['flux']):.4f} - {np.max(data['flux']):.4f}")
    print()
    
    # =========================================================================
    # Test 2: CSV con errori
    # =========================================================================
    
    print("Test 2: CSV con errori (JD, mag, mag_err)")
    print("-"*60)
    
    csv_content2 = """2460001.5 15.000 0.010
2460001.6 15.010 0.012
2460001.7 15.020 0.011
"""
    
    data2 = parse_csv_file(csv_content2, delimiter=' ')
    
    print(f"Points: {len(data2['jd'])}")
    print(f"Columns: {list(data2.keys() - {'metadata'})}")
    print(f"Flux: {data2['flux'][:3]}")
    print()
    
    # =========================================================================
    # Test 3: Validation
    # =========================================================================
    
    print("Test 3: Validation")
    print("-"*60)
    
    is_valid, warnings = validate_lightcurve_data(data2)
    
    print(f"Valid: {is_valid}")
    print(f"Warnings: {len(warnings)}")
    for w in warnings:
        print(f"  - {w}")
    
    print()
    print("="*60)
    print("✓ Test completato")
    print("="*60)
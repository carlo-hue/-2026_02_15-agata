"""
periodigramma.py - Analisi periodogramma Lomb-Scargle e multi-periodo

Endpoint per:
- Periodogramma singolo (Lomb-Scargle)
- Analisi multi-periodo con pre-whitening iterativo
"""

import logging
import numpy as np
from flask import request, jsonify
from astropy.timeseries import LombScargle
from scipy.optimize import curve_fit

from agata.variable_stars import variable_stars_bp
from agata.variable_stars.constants import MIN_PERIOD, MAX_PERIOD, MAX_N_FREQ
from agata.variable_stars.services.arrow_parser import read_arrow_table_from_request

logger = logging.getLogger(__name__)


@variable_stars_bp.post("/api/periodogram.arrow")
def api_periodogram_arrow():
    """
    Calcola periodogramma Lomb-Scargle (endpoint Arrow - raccomandato).

    Versione Arrow: 10-100x più veloce di JSON per grandi dataset.

    Request:
        Body: Arrow IPC stream con colonne jd, mag
        Query params:
            - min_period: float (default: 0.02)
            - max_period: float (default: 10.0)
            - n_freq: int (default: 6000)

    Returns:
        JSON con periodogramma + metriche qualità:
        {
            "period": [float...],    // Periodi [giorni]
            "power": [float...],     // Potenza [0-1]
            "peaks": [              // Top 5 picchi annotati
                {
                    "period": float,
                    "power": float,
                    "fap": float,        // False Alarm Probability
                    "snr": float         // Signal-to-Noise Ratio
                },
                ...
            ],
            "fap_levels": {         // Soglie significatività
                "0.1": float,       // 10% FAP
                "0.01": float,      // 1% FAP
                "0.001": float      // 0.1% FAP
            }
        }

    Note:
        FAP (False Alarm Probability):
        - Probabilità che picco sia rumore casuale
        - FAP < 0.01 → significativo (99% confidence)
        - FAP < 0.001 → altamente significativo (99.9% confidence)

        Calcolo basato su: Baluev 2008, MNRAS 385, 1279
    """
    try:
        # Leggi tabella Arrow da request
        table = read_arrow_table_from_request()

        # Estrai colonne (zero-copy quando possibile)
        jd = np.asarray(table["jd"].to_numpy(zero_copy_only=False), dtype=float)
        mag = np.asarray(table["mag"].to_numpy(zero_copy_only=False), dtype=float)

        # Parametri da query string con validazione
        min_period = float(request.args.get("min_period", 0.02))
        max_period = float(request.args.get("max_period", 10.0))
        n_freq = int(request.args.get("n_freq", 10000))

        # Sanitizza input
        min_period = max(MIN_PERIOD, min(min_period, MAX_PERIOD))
        max_period = max(MIN_PERIOD, min(max_period, MAX_PERIOD))
        n_freq = max(100, min(n_freq, MAX_N_FREQ))

        if min_period >= max_period:
            return jsonify({"error": "min_period deve essere < max_period"}), 400

        logger.info(f"Periodogramma Arrow: {len(jd)} punti, {n_freq} freq")

        # Griglia frequenze
        freq = np.linspace(1.0 / max_period, 1.0 / min_period, n_freq)

        # Istanza Lomb-Scargle
        ls = LombScargle(jd, mag)

        # Calcola potenza spettrale
        power = ls.power(freq)

        # Converti a periodi (più intuitivo per astronomi)
        period = (1.0 / freq).astype(float)

        # ---------- IDENTIFICA PICCHI ----------
        n_peaks = 5
        idx = np.argpartition(power, -n_peaks)[-n_peaks:]
        idx = idx[np.argsort(power[idx])[::-1]]

        # Statistiche robuste per SNR
        power_med = np.median(power)
        power_std = np.std(power)

        # Annota ogni picco con metriche qualità
        peaks = []
        for i in idx:
            pwr = float(power[i])
            per = float(period[i])

            # False Alarm Probability
            # Prob che questo picco sia noise spike
            fap = float(ls.false_alarm_probability(pwr))

            # Signal-to-Noise Ratio
            # Quante sigma sopra mediana
            snr = float((pwr - power_med) / power_std)

            peaks.append({
                "period": per,
                "power": pwr,
                "fap": fap,     # <0.01 è buono
                "snr": snr      # >10 è ottimo
            })

        # ---------- SOGLIE FAP GLOBALI ----------
        # Livelli power corrispondenti a FAP fissate
        # Utili per disegnare linee di significatività su plot
        fap_levels = {
            "0.1": float(ls.false_alarm_level(0.1)),     # 90% confidence
            "0.01": float(ls.false_alarm_level(0.01)),   # 99% confidence
            "0.001": float(ls.false_alarm_level(0.001)), # 99.9% confidence
        }

        logger.info(f"Top peak: P={peaks[0]['period']:.4f}d, FAP={peaks[0]['fap']:.2e}, SNR={peaks[0]['snr']:.1f}")

        return jsonify({
            "period": period.tolist(),
            "power": power.astype(float).tolist(),
            "peaks": peaks,
            "fap_levels": fap_levels
        })

    except ValueError as e:
        logger.error(f"Errore validazione input: {e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Errore periodogramma Arrow: {e}", exc_info=True)
        return jsonify({"error": "Errore interno"}), 500


@variable_stars_bp.post("/api/multiperiod.arrow")
def api_multiperiod_arrow():
    """
    Analisi multi-periodo con pre-whitening iterativo usando Astropy.

    Strategia:
    1. Calcola periodogramma → trova P₁
    2. Fit sinusoide P₁ e sottrai dai dati (pre-whitening)
    3. Calcola periodogramma sui residui → trova P₂
    4. Ripeti per N periodi

    Request:
        Body: Arrow IPC stream con colonne jd, mag
        Query params:
            - min_period: float (default: 0.02)
            - max_period: float (default: 10.0)
            - n_freq: int (default: 6000)
            - n_periods: int (default: 3, max: 5)

    Returns:
        JSON con array di periodi trovati + spettro originale:
        {
            "periods": [
                {
                    "iteration": int,
                    "period": float,
                    "power": float,
                    "fap": float,
                    "snr": float,
                    "amplitude": float,
                    "phase": float,
                    "rms_before": float,
                    "rms_after": float
                },
                ...
            ],
            "spectrum": {
                "period": [float...],
                "power": [float...],
                "fap_levels": {...}
            }
        }
    """
    try:
        table = read_arrow_table_from_request()

        jd = np.asarray(table["jd"].to_numpy(zero_copy_only=False), dtype=float)
        mag = np.asarray(table["mag"].to_numpy(zero_copy_only=False), dtype=float)

        min_period = float(request.args.get("min_period", 0.02))
        max_period = float(request.args.get("max_period", 10.0))
        n_freq = int(request.args.get("n_freq", 6000))
        n_periods = min(int(request.args.get("n_periods", 3)), 5)

        # Sanitizza
        min_period = max(MIN_PERIOD, min(min_period, MAX_PERIOD))
        max_period = max(MIN_PERIOD, min(max_period, MAX_PERIOD))
        n_freq = max(100, min(n_freq, MAX_N_FREQ))

        logger.info(f"Multi-periodo: {len(jd)} punti, {n_periods} periodi da cercare")

        # Usa tempo relativo per precisione
        t0 = jd[0]
        t_rel = jd - t0

        # Griglia frequenze
        freq = np.linspace(1.0 / max_period, 1.0 / min_period, n_freq)
        period_grid = 1.0 / freq

        results = []
        current_mag = mag.copy()

        # Spettro originale (salva per plot)
        ls_original = LombScargle(t_rel, mag)
        power_original = ls_original.power(freq)

        for iteration in range(n_periods):
            logger.info(f"  Iterazione {iteration + 1}/{n_periods}")

            # Periodogramma sui dati correnti
            ls = LombScargle(t_rel, current_mag)
            power = ls.power(freq)

            # Trova picco massimo
            idx_max = np.argmax(power)
            best_period = float(period_grid[idx_max])
            best_power = float(power[idx_max])
            best_fap = float(ls.false_alarm_probability(best_power))

            # Calcola SNR
            power_med = np.median(power)
            power_std = np.std(power)
            snr = float((best_power - power_med) / power_std)

            # Fit sinusoide con scipy per robustezza
            def sinusoid(t, A0, A, phase):
                return A0 + A * np.sin(2 * np.pi * t / best_period + phase)

            try:
                # Stima iniziale
                A0_init = np.mean(current_mag)
                A_init = (np.max(current_mag) - np.min(current_mag)) / 2

                popt, _ = curve_fit(
                    sinusoid,
                    t_rel,
                    current_mag,
                    p0=[A0_init, A_init, 0],
                    maxfev=2000
                )

                A0, A, phase = popt

            except Exception as e:
                logger.warning(f"Fit fallito, uso metodo semplice: {e}")
                # Fallback: fit least-squares diretto
                angle = (2 * np.pi * t_rel) / best_period
                A0 = np.mean(current_mag)
                sumCos = np.sum((current_mag - A0) * np.cos(angle))
                sumSin = np.sum((current_mag - A0) * np.sin(angle))
                A = 2 * np.sqrt(sumCos**2 + sumSin**2) / len(t_rel)
                phase = np.arctan2(sumSin, sumCos)

            # RMS prima del pre-whitening
            rms_before = float(np.std(current_mag))

            # Sottrai segnale (pre-whitening)
            fitted = A0 + A * np.sin(2 * np.pi * t_rel / best_period + phase)
            residuals = current_mag - fitted

            # RMS dopo
            rms_after = float(np.std(residuals))
            reduction = (rms_before - rms_after) / rms_before * 100

            logger.info(f"    P={best_period:.6f}d, A={A:.4f} mag, RMS: {rms_before:.4f} → {rms_after:.4f} ({reduction:.1f}%)")

            results.append({
                "iteration": iteration + 1,
                "period": best_period,
                "power": best_power,
                "fap": best_fap,
                "snr": snr,
                "amplitude": float(np.abs(A)),
                "phase": float(phase),
                "rms_before": rms_before,
                "rms_after": rms_after,
                "reduction_percent": float(reduction)
            })

            # Continua con residui
            current_mag = residuals

            # Stop se riduzione < 3% (soglia più permissiva per segnali deboli)
            # Ma solo dopo la 2a iterazione per dare più possibilità
            if reduction < 3 and iteration > 1:
                logger.info("    Pre-whitening inefficace (<3%), stop")
                break

            # Stop se RMS troppo piccolo
            if rms_after < 0.001:
                logger.info("    RMS residui troppo piccolo, stop")
                break

            # Stop se SNR del picco trovato è troppo basso
            if snr < 5 and iteration > 0:
                logger.info(f"    SNR troppo basso ({snr:.1f} < 5), stop")
                break

        # FAP levels dal periodogramma originale
        fap_levels = {
            "0.1": float(ls_original.false_alarm_level(0.1)),
            "0.01": float(ls_original.false_alarm_level(0.01)),
            "0.001": float(ls_original.false_alarm_level(0.001)),
        }

        return jsonify({
            "periods": results,
            "spectrum": {
                "period": period_grid.astype(float).tolist(),
                "power": power_original.astype(float).tolist(),
                "fap_levels": fap_levels
            }
        })

    except Exception as e:
        logger.error(f"Errore multi-periodo: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

# agata/admin/services/vast_executor.py
"""
VAST External Tool Executor

Fornisce wrapper sicuro per esecuzione del binario VAST.
"""
import subprocess
import os
import logging
from pathlib import Path
from typing import Optional, List, Dict
import glob

logger = logging.getLogger(__name__)


class VastExecutor:
    """Esecuzione tool VAST per fotometria astronomica."""

    def __init__(self):
        self.vast_binary = os.getenv(
            'VAST_BINARY_PATH',
            '/home/azureuser/Documents/vast-1.0rc87/vast'
        )
        if not Path(self.vast_binary).exists():
            raise FileNotFoundError(f"VAST binary not found: {self.vast_binary}")

        logger.info(f"VastExecutor initialized with binary: {self.vast_binary}")

    def run_vast_analysis(
        self,
        image_dir: str = None,
        output_dir: str = None,
        reference_frame: str = None,
        image_paths: List[str] = None,
        options: dict = None
    ) -> Dict:
        """
        Esecuzione VAST (singola, senza crop).

        Args:
            image_dir: Directory contenente immagini FITS
            output_dir: Directory per salvare risultati
            reference_frame: Immagine riferimento (auto-selezionata se None)
            image_paths: Ignorato - usa image_dir e glob pattern
            options: Parametri VAST aggiuntivi

        Returns:
            dict con stdout, stderr, return_code, success
        """
        # Valida directory
        if not image_dir:
            raise ValueError("image_dir is required")

        if not os.path.isdir(image_dir):
            raise ValueError(f"image_dir does not exist: {image_dir}")

        # Verifica che ci siano file FITS
        fits_files = sorted(glob.glob(f"{image_dir}/*.fit*"))
        if not fits_files:
            raise FileNotFoundError(f"No FITS files found in {image_dir}")

        logger.info(f"Found {len(fits_files)} FITS files in {image_dir}")

        # Se nessuna immagine di riferimento, usa la prima
        if not reference_frame:
            reference_frame = fits_files[0]
            logger.info(f"Auto-selected reference frame: {reference_frame}")

        # Build VAST command con shell pattern
        # Parametri: -u (update mode), -r (reference), -f (full output), -y (threshold), -t (trials)
        vast_dir = os.path.dirname(self.vast_binary)

        threshold = '3'
        trials = '0'
        if options:
            threshold = options.get('threshold', '3')
            trials = options.get('trials', '0')

        # Build command string for shell execution
        # NOTA: il reference_frame viene passato singolarmente
        # I file per la fotometria vengono passati col pattern glob
        # Questo evita di duplicare il reference nel pattern
        cmd_str = f"{self.vast_binary} -u -r -f -y {threshold} -t {trials} {reference_frame} {image_dir}/*.fit*"

        logger.info(f"Running VAST command: {cmd_str[:100]}...")  # Log first 100 chars only

        try:
            logger.info(f"VAST working directory: {vast_dir}")
            logger.info(f"VAST reference frame: {reference_frame}")

            # Crea file di log per VAST
            vast_log_file = os.path.join(vast_dir, 'vast_execution.log')
            logger.info(f"VAST output will be saved to: {vast_log_file}")

            result = subprocess.run(
                cmd_str,
                shell=True,
                cwd=vast_dir,
                capture_output=True,
                text=True,
                timeout=28800,  # 8 hours max
                check=False
            )

            # Salva output VAST a file per debug
            with open(vast_log_file, 'w') as f:
                f.write("=== VAST STDOUT ===\n")
                f.write(result.stdout)
                f.write("\n=== VAST STDERR ===\n")
                f.write(result.stderr)
            logger.info(f"VAST output saved to {vast_log_file}")

            logger.info(f"VAST completed with return code {result.returncode}")

            # Verifica file output - VAST crea i file principali nella sua directory
            # I file principali sono:
            # - vast_lightcurve_statistics.log (statistiche fotometriche)
            # - vast_autocandidates.log (candidate variabili)
            # - vast_autocandidates_details.log (dettagli candidate con flag)
            # - vast_summary.log (sommario esecuzione)
            lightcurve_stats = os.path.join(vast_dir, 'vast_lightcurve_statistics.log')
            candidates_log = os.path.join(vast_dir, 'vast_autocandidates.log')
            candidates_details_log = os.path.join(vast_dir, 'vast_autocandidates_details.log')
            summary_log = os.path.join(vast_dir, 'vast_summary.log')

            has_output = os.path.exists(lightcurve_stats) and os.path.exists(candidates_log)
            success = result.returncode == 0 and has_output

            if not success:
                logger.warning(f"VAST analysis may have failed. Stats file: {os.path.exists(lightcurve_stats)}, Candidates file: {os.path.exists(candidates_log)}, return code: {result.returncode}")

            return {
                'success': success,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'return_code': result.returncode,
                'output_csv': candidates_log if has_output else None,
                'candidates_details_log': candidates_details_log if os.path.exists(candidates_details_log) else None,
                'stats_log': lightcurve_stats if has_output else None,
                'summary_log': summary_log if os.path.exists(summary_log) else None,
                'reference_frame': reference_frame,
                'vast_dir': vast_dir,
            }

        except subprocess.TimeoutExpired:
            logger.error("VAST analysis timed out after 2 hours")
            raise
        except Exception as e:
            logger.error(f"VAST execution failed: {e}", exc_info=True)
            raise

    def validate_existing_output(
        self,
        image_dir: str = None,
        reference_frame: str = None
    ) -> Dict:
        """
        Valida output VAST esistente (VAST già lanciato fuori dall'app).

        Controlla che i file principali esistano nella directory VAST
        e che ci siano file outNNNNN.dat con le curve di luce.

        Args:
            image_dir: Directory con le immagini FITS
            reference_frame: Immagine di riferimento

        Returns:
            dict con stessa struttura di run_vast_analysis
        """
        vast_dir = os.path.dirname(self.vast_binary)

        # Verifica file principali VAST output
        lightcurve_stats = os.path.join(vast_dir, 'vast_lightcurve_statistics.log')
        candidates_log = os.path.join(vast_dir, 'vast_autocandidates.log')
        candidates_details_log = os.path.join(vast_dir, 'vast_autocandidates_details.log')
        summary_log = os.path.join(vast_dir, 'vast_summary.log')

        # Check file obbligatori
        missing = []
        if not os.path.exists(lightcurve_stats):
            missing.append('vast_lightcurve_statistics.log')
        if not os.path.exists(candidates_log):
            missing.append('vast_autocandidates.log')

        if missing:
            raise FileNotFoundError(
                f"VAST output files missing in {vast_dir}: {', '.join(missing)}. "
                f"Run VAST first before using skip mode."
            )

        # Conta file .dat (curve di luce)
        dat_files = glob.glob(os.path.join(vast_dir, 'out*.dat'))
        if not dat_files:
            raise FileNotFoundError(
                f"No out*.dat lightcurve files found in {vast_dir}. "
                f"VAST output appears incomplete."
            )

        logger.info(
            f"Validated existing VAST output in {vast_dir}: "
            f"stats=OK, candidates=OK, {len(dat_files)} .dat files"
        )

        # Se nessuna reference_frame fornita, cerca nella directory immagini
        if not reference_frame and image_dir:
            fits_files = sorted(glob.glob(f"{image_dir}/*.fit*"))
            if fits_files:
                reference_frame = fits_files[0]
                logger.info(f"Auto-selected reference frame: {reference_frame}")

        return {
            'success': True,
            'stdout': '[skip_vast mode] Using existing VAST output',
            'stderr': '',
            'return_code': 0,
            'output_csv': candidates_log,
            'candidates_details_log': candidates_details_log if os.path.exists(candidates_details_log) else None,
            'stats_log': lightcurve_stats,
            'summary_log': summary_log if os.path.exists(summary_log) else None,
            'reference_frame': reference_frame,
            'vast_dir': vast_dir,
        }

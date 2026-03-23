/**
 * config.js - Configurazione Centralizzata AAAAT
 * 
 * Contiene tutte le costanti, limiti e parametri default dell'applicazione.
 * Centralizzare la configurazione permette:
 * - Facile manutenzione
 * - Nessun "magic number" sparso nel codice
 * - Modifiche in un solo posto
 * - Documentazione integrata
 * 
 * UTILIZZO:
 * 
 * ```javascript
 * import { CONFIG } from './config.js';
 * 
 * // Usa costanti invece di valori hardcoded
 * if (nPoints > CONFIG.LIMITS.MAX_POINTS_PLOT) {
 *   // downsample
 * }
 * 
 * // Parametri default
 * const sigma = CONFIG.SIGMA_CLIP.DEFAULT_THRESHOLD;
 * ```
 */

// =============================================================================
// CONFIGURAZIONE PRINCIPALE
// =============================================================================

export const CONFIG = {
  
  // ===========================================================================
  // VERSIONE APPLICAZIONE
  // ===========================================================================
  VERSION: '1.3.3',
  BUILD_DATE: '2026-01-01',
  
  // ===========================================================================
  // API ENDPOINTS
  // ===========================================================================
  API: {
    // Base URL (relativo)
    BASE: '/agata/api',
    
    // Endpoint specifici
    LIGHTCURVE: '/agata/variable-stars/api/lightcurve.arrow',
    PERIODOGRAM: '/agata/variable-stars/api/periodogram.arrow',
    PHASE: '/agata/variable-stars/api/phase.arrow',
    SIGMA_CLIP: '/agata/variable-stars/api/sigma_clip.arrow',
    STATE_SAVE: '/agata/variable-stars/api/state/save',
    STATE_LOAD: '/agata/variable-stars/api/state/load',
    
    // Timeout requests (ms)
    TIMEOUT: {
      LIGHTCURVE: 30000,    // 30s per caricamento dati
      PERIODOGRAM: 60000,   // 60s per calcolo periodogramma
      PHASE: 10000,         // 10s per phase folding
      SIGMA_CLIP: 20000,    // 20s per sigma clipping
      STATE: 5000           // 5s per save/load stato
    }
  },
  
  // ===========================================================================
  // LIMITI VALIDAZIONE
  // ===========================================================================
  LIMITS: {
    // Punti dati
    MIN_POINTS_TOTAL: 10,           // Minimo punti totali
    MIN_POINTS_SESSION: 5,          // Minimo punti per sessione
    MAX_POINTS_PLOT: 100000,        // Max punti senza downsampling
    MAX_POINTS_TOTAL: 10000000,     // Max punti assoluto
    
    // Sessioni
    MIN_SESSIONS: 1,
    MAX_SESSIONS: 50,               // Max sessioni sintetiche
    
    // Periodogramma
    MIN_PERIOD: 0.001,              // Periodo minimo [giorni]
    MAX_PERIOD: 1000.0,             // Periodo massimo [giorni]
    MIN_FREQ_POINTS: 100,           // Minimo punti frequenza
    MAX_FREQ_POINTS: 50000,         // Massimo punti frequenza
    
    // Fase
    MIN_PHASE_BINS: 10,
    MAX_PHASE_BINS: 1000,
    
    // Input utente
    MAX_GAIA_ID_LENGTH: 50,
    MAX_SEED: 999999,
    MIN_SEED: 0
  },
  
  // ===========================================================================
  // SIGMA CLIPPING
  // ===========================================================================
  SIGMA_CLIP: {
    // Threshold sigma
    DEFAULT_THRESHOLD: 3.0,
    MIN_THRESHOLD: 0.5,
    MAX_THRESHOLD: 10.0,
    
    // Fattore conversione MAD → σ
    // Per distribuzione Gaussiana: σ = 1.4826 × MAD
    MAD_TO_SIGMA_FACTOR: 1.4826,
    
    // Minimo punti per sessione (sotto questo skip)
    MIN_POINTS_PER_SESSION: 5,
    
    // Protezione MAD = 0 (tutti punti identici)
    MAD_EPSILON: 1e-6
  },
  
  // ===========================================================================
  // PERIODOGRAMMA
  // ===========================================================================
  PERIODOGRAM: {
    // Parametri default
    DEFAULT_MIN_PERIOD: 0.02,       // 28.8 minuti
    DEFAULT_MAX_PERIOD: 10.0,       // 10 giorni
    DEFAULT_N_FREQ: 6000,           // Numero frequenze
    
    // Top N picchi da mostrare
    N_PEAKS_DISPLAY: 5,
    N_PEAKS_COMPUTE: 10,            // Calcoliamo top 10, mostriamo top 5
    
    // Soglie significatività FAP (False Alarm Probability)
    FAP_LEVELS: [0.1, 0.01, 0.001], // 10%, 1%, 0.1%
    FAP_SIGNIFICANT: 0.01,          // <1% = significativo
    FAP_HIGHLY_SIGNIFICANT: 0.001,  // <0.1% = altamente significativo
    
    // SNR (Signal to Noise Ratio)
    SNR_GOOD: 5.0,                  // SNR >5 è buono
    SNR_EXCELLENT: 10.0             // SNR >10 è eccellente
  },
  
  // ===========================================================================
  // PHASE FOLDING
  // ===========================================================================
  PHASE: {
    // Range fase supportati
    RANGES: [
      { value: '-1-1', label: '-1 a +1', min: -1, max: 1 },
      { value: '0-2', label: '0 a 2', min: 0, max: 2 },
      { value: '-0.5-0.5', label: '-0.5 a +0.5', min: -0.5, max: 0.5 }
    ],
    DEFAULT_RANGE: '-1-1',
    
    // Shift fase
    DEFAULT_SHIFT: 0.0,
    MIN_SHIFT: -1.0,
    MAX_SHIFT: 1.0,
    
    // Binning per statistiche
    DEFAULT_BINS: 20,
    
    // Coverage minima per fit affidabile
    MIN_COVERAGE_GOOD: 0.80,        // 80%
    MIN_COVERAGE_ACCEPTABLE: 0.60   // 60%
  },
  
  // ===========================================================================
  // VISUALIZZAZIONE
  // ===========================================================================
  PLOT: {
    // Colori sessioni (Tableau 10)
    SESSION_COLORS: [
      '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728',
      '#9467bd', '#8c564b', '#e377c2', '#7f7f7f',
      '#bcbd22', '#17becf'
    ],
    
    // Dimensioni grafici
    DEFAULT_WIDTH: 800,
    DEFAULT_HEIGHT: 400,
    
    // Marker - Dimensioni punti regolabili
    MARKER_SIZE: {
      DEFAULT: 3,        // Dimensione default dei punti normali
      MIN: 1,            // Minimo consentito
      MAX: 15,           // Massimo consentito
      STEP: 0.5,         // Step dello slider
      
      // Moltiplicatori per punti speciali (relativi al valore corrente)
      OUTLIER_MULTIPLIER: 3.0,      // Outlier sigma-clip (es: 3 → 9)
      SELECTED_MULTIPLIER: 2.5,     // Selezione manuale (es: 3 → 7.5)
      HIGHLIGHT_MULTIPLIER: 2.0     // Evidenziazione (es: 3 → 6)
    },
    
    // Opacità
    OPACITY: {
      NORMAL: 0.7,
      DIMMED: 0.3,
      HIGHLIGHTED: 1.0
    },
    
    // Line width
    LINE_WIDTH: {
      THIN: 1,
      NORMAL: 2,
      BOLD: 3
    },
    
    // Downsampling
    DOWNSAMPLE_THRESHOLD: 10000,    // Oltre 10k punti → downsample
    DOWNSAMPLE_TARGET: 5000         // Target ~5k punti
  },
  
  // ===========================================================================
  // DATI SINTETICI
  // ===========================================================================
  SYNTHETIC: {
    // Tipi stelle supportati
    TYPES: [
      { value: 'rrlyrae', label: 'RR Lyrae tipo ab', period: 0.57 },
      { value: 'delta_scuti', label: 'Delta Scuti', period: 0.08 },
      { value: 'eclipsing', label: 'Binaria Eclissante', period: 1.23 },
      { value: 'cepheid', label: 'Cepheide Classica', period: 5.4 },
      { value: 'irregular', label: 'Variabile Irregolare', period: 2.5 }
    ],
    
    // Parametri default
    DEFAULT_TYPE: 'rrlyrae',
    DEFAULT_SESSIONS: 6,
    DEFAULT_SEED: 1,
    DEFAULT_REALISM: 4,             // 0=ideale, 5=realistico max
    
    // Range parametri
    MIN_REALISM: 0,
    MAX_REALISM: 5
  },
  
  // ===========================================================================
  // STATO PERSISTENZA
  // ===========================================================================
  STATE: {
    // Chiave localStorage per backup locale
    LOCAL_STORAGE_KEY: 'aaaat_state_backup',
    
    // Auto-save intervallo (ms)
    AUTO_SAVE_INTERVAL: 30000,      // Ogni 30s
    
    // Compressione stato (se >X bytes)
    COMPRESSION_THRESHOLD: 50000,   // 50KB
    
    // Versione schema stato (per migrazioni future)
    SCHEMA_VERSION: 2
  },
  
  // ===========================================================================
  // UI/UX
  // ===========================================================================
  UI: {
    // Debounce slider (ms)
    SLIDER_DEBOUNCE: 300,
    
    // Debounce input (ms)
    INPUT_DEBOUNCE: 500,
    
    // Toast notification duration (ms)
    TOAST_DURATION: 3000,
    
    // Animazioni
    ANIMATION_DURATION: 300,        // ms
    
    // Loader delay (evita flash per operazioni veloci)
    LOADER_DELAY: 200               // ms
  },
  
  // ===========================================================================
  // PERFORMANCE
  // ===========================================================================
  PERFORMANCE: {
    // Web Worker per calcoli pesanti?
    USE_WEB_WORKER: false,          // TODO: implementare
    
    // Batch size per processamento
    BATCH_SIZE: 1000,
    
    // Request caching (ms)
    CACHE_TTL: 300000,              // 5 minuti
    
    // Max memory per cache (bytes)
    MAX_CACHE_SIZE: 100 * 1024 * 1024  // 100MB
  },
  
  // ===========================================================================
  // TEMPLATE TEORICI
  // ===========================================================================
  TEMPLATES: {
    // Template disponibili per overlay
    AVAILABLE: [
      { value: 'none', label: 'Nessuno' },
      { value: 'rrlyrae_ab', label: 'RR Lyrae ab' },
      { value: 'rrlyrae_c', label: 'RR Lyrae c' },
      { value: 'cepheid', label: 'Cepheide Classica' },
      { value: 'ea_algol', label: 'EA (Algol)' },
      { value: 'ew_wuma', label: 'EW (W UMa)' }
    ],
    
    // Stile linea template
    LINE_STYLE: 'dash',
    LINE_COLOR: '#dc3545',          // Rosso
    LINE_WIDTH: 2
  },
  
  // ===========================================================================
  // EXPORT
  // ===========================================================================
  EXPORT: {
    // Formati supportati
    FORMATS: {
      CSV: { ext: '.csv', mime: 'text/csv' },
      JSON: { ext: '.json', mime: 'application/json' },
      PNG: { ext: '.png', mime: 'image/png' },
      PDF: { ext: '.pdf', mime: 'application/pdf' }
    },
    
    // Default filename prefix
    FILENAME_PREFIX: 'aaaat_export',
    
    // CSV
    CSV_DELIMITER: ',',
    CSV_DECIMAL: '.',
    CSV_ENCODING: 'utf-8'
  },
  
  // ===========================================================================
  // DEBUG
  // ===========================================================================
  DEBUG: {
    // Abilita logging esteso?
    ENABLED: false,
    
    // Log performance?
    LOG_PERFORMANCE: false,
    
    // Log API calls?
    LOG_API: false,
    
    // Mostra banner versione?
    SHOW_VERSION_BANNER: true
  }
};

// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================

/**
 * Valida periodo in range valido
 * @param {number} period - Periodo in giorni
 * @returns {boolean}
 */
export function isValidPeriod(period) {
  return period >= CONFIG.LIMITS.MIN_PERIOD && 
         period <= CONFIG.LIMITS.MAX_PERIOD;
}

/**
 * Valida sigma threshold
 * @param {number} sigma - Soglia sigma
 * @returns {boolean}
 */
export function isValidSigma(sigma) {
  return sigma >= CONFIG.SIGMA_CLIP.MIN_THRESHOLD && 
         sigma <= CONFIG.SIGMA_CLIP.MAX_THRESHOLD;
}

/**
 * Valida numero punti
 * @param {number} n - Numero punti
 * @returns {boolean}
 */
export function isValidPointCount(n) {
  return n >= CONFIG.LIMITS.MIN_POINTS_TOTAL && 
         n <= CONFIG.LIMITS.MAX_POINTS_TOTAL;
}

/**
 * Ottieni colore per sessione
 * @param {number} sessionId - ID sessione
 * @returns {string} - Colore hex
 */
export function getSessionColor(sessionId) {
  const colors = CONFIG.PLOT.SESSION_COLORS;
  return colors[sessionId % colors.length];
}

/**
 * Formatta periodo per display
 * @param {number} period - Periodo in giorni
 * @returns {string} - Periodo formattato con unità
 */
export function formatPeriod(period) {
  if (period < 1) {
    // Converti in ore
    return `${(period * 24).toFixed(3)} h`;
  } else if (period < 365) {
    return `${period.toFixed(4)} d`;
  } else {
    // Converti in anni
    return `${(period / 365.25).toFixed(2)} yr`;
  }
}

/**
 * Formatta FAP (False Alarm Probability)
 * @param {number} fap - FAP [0-1]
 * @returns {string} - FAP formattato
 */
export function formatFAP(fap) {
  if (fap < 0.0001) {
    return '<0.01%';
  } else if (fap < 0.01) {
    return `${(fap * 100).toFixed(2)}%`;
  } else {
    return `${(fap * 100).toFixed(1)}%`;
  }
}

/**
 * Determina se downsampling è necessario
 * @param {number} nPoints - Numero punti
 * @returns {boolean}
 */
export function needsDownsampling(nPoints) {
  return nPoints > CONFIG.PLOT.DOWNSAMPLE_THRESHOLD;
}

/**
 * Calcola target downsampling
 * @param {number} nPoints - Numero punti originale
 * @returns {number} - Numero punti target
 */
export function getDownsampleTarget(nPoints) {
  if (!needsDownsampling(nPoints)) {
    return nPoints;
  }
  return CONFIG.PLOT.DOWNSAMPLE_TARGET;
}

// =============================================================================
// EXPORT GLOBALE (per debug console)
// =============================================================================

if (typeof window !== 'undefined') {
  // Esponi CONFIG globalmente per ispezione/debug
  window.AAAAT_CONFIG = CONFIG;
  
  // Utility globali
  window.getSessionColor = getSessionColor;
  window.formatPeriod = formatPeriod;
  window.formatFAP = formatFAP;
  
  // Banner versione
  if (CONFIG.DEBUG.SHOW_VERSION_BANNER) {
    console.log(
      `%c╔════════════════════════════════════════╗\n` +
      `║   AAAAT v${CONFIG.VERSION}                  ║\n` +
      `║   Analisi Curve di Luce Stellari      ║\n` +
      `║   Build: ${CONFIG.BUILD_DATE}               ║\n` +
      `╚════════════════════════════════════════╝`,
      'color: #0dcaf0; font-weight: bold; font-family: monospace;'
    );
  }
}

// =============================================================================
// ESEMPI USO
// =============================================================================

/**
 * ESEMPI:
 * 
 * // Import config
 * import { CONFIG, isValidPeriod, formatPeriod } from './config.js';
 * 
 * // Usa costanti
 * const threshold = CONFIG.SIGMA_CLIP.DEFAULT_THRESHOLD;
 * const maxPoints = CONFIG.LIMITS.MAX_POINTS_PLOT;
 * 
 * // Validazione
 * if (!isValidPeriod(userPeriod)) {
 *   alert(`Periodo deve essere tra ${CONFIG.LIMITS.MIN_PERIOD} e ${CONFIG.LIMITS.MAX_PERIOD}`);
 * }
 * 
 * // Formattazione
 * const periodStr = formatPeriod(0.573);  // "0.5730 d"
 * const fapStr = formatFAP(0.0023);       // "0.23%"
 * 
 * // Colori
 * const color = getSessionColor(sessionId);
 * 
 * // Da console:
 * window.AAAAT_CONFIG  // Ispeziona tutta config
 */
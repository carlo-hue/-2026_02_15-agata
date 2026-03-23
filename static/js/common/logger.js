/**
 * logger.js - Sistema di Logging Professionale per AAAAT
 * 
 * Sistema di logging completo con:
 * - Livelli di log (DEBUG, INFO, WARN, ERROR)
 * - Formattazione colorata in console
 * - Timestamp
 * - Namespace per moduli
 * - On/Off globale o per namespace
 * - Performance timing
 * - Persistenza configurazione in localStorage
 * 
 * UTILIZZO:
 * 
 * ```javascript
 * import { logger, setLogLevel } from './logger.js';
 * 
 * // Crea logger per modulo specifico
 * const log = logger('ModuleName');
 * 
 * // Usa logging
 * log.debug('Dettagli tecnici', { data: value });
 * log.info('Operazione completata', result);
 * log.warn('Attenzione!', issue);
 * log.error('Errore critico!', error);
 * 
 * // Performance timing
 * log.time('operazione-pesante');
 * // ... codice ...
 * log.timeEnd('operazione-pesante');  // Log: "operazione-pesante: 123.45ms"
 * 
 * // Configurazione globale
 * setLogLevel('DEBUG');  // Mostra tutto
 * setLogLevel('WARN');   // Solo warning ed errori
 * setLogLevel('OFF');    // Disabilita tutto
 * 
 * // Configurazione per namespace
 * setNamespaceLevel('Arrow', 'DEBUG');  // Solo Arrow in debug
 * setNamespaceLevel('UI', 'OFF');       // Disabilita log UI
 * ```
 * 
 * ATTIVAZIONE DA CONSOLE BROWSER:
 * 
 * ```javascript
 * // Attiva logging globale DEBUG
 * window.AAAAT_DEBUG = true;
 * 
 * // O imposta livello specifico
 * window.setLogLevel('DEBUG');
 * 
 * // Attiva solo per modulo
 * window.setNamespaceLevel('Periodogram', 'DEBUG');
 * 
 * // Performance profiling
 * window.AAAAT_PROFILE = true;
 * ```
 */

// =============================================================================
// CONFIGURAZIONE
// =============================================================================

/**
 * Livelli di log (in ordine di severità)
 */
const LOG_LEVELS = {
  DEBUG: 0,   // Dettagli tecnici sviluppo
  INFO: 1,    // Informazioni generali
  WARN: 2,    // Warning, situazioni anomale
  ERROR: 3,   // Errori critici
  OFF: 999    // Disabilita tutto
};

/**
 * Colori ANSI per console (browser moderni)
 */
const COLORS = {
  DEBUG: '#6c757d',   // Grigio
  INFO: '#0dcaf0',    // Cyan
  WARN: '#ffc107',    // Giallo
  ERROR: '#dc3545',   // Rosso
  NAMESPACE: '#6f42c1', // Viola
  TIME: '#20c997'     // Verde
};

/**
 * Emoji per livelli (opzionale, rende log più visibili)
 */
const EMOJI = {
  DEBUG: '🔍',
  INFO: 'ℹ️',
  WARN: '⚠️',
  ERROR: '❌',
  TIME: '⏱️'
};

// =============================================================================
// STATO GLOBALE
// =============================================================================

/**
 * Configurazione logging globale
 */
const config = {
  // Livello globale (default: INFO per produzione, DEBUG per dev)
  globalLevel: LOG_LEVELS.INFO,
  
  // Livelli per namespace specifici
  // Es: { 'Arrow': LOG_LEVELS.DEBUG, 'UI': LOG_LEVELS.OFF }
  namespaceLevel: new Map(),
  
  // Mostra timestamp?
  showTimestamp: true,
  
  // Usa emoji?
  useEmoji: true,
  
  // Profiling attivo?
  profiling: false,
  
  // Timer per performance
  timers: new Map()
};

// =============================================================================
// GESTIONE CONFIGURAZIONE
// =============================================================================

/**
 * Carica configurazione da localStorage
 */
function loadConfig() {
  try {
    const saved = localStorage.getItem('aaaat_log_config');
    if (saved) {
      const data = JSON.parse(saved);
      
      if (data.globalLevel !== undefined) {
        config.globalLevel = data.globalLevel;
      }
      
      if (data.namespaceLevel) {
        config.namespaceLevel = new Map(Object.entries(data.namespaceLevel));
      }
      
      if (data.showTimestamp !== undefined) {
        config.showTimestamp = data.showTimestamp;
      }
      
      if (data.useEmoji !== undefined) {
        config.useEmoji = data.useEmoji;
      }
      
      if (data.profiling !== undefined) {
        config.profiling = data.profiling;
      }
    }
  } catch (e) {
    console.warn('Errore caricamento config log:', e);
  }
}

/**
 * Salva configurazione in localStorage
 */
function saveConfig() {
  try {
    const data = {
      globalLevel: config.globalLevel,
      namespaceLevel: Object.fromEntries(config.namespaceLevel),
      showTimestamp: config.showTimestamp,
      useEmoji: config.useEmoji,
      profiling: config.profiling
    };
    localStorage.setItem('aaaat_log_config', JSON.stringify(data));
  } catch (e) {
    console.warn('Errore salvataggio config log:', e);
  }
}

// Carica config all'avvio
loadConfig();

// =============================================================================
// API PUBBLICA - CONFIGURAZIONE
// =============================================================================

/**
 * Imposta livello di log globale
 * 
 * @param {string} level - 'DEBUG' | 'INFO' | 'WARN' | 'ERROR' | 'OFF'
 */
export function setLogLevel(level) {
  const upperLevel = level.toUpperCase();
  
  if (LOG_LEVELS[upperLevel] === undefined) {
    console.error(`Livello log non valido: ${level}. Usa: DEBUG, INFO, WARN, ERROR, OFF`);
    return;
  }
  
  config.globalLevel = LOG_LEVELS[upperLevel];
  saveConfig();
  
  console.log(
    `%c[LOGGER] Livello globale impostato: ${upperLevel}`,
    `color: ${COLORS.INFO}; font-weight: bold;`
  );
}

/**
 * Imposta livello di log per namespace specifico
 * 
 * @param {string} namespace - Nome modulo
 * @param {string} level - Livello log o 'INHERIT' per usare globale
 */
export function setNamespaceLevel(namespace, level) {
  const upperLevel = level.toUpperCase();
  
  if (upperLevel === 'INHERIT') {
    config.namespaceLevel.delete(namespace);
    saveConfig();
    console.log(
      `%c[LOGGER] ${namespace}: usa livello globale`,
      `color: ${COLORS.INFO}`
    );
    return;
  }
  
  if (LOG_LEVELS[upperLevel] === undefined) {
    console.error(`Livello log non valido: ${level}`);
    return;
  }
  
  config.namespaceLevel.set(namespace, LOG_LEVELS[upperLevel]);
  saveConfig();
  
  console.log(
    `%c[LOGGER] ${namespace}: livello impostato a ${upperLevel}`,
    `color: ${COLORS.INFO}`
  );
}

/**
 * Abilita/disabilita profiling performance
 */
export function setProfiling(enabled) {
  config.profiling = enabled;
  saveConfig();
  console.log(
    `%c[LOGGER] Profiling: ${enabled ? 'ABILITATO' : 'DISABILITATO'}`,
    `color: ${COLORS.TIME}; font-weight: bold;`
  );
}

/**
 * Mostra configurazione attuale
 */
export function showConfig() {
  console.group('%c[LOGGER] Configurazione', `color: ${COLORS.INFO}; font-weight: bold;`);
  console.log('Livello globale:', Object.keys(LOG_LEVELS).find(k => LOG_LEVELS[k] === config.globalLevel));
  console.log('Namespace specifici:', Object.fromEntries(config.namespaceLevel));
  console.log('Timestamp:', config.showTimestamp);
  console.log('Emoji:', config.useEmoji);
  console.log('Profiling:', config.profiling);
  console.groupEnd();
}

/**
 * Reset completo configurazione
 */
export function resetConfig() {
  config.globalLevel = LOG_LEVELS.INFO;
  config.namespaceLevel.clear();
  config.showTimestamp = true;
  config.useEmoji = true;
  config.profiling = false;
  config.timers.clear();
  saveConfig();
  console.log('%c[LOGGER] Configurazione resettata', `color: ${COLORS.WARN}`);
}

// =============================================================================
// CORE LOGGING
// =============================================================================

/**
 * Determina se loggare per dato namespace e livello
 */
function shouldLog(namespace, level) {
  // Se log è completamente disabilitato
  if (config.globalLevel === LOG_LEVELS.OFF) {
    return false;
  }
  
  // Livello specifico per namespace?
  const nsLevel = config.namespaceLevel.get(namespace);
  const threshold = nsLevel !== undefined ? nsLevel : config.globalLevel;
  
  return level >= threshold;
}

/**
 * Formatta timestamp
 */
function formatTimestamp() {
  const now = new Date();
  const h = String(now.getHours()).padStart(2, '0');
  const m = String(now.getMinutes()).padStart(2, '0');
  const s = String(now.getSeconds()).padStart(2, '0');
  const ms = String(now.getMilliseconds()).padStart(3, '0');
  return `${h}:${m}:${s}.${ms}`;
}

/**
 * Log generico con formatting
 */
function doLog(namespace, level, levelName, args) {
  if (!shouldLog(namespace, level)) {
    return;
  }
  
  // Costruisci prefix
  const parts = [];
  
  // Timestamp
  if (config.showTimestamp) {
    parts.push(`%c${formatTimestamp()}`);
  }
  
  // Namespace
  parts.push(`%c[${namespace}]`);
  
  // Livello
  const emoji = config.useEmoji ? EMOJI[levelName] + ' ' : '';
  parts.push(`%c${emoji}${levelName}`);
  
  const prefix = parts.join(' ');
  
  // Stili CSS
  const styles = [];
  
  if (config.showTimestamp) {
    styles.push(`color: ${COLORS.TIME}; font-weight: normal;`);
  }
  
  styles.push(`color: ${COLORS.NAMESPACE}; font-weight: bold;`);
  styles.push(`color: ${COLORS[levelName]}; font-weight: bold;`);
  
  // Log!
  console[levelName.toLowerCase()](prefix, ...styles, ...args);
}

// =============================================================================
// FACTORY LOGGER
// =============================================================================

/**
 * Crea logger per namespace specifico
 * 
 * @param {string} namespace - Nome modulo (es: 'Arrow', 'Periodogram', 'UI')
 * @returns {Object} - Logger instance con metodi debug, info, warn, error, time, timeEnd
 */
export function logger(namespace) {
  return {
    /**
     * Log DEBUG - Dettagli tecnici sviluppo
     */
    debug: (...args) => {
      doLog(namespace, LOG_LEVELS.DEBUG, 'DEBUG', args);
    },
    
    /**
     * Log INFO - Informazioni generali
     */
    info: (...args) => {
      doLog(namespace, LOG_LEVELS.INFO, 'INFO', args);
    },
    
    /**
     * Log WARN - Warning, situazioni anomale
     */
    warn: (...args) => {
      doLog(namespace, LOG_LEVELS.WARN, 'WARN', args);
    },
    
    /**
     * Log ERROR - Errori critici
     */
    error: (...args) => {
      doLog(namespace, LOG_LEVELS.ERROR, 'ERROR', args);
    },
    
    /**
     * Avvia timer per performance profiling
     * 
     * @param {string} label - Etichetta timer
     */
    time: (label) => {
      if (!config.profiling) return;
      
      const key = `${namespace}:${label}`;
      config.timers.set(key, performance.now());
      
      if (shouldLog(namespace, LOG_LEVELS.DEBUG)) {
        console.log(
          `%c⏱️ [${namespace}] Timer START: ${label}`,
          `color: ${COLORS.TIME}`
        );
      }
    },
    
    /**
     * Termina timer e logga durata
     * 
     * @param {string} label - Etichetta timer
     * @returns {number} - Durata in ms
     */
    timeEnd: (label) => {
      if (!config.profiling) return 0;
      
      const key = `${namespace}:${label}`;
      const start = config.timers.get(key);
      
      if (start === undefined) {
        console.warn(`Timer non trovato: ${key}`);
        return 0;
      }
      
      const duration = performance.now() - start;
      config.timers.delete(key);
      
      if (shouldLog(namespace, LOG_LEVELS.DEBUG)) {
        console.log(
          `%c⏱️ [${namespace}] Timer END: ${label} → ${duration.toFixed(2)}ms`,
          `color: ${COLORS.TIME}; font-weight: bold;`
        );
      }
      
      return duration;
    },
    
    /**
     * Log con group (collapsable)
     */
    group: (title, ...args) => {
      if (!shouldLog(namespace, LOG_LEVELS.INFO)) return;
      console.group(`[${namespace}] ${title}`, ...args);
    },
    
    /**
     * Chiudi group
     */
    groupEnd: () => {
      console.groupEnd();
    },
    
    /**
     * Log tabella (per array/oggetti)
     */
    table: (data, columns) => {
      if (!shouldLog(namespace, LOG_LEVELS.DEBUG)) return;
      console.log(`[${namespace}] Table:`);
      console.table(data, columns);
    }
  };
}

// =============================================================================
// EXPORT NAMESPACE GLOBALE (per console browser)
// =============================================================================

// Esponi API globalmente per debug da console
if (typeof window !== 'undefined') {
  window.setLogLevel = setLogLevel;
  window.setNamespaceLevel = setNamespaceLevel;
  window.setProfiling = setProfiling;
  window.showLogConfig = showConfig;
  window.resetLogConfig = resetConfig;
  
  // Alias comodi
  window.logDebug = () => setLogLevel('DEBUG');
  window.logInfo = () => setLogLevel('INFO');
  window.logWarn = () => setLogLevel('WARN');
  window.logOff = () => setLogLevel('OFF');
  window.profileOn = () => setProfiling(true);
  window.profileOff = () => setProfiling(false);
  
  // Backward compatibility con variabile AAAAT_DEBUG
  Object.defineProperty(window, 'AAAAT_DEBUG', {
    get: () => config.globalLevel === LOG_LEVELS.DEBUG,
    set: (val) => setLogLevel(val ? 'DEBUG' : 'INFO')
  });
  
  Object.defineProperty(window, 'AAAAT_PROFILE', {
    get: () => config.profiling,
    set: (val) => setProfiling(val)
  });
}

// =============================================================================
// ESEMPI USO
// =============================================================================

/**
 * ESEMPI:
 * 
 * // Crea logger
 * const log = logger('MyModule');
 * 
 * // Log semplici
 * log.debug('Valore:', value);
 * log.info('Operazione completata');
 * log.warn('Attenzione!', { details });
 * log.error('Errore critico!', error);
 * 
 * // Performance timing
 * log.time('fetch-data');
 * const data = await fetch(...);
 * log.timeEnd('fetch-data');  // → "fetch-data: 234.56ms"
 * 
 * // Group collapsable
 * log.group('Calcolo periodogramma');
 * log.debug('Freq range:', [fMin, fMax]);
 * log.debug('N points:', n);
 * log.groupEnd();
 * 
 * // Tabelle
 * log.table(peaks, ['period', 'power', 'fap']);
 * 
 * // Da console browser:
 * window.logDebug()                    // Abilita debug globale
 * window.setNamespaceLevel('Arrow', 'DEBUG')  // Solo Arrow in debug
 * window.profileOn()                   // Abilita profiling
 * window.showLogConfig()               // Mostra config
 */

// Log iniziale
if (typeof window !== 'undefined') {
  const welcomeLog = logger('System');
  welcomeLog.info('Logger inizializzato. Usa window.showLogConfig() per dettagli');
  welcomeLog.debug('Comandi disponibili:', {
    'window.logDebug()': 'Abilita debug',
    'window.logOff()': 'Disabilita log',
    'window.profileOn()': 'Abilita profiling',
    'window.setNamespaceLevel(ns, level)': 'Config per modulo',
    'window.showLogConfig()': 'Mostra config'
  });
}
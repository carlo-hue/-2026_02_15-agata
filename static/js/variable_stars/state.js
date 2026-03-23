/**
 * state.js - Gestione Stato Globale Applicazione
 * 
 * Centralizza TUTTO lo stato dell'applicazione in un unico oggetto.
 * Pattern simile a Redux ma semplificato.
 * 
 * LO STATO CONTIENE:
 * - Dati curva di luce (jd, mag, session_id, point_id)
 * - Stato punti (attivi, selezionati, outlier)
 * - Configurazione sessioni (nomi, colori, offset, visibilità)
 * - Parametri analisi (periodo, fase, detrend)
 * - UI state (titoli, range, etichette)
 * 
 * MOTIVAZIONE STATO GLOBALE:
 * - Single source of truth
 * - Facile debug (inspeciona `window.state`)
 * - Persistenza semplice (serialize tutto)
 * - Undo/redo futuro (snapshot stato)
 * 
 * UTILIZZO:
 * 
 * ```javascript
 * import { state, nameForSession, colorForSession } from './state.js';
 * 
 * // Accesso dati
 * const nPoints = state.n;
 * const jd = state.jd;
 * const mag = state.mag;
 * 
 * // Check se punto attivo
 * if (state.activePoint[i]) {
 *   // punto visibile
 * }
 * 
 * // Ottieni nome sessione
 * const name = nameForSession(sessionId);
 * 
 * // Offset totale (automatico + manuale)
 * const offset = getTotalOffset(sessionId);
 * ```
 * 
 * IMPORTANTE:
 * - NON modificare direttamente arrays (jd, mag) dopo init
 * - activePoint può essere modificato (toggle visibilità)
 * - Offset sono additivi: totale = auto + manual
 */

import { logger } from '../common/logger.js';

// Crea logger per questo modulo
const log = logger('State');

// =============================================================================
// COSTANTI
// =============================================================================

/**
 * Palette colori per sessioni osservative.
 * 
 * Usa Tableau 10 color palette (scientificamente ottimizzata):
 * - Distinti anche per daltonici
 * - Buon contrasto
 * - Esteticamente piacevoli
 * 
 * NOTA: Se servono >10 sessioni, i colori si ripetono (modulo).
 */
export const SESSION_COLORS = [
  "#1f77b4",  // Blu
  "#ff7f0e",  // Arancione
  "#2ca02c",  // Verde
  "#d62728",  // Rosso
  "#9467bd",  // Viola
  "#8c564b",  // Marrone
  "#e377c2",  // Rosa
  "#7f7f7f",  // Grigio
  "#bcbd22",  // Verde-giallo
  "#17becf"   // Cyan
];

// =============================================================================
// STATO GLOBALE
// =============================================================================

/**
 * Oggetto stato globale dell'applicazione.
 * 
 * IMPORTANTE: Questo è l'UNICA sorgente di verità.
 * Ogni modulo dovrebbe leggere da qui, non mantenere copie locali.
 */
export const state = {
  
  // ===========================================================================
  // DATI CURVA DI LUCE (read-only dopo caricamento)
  // ===========================================================================
  
  /**
   * Numero totale punti caricati
   * @type {number}
   */
  n: 0,

  /**
   * GAIA ID della stella (se caricato da DB)
   * @type {string|null}
   */
  gaiaId: null,
  
  /**
   * Array Julian Date
   * @type {Float64Array}
   * 
   * NOTA: Float64 necessario per precisione JD.
   * Float32 causerebbe errori ~0.001 giorni = ~90 secondi!
   */
  jd: null,
  
  /**
   * Array magnitudini
   * @type {Float32Array}
   * 
   * NOTA: Float32 sufficiente per mag (precisione ~0.00001 mag OK)
   */
  mag: null,
  
  /**
   * Array session ID per ogni punto
   * @type {Int32Array}
   * 
   * session[i] = ID sessione osservativa del punto i
   * Es: [0,0,0,1,1,1,2,2] = primi 3 punti sessione 0, poi 3 sessione 1, etc.
   */
  session: null,
  
  /**
   * Array point ID univoco
   * @type {Int32Array}
   * 
   * pid[i] = ID univoco punto i (usato per tracking selezioni)
   * Tipicamente: pid = [0,1,2,3,...,n-1]
   */
  pid: null,
  
  // ===========================================================================
  // STATO PUNTI (modificabile)
  // ===========================================================================
  
  /**
   * Array booleano: quali punti sono attualmente attivi (visibili)?
   * @type {Uint8Array}
   * 
   * activePoint[i] = 1 → punto visibile
   * activePoint[i] = 0 → punto nascosto/rimosso
   * 
   * NOTA: Uint8Array invece di Array<boolean> per:
   * - Efficienza memoria (1 byte vs 8 bytes)
   * - Performance (typed array più veloce)
   * - Facile serializzazione (bitpack + base64)
   */
  activePoint: null,
  
  /**
   * Set di indici punti selezionati da utente (con BoxSelect, etc.)
   * @type {Set<number>}
   * 
   * UTILIZZO:
   * - Utente seleziona punti con tool BoxSelect
   * - Indici aggiunti a questo Set
   * - Pulsante "Rimuovi" → activePoint[i] = 0 per i in selectedRaw
   */
  selectedRaw: new Set(),
  
  /**
   * Set di indici outlier suggeriti da sigma clipping
   * @type {Set<number>}
   * 
   * WORKFLOW:
   * 1. Utente clicca "Sigma Clip"
   * 2. Server risponde con outlier_indices
   * 3. Indici aggiunti a questo Set
   * 4. UI evidenzia suggerimenti
   * 5. Utente decide: accetta (rimuovi) o ignora
   */
  sigmaClipSuggested: new Set(),
  
  // ===========================================================================
  // CONFIGURAZIONE SESSIONI
  // ===========================================================================
  
  /**
   * Map: session_id → visibilità sessione
   * @type {Map<number, boolean>}
   * 
   * activeSession.get(sid) = true → sessione visibile
   * activeSession.get(sid) = false → sessione nascosta
   * 
   * NOTA: Nascondere sessione NON rimuove punti, solo nasconde in plot.
   * Per rimuovere permanentemente: impostare activePoint[i] = 0
   */
  activeSession: new Map(),
  
  /**
   * Map: session_id → offset automatico [mag]
   * @type {Map<number, number>}
   * 
   * Offset calcolato da algoritmi automatici:
   * - Allineamento per mediana fase
   * - Allineamento zero-point
   * - Detrending
   * 
   * NOTA: NON modificare direttamente, usare funzioni dedicate.
   */
  sessionAutoOffset: new Map(),
  
  /**
   * Map: session_id → offset manuale [mag]
   * @type {Map<number, number>}
   * 
   * Offset impostato da utente tramite:
   * - Slider UI
   * - Input numerico
   * 
   * IMPORTANTE: Offset sono ADDITIVI!
   * Offset totale = sessionAutoOffset + sessionManualOffset
   */
  sessionManualOffset: new Map(),
  
  /**
   * Map: session_id → nome personalizzato sessione
   * @type {Map<number, string>}
   * 
   * Default: "S0", "S1", "S2", ...
   * Utente può personalizzare: "Notte 2024-03-15", etc.
   */
  sessionName: new Map(),
  
  /**
   * Map: session_id → colore personalizzato sessione
   * @type {Map<number, string>}
   * 
   * Default: da SESSION_COLORS array
   * Utente può personalizzare: "#ff0000", etc.
   */
  sessionColor: new Map(),
  
  /**
   * Map: session_id → nome sessione dal database
   * @type {Map<number, string>}
   *
   * Quando carichi da DB, server manda session_name.
   * Salvato qui per preservare nome originale anche dopo personalizzazione.
   */
  sessionNameFromDB: new Map(),

  /**
   * Map: session_id → range slider offset manuale {min, max}
   * @type {Map<number, Object>}
   *
   * Range calcolato con sigma clipping, ma NON ricalcolato automaticamente.
   * Utente può ricalcolare manualmente con apposito bottone.
   * Se non presente, usa range di default.
   */
  sessionSliderRange: new Map(),

  // ===========================================================================
  // DETRENDING
  // ===========================================================================
  
  /**
   * Configurazione detrending
   * @type {Object}
   */
  detrend: {
    /**
     * Modello detrend: "none" | "linear" | "quadratic"
     * @type {string}
     */
    model: "linear",
    
    /**
     * Map: session_id → coefficienti fit [a, b, c]
     * @type {Map<number, Array<number>>}
     * 
     * Linear: mag_fit = a + b*jd
     * Quadratic: mag_fit = a + b*jd + c*jd²
     */
    coeff: new Map(),
  },
  
  // ===========================================================================
  // ANALISI PERIODO E FASE
  // ===========================================================================
  
  /**
   * Ultimo periodo usato per folding [giorni]
   * @type {number|null}
   * 
   * Salvato per:
   * - Re-fold automatico quando cambiano dati
   * - Sync con altri moduli (harmonics, O-C)
   */
  lastPeriod: null,
  
  /**
   * Metodo calcolo epoca: "minJD" | "maxMag" | "custom"
   * @type {string|null}
   * 
   * - minJD: epoca = min(JD) (default)
   * - maxMag: epoca = JD corrispondente a max(mag)
   * - custom: utente specifica JD manualmente
   */
  epochMethod: null,
  
  /**
   * Shift fase manuale [0-1]
   * @type {number}
   * 
   * Permette traslare curva in fase senza cambiare periodo.
   * Utile per allineare template o centrare massimo.
   * 
   * Formula: fase = ((jd - epoch) / period + phaseShift) % 1
   */
  phaseShift: 0.0,
  
  /**
   * Titolo personalizzato grafico fase
   * @type {string}
   * 
   * Default: "Phase plot"
   * Utente può personalizzare: "RR Lyrae V123 - Fase", etc.
   */
  phaseTitle: "Phase plot",
  
  /**
   * Range fase visualizzazione: "-1-1" | "0-2" | "-0.5-0.5"
   * @type {string}
   * 
   * Controlla asse X del grafico fase:
   * - "-1-1": da -1 a +1 (mostra 2 cicli completi)
   * - "0-2": da 0 a 2 (2 cicli, partenza da 0)
   * - "-0.5-0.5": da -0.5 a +0.5 (1 ciclo, centrato su 0)
   */
  phaseRange: "-1-1",
  
  /**
   * Etichetta personalizzata periodo nel titolo
   * @type {string}
   *
   * Es: "P = 0.573 d" oppure "P1 = 0.573 d" per multiperiodiche
   */
  phasePeriodLabel: "",

  /**
   * Blocca zoom automatico nel grafico fase
   * @type {boolean}
   *
   * Se true, mantiene il range attuale di zoom quando si aggiorna il grafico
   * Se false, esegue autoscale ad ogni aggiornamento
   */
  lockPhaseZoom: false,

  /**
   * Range salvato per il grafico fase quando lockPhaseZoom è attivo
   * @type {Object|null}
   */
  savedPhaseRange: null,

  // ===========================================================================
  // PLOT SETTINGS
  // ===========================================================================
  
  /**
   * Dimensione corrente dei punti nel grafico [px]
   * @type {number}
   *
   * Valore modificabile dall'utente tramite slider UI.
   * Range tipico: 1-15 px
   */
  currentMarkerSize: 3,

  /**
   * Cache dati estremi (min/max/ampiezza) per sessione
   * @type {Object|null}
   *
   * Struttura:
   * {
   *   "session_id": {
   *     global_max: {jd: float, mag: float},
   *     global_min: {jd: float, mag: float},
   *     amplitude: float,
   *     local_maxima: [...],
   *     local_minima: [...]
   *   },
   *   ...
   * }
   *
   * Invalida quando cambiano i dati attivi (detrend, rimozione punti)
   */
  extremaData: null,

  /**
   * Risultati ultimo periodigramma calcolato
   * @type {Object|null}
   *
   * Struttura:
   * {
   *   periods: [float...],    // Array periodi trovati (ordinati per power)
   *   amplitudes: [float...], // Ampiezze corrispondenti (se multiperiod)
   *   powers: [float...],     // Potenze spettrali
   *   peaks: [Object...],     // Top 5 picchi con {period, power, fap, snr}
   *   timestamp: float        // JD dell'analisi
   * }
   *
   * Usato da AI Advisor per classificazione stelle variabili.
   * Invalida quando cambiano i dati attivi (detrend, rimozione punti).
   */
  periodogramResult: null,

  /**
   * Ampiezza manuale (linee draggabili in fase)
   * @type {Object|null}
   *
   * Struttura:
   * {
   *   min: float,  // Magnitudine minima (massimo di luce)
   *   max: float   // Magnitudine massima (minimo di luce)
   * }
   *
   * null se non impostato manualmente
   */
  manualAmplitude: null
};

// =============================================================================
// STATO UI (non serializzato)
// =============================================================================

/**
 * Range Y base per grafico stella (preservato tra operazioni)
 * @type {Array<number>|null}
 * 
 * Formato: [yMin, yMax]
 * 
 * MOTIVAZIONE:
 * - Quando rimuovi outlier, range Y cambia
 * - Ma utente potrebbe voler mantenere zoom originale
 * - baseYRange salva range iniziale
 * 
 * null = auto-range (default)
 */
export let baseYRange = null;

/**
 * Setter per baseYRange (necessario per export)
 * @param {Array<number>|null} val - Nuovo range
 */
export function setBaseYRange(val) {
  log.debug('Setting base Y range:', val);
  baseYRange = val;
}

// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================

/**
 * Ottieni colore per sessione.
 * 
 * Ordine priorità:
 * 1. Colore personalizzato (se settato da utente)
 * 2. Colore default da palette
 * 
 * @param {number} sid - Session ID
 * @returns {string} - Colore hex (es: "#1f77b4")
 */
export function colorForSession(sid) {
  // Check se utente ha personalizzato colore
  if (state.sessionColor.has(sid)) {
    const customColor = state.sessionColor.get(sid);
    log.debug(`Session ${sid}: custom color ${customColor}`);
    return customColor;
  }
  
  // Usa colore default da palette (modulo per wrap-around)
  const defaultColor = SESSION_COLORS[sid % SESSION_COLORS.length];
  log.debug(`Session ${sid}: default color ${defaultColor}`);
  return defaultColor;
}

/**
 * Ottieni nome per sessione.
 * 
 * Ordine priorità:
 * 1. Nome personalizzato (se settato da utente)
 * 2. Nome da database (se disponibile)
 * 3. Nome default "S{id}"
 * 
 * @param {number} sid - Session ID
 * @returns {string} - Nome sessione
 */
export function nameForSession(sid) {
  // Check se utente ha personalizzato nome
  if (state.sessionName.has(sid)) {
    const customName = state.sessionName.get(sid);
    log.debug(`Session ${sid}: custom name "${customName}"`);
    return customName;
  }
  
  // Altrimenti usa default
  const defaultName = `S${sid}`;
  log.debug(`Session ${sid}: default name "${defaultName}"`);
  return defaultName;
}

/**
 * Calcola offset totale per sessione.
 * 
 * Offset totale = offset automatico + offset manuale
 * 
 * UTILIZZO:
 * magAdjusted = mag + getTotalOffset(session_id)
 * 
 * @param {number} sid - Session ID
 * @returns {number} - Offset totale [mag]
 */
export function getTotalOffset(sid) {
  // Offset automatico (da algoritmi)
  const autoOffset = state.sessionAutoOffset.get(sid) || 0;
  
  // Offset manuale (da utente)
  const manualOffset = state.sessionManualOffset.get(sid) || 0;
  
  // Totale (additivo)
  const total = autoOffset + manualOffset;
  
  log.debug(`Session ${sid}: offset total=${total.toFixed(4)} (auto=${autoOffset.toFixed(4)}, manual=${manualOffset.toFixed(4)})`);
  
  return total;
}

// ============================================
// ✅ CACHE OTTIMIZZAZIONE FASE
// ============================================
if (!state.phaseCache) {
  state.phaseCache = {
    P: null,              // Periodo corrente
    epoch: null,          // Epoca corrente
    basePhase: null,      // Float32Array - fase base senza shift
    yCorr: null,          // Float32Array - magnitudine corretta
    sessionId: null,      // Int32Array - session id
    activeIndices: null,  // Int32Array - indici punti attivi
    bySession: new Map()  // Dati per sessione
  };
}


// =============================================================================
// INIZIALIZZAZIONE STATO
// =============================================================================

/**
 * Ricostruisce defaults per tutte le sessioni.
 * 
 * Chiamato quando:
 * - Caricamento nuovi dati
 * - Reset applicazione
 * - Cambio sorgente dati
 * 
 * OPERAZIONI:
 * 1. Reset activePoint (tutti punti attivi)
 * 2. Clear selezioni e suggerimenti
 * 3. Reset offset
 * 4. Inizializza configurazione sessioni
 * 5. Reset detrend coefficienti
 * 6. Reset range Y
 * 
 * IMPORTANTE: NON tocca i dati raw (jd, mag, session, pid)
 */
export function rebuildDefaults() {
  log.info('Rebuilding state defaults');
  log.time('rebuild-defaults');
  
  // ===== 1. RESET ACTIVE POINTS =====
  // Crea nuovo array (tutti attivi)
  state.activePoint = new Uint8Array(state.n);
  state.activePoint.fill(1);  // 1 = attivo
  log.debug(`Activated all ${state.n} points`);
  
  // ===== 2. CLEAR SELEZIONI =====
  const prevSelected = state.selectedRaw.size;
  const prevSuggested = state.sigmaClipSuggested.size;
  
  state.selectedRaw.clear();
  state.sigmaClipSuggested.clear();
  
  log.debug(`Cleared selections: ${prevSelected} selected, ${prevSuggested} suggested`);
  
  // ===== 3. RESET SESSIONI CONFIG =====
  state.activeSession.clear();
  state.sessionAutoOffset.clear();
  state.sessionManualOffset.clear();
  state.sessionSliderRange.clear();

  // ===== 4. RESET DETREND =====
  state.detrend.coeff.clear();
  
  // ===== 5. RESET RANGE Y =====
  baseYRange = null;
  log.debug('Reset Y range to auto');
  
  // ===== 6. SCOPRI SESSIONI UNICHE =====
  // Itera su tutti i punti per trovare session_id uniche
  const sessionIds = new Set();
  for (let i = 0; i < state.n; i++) {
    sessionIds.add(state.session[i]);
  }
  
  log.info(`Found ${sessionIds.size} unique sessions:`, Array.from(sessionIds));
  
  // ===== 7. INIZIALIZZA OGNI SESSIONE =====
  for (const sid of sessionIds) {
    // Sessione attiva
    state.activeSession.set(sid, true);
    
    // Offset zero
    state.sessionAutoOffset.set(sid, 0.0);
    state.sessionManualOffset.set(sid, 0.0);
    
    // ===== NOME SESSIONE =====
    // Se non già personalizzato, usa nome da DB o default
    if (!state.sessionName.has(sid)) {
      // Cerca nome dal DB
      const dbName = state.sessionNameFromDB.get(sid);
      
      if (dbName) {
        // Usa nome dal DB
        state.sessionName.set(sid, dbName);
        log.debug(`Session ${sid}: using DB name "${dbName}"`);
      } else {
        // Usa nome default
        const defaultName = `S${sid}`;
        state.sessionName.set(sid, defaultName);
        log.debug(`Session ${sid}: using default name "${defaultName}"`);
      }
    }
    
    // ===== COLORE SESSIONE =====
    // Se non già personalizzato, usa colore default
    if (!state.sessionColor.has(sid)) {
      const defaultColor = SESSION_COLORS[sid % SESSION_COLORS.length];
      state.sessionColor.set(sid, defaultColor);
      log.debug(`Session ${sid}: using default color ${defaultColor}`);
    }
  }
  
  log.timeEnd('rebuild-defaults');
  log.info('State defaults rebuilt successfully');

  
}

// =============================================================================
// EXPORT GLOBALE (per debug console)
// =============================================================================

if (typeof window !== 'undefined') {
  // Esponi stato globalmente per ispezione facile
  window.state = state;
  
  // Utility globali
  window.nameForSession = nameForSession;
  window.colorForSession = colorForSession;
  window.getTotalOffset = getTotalOffset;
  window.rebuildDefaults = rebuildDefaults;
  
  // Snapshot stato (per debug)
  window.snapshotState = () => {
    return {
      n: state.n,
      activeSessions: Array.from(state.activeSession.entries()),
      activePoints: state.activePoint.reduce((a, b) => a + b, 0),
      selectedRaw: state.selectedRaw.size,
      sigmaClipSuggested: state.sigmaClipSuggested.size,
      lastPeriod: state.lastPeriod,
      phaseShift: state.phaseShift
    };
  };
  
  // Log stato corrente
  log.info('State module initialized. Use window.state for inspection');

}


// ============================================
// SISTEMA SAMPLING PERSISTENTE
// ============================================

/**
 * Percentuale di punti attivi (10-100)
 * Si auto-imposta al caricamento, persiste durante analisi
 */
export let activeSamplingPercent = 100;

/**
 * Cache del set di indici campionati
 */
let cachedSampledIndices = null;

/**
 * Aggiorna percentuale sampling
 */
export function setActiveSamplingPercent(value) {
  activeSamplingPercent = value;
  cachedSampledIndices = null; // Invalida cache
}

/**
 * Genera set di indici campionati in modo stratificato
 * - Mantiene proporzioni tra sessioni
 * - Cache per performance
 * @returns {Set|null} Set di indici campionati, o null se 100%
 */
export function getSampledIndices() {
  // Se è al 100%, usa tutti i punti
  if (activeSamplingPercent >= 100) {
    return null;
  }
  
  // Se abbiamo cache valida, usala
  if (cachedSampledIndices !== null) {
    return cachedSampledIndices;
  }
  
  // Genera nuovo set campionato
  const targetFraction = activeSamplingPercent / 100;
  const sampledIndices = new Set();
  
  // Campionamento stratificato per sessione
  state.activeSession.forEach((enabled, sid) => {
    if (!enabled) return;
    
    // Raccogli indici di questa sessione
    const sessionIndices = [];
    for (let i = 0; i < state.n; i++) {
      if (state.session[i] === sid && state.activePoint[i] === 1) {
        sessionIndices.push(i);
      }
    }
    
    if (sessionIndices.length === 0) return;
    
    // Target per questa sessione (minimo 10 punti)
    const targetCount = Math.max(10, Math.floor(sessionIndices.length * targetFraction));
    const step = Math.max(1, Math.floor(sessionIndices.length / targetCount));
    
    // Campionamento uniforme
    for (let i = 0; i < sessionIndices.length; i += step) {
      sampledIndices.add(sessionIndices[i]);
    }
  });
  
  // Salva in cache
  cachedSampledIndices = sampledIndices;
  
  console.log(`📊 Sampling: ${sampledIndices.size.toLocaleString()}/${state.n.toLocaleString()} punti (${activeSamplingPercent}%)`);
  
  return sampledIndices;
}

/**
 * Invalida cache quando cambiano punti/sessioni
 */
export function invalidateSamplingCache() {
  cachedSampledIndices = null;
}

// =============================================================================
// ESEMPI USO
// =============================================================================

/**
 * ESEMPI:
 * 
 * // Accedi dati
 * const jd = state.jd;
 * const mag = state.mag;
 * const n = state.n;
 * 
 * // Itera su punti attivi
 * for (let i = 0; i < state.n; i++) {
 *   if (state.activePoint[i]) {
 *     console.log(`Point ${i}: JD=${state.jd[i]}, mag=${state.mag[i]}`);
 *   }
 * }
 * 
 * // Ottieni offset totale
 * const offset = getTotalOffset(sessionId);
 * const magAdjusted = mag + offset;
 * 
 * // Nome e colore sessione
 * const name = nameForSession(sessionId);
 * const color = colorForSession(sessionId);
 * 
 * // Nascondi sessione
 * state.activeSession.set(sessionId, false);
 * 
 * // Reset tutto
 * rebuildDefaults();
 * 
 * // Da console:
 * window.state                    // Inspeciona stato
 * window.snapshotState()          // Snapshot compatto
 * window.getTotalOffset(0)        // Offset sessione 0
 */
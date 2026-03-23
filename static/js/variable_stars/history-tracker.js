/**
 * =============================================================================
 * modules/history-tracker.js - Sistema Tracciamento Modifiche Dati
 * =============================================================================
 * 
 * SCOPO:
 * Traccia tutte le operazioni fatte sui dati (detrend, sigma clip, remove points)
 * per permettere:
 * - Visualizzazione cronologia operazioni
 * - Undo/Redo (opzionale)
 * - Export log analisi
 * - Riproducibilità workflow
 * 
 * USO:
 * import { HistoryTracker } from './history-tracker.js';
 * 
 * // Dopo ogni operazione
 * HistoryTracker.record('detrend', { model: 'linear', sessions: [0,1,2] });
 * HistoryTracker.record('sigma_clip', { sigma: 3, outliers: 15 });
 * 
 * // Visualizza cronologia
 * HistoryTracker.getHistory();  // Array di operazioni
 * HistoryTracker.renderToHTML('#historyPanel');  // Mostra in UI
 */

class HistoryTrackerClass {
  constructor() {
    /**
     * Array cronologico di operazioni.
     * Ogni entry: { timestamp, action, params, state_snapshot }
     */
    this.history = [];
    
    /**
     * Max history entries (evita memory leak su sessioni lunghe).
     */
    this.maxEntries = 100;
    
    /**
     * Flag per enable/disable tracking.
     */
    this.enabled = true;
  }
  
  /**
   * Registra un'operazione nella cronologia.
   * 
   * @param {string} action - Nome operazione ('detrend', 'sigma_clip', 'remove_points', etc)
   * @param {Object} params - Parametri operazione
   * @param {Object} stateSnapshot - (opzionale) Snapshot stato per undo
   * 
   * @example
   * HistoryTracker.record('detrend', {
   *   model: 'linear',
   *   sessions: [0, 1, 2],
   *   coefficients: { 0: [0.5, -0.02], 1: [0.3, -0.01] }
   * });
   * 
   * HistoryTracker.record('sigma_clip', {
   *   sigma: 3.0,
   *   iterations: 5,
   *   outliers_found: 15,
   *   outlier_indices: [10, 25, 103, ...]
   * });
   * 
   * HistoryTracker.record('remove_points', {
   *   count: 5,
   *   indices: [10, 20, 30, 40, 50],
   *   reason: 'user_selection'
   * });
   */
  record(action, params = {}, stateSnapshot = null) {
    if (!this.enabled) return;
    
    const entry = {
      // Timestamp preciso
      timestamp: Date.now(),
      datetime: new Date().toISOString(),
      
      // Azione
      action: action,
      
      // Parametri operazione
      params: JSON.parse(JSON.stringify(params)),  // Deep copy
      
      // Snapshot stato (per undo - opzionale)
      state_snapshot: stateSnapshot,
      
      // ID sequenziale
      id: this.history.length
    };
    
    this.history.push(entry);
    
    // Limita lunghezza history (FIFO)
    if (this.history.length > this.maxEntries) {
      this.history.shift();  // Rimuovi più vecchio
    }
    
    console.log(`📝 History: ${action}`, params);
    
    // Emit event per UI update
    this._emitUpdate();
  }
  
  /**
   * Ottieni cronologia completa.
   * 
   * @returns {Array} Array di entry history
   */
  getHistory() {
    return [...this.history];  // Copia per evitare modifiche
  }
  
  /**
   * Ottieni cronologia come testo leggibile.
   * 
   * @returns {string} Testo formattato
   */
  getHistoryText() {
    if (this.history.length === 0) {
      return 'Nessuna operazione registrata';
    }
    
    let text = 'CRONOLOGIA OPERAZIONI\n';
    text += '='.repeat(60) + '\n\n';
    
    for (const entry of this.history) {
      const time = new Date(entry.timestamp).toLocaleTimeString();
      text += `[${time}] ${this._formatAction(entry.action)}\n`;
      text += `  ${this._formatParams(entry.params)}\n\n`;
    }
    
    return text;
  }
  
  /**
   * Renderizza cronologia in HTML element.
   * 
   * @param {string} selector - CSS selector del container
   * 
   * @example
   * <div id="historyPanel"></div>
   * HistoryTracker.renderToHTML('#historyPanel');
   */
  renderToHTML(selector) {
    const container = document.querySelector(selector);
    if (!container) {
      console.warn(`History render: container ${selector} not found`);
      return;
    }
    
    if (this.history.length === 0) {
      container.innerHTML = '<p class="text-muted">Nessuna operazione registrata</p>';
      return;
    }
    
    let html = '<div class="history-list">';
    
    // Mostra dal più recente
    for (let i = this.history.length - 1; i >= 0; i--) {
      const entry = this.history[i];
      const time = new Date(entry.timestamp).toLocaleTimeString();
      
      html += `
        <div class="history-entry" data-id="${entry.id}">
          <div class="history-header">
            <span class="history-action">${this._formatAction(entry.action)}</span>
            <span class="history-time text-muted">${time}</span>
          </div>
          <div class="history-details text-muted small">
            ${this._formatParamsHTML(entry.params)}
          </div>
        </div>
      `;
    }
    
    html += '</div>';
    
    container.innerHTML = html;
  }
  
  /**
   * Esporta cronologia come JSON.
   * 
   * @returns {string} JSON string
   */
  exportJSON() {
    return JSON.stringify({
      export_date: new Date().toISOString(),
      history: this.history,
      version: '1.0'
    }, null, 2);
  }
  
  /**
   * Pulisci cronologia.
   */
  clear() {
    this.history = [];
    console.log('📝 History cleared');
    this._emitUpdate();
  }
  
  /**
   * Enable/disable tracking.
   */
  setEnabled(enabled) {
    this.enabled = enabled;
    console.log(`📝 History tracking: ${enabled ? 'ON' : 'OFF'}`);
  }
  
  // =========================================================================
  // HELPER INTERNI
  // =========================================================================
  
  /**
   * Formatta nome azione per display.
   * @private
   */
  _formatAction(action) {
    const labels = {
      'load_data': '📂 Caricamento Dati',
      'detrend': '📉 Detrending',
      'sigma_clip': '🎯 Sigma Clipping',
      'remove_points': '🗑️ Rimozione Punti',
      'remove_outliers': '⚠️ Rimozione Outlier',
      'compute_period': '🔄 Calcolo Periodo',
      'compute_phase': '🌙 Calcolo Fase',
      'compute_harmonics': '🎵 Analisi Armonica',
      'compute_oc': '📊 Diagramma O-C',
      'session_toggle': '🔲 Toggle Sessione',
      'session_offset': '↕️ Offset Sessione',
      'export': '💾 Export Dati'
    };
    
    return labels[action] || action;
  }
  
  /**
   * Formatta parametri per testo.
   * @private
   */
  _formatParams(params) {
    const parts = [];
    
    for (const [key, value] of Object.entries(params)) {
      if (Array.isArray(value)) {
        parts.push(`${key}: [${value.length} items]`);
      } else if (typeof value === 'object') {
        parts.push(`${key}: ${JSON.stringify(value)}`);
      } else {
        parts.push(`${key}: ${value}`);
      }
    }
    
    return parts.join(', ');
  }
  
  /**
   * Formatta parametri per HTML.
   * @private
   */
  _formatParamsHTML(params) {
    const parts = [];
    
    for (const [key, value] of Object.entries(params)) {
      let displayValue;
      
      if (Array.isArray(value)) {
        displayValue = `[${value.length} elementi]`;
      } else if (typeof value === 'object') {
        displayValue = JSON.stringify(value);
      } else {
        displayValue = value;
      }
      
      parts.push(`<strong>${key}:</strong> ${displayValue}`);
    }
    
    return parts.join(' &middot; ');
  }
  
  /**
   * Emetti evento DOM per update UI.
   * @private
   */
  _emitUpdate() {
    const event = new CustomEvent('historyUpdate', {
      detail: { count: this.history.length }
    });
    document.dispatchEvent(event);
  }
}

// Singleton instance
export const HistoryTracker = new HistoryTrackerClass();

// Export class per testing
export { HistoryTrackerClass };

export default HistoryTracker;
//extrema-analysis.js
/**
 * Modulo per calcolo e visualizzazione estremi (max/min) per sessione
 * Usa approccio scientifico: binning mediano + scipy.signal.find_peaks
 */

import { state } from './state.js';
import { buildArrowStreamJDMag } from '../common/utils-arrow.js';
import { buildAnalysisArraysTyped } from './math-logic.js';

/**
 * Calcola estremi per tutte le sessioni attive
 * @param {number} binSize - Dimensione bin in giorni (default: 0.05 ≈ 1h)
 * @param {number} prominence - Prominenza minima picchi in mag (default: 0.1)
 * @returns {Promise<Object>} Oggetto con estremi per sessione
 */
export async function computeExtremaPerSession(binSize = 0.05, prominence = 0.1) {
  try {
    // Costruisci array dati con session_id
    const { jd, mag } = buildAnalysisArraysTyped();

    if (jd.length === 0) {
      console.warn('Nessun dato disponibile per calcolo estremi');
      return null;
    }

    // Costruisci Arrow stream con session_id
    // Dobbiamo includere session_id per analisi per sessione
    const sessionIds = new Int32Array(jd.length);
    let idx = 0;
    for (let i = 0; i < state.n; i++) {
      if (state.activePoint[i] === 0) continue;
      const sid = state.session[i];
      if (!state.activeSession.get(sid)) continue;
      sessionIds[idx] = sid;
      idx++;
    }

    // Costruisci tabella Arrow con session_id usando window.Arrow
    const Arrow = window.Arrow;

    const schema = new Arrow.Schema([
      new Arrow.Field('jd', new Arrow.Float64()),
      new Arrow.Field('mag', new Arrow.Float32()),
      new Arrow.Field('session_id', new Arrow.Int32())
    ]);

    const table = Arrow.tableFromArrays({
      jd: jd,
      mag: mag,
      session_id: sessionIds
    });

    // Serializza a IPC stream
    const writer = Arrow.RecordBatchStreamWriter.writeAll(table);
    const buffer = await writer.toUint8Array();

    // Invia richiesta
    const res = await fetch(
      `/agata/variable-stars/api/extrema.arrow?bin_size=${binSize}&prominence=${prominence}`,
      {
        method: 'POST',
        body: buffer,
        headers: {
          'Content-Type': 'application/vnd.apache.arrow.stream'
        }
      }
    );

    if (!res.ok) {
      const errorData = await res.json();
      throw new Error(errorData.error || 'Errore calcolo estremi');
    }

    const data = await res.json();

    console.log('Estremi calcolati:', data);

    // Salva nello stato globale
    state.extremaData = data.sessions;

    return data;

  } catch (error) {
    console.error('Errore calcolo estremi:', error);
    throw error;
  }
}

/**
 * Ottieni ampiezza totale (su tutte le sessioni attive)
 * @returns {number|null} Ampiezza totale in magnitudini
 */
export function getTotalAmplitude() {
  if (!state.extremaData) return null;

  let globalMin = Infinity;
  let globalMax = -Infinity;

  Object.values(state.extremaData).forEach(sessionData => {
    if (sessionData.global_min.mag < globalMin) {
      globalMin = sessionData.global_min.mag;
    }
    if (sessionData.global_max.mag > globalMax) {
      globalMax = sessionData.global_max.mag;
    }
  });

  if (globalMin === Infinity || globalMax === -Infinity) return null;

  return globalMax - globalMin;
}

/**
 * Ottieni ampiezza per sessione specifica
 * @param {number} sid - Session ID
 * @returns {number|null} Ampiezza sessione in magnitudini
 */
export function getSessionAmplitude(sid) {
  if (!state.extremaData || !state.extremaData[sid]) return null;
  return state.extremaData[sid].amplitude;
}

/**
 * Formatta visualizzazione estremi per UI
 * @param {number} sid - Session ID
 * @returns {string} HTML per visualizzazione estremi
 */
export function formatExtremaForSession(sid) {
  if (!state.extremaData || !state.extremaData[sid]) {
    return '<span style="font-size: 11px; opacity: 0.5;">-</span>';
  }

  const data = state.extremaData[sid];
  const amp = data.amplitude;

  // Colore basato su ampiezza (stelle variabili tipiche: 0.3-1.5 mag)
  let ampColor = '#94a3b8'; // grigio default
  if (amp > 1.0) {
    ampColor = '#ef4444'; // rosso per grandi ampiezze
  } else if (amp > 0.5) {
    ampColor = '#f59e0b'; // arancione per medie ampiezze
  } else if (amp > 0.1) {
    ampColor = '#22c55e'; // verde per piccole ampiezze
  }

  return `
    <div style="font-size: 11px; padding: 4px 6px; background: #f8fafc; border-radius: 4px; margin-top: 4px;">
      <div style="display: flex; justify-content: space-between; margin-bottom: 2px;">
        <span style="opacity: 0.7;">Min:</span>
        <strong style="color: #22c55e;">${data.global_min.mag.toFixed(3)}</strong>
      </div>
      <div style="display: flex; justify-content: space-between; margin-bottom: 2px;">
        <span style="opacity: 0.7;">Max:</span>
        <strong style="color: #ef4444;">${data.global_max.mag.toFixed(3)}</strong>
      </div>
      <div style="display: flex; justify-content: space-between; padding-top: 2px; border-top: 1px solid #e2e8f0;">
        <span style="opacity: 0.7;">Ampiezza:</span>
        <strong style="color: ${ampColor};">${amp.toFixed(3)} mag</strong>
      </div>
    </div>
  `;
}

/**
 * Invalida cache estremi (da chiamare quando cambiano i dati)
 */
export function invalidateExtremaCache() {
  state.extremaData = null;
}

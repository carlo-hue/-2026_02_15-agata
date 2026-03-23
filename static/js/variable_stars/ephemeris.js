// ephemeris.js
import { state } from './state.js';

/**
 * Calcola effemeridi (tempi di massimo previsti)
 * @param {number} nPredictions - Numero di massimi futuri da predire
 * @returns {Array} Lista di {E, JD, date} dove E è epoch number
 */
export function generateEphemeris(nPredictions = 10) {
  if (!state.lastPeriod || !state.epoch) {
    return [];
  }
  
  const P = state.lastPeriod;
  const JD0 = state.epoch;
  
  // Trova ultimo JD osservato
  let maxJD = -Infinity;
  for (let i = 0; i < state.n; i++) {
    if (state.activePoint[i] === 1 && state.activeSession.get(state.session[i])) {
      if (state.jd[i] > maxJD) maxJD = state.jd[i];
    }
  }
  
  // Calcola epoch number dell'ultima osservazione
  const lastE = Math.floor((maxJD - JD0) / P);
  
  // Genera effemeridi future
  const ephemeris = [];
  for (let i = 1; i <= nPredictions; i++) {
    const E = lastE + i;
    const JD = JD0 + E * P;
    
    // Converti JD in data Gregoriana (approssimativo)
    const date = jdToGregorian(JD);
    
    ephemeris.push({
      E,
      JD: JD.toFixed(5),
      date,
      daysFromNow: (JD - maxJD).toFixed(2)
    });
  }
  
  return ephemeris;
}

/**
 * Conversione JD → Data Gregoriana (algoritmo standard)
 */
function jdToGregorian(JD) {
  const a = JD + 0.5;
  const z = Math.floor(a);
  const f = a - z;
  
  let A = z;
  if (z >= 2299161) {
    const alpha = Math.floor((z - 1867216.25) / 36524.25);
    A = z + 1 + alpha - Math.floor(alpha / 4);
  }
  
  const B = A + 1524;
  const C = Math.floor((B - 122.1) / 365.25);
  const D = Math.floor(365.25 * C);
  const E = Math.floor((B - D) / 30.6001);
  
  const day = B - D - Math.floor(30.6001 * E) + f;
  const month = E < 14 ? E - 1 : E - 13;
  const year = month > 2 ? C - 4716 : C - 4715;
  
  const hours = (day % 1) * 24;
  const minutes = (hours % 1) * 60;
  
  return `${year}-${String(month).padStart(2, '0')}-${String(Math.floor(day)).padStart(2, '0')} ${String(Math.floor(hours)).padStart(2, '0')}:${String(Math.floor(minutes)).padStart(2, '0')} UT`;
}

/**
 * Renderizza tabella effemeridi nell'UI
 */
export function renderEphemeris() {
  const container = document.getElementById("ephemerisTable");
  if (!container) return;
  
  const ephemeris = generateEphemeris(10);
  
  if (ephemeris.length === 0) {
    container.innerHTML = '<em>Calcola prima periodo ed epoca</em>';
    return;
  }
  
  let html = `
    <div style="font-weight: 600; margin-bottom: 8px;">
      📅 Prossimi Massimi Previsti (JD₀=${state.epoch.toFixed(4)}, P=${state.lastPeriod.toFixed(6)} d)
    </div>
    <div style="max-height: 300px; overflow-y: auto;">
      <table style="width: 100%; font-size: 11px; border-collapse: collapse;">
        <thead style="position: sticky; top: 0; background: white; border-bottom: 2px solid #e2e8f0;">
          <tr>
            <th style="padding: 6px; text-align: left;">Ciclo (E)</th>
            <th style="padding: 6px; text-align: left;">JD</th>
            <th style="padding: 6px; text-align: left;">Data (UT)</th>
            <th style="padding: 6px; text-align: right;">Giorni</th>
          </tr>
        </thead>
        <tbody>
  `;
  
  ephemeris.forEach(e => {
    html += `
      <tr style="border-bottom: 1px solid #f1f5f9;">
        <td style="padding: 6px;">${e.E}</td>
        <td style="padding: 6px; font-family: monospace;">${e.JD}</td>
        <td style="padding: 6px;">${e.date}</td>
        <td style="padding: 6px; text-align: right; color: #64748b;">+${e.daysFromNow}</td>
      </tr>
    `;
  });
  
  html += `
        </tbody>
      </table>
    </div>
  `;
  
  container.innerHTML = html;
}
// session-ui.js
import { state, colorForSession, nameForSession, invalidateSamplingCache } from './state.js';
import { drawLightcurve } from './plots.js';
import { computeDetrendCoefficients, calculateGlobalSliderRange, recalculateManualAmplitude } from './math-logic.js';
import { computePhase, invalidateEpoch } from './phase-analysis.js';
import { calculatePhaseStatistics, renderPhaseStatistics } from './phase-statistics.js';
import { updateEphemerisIfVisible } from './phase-controls.js';
import { formatExtremaForSession } from './extrema-analysis.js';

/**
 * Aggiorna i contatori e le statistiche delle sessioni
 */
export function updateCounters() {
  const div = document.getElementById("stats");
  if (!div) return; // Se stats box non esiste, esci gracefully
  let total = 0, rows = [];

  // ✅ CONTEGGIO PUNTI ATTIVI PER SESSIONE
  state.activeSession.forEach((enabled, sid) => {
    if (!enabled) return;
    let cnt = 0;
    for (let i = 0; i < state.n; i++) {
      if (state.activePoint[i] === 1 && state.session[i] === sid) cnt++;
    }
    total += cnt;
    rows.push(`
      <div style="display:flex;align-items:center;gap:6px;padding:2px 0;">
        <span style="width:12px;height:12px;background:${colorForSession(sid)};border-radius:50%;"></span>
        <span style="flex:1;">${nameForSession(sid)}:</span>
        <strong>${cnt}</strong>
      </div>
    `);
  });

  let html = rows.join("");
  html += `<hr style="margin: 8px 0; border:none; border-top:1px solid var(--border);"><div><strong>Totale attivi:</strong> ${total}</div>`;

  // ✅ DETTAGLIO SELEZIONI (se presenti)
  if (state.selectedRaw.size > 0 || state.sigmaClipSuggested.size > 0) {
    const manualCount = state.selectedRaw.size;
    const sigmaCount = state.sigmaClipSuggested.size;

    // Calcola overlap
    const overlap = [...state.selectedRaw].filter(i => state.sigmaClipSuggested.has(i)).length;
    const uniqueSelected = new Set([...state.selectedRaw, ...state.sigmaClipSuggested]).size;

    // Conta per sessione
    const sigmaBySession = new Map();
    const manualBySession = new Map();

    for (const idx of state.sigmaClipSuggested) {
      if (state.activePoint[idx] === 0) continue;
      const sid = state.session[idx];
      sigmaBySession.set(sid, (sigmaBySession.get(sid) || 0) + 1);
    }

    for (const idx of state.selectedRaw) {
      if (state.activePoint[idx] === 0) continue;
      if (state.sigmaClipSuggested.has(idx)) continue; // Evita conteggio doppio
      const sid = state.session[idx];
      manualBySession.set(sid, (manualBySession.get(sid) || 0) + 1);
    }

    html += `
      <hr style="margin: 8px 0; border:none; border-top:2px solid #f59e0b;">
      <div style="padding: 10px; background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); border-radius: 6px; border: 2px solid #f59e0b;">
        <div style="font-weight: 700; margin-bottom: 8px; color: #92400e; text-align: center;">
          🎯 Selezionati per Rimozione
        </div>
    `;

    // ✅ SIGMA CLIPPING
    if (sigmaCount > 0) {
      html += `
        <div style="margin-bottom: 8px; padding: 6px; background: white; border-radius: 4px; border-left: 3px solid #ef4444;">
          <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 4px;">
            <span style="color: #ef4444; font-size: 14px; font-weight: bold;">✕</span>
            <strong>Outlier σ-clip:</strong>
            <span style="margin-left: auto; font-weight: 700; color: #ef4444;">${sigmaCount}</span>
          </div>
      `;

      // Dettaglio per sessione
      if (sigmaBySession.size > 0) {
        html += '<div style="font-size: 11px; padding-left: 20px;">';
        sigmaBySession.forEach((count, sid) => {
          html += `
            <div style="display: flex; gap: 4px; align-items: center;">
              <span style="width: 8px; height: 8px; background: ${colorForSession(sid)}; border-radius: 50%;"></span>
              <span>${nameForSession(sid)}: ${count}</span>
            </div>
          `;
        });
        html += '</div>';
      }

      html += '</div>';
    }


    // ✅ SELEZIONE MANUALE
    if (manualCount > 0) {
      html += `
        <div style="margin-bottom: 8px; padding: 6px; background: white; border-radius: 4px; border-left: 3px solid #f59e0b;">
          <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 4px;">
            <span style="color: #f59e0b; font-size: 14px; font-weight: bold;">◆</span>
            <strong>Manuali:</strong>
            <span style="margin-left: auto; font-weight: 700; color: #f59e0b;">${manualCount - overlap}</span>
          </div>
      `;

      // Dettaglio per sessione
      if (manualBySession.size > 0) {
        html += '<div style="font-size: 11px; padding-left: 20px;">';
        manualBySession.forEach((count, sid) => {
          html += `
            <div style="display: flex; gap: 4px; align-items: center;">
              <span style="width: 8px; height: 8px; background: ${colorForSession(sid)}; border-radius: 50%;"></span>
              <span>${nameForSession(sid)}: ${count}</span>
            </div>
          `;
        });
        html += '</div>';
      }

      html += '</div>';
    }

    // ✅ OVERLAP
    if (overlap > 0) {
      html += `
        <div style="font-size: 11px; padding: 4px 6px; background: white; border-radius: 4px; text-align: center; color: #6b7280; margin-bottom: 6px;">
          (${overlap} punti in entrambe le selezioni)
        </div>
      `;
    }

    // ✅ TOTALE
    html += `
        <div style="padding: 6px; background: #dc2626; color: white; border-radius: 4px; text-align: center; font-weight: 700; font-size: 13px;">
          TOTALE DA RIMUOVERE: ${uniqueSelected}
        </div>
      </div>
    `;
  }

  div.innerHTML = html;
}

/**
 * Renderizza la lista delle sessioni con tutti i controlli
 */
export function renderSessionList() {
  const div = document.getElementById("sessionList");
  div.innerHTML = "";

  Array.from(state.activeSession.keys()).sort((a,b)=>a-b).forEach(sid => {
    const row = document.createElement("div");
    row.className = "session-card";

    const auto = state.sessionAutoOffset.get(sid) || 0;
    const manual = state.sessionManualOffset.get(sid) || 0;

    // ✅ Usa range salvato o default [-2, 2]
    let sliderRange = state.sessionSliderRange.get(sid);
    if (!sliderRange) {
      // Prima volta: usa default conservativo
      sliderRange = { min: -2, max: 2 };
    }

    row.innerHTML = `
      <!-- Prima riga: nome e controlli principali -->
      <div class="session-row-1">
        <input type="checkbox" id="cb${sid}" class="session-checkbox"
               ${state.activeSession.get(sid)?'checked':''}>
        <input type="text" id="name${sid}" value="${nameForSession(sid)}"
               class="session-name">
        <input type="color" id="color${sid}" value="${colorForSession(sid)}"
               class="session-color">
      </div>

      <!-- Seconda riga: offset -->
      <div class="session-row-2">
        <!-- Offset automatico -->
        <div class="offset-group">
          <label class="offset-label">Auto Offset</label>
          <div class="offset-controls">
            <span class="offset-value">${auto >= 0 ? "+" : ""}${auto.toFixed(4)}</span>
          </div>
        </div>

        <!-- Offset manuale con delta mag -->
        <div class="offset-group">
          <label class="offset-label">
            Manuale <span class="delta-mag-label">(Δ mag)</span>
          </label>
          <div class="offset-controls">
            <input type="range" id="slider${sid}" class="offset-slider"
                   min="${sliderRange.min}" max="${sliderRange.max}" step="0.01" value="${manual}">
            <input type="number" step="0.01" id="off${sid}"
                   value="${manual}" class="offset-input">
          </div>
        </div>
      </div>

      <!-- Terza riga: Estremi (Min, Max, Ampiezza) -->
      <div id="extrema${sid}" class="session-extrema">
        ${formatExtremaForSession(sid)}
      </div>
    `;


    div.appendChild(row);

    // ============================================
    // ✅ FUNZIONE HELPER per aggiornamento completo fase
    // ============================================
    const updatePhaseIfNeeded = () => {
      if (state.lastPeriod) {
        computePhase();
        const stats = calculatePhaseStatistics();
        renderPhaseStatistics(stats);
        updateEphemerisIfVisible();
      }
    };

    // ============================================
    // Event listeners
    // ============================================

    // ✅ CHECKBOX: Attiva/disattiva sessione
    row.querySelector(`#cb${sid}`).onchange = (e) => {
      state.activeSession.set(sid, e.target.checked);
      invalidateSamplingCache();
      invalidateEpoch();
      computeDetrendCoefficients();
      drawLightcurve();
      updateCounters();

      // ✅ Aggiorna fase COMPLETA (con stats + effemeridi)
      updatePhaseIfNeeded();
    };

    // ✅ OFFSET: Funzione condivisa per slider + input
    const updateOffset = (value) => {
      const val = parseFloat(value) || 0;
      state.sessionManualOffset.set(sid, val);
      row.querySelector(`#slider${sid}`).value = val;
      row.querySelector(`#off${sid}`).value = val;
      drawLightcurve();
      updateCounters();

      // ✅ Aggiorna fase COMPLETA
      updatePhaseIfNeeded();
    };

    // ✅ SLIDER: Input + supporto tasti freccia sinistra/destra
    const sliderEl = row.querySelector(`#slider${sid}`);
    sliderEl.oninput = (e) => updateOffset(e.target.value);

    // ✅ Tasti freccia sinistra/destra per lo slider
    sliderEl.addEventListener('keydown', (e) => {
      const step = parseFloat(sliderEl.step) || 0.01;
      const currentValue = parseFloat(sliderEl.value) || 0;

      if (e.key === 'ArrowLeft') {
        e.preventDefault();
        const newValue = Math.max(parseFloat(sliderEl.min), currentValue - step);
        updateOffset(newValue);
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        const newValue = Math.min(parseFloat(sliderEl.max), currentValue + step);
        updateOffset(newValue);
      }
    });

    // ✅ INPUT NUMBER: Change + supporto nativo frecce su/giù
    const inputEl = row.querySelector(`#off${sid}`);
    inputEl.onchange = (e) => updateOffset(e.target.value);

    // ✅ Input su frecce su/giù (già supportato nativamente da type="number")
    inputEl.oninput = (e) => updateOffset(e.target.value);

    // ✅ NOME: Cambio nome sessione
    row.querySelector(`#name${sid}`).onchange = (e) => {
      state.sessionName.set(sid, e.target.value || `S${sid}`);
      updateCounters();
      drawLightcurve();

      // ✅ Aggiorna fase COMPLETA (nome appare nella legenda)
      updatePhaseIfNeeded();
    };

    // ✅ COLORE: Cambio colore sessione
    row.querySelector(`#color${sid}`).onchange = (e) => {
      state.sessionColor.set(sid, e.target.value);
      drawLightcurve();
      updateCounters();

      // ✅ Aggiorna fase COMPLETA (colore cambia nel plot)
      updatePhaseIfNeeded();
    };
  });
}

/**
 * Ricalcola l'ampiezza manuale (✏️) e i range degli slider
 * usando sigma clipping sui dati/sessioni attivi correnti
 */
export function recalculateAllSliderRanges() {
  // ✅ STEP 1: Ricalcola ampiezza manuale con sigma clipping
  const ampResult = recalculateManualAmplitude();

  if (!ampResult) {
    console.warn('⚠️ Impossibile ricalcolare ampiezza manuale');
    return 0;
  }

  // ✅ STEP 2: Calcola range slider basato sulla nuova ampiezza
  const globalRange = calculateGlobalSliderRange();

  let updated = 0;

  // ✅ STEP 3: Applica il range a tutte le sessioni attive
  state.activeSession.forEach((enabled, sid) => {
    if (!enabled) return;

    // Salva nello state
    state.sessionSliderRange.set(sid, { min: globalRange.min, max: globalRange.max });
    updated++;
  });

  // ✅ STEP 4: Ridisegna plot fase con le nuove linee
  if (state.lastPeriod) {
    computePhase();
  }

  // ✅ STEP 5: Ri-renderizza statistiche di fase
  const stats = calculatePhaseStatistics();
  if (stats) {
    renderPhaseStatistics(stats);
  }

  // ✅ STEP 6: Ri-renderizza lista sessioni
  renderSessionList();

  console.log(`✅ Ampiezza manuale: ${ampResult.amplitude.toFixed(3)} mag → Range slider: [${globalRange.min}, ${globalRange.max}] applicato a ${updated} sessioni`);

  // ✅ STEP 7: Aggiorna campo ampiezza nel tab Analisi di Supporto
  if (window.updateSupportAmplitude && state.manualAmplitude) {
    window.updateSupportAmplitude(state.manualAmplitude);
  }

  return updated;
}

//  phase-analysis.js - FIXED: Epoch calculation sempre su 100% dati

import { state, getTotalOffset, colorForSession, nameForSession, getSampledIndices, activeSamplingPercent } from './state.js';
import { detrendValue, recalculateManualAmplitude } from './math-logic.js';
import { calculatePhaseStatistics, renderPhaseStatistics } from './phase-statistics.js';
import { computeExtremaPerSession, getTotalAmplitude } from './extrema-analysis.js';

/**
 * ✅ PREVIEW VELOCE durante drag slider (solo restyle, no full redraw)
 */
export function computePhasePreviewOnly() {
  const P = parseFloat(document.getElementById("chosenP").value);
  const shift = parseFloat(document.getElementById("phaseShift").value);
  const phaseRange = document.getElementById("phaseRange")?.value || state.phaseRange;
  
  if (!isFinite(P) || P <= 0) return;
  
  const epoch = state.epoch || state.jd[0];
  const gd = document.getElementById("plotPhase");
  
  // Se plot non esiste, fai full update
  if (!gd || !gd.data || gd.data.length === 0) {
    computePhase();
    return;
  }
  
  console.time('computePhasePreviewOnly');
  
  // ✅ USA SAMPLING PERSISTENTE
  const sampledIndices = getSampledIndices();
  
  // Ricostruisci solo X/Y per ogni trace esistente
  const sessionsData = new Map();
  
  for (let i = 0; i < state.n; i++) {
    // ✅ SAMPLING
    if (sampledIndices && !sampledIndices.has(i)) continue;
    
    if (state.activePoint[i] === 0 || !state.activeSession.get(state.session[i])) continue;
    const sid = state.session[i];
    
    if (!sessionsData.has(sid)) sessionsData.set(sid, { x: [], y: [] });
    
    let phase = (((state.jd[i] - epoch) / P) + shift) % 1.0;
    if (phase < 0) phase += 1.0;
    
    const yval = (state.mag[i] - detrendValue(sid, state.jd[i])) + getTotalOffset(sid);
    
    // Duplicazione come computePhase
    if (phaseRange === "0-2") {
      sessionsData.get(sid).x.push(phase);
      sessionsData.get(sid).y.push(yval);
      sessionsData.get(sid).x.push(phase + 1.0);
      sessionsData.get(sid).y.push(yval);
    } else if (phaseRange === "-0.5-0.5") {
      if (phase > 0.5) phase -= 1.0;
      sessionsData.get(sid).x.push(phase);
      sessionsData.get(sid).y.push(yval);
    } else {
      sessionsData.get(sid).x.push(phase);
      sessionsData.get(sid).y.push(yval);
      sessionsData.get(sid).x.push(phase - 1.0);
      sessionsData.get(sid).y.push(yval);
      sessionsData.get(sid).x.push(phase + 1.0);
      sessionsData.get(sid).y.push(yval);
    }
  }
  
  // Mappa sid → trace index
  const sidToTraceIdx = new Map();
  gd.data.forEach((trace, idx) => {
    if (trace.sid !== undefined) {
      sidToTraceIdx.set(trace.sid, idx);
    }
  });
  
  // Prepara update per Plotly.restyle
  const updates = { x: [], y: [] };
  const traceIndices = [];
  
  sessionsData.forEach((data, sid) => {
    const idx = sidToTraceIdx.get(sid);
    if (idx !== undefined) {
      updates.x.push(data.x);
      updates.y.push(data.y);
      traceIndices.push(idx);
    }
  });
  
  if (traceIndices.length > 0) {
    Plotly.restyle(gd, updates, traceIndices);
  }
  
  state.phaseShift = shift;
  
  console.timeEnd('computePhasePreviewOnly');
}

/**
 * ✅ VERSIONE CORRETTA - Epoch calculation su 100% dati
 */
export function computePhase() {
  const P = parseFloat(document.getElementById("chosenP").value);
  const shift = parseFloat(document.getElementById("phaseShift").value);
  const customTitle = document.getElementById("phaseCustomTitle")?.value || state.phaseTitle;
  const phaseRange = document.getElementById("phaseRange")?.value || state.phaseRange;
  const periodLabel = document.getElementById("phasePeriodLabel")?.value || "";
  
  if (!isFinite(P) || P <= 0) return;
  
  console.time('computePhase');
  
  // 1. GESTIONE EPOCA - ✅ CORRETTO
  let epoch = parseFloat(document.getElementById("epoch")?.value);
  if (!isFinite(epoch) || !epoch) {
    // ✅ Calcola epoca SEMPRE su 100% dati (no sampling)
    epoch = calculateEpochOn100Percent(P);
    state.epoch = epoch;
    if (document.getElementById("epoch")) {
      document.getElementById("epoch").value = epoch.toFixed(4);
    }
    console.log(`📍 Epoca calcolata su 100% dati: JD₀ = ${epoch.toFixed(4)}`);
  } else {
    state.epoch = epoch;
    console.log(`📍 Epoca da input utente: JD₀ = ${epoch.toFixed(4)}`);
  }
  
  // Aggiornamento stato
  state.lastPeriod = P;
  state.phaseShift = shift;
  state.phaseTitle = customTitle;
  state.phaseRange = phaseRange;
  state.phasePeriodLabel = periodLabel;

  // 2. OTTIENI SET CAMPIONATO (solo per VISUALIZZAZIONE)
  const sampledIndices = getSampledIndices();
  
  // 3. CONTEGGIO PUNTI
  let totalActive = 0;
  for (let i = 0; i < state.n; i++) {
    if (sampledIndices && !sampledIndices.has(i)) continue;
    if (state.activePoint[i] === 1 && state.activeSession.get(state.session[i])) {
      totalActive++;
    }
  }

  let pointMultiplier = (phaseRange === "0-2") ? 2 : 
                        (phaseRange === "-0.5-0.5") ? 1 : 3;
  const estimatedPoints = totalActive * pointMultiplier;
  
  // Marker size adattivo
  const markerSize = estimatedPoints > 1000000 ? 1 :
                     estimatedPoints > 500000 ? 1.5 :
                     estimatedPoints > 200000 ? 2 :
                     estimatedPoints > 100000 ? 2.5 :
                     estimatedPoints > 50000 ? 3 : 4;

  console.log(`Phase: ${totalActive.toLocaleString()} active (${activeSamplingPercent}%) × ${pointMultiplier} = ${estimatedPoints.toLocaleString()} pts → marker ${markerSize}px`);

  // 4. ELABORAZIONE DATI - con sampling per VISUALIZZAZIONE
  const traces = [];
  const sessionsData = new Map();
  
  for (let i = 0; i < state.n; i++) {
    // Sampling solo per visualizzazione
    if (sampledIndices && !sampledIndices.has(i)) continue;
    
    if (state.activePoint[i] === 0 || !state.activeSession.get(state.session[i])) continue;
    const sid = state.session[i];
    
    if (!sessionsData.has(sid)) {
      sessionsData.set(sid, { x: [], y: [] });
    }
    
    let phase = (((state.jd[i] - epoch) / P) + shift) % 1.0;
    if (phase < 0) phase += 1.0;
    
    const yval = (state.mag[i] - detrendValue(sid, state.jd[i])) + getTotalOffset(sid);
    
    // Duplicazione range
    if (phaseRange === "0-2") {
      sessionsData.get(sid).x.push(phase);
      sessionsData.get(sid).y.push(yval);
      sessionsData.get(sid).x.push(phase + 1.0);
      sessionsData.get(sid).y.push(yval);
    } else if (phaseRange === "-0.5-0.5") {
      if (phase > 0.5) phase -= 1.0;
      sessionsData.get(sid).x.push(phase);
      sessionsData.get(sid).y.push(yval);
    } else {
      sessionsData.get(sid).x.push(phase);
      sessionsData.get(sid).y.push(yval);
      sessionsData.get(sid).x.push(phase - 1.0);
      sessionsData.get(sid).y.push(yval);
      sessionsData.get(sid).x.push(phase + 1.0);
      sessionsData.get(sid).y.push(yval);
    }
  }

  // 5. CREAZIONE TRACES
  sessionsData.forEach((data, sid) => {
    traces.push({
      type: "scattergl",
      mode: "markers",
      x: data.x,
      y: data.y,
      name: nameForSession(sid),
      marker: { size: markerSize, color: colorForSession(sid), opacity: 0.5 },
      sid: sid
    });
  });

  // 5.5 LINEE AMPIEZZA DRAGGABILI
  // ✅ Inizializza ampiezza manuale con sigma clipping se non presente
  if (!state.manualAmplitude) {
    console.log('🎯 Prima fase: inizializzo ampiezza manuale con sigma clipping');
    recalculateManualAmplitude();
    // Aggiorna campo ampiezza nel tab Analisi di Supporto
    if (window.updateSupportAmplitude && state.manualAmplitude) {
      window.updateSupportAmplitude(state.manualAmplitude);
    }
  }

  // Linee ampiezza - salvate per gestione shapes nel layout

  // 6. LAYOUT E RENDER
  const xRange = phaseRange === "0-2" ? [0, 2] : 
                 phaseRange === "-0.5-0.5" ? [-0.5, 0.5] : [-1, 1];
  
  let periodText = periodLabel.trim() ? periodLabel : `P=${P.toFixed(6)} d`;
  if (activeSamplingPercent < 100) {
    periodText += ` [${activeSamplingPercent}%]`;
  }

  // Costruisci shapes per linee ampiezza draggabili
  const shapes = [];
  if (state.manualAmplitude) {
    shapes.push(
      // Linea MIN (massimo di luce - mag minore)
      {
        type: 'line',
        x0: xRange[0],
        x1: xRange[1],
        y0: state.manualAmplitude.min,
        y1: state.manualAmplitude.min,
        line: {
          color: '#22c55e',
          width: 2,
          dash: 'dash'
        },
        editable: true,
        name: 'amplitude_min'
      },
      // Linea MAX (minimo di luce - mag maggiore)
      {
        type: 'line',
        x0: xRange[0],
        x1: xRange[1],
        y0: state.manualAmplitude.max,
        y1: state.manualAmplitude.max,
        line: {
          color: '#ef4444',
          width: 2,
          dash: 'dash'
        },
        editable: true,
        name: 'amplitude_max'
      }
    );
  }

  // Costruisci titolo con Gaia ID se disponibile
  let titleText = customTitle;
  if (state.gaiaId) {
    titleText += ` ${state.gaiaId}`;
  }
  titleText += ` (${periodText}, JD₀=${epoch.toFixed(4)})`;

  // ✅ GESTIONE BLOCCO ZOOM
  // Se lockPhaseZoom è attivo e abbiamo un range salvato, lo usiamo
  // Altrimenti usiamo l'autorange normale
  const yAxisConfig = state.lockPhaseZoom && state.savedPhaseRange?.yaxis
    ? {
        range: state.savedPhaseRange.yaxis,
        autorange: false,
        title: { text: "Magnitudine", font: { size: 13 } },
        gridcolor: "#e2e8f0",
        fixedrange: false
      }
    : {
        autorange: "reversed",
        title: { text: "Magnitudine", font: { size: 13 } },
        gridcolor: "#e2e8f0",
        fixedrange: false
      };

  // ✅ GESTIONE ZOOM ASSE X (fase)
  // Se lockPhaseZoom è attivo e abbiamo un range X salvato, usalo
  const xAxisConfig = state.lockPhaseZoom && state.savedPhaseRange?.xaxis
    ? {
        range: state.savedPhaseRange.xaxis,
        autorange: false,
        title: { text: "Fase", font: { size: 13 } },
        tickmode: "linear",
        dtick: 0.5,
        zeroline: true,
        zerolinecolor: "#94a3b8",
        gridcolor: "#e2e8f0",
        fixedrange: false
      }
    : {
        range: xRange,
        autorange: false,
        title: { text: "Fase", font: { size: 13 } },
        tickmode: "linear",
        dtick: 0.5,
        zeroline: true,
        zerolinecolor: "#94a3b8",
        gridcolor: "#e2e8f0",
        fixedrange: false
      };

  Plotly.react("plotPhase", traces, {
    title: {
      text: titleText,
      font: {
        size: 16,
        family: 'Inter, sans-serif',
        color: activeSamplingPercent < 100 ? '#f59e0b' : '#0f172a'
      }
    },
    yaxis: yAxisConfig,
    xaxis: xAxisConfig,
    shapes: shapes,
    showlegend: true,
    legend: {
      x: 0.02,
      y: 0.98,
      bgcolor: "rgba(255,255,255,0.8)",
      bordercolor: "#e2e8f0",
      borderwidth: 1
    },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#fafafa",
    margin: { l: 60, r: 30, t: 60, b: 50 },
    dragmode: 'zoom'
  }, {
    responsive: true,
    displaylogo: false,
    editable: true
  });

  // 7. EVENT HANDLERS
  const phgd = document.getElementById("plotPhase");
  phgd.removeAllListeners?.('plotly_click');
  phgd.removeAllListeners?.('plotly_relayout');

  phgd.on('plotly_click', (data) => {
    if (data.event.shiftKey && data.points && data.points.length > 0) {
      const sid = data.points[0].data.sid;
      if (sid !== undefined) {
        const slider = document.getElementById(`slider${sid}`);
        if (slider) {
          slider.scrollIntoView({ behavior: 'smooth', block: 'center' });
          slider.focus();
        }
      }
    }
  });

  // Handler per drag delle linee di ampiezza e salvataggio range zoom
  phgd.on('plotly_relayout', (eventData) => {
    // ✅ SALVATAGGIO RANGE ZOOM quando l'utente fa zoom/pan
    const plotDiv = document.getElementById("plotPhase");

    // Salva range Y (magnitudine)
    if (eventData['yaxis.range[0]'] !== undefined || eventData['yaxis.range'] !== undefined) {
      if (plotDiv && plotDiv.layout && plotDiv.layout.yaxis) {
        if (!state.savedPhaseRange) state.savedPhaseRange = {};
        state.savedPhaseRange.yaxis = plotDiv.layout.yaxis.range || [eventData['yaxis.range[0]'], eventData['yaxis.range[1]']];
        console.log('🔍 Range Y zoom salvato:', state.savedPhaseRange.yaxis);
      }
    }

    // ✅ SALVA anche range X (fase) quando l'utente fa zoom
    if (eventData['xaxis.range[0]'] !== undefined || eventData['xaxis.range'] !== undefined) {
      if (plotDiv && plotDiv.layout && plotDiv.layout.xaxis) {
        if (!state.savedPhaseRange) state.savedPhaseRange = {};
        state.savedPhaseRange.xaxis = plotDiv.layout.xaxis.range || [eventData['xaxis.range[0]'], eventData['xaxis.range[1]']];
        console.log('🔍 Range X zoom salvato:', state.savedPhaseRange.xaxis);
      }
    }

    // Reset zoom: quando l'utente fa doppio click per resettare, pulisci il range salvato
    if (eventData['xaxis.autorange'] || eventData['yaxis.autorange']) {
      state.savedPhaseRange = null;
      console.log('🔍 Range zoom resettato (autorange)');
    }

    // Handler linee di ampiezza (codice esistente)
    if (!state.manualAmplitude) return;

    let updated = false;

    // Controlla se è stata modificata una shape
    Object.keys(eventData).forEach(key => {
      // shapes[0].y0, shapes[0].y1 per linea MIN
      // shapes[1].y0, shapes[1].y1 per linea MAX
      if (key.startsWith('shapes[0]') && key.includes('y')) {
        // Linea MIN modificata
        const newY = eventData[key];
        if (typeof newY === 'number' && isFinite(newY)) {
          state.manualAmplitude.min = newY;
          updated = true;
        }
      } else if (key.startsWith('shapes[1]') && key.includes('y')) {
        // Linea MAX modificata
        const newY = eventData[key];
        if (typeof newY === 'number' && isFinite(newY)) {
          state.manualAmplitude.max = newY;
          updated = true;
        }
      }
    });

    // Aggiorna statistiche se le linee sono cambiate
    if (updated) {
      const stats = calculatePhaseStatistics();
      renderPhaseStatistics(stats);
      console.log(`📏 Ampiezza manuale aggiornata: ${(state.manualAmplitude.max - state.manualAmplitude.min).toFixed(4)} mag`);
      // Aggiorna campo ampiezza nel tab Analisi di Supporto
      if (window.updateSupportAmplitude && state.manualAmplitude) {
        window.updateSupportAmplitude(state.manualAmplitude);
      }
    }
  });

  // 8. RICALCOLA ESTREMI (in background, non bloccante)
  // Gli estremi sono utili per avere ampiezza nelle statistiche
  computeExtremaPerSession().then(() => {
    // Ri-renderizza statistiche per includere ampiezza
    const stats = calculatePhaseStatistics();
    renderPhaseStatistics(stats);
  }).catch(error => {
    console.warn('⚠️ Errore calcolo estremi (non bloccante):', error);
  });

  console.timeEnd('computePhase');
}

/**
 * ✅ NUOVO: Calcolo epoca SEMPRE su 100% dati attivi (no sampling)
 * 
 * IMPORTANTE: Questa funzione ignora completamente il sampling e usa
 * tutti i punti attivi per garantire coerenza scientifica dell'epoca.
 * 
 * @param {number} P - Periodo in giorni
 * @returns {number} - Epoca (JD del massimo di luce)
 */
function calculateEpochOn100Percent(P) {
  console.time('calculateEpochOn100Percent');
  
  // ✅ NESSUN SAMPLING - conta TUTTI i punti attivi
  let count = 0;
  for (let i = 0; i < state.n; i++) {
    // ❌ NON usiamo getSampledIndices() qui!
    if (state.activePoint[i] === 1 && state.activeSession.get(state.session[i])) {
      count++;
    }
  }

  if (count === 0) {
    console.warn('Nessun punto attivo per calcolo epoca');
    return state.jd[0] || 0;
  }

  console.log(`🔬 Calcolo epoca su ${count.toLocaleString()} punti (100% dati attivi)`);

  // Alloca array per TUTTI i punti attivi
  const activeJD = new Float64Array(count);
  const activeMag = new Float32Array(count);
  let jdMin = Infinity;
  
  let ptr = 0;
  for (let i = 0; i < state.n; i++) {
    // ✅ NO SAMPLING - tutti i punti attivi
    if (state.activePoint[i] === 1 && state.activeSession.get(state.session[i])) {
      const sid = state.session[i];
      activeJD[ptr] = state.jd[i];
      activeMag[ptr] = (state.mag[i] - detrendValue(sid, state.jd[i])) + getTotalOffset(sid);
      if (activeJD[ptr] < jdMin) jdMin = activeJD[ptr];
      ptr++;
    }
  }

  // Binning dinamico basato su numero punti
  const nBins = Math.min(100, Math.max(20, Math.floor(count / 50)));
  console.log(`  → Usando ${nBins} bin per binning fase`);
  
  const bins = Array.from({ length: nBins }, () => []);

  for (let i = 0; i < count; i++) {
    const phase = ((activeJD[i] - jdMin) / P) % 1.0;
    const binIdx = Math.floor(((phase < 0 ? phase + 1 : phase) * nBins)) % nBins;
    bins[binIdx].push(activeMag[i]);
  }

  // Trova bin con mediana minima (massimo luce = mag minima)
  let minMedianMag = Infinity;
  let bestPhase = 0;
  const minPointsPerBin = Math.max(5, count / (nBins * 4));

  for (let i = 0; i < nBins; i++) {
    const bin = bins[i];
    if (bin.length < minPointsPerBin) continue;

    bin.sort((a, b) => a - b);
    const median = bin[Math.floor(bin.length / 2)];

    if (median < minMedianMag) {
      minMedianMag = median;
      bestPhase = (i + 0.5) / nBins;
    }
  }

  const epoch = jdMin + (bestPhase * P);
  
  console.log(`  → Epoca trovata: JD₀ = ${epoch.toFixed(4)} (fase ${bestPhase.toFixed(3)}, mag ${minMedianMag.toFixed(3)})`);
  console.timeEnd('calculateEpochOn100Percent');
  
  return epoch;
}

/**
 * ✅ NUOVO: Funzione per invalidare epoca quando cambiano i DATI
 * (non il sampling!)
 * 
 * Chiamare quando:
 * - Cambiano punti attivi/disattivi
 * - Cambiano sessioni abilitate
 * - Cambia detrending
 * - Cambiano offset
 * 
 * NON chiamare quando cambia solo il sampling percentage.
 */
export function invalidateEpoch() {
  state.epoch = null;
  console.log('🔄 Epoca invalidata - verrà ricalcolata al prossimo computePhase()');
}
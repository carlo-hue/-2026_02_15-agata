//phase-statistics.js
import { state, colorForSession, nameForSession, getTotalOffset, getSampledIndices } from './state.js';
import { detrendValue } from './math-logic.js';
import { getTotalAmplitude, getSessionAmplitude } from './extrema-analysis.js';

// Template di curve di luce (forma normalizzata 0-1 in fase)
const TEMPLATES = {
  rrab: {
    name: "RR Lyrae ab (Bailey type)",
    generate: (phase) => {
      // Forma asimmetrica tipica RRab
      const p = phase % 1.0;
      if (p < 0.15) {
        // Rise veloce
        return -0.5 + 3.33 * p;
      } else {
        // Decay lento
        return 0.5 * Math.exp(-5 * (p - 0.15)) - 0.3 * Math.sin(2 * Math.PI * p);
      }
    }
  },
  rrc: {
    name: "RR Lyrae c (sinusoidale)",
    generate: (phase) => {
      return Math.sin(2 * Math.PI * phase);
    }
  },
  cepheid: {
    name: "Cepheid Classica",
    generate: (phase) => {
      const p = phase % 1.0;
      // Rise rapido, decay lento
      if (p < 0.2) {
        return -0.7 + 3.5 * p;
      } else {
        return 0.7 * Math.exp(-3 * (p - 0.2));
      }
    }
  },
  ea: {
    name: "Eclipsing EA (Algol)",
    generate: (phase) => {
      const p = (phase + 0.5) % 1.0; // Centra l'eclissi
      if (p > 0.45 && p < 0.55) {
        // Eclissi primaria
        return -1.0;
      } else if (p > 0.95 || p < 0.05) {
        // Eclissi secondaria (più shallow)
        return -0.3;
      } else {
        return 0;
      }
    }
  },
  ew: {
    name: "Eclipsing EW (W UMa)",
    generate: (phase) => {
      const p = phase % 1.0;
      // Due eclissi simili
      const e1 = Math.exp(-50 * (p - 0.0) ** 2);
      const e2 = Math.exp(-50 * (p - 0.5) ** 2);
      return -(e1 + e2) * 0.8;
    }
  }
};

// Calcola statistiche del fit in fase
export function calculatePhaseStatistics() {
  const P = state.lastPeriod;
  if (!P || P <= 0) return null;
  
  const shift = state.phaseShift;
  const epoch = state.epoch || state.jd[0]; // ✅ FIX: usa epoca salvata

  const sampledIndices = getSampledIndices();
  
  // ✅ OTTIMIZZAZIONE: Raccogli dati con pre-allocazione stimata
  const estimatedSize = Math.floor(state.n * 0.8); // Stima 80% punti attivi
  const data = [];
  data.length = 0; // Force array optimization
  
  for (let i = 0; i < state.n; i++) {
    if (sampledIndices && !sampledIndices.has(i)) continue;
    if (state.activePoint[i] === 0) continue;
    const sid = state.session[i];
    if (!state.activeSession.get(sid)) continue;
    
    // ✅ FIX: usa epoca corretta
    let phase = (((state.jd[i] - epoch) / P) + shift) % 1.0;
    if (phase < 0) phase += 1.0;
    
    const mag = (state.mag[i] - detrendValue(sid, state.jd[i])) + getTotalOffset(sid);
    data.push({ phase, mag, sid });
  }
  
  if (data.length < 10) return null;
  
  // Sort per fase
  data.sort((a, b) => a.phase - b.phase);
  
  // Media mobile per fit locale (finestra 5%)
  const windowSize = Math.max(10, Math.floor(data.length * 0.05));
  const fitted = [];
  
  for (let i = 0; i < data.length; i++) {
    const start = Math.max(0, i - Math.floor(windowSize / 2));
    const end = Math.min(data.length, i + Math.floor(windowSize / 2));
    const window = data.slice(start, end);
    const mean = window.reduce((sum, d) => sum + d.mag, 0) / window.length;
    fitted.push(mean);
  }
  
  // RMS scatter
  let sumSqDiff = 0;
  for (let i = 0; i < data.length; i++) {
    const diff = data[i].mag - fitted[i];
    sumSqDiff += diff * diff;
  }
  const rms = Math.sqrt(sumSqDiff / data.length);
  
  // Chi-squared (assumo errore uniforme 0.03 mag)
  const sigma = 0.03;
  const chiSq = sumSqDiff / (sigma * sigma);
  const reducedChiSq = chiSq / (data.length - 3); // 3 parametri: periodo, fase, ampiezza
  
  // Phase coverage (dividi in 20 bin)
  const nBins = 20;
  const bins = new Array(nBins).fill(0);
  data.forEach(d => {
    const bin = Math.floor(d.phase * nBins) % nBins;
    bins[bin]++;
  });
  const filledBins = bins.filter(b => b > 0).length;
  const coverage = filledBins / nBins;
  
  // String length (Stetson 1996) - misura della "smoothness"
  let stringLength = 0;
  for (let i = 0; i < data.length - 1; i++) {
    const dm = data[i + 1].mag - data[i].mag;
    const dp = data[i + 1].phase - data[i].phase;
    stringLength += Math.sqrt(dm * dm + dp * dp);
  }
  
  // ✅ FIX: Calcolo range senza spread operator
  let magMin = data[0].mag;
  let magMax = data[0].mag;
  for (let i = 1; i < data.length; i++) {
    if (data[i].mag < magMin) magMin = data[i].mag;
    if (data[i].mag > magMax) magMax = data[i].mag;
  }
  const magRange = magMax - magMin;
  const normalizedStringLength = stringLength / (data.length * magRange);
  
  return {
    nPoints: data.length,
    rms,
    chiSq,
    reducedChiSq,
    coverage,
    stringLength: normalizedStringLength,
    mag_min: magMin,  // ✅ Aggiunto per ricerca VSX
    mag_max: magMax,  // ✅ Aggiunto per ricerca VSX
    data
  };
}

// Render statistiche
export function renderPhaseStatistics(stats) {
  const div = document.getElementById("phaseStats");
  
  if (!stats) {
    div.innerHTML = '<div class="small" style="text-align: center; opacity: 0.6; padding: 20px;">Calcola la fase per vedere le statistiche</div>';
    return;
  }
  
  // ✅ COMPATTO: una sola riga con tutte le statistiche
  const rmsColor = stats.rms < 0.05 ? '#22c55e' : stats.rms < 0.1 ? '#facc15' : '#ef4444';
  const chiColor = stats.reducedChiSq < 1.5 ? '#22c55e' : stats.reducedChiSq < 3 ? '#facc15' : '#ef4444';
  const slColor = stats.stringLength < 0.3 ? '#22c55e' : stats.stringLength < 0.5 ? '#facc15' : '#ef4444';
  const covColor = stats.coverage > 0.8 ? '#22c55e' : stats.coverage > 0.6 ? '#facc15' : '#ef4444';
  
  // Valutazione qualità complessiva
  let qualityIcon = '⭐';
  let qualityText = 'Eccellente';
  let qualityColor = '#22c55e';
  
  if (stats.reducedChiSq < 1.5 && stats.rms < 0.05 && stats.coverage > 0.8) {
    qualityIcon = '⭐';
    qualityText = 'Eccellente';
    qualityColor = '#22c55e';
  } else if (stats.reducedChiSq < 3 && stats.rms < 0.1 && stats.coverage > 0.6) {
    qualityIcon = '✓';
    qualityText = 'Buono';
    qualityColor = '#facc15';
  } else {
    qualityIcon = '⚠';
    qualityText = 'Accettabile';
    qualityColor = '#ef4444';
  }
  
  // Ottieni ampiezza totale
  const totalAmplitude = getTotalAmplitude();

  // Ottieni ampiezza manuale se presente
  const manualAmplitude = state.manualAmplitude ?
    (state.manualAmplitude.max - state.manualAmplitude.min) : null;

  let html = `
    <div style="display: flex; align-items: center; gap: 16px; flex-wrap: wrap; padding: 8px; background: #f8fafc; border-radius: 6px; font-size: 12px;">
      <!-- Qualità globale -->
      <div style="display: flex; align-items: center; gap: 6px; padding: 4px 10px; background: white; border-radius: 4px; border: 2px solid ${qualityColor};">
        <span style="font-size: 16px;">${qualityIcon}</span>
        <strong style="color: ${qualityColor};">${qualityText}</strong>
      </div>

      <!-- Punti -->
      <div style="display: flex; align-items: center; gap: 4px;">
        <span style="opacity: 0.7;">Punti:</span>
        <strong>${stats.nPoints}</strong>
      </div>

      <!-- Coverage -->
      <div style="display: flex; align-items: center; gap: 4px;">
        <span style="opacity: 0.7;">Coverage:</span>
        <strong style="color: ${covColor}">${(stats.coverage * 100).toFixed(1)}%</strong>
      </div>

      <!-- RMS -->
      <div style="display: flex; align-items: center; gap: 4px;">
        <span style="opacity: 0.7;">RMS:</span>
        <strong style="color: ${rmsColor}">${stats.rms.toFixed(4)}</strong>
      </div>

      <!-- Chi quadro ridotto -->
      <div style="display: flex; align-items: center; gap: 4px;">
        <span style="opacity: 0.7;">χ²ᵣ:</span>
        <strong style="color: ${chiColor}">${stats.reducedChiSq.toFixed(2)}</strong>
      </div>

      <!-- String Length -->
      <div style="display: flex; align-items: center; gap: 4px;">
        <span style="opacity: 0.7;">String:</span>
        <strong style="color: ${slColor}">${stats.stringLength.toFixed(3)}</strong>
      </div>
  `;

  // ✅ AMPIEZZA TOTALE (se disponibile)
  if (totalAmplitude !== null) {
    // Colore basato su ampiezza
    let ampColor = '#94a3b8';
    if (totalAmplitude > 1.0) {
      ampColor = '#ef4444'; // rosso per grandi ampiezze
    } else if (totalAmplitude > 0.5) {
      ampColor = '#f59e0b'; // arancione per medie ampiezze
    } else if (totalAmplitude > 0.1) {
      ampColor = '#22c55e'; // verde per piccole ampiezze
    }

    html += `
      <!-- Ampiezza totale -->
      <div style="display: flex; align-items: center; gap: 6px; padding: 4px 10px; background: white; border-radius: 4px; border: 2px solid ${ampColor};">
        <span style="opacity: 0.7;">Ampiezza:</span>
        <strong style="color: ${ampColor};">${totalAmplitude.toFixed(3)} mag</strong>
      </div>
    `;
  }

  // ✅ AMPIEZZA MANUALE (se presente)
  if (manualAmplitude !== null) {
    // Colore basato su ampiezza manuale
    let manAmpColor = '#94a3b8';
    if (manualAmplitude > 1.0) {
      manAmpColor = '#ef4444';
    } else if (manualAmplitude > 0.5) {
      manAmpColor = '#f59e0b';
    } else if (manualAmplitude > 0.1) {
      manAmpColor = '#22c55e';
    }

    html += `
      <!-- Ampiezza manuale -->
      <div style="display: flex; align-items: center; gap: 6px; padding: 4px 10px; background: white; border-radius: 4px; border: 2px solid ${manAmpColor}; border-style: dashed;">
        <span style="opacity: 0.7;">Ampiezza ✏️:</span>
        <strong style="color: ${manAmpColor};">${manualAmplitude.toFixed(3)} mag</strong>
      </div>
    `;
  }

  html += `
      <!-- Bottone ricalcola -->
      <button id="recalcSliderRanges" class="btn-recalc-ranges"
              title="Ricalcola ampiezza manuale (✏️) con sigma clipping sui punti/sessioni attivi correnti">
        ⟲ Ricalcola
      </button>
    </div>
  `;

  div.innerHTML = html;
}

// Overlay template sulla curva in fase
export function overlayTemplate(templateKey) {
  const gd = document.getElementById("plotPhase");
  
  // Rimuovi eventuali template precedenti
  const traces = gd.data || [];
  const dataTraces = traces.filter(t => !t.name || !t.name.includes("RR Lyrae") && !t.name.includes("Cepheid") && !t.name.includes("Eclipsing"));
  
  if (templateKey === "none" || !state.lastPeriod) {
    // Ridisegna solo con i dati
    if (dataTraces.length < traces.length) {
      Plotly.deleteTraces(gd, traces.length - 1);
    }
    return;
  }
  
  const template = TEMPLATES[templateKey];
  if (!template) return;
  
  // Genera punti del template
  const nPoints = 200;
  const templatePhases = [];
  const templateMags = [];
  
  for (let i = 0; i < nPoints; i++) {
    const phase = i / nPoints;
    templatePhases.push(phase);
    templateMags.push(template.generate(phase));
  }
  
  // Normalizza template per matchare range dati
  const stats = calculatePhaseStatistics();
  if (!stats) return;
  
  const dataMags = stats.data.map(d => d.mag);
  
  // ✅ FIX: Calcolo min/max senza spread operator
  let dataMin = dataMags[0];
  let dataMax = dataMags[0];
  let dataSum = 0;
  for (let i = 0; i < dataMags.length; i++) {
    if (dataMags[i] < dataMin) dataMin = dataMags[i];
    if (dataMags[i] > dataMax) dataMax = dataMags[i];
    dataSum += dataMags[i];
  }
  const dataMean = dataSum / dataMags.length;
  const dataRange = dataMax - dataMin;
  
  // ✅ FIX: Calcolo min/max template
  let templateMin = templateMags[0];
  let templateMax = templateMags[0];
  for (let i = 1; i < templateMags.length; i++) {
    if (templateMags[i] < templateMin) templateMin = templateMags[i];
    if (templateMags[i] > templateMax) templateMax = templateMags[i];
  }
  const templateRange = templateMax - templateMin;
  
  const scaledTemplate = templateMags.map(m => {
    const normalized = (m - templateMin) / templateRange;
    return dataMean + (normalized - 0.5) * dataRange;
  });
  
  // Rimuovi template precedente se esiste
  if (dataTraces.length < traces.length) {
    Plotly.deleteTraces(gd, traces.length - 1);
  }
  
  // Aggiungi nuovo template
  const templateTrace = {
    x: templatePhases,
    y: scaledTemplate,
    type: "scatter",
    mode: "lines",
    name: template.name,
    line: { color: "#ef4444", width: 3, dash: "dash" },
    hoverinfo: "skip"
  };
  
  Plotly.addTraces(gd, templateTrace);
}
//plots.js
import { state, colorForSession, nameForSession, baseYRange, setBaseYRange, getTotalOffset } from './state.js';
import { detrendValue, buildAnalysisArraysTyped } from './math-logic.js';
import { buildArrowStreamJDMag } from '../common/utils-arrow.js';
import { calculatePhaseStatistics, renderPhaseStatistics } from './phase-statistics.js';
import { updateCounters } from './session-ui.js';
import { CONFIG } from './config.js';
import { computeMultiPeriod, classifySinglePeriod } from './period-analysis.js';


/**
 * Calcola offset temporali per visualizzazione compatta
 * Mantiene relazioni temporali DENTRO ogni sessione, ma rimuove gap TRA sessioni
 */
function calculateCompactTimeOffsets() {
  const offsets = new Map();
  const sessionRanges = new Map();
  
  // 1. Trova range JD per ogni sessione
  for (let i = 0; i < state.n; i++) {
    if (state.activePoint[i] === 0) continue;
    const sid = state.session[i];
    if (!state.activeSession.get(sid)) continue;
    
    if (!sessionRanges.has(sid)) {
      sessionRanges.set(sid, { min: Infinity, max: -Infinity });
    }
    
    const range = sessionRanges.get(sid);
    if (state.jd[i] < range.min) range.min = state.jd[i];
    if (state.jd[i] > range.max) range.max = state.jd[i];
  }
  
  // 2. Calcola offset cumulativo per "impacchettare" le sessioni
  let cumulativeOffset = 0;
  const sortedSessions = Array.from(sessionRanges.keys()).sort((a, b) => {
    return sessionRanges.get(a).min - sessionRanges.get(b).min;
  });
  
  for (const sid of sortedSessions) {
    const range = sessionRanges.get(sid);
    
    // Offset = sposta questa sessione all'inizio del "pacchetto"
    offsets.set(sid, cumulativeOffset - range.min);
    
    // Prossima sessione parte dopo questa (con piccolo gap di 1 giorno)
    cumulativeOffset += (range.max - range.min) + 1.0;
  }
  
  return offsets;
}

export function drawLightcurve(preservedRange = null) {
  const traces = [];
  let totalCount = 0;
  const sids = Array.from(state.activeSession.keys()).sort((a,b)=>a-b);

  const hasOutliers = state.sigmaClipSuggested && state.sigmaClipSuggested.size > 0;
  if (hasOutliers) {
    preservedRange = null;
  }

  const compactMode = document.getElementById("compactView")?.checked || false;

  // ✅ Vista compatta: normalizza e compatta sequenzialmente
  let timeOffsets = null;
  let sessionNormalization = null;

  if (compactMode) {
    // 1. Raccolgo dati grezzi per ogni sessione (t, y, indices)
    const sessionData = new Map();

    for (let i = 0; i < state.n; i++) {
      if (state.activePoint[i] === 0) continue;
      const sid = state.session[i];
      if (!state.activeSession.get(sid)) continue;

      if (!sessionData.has(sid)) {
        sessionData.set(sid, { t: [], y: [], indices: [] });
      }

      const data = sessionData.get(sid);
      data.t.push(state.jd[i]);
      data.y.push(state.mag[i] - detrendValue(sid, state.jd[i]));
      data.indices.push(i);
    }

    // 2. Raggruppa sessioni per range identico e calcola shift preservando overlap
    const sessionToRange = new Map();
    const uniqueRanges = []; // array di {tMin, tMax, tRange, sessions: [sid1, sid2, ...]}

    // Primo: raccolgo range unici
    for (const [sid, data] of sessionData) {
      const tMin = Math.min(...data.t);
      const tMax = Math.max(...data.t);

      // Cerca se esiste già questo range
      let found = false;
      for (const range of uniqueRanges) {
        if (range.tMin === tMin && range.tMax === tMax) {
          range.sessions.push(sid);
          sessionToRange.set(sid, range);
          found = true;
          break;
        }
      }

      if (!found) {
        const newRange = { tMin, tMax, tRange: tMax - tMin || 1, sessions: [sid] };
        uniqueRanges.push(newRange);
        sessionToRange.set(sid, newRange);
      }
    }

    // Secondo: ordina range per tMin (dal più vecchio al più recente)
    uniqueRanges.sort((a, b) => a.tMin - b.tMin);

    // Terzo: calcola shift per ogni range preservando sovrapposizioni e comprimendo gap
    // Algoritmo: per ogni range successivo, calcola dove dovrebbe iniziare basato su:
    // 1. Se c'è sovrapposizione: posiziona per mostrare la percentuale di overlap
    // 2. Se NO overlap: riduce un po' il gap per compressione visiva, ma mantiene proporzioni
    const firstRange = uniqueRanges[0];
    firstRange.shift = 0;

    for (let i = 1; i < uniqueRanges.length; i++) {
      const range = uniqueRanges[i];
      const prevRange = uniqueRanges[i - 1];

      // Se questo range inizia prima della fine del precedente: c'è sovrapposizione
      if (range.tMin < prevRange.tMax) {
        // Calcola percentuale di sovrapposizione
        // relativeStart = dove inizia questo range nel normalizzato [0,1] del range precedente
        const relativeStart = (range.tMin - prevRange.tMin) / prevRange.tRange;
        range.shift = prevRange.shift + relativeStart;
      } else {
        // No overlap: riduce il gap per "comprimere" ma mantiene separazione
        // gap_fraction: quanto è grande il gap rispetto al range precedente
        const gap = range.tMin - prevRange.tMax;
        const gapFraction = Math.min(0.3, gap / prevRange.tRange); // max 30% di compressione
        range.shift = prevRange.shift + 1.0 - gapFraction;
      }
    }

    // Quarto: calcola normalizzazione per ogni sessione
    timeOffsets = new Map();
    sessionNormalization = new Map();

    for (const [sid, range] of sessionToRange) {
      sessionNormalization.set(sid, {
        tMin: range.tMin,
        tRange: range.tRange,
        shift: range.shift
      });

      timeOffsets.set(sid, range.shift);
    }
  }

  // TRACCE NORMALI
  for (const sid of sids) {
    if (!state.activeSession.get(sid)) continue;

    const totalOffset = getTotalOffset(sid);
    let m = 0;
    for (let i = 0; i < state.n; i++) if (state.activePoint[i] === 1 && state.session[i] === sid) m++;
    if (m === 0) continue;

    const x = new Float64Array(m);
    const y = new Float32Array(m);
    const rawMap = new Int32Array(m);
    const realJD = compactMode ? new Float64Array(m) : null;

    let j = 0;

    for (let i = 0; i < state.n; i++) {
      if (state.activePoint[i] === 0 || state.session[i] !== sid) continue;

      let xVal = state.jd[i];

      // Se in compactMode, normalizza il tempo
      if (compactMode && sessionNormalization) {
        const norm = sessionNormalization.get(sid);
        const tNorm = (state.jd[i] - norm.tMin) / norm.tRange; // [0, 1]
        xVal = tNorm + norm.shift; // [shift, shift+1]
      }

      x[j] = xVal;
      y[j] = (state.mag[i] - detrendValue(sid, state.jd[i])) + totalOffset;
      rawMap[j] = i;

      if (compactMode) {
        realJD[j] = state.jd[i]; // JD reale per hover
      }

      j++;
    }

    totalCount += m;

    traces.push({
      type: "scattergl",
      mode: "markers",
      x,
      y,
      name: `${nameForSession(sid)} (${m})`,
      marker: {
        size: state.currentMarkerSize,
        color: colorForSession(sid),
        opacity: 0.85
      },
      customdata: compactMode ? realJD : rawMap,
      hovertemplate: compactMode
        ? `<b>${nameForSession(sid)}</b><br>JD=%{customdata:.5f}<br>mag=%{y:.4f}<extra></extra>`
        : `<b>${nameForSession(sid)}</b><br>JD=%{x:.5f}<br>mag=%{y:.4f}<br><i>Shift+Click per offset rapido</i><extra></extra>`,
      sid: sid
    });
  }
  
  // OUTLIER SIGMA CLIPPING
  if (state.sigmaClipSuggested?.size > 0) {
    const outliersBySession = new Map();

    for (const idx of state.sigmaClipSuggested) {
      if (state.activePoint[idx] === 0) continue;

      const sid = state.session[idx];
      if (!state.activeSession.get(sid)) continue;

      if (!outliersBySession.has(sid)) {
        outliersBySession.set(sid, { x: [], y: [], indices: [] });
      }

      const data = outliersBySession.get(sid);

      let xVal = state.jd[idx];

      // Se in compactMode, normalizza il tempo come sopra
      if (compactMode && sessionNormalization) {
        const norm = sessionNormalization.get(sid);
        const tNorm = (state.jd[idx] - norm.tMin) / norm.tRange;
        xVal = tNorm + norm.shift;
      }

      data.x.push(xVal);
      data.y.push((state.mag[idx] - detrendValue(sid, state.jd[idx])) + getTotalOffset(sid));
      data.indices.push(idx);
    }
    
    outliersBySession.forEach((data, sid) => {
      traces.push({
        type: "scattergl",
        mode: "markers",
        x: data.x,
        y: data.y,
        name: `🚨 ${nameForSession(sid)} - Outlier (${data.x.length})`,
        marker: { 
          size: state.currentMarkerSize * CONFIG.PLOT.MARKER_SIZE.OUTLIER_MULTIPLIER,
          color: "#ef4444",
          symbol: "x",
          line: { width: 3, color: "#ffffff" },
          opacity: 1.0
        },
        hovertemplate: `<b>⚠️ OUTLIER σ-clip</b><br>${nameForSession(sid)}<br>JD=%{x:.5f}<br>mag=%{y:.4f}<extra></extra>`,
        showlegend: true,
        legendgroup: `outliers-${sid}`
      });
    });
  }
  
  // SELEZIONE MANUALE
  if (state.selectedRaw.size > 0) {
    const manualX = [], manualY = [];
    
    for (const idx of state.selectedRaw) {
      if (state.activePoint[idx] === 0) continue;
      if (state.sigmaClipSuggested.has(idx)) continue;
      
      const sid = state.session[idx];
      if (!state.activeSession.get(sid)) continue;
      
      const timeOffset = compactMode ? (timeOffsets.get(sid) || 0) : 0;
      
      manualX.push(state.jd[idx] + timeOffset);
      manualY.push((state.mag[idx] - detrendValue(sid, state.jd[idx])) + getTotalOffset(sid));
    }
    
    if (manualX.length > 0) {
      traces.push({
        type: "scattergl",
        mode: "markers",
        x: manualX,
        y: manualY,
        name: `📌 Selezione Manuale (${manualX.length})`,
        marker: { 
          size: state.currentMarkerSize * CONFIG.PLOT.MARKER_SIZE.SELECTED_MULTIPLIER, 
          color: "#f59e0b",
          symbol: "diamond",
          line: { width: 2, color: "#fff" },
          opacity: 0.9
        },
        hovertemplate: "<b>📌 Selezionato</b><br>JD=%{x:.5f}<br>mag=%{y:.4f}<extra></extra>",
        showlegend: true
      });
    }
  }

  const titleSuffix = compactMode ? " 📦" : "";
  
  const layout = {
    title: `Curva di luce — ${totalCount} punti${titleSuffix}`,
    xaxis: {
      title: compactMode ? "Tempo Relativo (d)" : "JD",
      ...(preservedRange ? { range: preservedRange.x } : { autorange: true })
    },
    yaxis: {
      title: "Mag",
      ...(preservedRange ? { range: preservedRange.y } : { autorange: "reversed" })
    },
    dragmode: "select",
    showlegend: true,
    legend: {
      x: 1.02,
      y: 1,
      xanchor: 'left',
      bgcolor: 'rgba(255,255,255,0.9)',
      bordercolor: '#e2e8f0',
      borderwidth: 1
    }
  };
  
  Plotly.react("plotLC", traces, layout);
  
  if (!baseYRange) {
    const gd = document.getElementById("plotLC");
    if (gd?.layout?.yaxis?.range) setBaseYRange([...gd.layout.yaxis.range]);
  }
  
  setupLightcurveInteractions();
}

// Interazioni avanzate: Shift+Click per selezione rapida sessione
function setupLightcurveInteractions() {
  const gd = document.getElementById("plotLC");
  
  gd.on('plotly_click', (data) => {
    if (data.event.shiftKey && data.points && data.points.length > 0) {
      const sid = data.points[0].data.sid;
      if (sid !== undefined) {
        const slider = document.getElementById(`slider${sid}`);
        if (slider) {
          slider.scrollIntoView({ behavior: 'smooth', block: 'center' });
          slider.focus();
          
          const card = slider.closest('.session-card');
          if (card) {
            card.style.transition = 'all 0.3s';
            card.style.background = '#dbeafe';
            card.style.transform = 'scale(1.02)';
          }
        }
      }
    }
  });
  
  gd.on('plotly_selected', (eventData) => {
    state.selectedRaw.clear();
    if (!eventData || !eventData.points) return;
    for (const p of eventData.points) {
      const rawIdx = p.customdata;
      if (rawIdx !== undefined && rawIdx !== null) {
        state.selectedRaw.add(rawIdx);
      }
    }
    updateCounters();
  });
}

export function getCurrentLCRange() {
  const gd = document.getElementById("plotLC");
  if (!gd || !gd.layout) return null;
  const xr = gd.layout.xaxis?.range;
  const yr = gd.layout.yaxis?.range;
  if (!xr || !yr) return null;
  return {
    x: [...xr],
    y: [...yr]
  };
}

export async function computePeriodogram(callbackClick) {
  const minP = Number(document.getElementById("minP").value);
  const maxP = Number(document.getElementById("maxP").value);
  const enablePrewhitening = document.getElementById("enablePrewhitening")?.checked || false;
  const nPeriods = enablePrewhitening ? parseInt(document.getElementById("nPeriods")?.value || 3) : 1;

  // ✅ MODALITÀ MULTI-PERIODO CON PRE-WHITENING
  if (enablePrewhitening && nPeriods > 1) {
    console.log(`🎯 Modalità multi-periodo: cercando ${nPeriods} periodi con pre-whitening`);

    try {
      const multiResults = await computeMultiPeriod(nPeriods, minP, maxP);

      // Usa lo spettro della prima iterazione per il plot
      const data = multiResults[0].spectrum;

      console.log(`📊 Spettro: ${data.period.length} punti, range power: ${Math.min(...data.power).toFixed(4)} - ${Math.max(...data.power).toFixed(4)}`);

      // Plot spettro base
      const traces = [
        {
          x: data.period,
          y: data.power,
          mode: "lines",
          name: "Spettro Originale",
          line: { color: "#38bdf8", width: 1.5 },
          opacity: 0.8,
          showlegend: true
        }
      ];

      // FAP levels
      const fapStyles = {
        "0.1": {dash:"dot", color:"#f97316", name:"FAP 10%"},
        "0.01": {dash:"dash", color:"#facc15", name:"FAP 1%"},
        "0.001": {dash:"solid", color:"#22c55e", name:"FAP 0.1%"}
      };

      Object.entries(data.fap_levels).forEach(([k, yval]) => {
        traces.push({
          x: [data.period[0], data.period[data.period.length-1]],
          y: [yval, yval],
          mode: "lines",
          name: fapStyles[k].name,
          line: { ...fapStyles[k], width: 2 },
          hoverinfo: "name"
        });
      });

      // ✅ ANNOTAZIONI PERIODI MULTIPLI
      const colors = ["#22c55e", "#3b82f6", "#a855f7", "#f59e0b", "#ef4444"];
      multiResults.forEach((result, idx) => {
        traces.push({
          x: [result.period],
          y: [result.power],
          mode: "markers+text",
          marker: {
            size: 14 + (2 * (nPeriods - idx)),
            color: colors[idx % colors.length],
            symbol: "star",
            line: {width: 2, color: '#fff'}
          },
          text: [`P${idx + 1}`],
          textposition: "top center",
          textfont: { size: 11, color: colors[idx % colors.length], family: "monospace" },
          hovertemplate:
            `<b>Periodo ${idx + 1}</b><br>` +
            `P: ${result.period.toFixed(6)} d<br>` +
            `Power: ${result.power.toFixed(3)}<br>` +
            `Amplitude: ${result.amplitude.toFixed(4)} mag<br>` +
            `FAP: ${result.fap.toExponential(2)}<br>` +
            `SNR: ${result.snr.toFixed(1)}<extra></extra>`,
          name: `P${idx + 1}: ${result.period.toFixed(6)} d`,
          showlegend: true
        });
      });

      Plotly.react("plotPeriod", traces, {
        title: {
          text: `Analisi Multi-Periodo (${multiResults.length} periodi trovati)`,
          font: { size: 16, color: "#e5e7eb" }
        },
        paper_bgcolor: "#020617",
        plot_bgcolor: "#020617",
        font: {color: "#e5e7eb"},
        xaxis: {
          title: "Periodo (giorni)",
          gridcolor: "#1e293b",
          type: "linear"
        },
        yaxis: {
          title: "Power",
          gridcolor: "#1e293b",
          type: "linear"
        },
        showlegend: true,
        legend: {x: 0.02, y: 0.98, bgcolor: "rgba(0,0,0,0.7)", font: {size: 10}},
        hovermode: "closest"
      });

      // ✅ RENDER TABELLA PERIODI MULTIPLI
      renderMultiPeriodTable(multiResults, callbackClick);

      const pd = document.getElementById("plotPeriod");
      pd.on("plotly_click", (ev) => {
        if (ev.points) callbackClick(ev.points[0].x);
      });

      // ✅ Salva risultati nello state per AI Advisor
      const periods = multiResults.map(r => r.period);
      const amplitudes = multiResults.map(r => r.amplitude);
      const powers = multiResults.map(r => r.power);

      state.periodogramResult = {
        periods,
        amplitudes,
        powers,
        peaks: multiResults.map(r => ({
          period: r.period,
          power: r.power,
          fap: r.fap,
          snr: r.snr,
          amplitude: r.amplitude
        })),
        timestamp: Date.now() / 86400000 + 2440587.5 // Convert to JD
      };

      console.log('📊 Risultati periodigramma salvati in state per AI Advisor');

      return multiResults.map(r => ({
        period: r.period,
        power: r.power,
        fap: r.fap,
        snr: r.snr
      }));

    } catch (error) {
      console.error("❌ Errore analisi multi-periodo:", error);
      alert(`Errore: ${error.message}`);
      return [];
    }
  }

  // ✅ MODALITÀ STANDARD (SINGOLO PERIODO)
  const { jd, mag } = buildAnalysisArraysTyped();

  const res = await fetch(`/agata/variable-stars/api/periodogram.arrow?min_period=${minP}&max_period=${maxP}&n_freq=6000`, {
    method: "POST",
    body: buildArrowStreamJDMag(jd, mag)
  });

  const data = await res.json();
  const traces = [
    {
      x: data.period,
      y: data.power,
      mode: "lines",
      name: "Lomb—Scargle",
      line: { color: "#38bdf8" }
    }
  ];

  const fapStyles = {
    "0.1": {dash:"dot", color:"#f97316", name:"FAP 10%"},
    "0.01": {dash:"dash", color:"#facc15", name:"FAP 1%"},
    "0.001": {dash:"solid", color:"#22c55e", name:"FAP 0.1%"}
  };

  Object.entries(data.fap_levels).forEach(([k, yval]) => {
    traces.push({
      x: [data.period[0], data.period[data.period.length-1]],
      y: [yval, yval],
      mode: "lines",
      name: fapStyles[k].name,
      line: { ...fapStyles[k], width: 2 },
      hoverinfo: "name"
    });
  });

  traces.push({
    x: data.peaks.map(p => p.period),
    y: data.peaks.map(p => p.power),
    mode: "markers",
    marker: {
      size: 10,
      color: data.peaks.map(p => p.fap < 1e-3 ? "#22c55e" : p.fap < 1e-2 ? "#facc15" : "#f97316"),
      line: {width: 2, color: '#fff'}
    },
    text: data.peaks.map(p =>
      `P: ${p.period.toFixed(6)} d<br>Power: ${p.power.toFixed(3)}<br>FAP: ${p.fap.toExponential(2)}<br>SNR: ${p.snr.toFixed(1)}`
    ),
    hoverinfo: "text",
    name: "Top Peaks"
  });

  Plotly.react("plotPeriod", traces, {
    title: "Periodogramma Lomb-Scargle",
    paper_bgcolor: "#020617",
    plot_bgcolor: "#020617",
    font: {color: "#e5e7eb"},
    xaxis: {title: "Periodo (giorni)", gridcolor: "#1e293b"},
    yaxis: {title: "Power", gridcolor: "#1e293b"},
    showlegend: true,
    legend: {x: 0.02, y: 0.98, bgcolor: "rgba(0,0,0,0.5)"}
  });

  const pd = document.getElementById("plotPeriod");
  pd.on("plotly_click", (ev) => {
    if (ev.points) callbackClick(ev.points[0].x);
  });

  // ✅ Salva risultati nello state per AI Advisor
  const periods = data.peaks.map(p => p.period);
  const powers = data.peaks.map(p => p.power);

  state.periodogramResult = {
    periods,
    amplitudes: [], // Non disponibili in modalità singola
    powers,
    peaks: data.peaks.map(p => ({
      period: p.period,
      power: p.power,
      fap: p.fap,
      snr: p.snr
    })),
    timestamp: Date.now() / 86400000 + 2440587.5 // Convert to JD
  };

  console.log('📊 Risultati periodigramma salvati in state per AI Advisor');

  return data.peaks;
}

/**
 * Render tabella riassuntiva periodi multipli
 */
function renderMultiPeriodTable(results, onPeriodClick) {
  const peaksDiv = document.getElementById("peaks");
  if (!peaksDiv) {
    console.error("❌ Elemento #peaks non trovato!");
    return;
  }

  console.log(`📋 Rendering tabella per ${results.length} periodi`);
  peaksDiv.innerHTML = "";

  // Layout orizzontale per i periodi
  peaksDiv.style.flexDirection = "row";
  peaksDiv.style.alignItems = "stretch";
  peaksDiv.style.justifyContent = "flex-start";
  peaksDiv.style.flexWrap = "wrap";
  peaksDiv.style.gap = "10px";

  // Colori per i periodi
  const colors = ["#22c55e", "#3b82f6", "#a855f7", "#f59e0b", "#ef4444"];

  results.forEach((result, idx) => {
    const div = document.createElement("div");
    div.className = "peak-item";
    div.style.cssText = `
      cursor: pointer;
      padding: 10px;
      background: #f8fafc;
      border: 2px solid ${colors[idx % colors.length]};
      border-radius: 6px;
      transition: all 0.2s;
      flex: 1;
      min-width: 200px;
      max-width: 300px;
    `;

    const qualityColor = result.fap < 1e-3 ? "#22c55e" : result.fap < 1e-2 ? "#facc15" : "#f97316";

    // Genera suggerimento specifico per QUESTO periodo
    const suggestion = classifySinglePeriod(result.period);
    console.log(`🔬 P${idx + 1}: ${result.period.toFixed(6)} d → "${suggestion}"`);

    div.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
        <strong style="font-size: 14px; color: ${colors[idx % colors.length]};">
          P${idx + 1}: ${result.period.toFixed(6)} d
        </strong>
        <span style="background: ${qualityColor}; color: #000; padding: 2px 6px; border-radius: 4px; font-size: 9px; font-weight: 600;">
          FAP: ${result.fap.toExponential(1)}
        </span>
      </div>
      <div style="font-size: 10px; color: #64748b; line-height: 1.5; margin-bottom: 8px;">
        Power: <strong>${result.power.toFixed(3)}</strong><br>
        Amp: <strong>${result.amplitude.toFixed(4)} mag</strong><br>
        SNR: <strong>${result.snr.toFixed(1)}</strong>
      </div>
      <div style="font-size: 10px; color: #6366f1; font-weight: 500; font-style: italic; padding-top: 6px; border-top: 1px solid #e2e8f0;">
        ${suggestion}
      </div>
    `;

    div.onmouseover = () => {
      div.style.transform = "translateY(-2px)";
      div.style.boxShadow = "0 4px 12px rgba(0,0,0,0.15)";
    };

    div.onmouseout = () => {
      div.style.transform = "translateY(0)";
      div.style.boxShadow = "none";
    };

    div.onclick = () => onPeriodClick(result.period);

    peaksDiv.appendChild(div);
  });

  // Verifica che sia stato aggiunto
  console.log(`✅ Periodi aggiunti a #peaks orizzontalmente`);
}

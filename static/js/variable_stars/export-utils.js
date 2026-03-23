//export-utils.js
import { state, nameForSession, getTotalOffset } from './state.js';
import { detrendValue } from './math-logic.js';
import { calculatePhaseStatistics } from './phase-statistics.js';


// Export CSV detrended (tutti i punti attivi con detrend applicato)
export function exportDetrendedCSV() {
  let csv = "session_id,session_name,jd,mag_original,mag_detrended,mag_offset_applied\n";
  
  for (let i = 0; i < state.n; i++) {
    if (state.activePoint[i] === 0) continue;
    const sid = state.session[i];
    if (!state.activeSession.get(sid)) continue;
    
    const jd = state.jd[i];
    const magOrig = state.mag[i];
    const detrend = detrendValue(sid, jd);
    const offset = getTotalOffset(sid)
    const magDetrended = magOrig - detrend;
    const magFinal = magDetrended + offset;
    
    csv += `${sid},${nameForSession(sid)},${jd.toFixed(8)},${magOrig.toFixed(6)},${magDetrended.toFixed(6)},${magFinal.toFixed(6)}\n`;
  }
  
  downloadFile(csv, `lightcurve_detrended_${timestamp()}.csv`, 'text/csv');
}

// Export CSV folded (dati in fase) con metadati
export function exportFoldedCSV() {
  if (!state.lastPeriod) {
    alert("Calcola prima l'analisi in fase!");
    return;
  }
  
  const P = state.lastPeriod;
  const shift = state.phaseShift;
  
  // Header con metadati
  let csv = `# Lightcurve Folded Data\n`;
  csv += `# Period: ${P.toFixed(8)} days\n`;
  csv += `# Phase Shift: ${shift.toFixed(6)}\n`;
  
  // Statistiche se disponibili
  const stats = calculatePhaseStatistics();
  if (stats) {
    csv += `# RMS: ${stats.rms.toFixed(6)} mag\n`;
    csv += `# Chi-squared (reduced): ${stats.reducedChiSq.toFixed(4)}\n`;
    csv += `# Phase Coverage: ${(stats.coverage * 100).toFixed(1)}%\n`;
  }
  
  csv += `#\n`;
  csv += "session_id,session_name,jd,mag,phase\n";
  
  for (let i = 0; i < state.n; i++) {
    if (state.activePoint[i] === 0) continue;
    const sid = state.session[i];
    if (!state.activeSession.get(sid)) continue;
    
    const jd = state.jd[i];
    const mag = (state.mag[i] - detrendValue(sid, jd)) + getTotalOffset(sid);
    const jd0 = state.epoch || state.jd[0];
    let phase = (((jd - jd0) / P) + shift) % 1.0;
    if (phase < 0) phase += 1.0;
    
    // Adatta al range se necessario
    if (state.phaseRange === "-0.5-0.5" && phase > 0.5) {
      phase -= 1.0;
    } else if (state.phaseRange === "-1-1" && phase > 0.5) {
      phase -= 1.0;
    }
    
    csv += `${sid},${nameForSession(sid)},${jd.toFixed(8)},${mag.toFixed(6)},${phase.toFixed(8)}\n`;
  }
  
  downloadFile(csv, `lightcurve_folded_P${P.toFixed(6)}_${timestamp()}.csv`, 'text/csv');
}

// Export PNG paper-ready del grafico in fase
export async function exportPhasePNG() {
  if (!state.lastPeriod) {
    alert("Calcola prima l'analisi in fase!");
    return;
  }

  const gd = document.getElementById("plotPhase");

  // ✅ CORREZIONE: Esporta esattamente il grafico come appare a video
  // NON modifichiamo il layout per evitare re-rendering
  // Il grafico già ha titolo e legenda corretti dalla funzione di render

  // Configurazione export ad alta qualità
  const opts = {
    format: 'png',
    width: 1200,
    height: 800,
    scale: 2  // 2x per migliore qualità (2400x1600px = DPI 200)
  };

  try {
    // Esporta il grafico esattamente come visualizzato
    const imgData = await Plotly.toImage(gd, opts);

    // Download
    const a = document.createElement('a');
    a.href = imgData;
    a.download = `phase_diagram_P${state.lastPeriod.toFixed(6)}_${timestamp()}.png`;
    a.click();

    console.log('✅ PNG esportato: grafico identico a quello visualizzato');
  } catch (error) {
    console.error('❌ Errore export PNG:', error);
    alert('Errore durante l\'export del PNG. Controlla la console.');
  }
}

// Helper: download file
function downloadFile(content, filename, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// Helper: timestamp per filename
function timestamp() {
  return new Date().toISOString().slice(0, 19).replace(/:/g, '-').replace('T', '_');
}
//main.js
import {
  state,
  rebuildDefaults,
  nameForSession,
  colorForSession,
  getSampledIndices,           // ✅ NUOVO
  setActiveSamplingPercent,    // ✅ NUOVO
  invalidateSamplingCache,     // ✅ NUOVO
  activeSamplingPercent        // ✅ NUOVO
} from './state.js';
import { unpackActiveBitsetFromBase64, packActiveBitsetToBase64 } from '../common/utils-arrow.js';
import { computeDetrendCoefficients } from './math-logic.js';
import { drawLightcurve, computePeriodogram } from './plots.js';
import { renderSessionList, updateCounters, recalculateAllSliderRanges } from './session-ui.js';
import { renderPeriodPeaks } from './period-ui.js';
import { loadDataArrow } from './data-loader.js';
import { exportDetrendedCSV, exportFoldedCSV, exportPhasePNG } from './export-utils.js';
import { computeHarmonics } from './harmonics-analysis.js';
import { computeOC } from './oc-analysis.js';
import { getCurrentLCRange } from './plots.js';
import {
  alignSessionsByPhaseMedian,
  alignSessionsZeroPoint
} from "./math-logic.js";
import { HistoryTracker } from './history-tracker.js';
import { initializePhaseControls, goToPhaseTabAndUpdate } from './phase-controls.js';
import { computeExtremaPerSession } from './extrema-analysis.js';
import { initAIAdvisor } from './ai-advisor.js';
import { initVariabilityComparison } from './variability-comparison.js';
import { initSupportAnalysis, loadSupportData } from './support-analysis.js';
import { initSlackExportButtons } from './slack-export.js';
import { initCatalogs } from './catalogs.js';
import { initImportCatalogs } from './import_catalogs.js';


// ============================================
// WIRING EVENT HANDLERS
// ============================================
document.getElementById("load").onclick = loadDataArrow;

// ============================================
// SINCRONIZZAZIONE PERIODO TRA ANALISI IN FASE E SUPPORTO
// ============================================
// Quando l'utente cambia il periodo nel campo chosenP,
// aggiorna automaticamente il display info-period nel tab Supporto
const chosenPInput = document.getElementById("chosenP");
if (chosenPInput) {
  chosenPInput.addEventListener('change', () => {
    const period = parseFloat(chosenPInput.value);
    const infoPeriodEl = document.getElementById("info-period");

    if (infoPeriodEl && isFinite(period) && period > 0) {
      infoPeriodEl.textContent = `${period.toFixed(6)} d`;
      console.log(`📊 Periodo aggiornato: ${period.toFixed(6)} d`);
    }
  });
}

// ============================================
// AUTO-LOAD PER PROJECT_ID PRECARICATO
// ============================================
// Attesa che il DOM sia completamente caricato
document.addEventListener('DOMContentLoaded', () => {
  const projectIdInput = document.getElementById("projectId");
  if (projectIdInput && projectIdInput.value) {
    // Delay per assicurare che tutti i moduli siano inizializzati
    setTimeout(async () => {
      console.log('🔄 Auto-caricamento dati per project_id:', projectIdInput.value);
      const loadingIndicator = document.getElementById("autoLoadingIndicator");
      if (loadingIndicator) loadingIndicator.style.display = "block";

      // Nascondi il bottone "Carica dati progetto" poiché il caricamento è automatico
      const loadButton = document.getElementById("load");
      if (loadButton) {
        loadButton.style.display = "none";
      }

      // Chiama direttamente loadDataArrow (il gestore è già stato associato sopra)
      if (loadButton && loadButton.onclick) {
        loadButton.click();
      } else {
        console.warn('❌ Bottone load non trovato o gestore non associato');
        const errorDiv = document.getElementById("autoLoadError");
        if (errorDiv) {
          errorDiv.innerHTML = '❌ Errore: bottone caricamento non trovato';
          errorDiv.style.display = "block";
        }
        if (loadingIndicator) loadingIndicator.style.display = "none";
      }

      // Carica periodo dal progetto se disponibile
      const projectPeriodInput = document.getElementById("projectPeriod");
      if (projectPeriodInput && projectPeriodInput.value) {
        const periodValue = parseFloat(projectPeriodInput.value);
        if (isFinite(periodValue) && periodValue > 0) {
          document.getElementById("chosenP").value = periodValue.toFixed(6);
          console.log(`📊 Periodo caricato dal progetto: ${periodValue.toFixed(6)} giorni`);
        }
      }

      // Carica dati analisi di supporto
      try {
        await loadSupportData(parseInt(projectIdInput.value));
        console.log('✅ Dati analisi di supporto caricati');
      } catch (error) {
        console.warn('⚠️ Errore caricamento dati supporto:', error);
      }

      // Inizializza bottoni export Slack
      initSlackExportButtons();
      console.log('✅ Bottoni Slack export inizializzati');
    }, 100); // Piccolo delay per assicurare inizializzazione moduli
  } else {
    // Anche se no project_id, inizializza i bottoni Slack
    initSlackExportButtons();
  }
});

// ✅ Ricalcola ampiezza manuale con sigma clipping
// Usa event delegation perché il bottone è aggiunto dinamicamente
document.getElementById("phaseStats").addEventListener('click', (e) => {
  if (e.target.id === 'recalcSliderRanges' || e.target.closest('#recalcSliderRanges')) {
    const btn = document.getElementById("recalcSliderRanges");
    if (!btn) return;

    // Ricalcola ampiezza manuale e range slider
    const updated = recalculateAllSliderRanges();

    if (updated > 0) {
      // Feedback visivo
      btn.classList.add('success');
      btn.innerHTML = `✓ Ampiezza aggiornata`;

      setTimeout(() => {
        btn.classList.remove('success');
        btn.innerHTML = '⟲ Ricalcola';
      }, 2000);

      HistoryTracker.record('recalc_manual_amplitude', {
        sessions_updated: updated
      });
    } else {
      // Errore
      btn.innerHTML = `⚠ Errore`;
      setTimeout(() => {
        btn.innerHTML = '⟲ Ricalcola';
      }, 2000);
    }
  }
});

// removeSelected handler è alla fine del file (versione combinata sigma+manuale)
document.getElementById("restoreAll").onclick = async () => {
  // Pulisci anche sigma clipping
  state.sigmaClipSuggested.clear();
  state.selectedRaw.clear();
  const resultsDiv = document.getElementById("sigmaClipResults");
  const infoDiv = document.getElementById("sigmaClipInfo");
  if (resultsDiv) resultsDiv.style.display = 'none';
  if (infoDiv) infoDiv.innerHTML = '';

  invalidateSamplingCache();
  rebuildDefaults();
  renderSessionList();
  drawLightcurve();
  updateCounters();

  // Ricalcola estremi
  try {
    await computeExtremaPerSession();
    renderSessionList();
    console.log('✅ Estremi ricalcolati dopo restore');
  } catch (error) {
    console.warn('⚠️ Errore ricalcolo estremi:', error);
  }

  HistoryTracker.record('restore_all', {
    points_restored: state.n
  });
};
document.getElementById("computeP").onclick = async () => {
  const enablePrewhitening = document.getElementById("enablePrewhitening")?.checked || false;
  const peaks = await computePeriodogram(goToPhaseTabAndUpdate);

  // ✅ Solo se NON è multi-periodo, usa il rendering standard
  if (!enablePrewhitening) {
    renderPeriodPeaks(peaks, goToPhaseTabAndUpdate);
  }
  // Altrimenti renderMultiPeriodTable è già stato chiamato dentro computePeriodogram

  if (peaks && peaks.length > 0) {
    HistoryTracker.record('compute_period', {
      min_period: parseFloat(document.getElementById('minP')?.value || 0.02),
      max_period: parseFloat(document.getElementById('maxP')?.value || 10),
      n_freq: parseInt(document.getElementById('nFreq')?.value || 6000),
      best_period: peaks[0]?.period?.toFixed(6),
      n_peaks: peaks.length
    });
  }
};

// VISTA COMPATTA
document.getElementById("compactView")?.addEventListener("change", () => {
  drawLightcurve();
});

// Export scientifico
document.getElementById("exportDetrended").onclick = () => {
  exportDetrendedCSV();
  document.getElementById("exportMsg").textContent = "CSV Detrended esportato ✅";
  setTimeout(() => document.getElementById("exportMsg").textContent = "", 3000);
};

document.getElementById("exportFolded").onclick = () => {
  exportFoldedCSV();
  document.getElementById("exportMsg").textContent = "CSV Folded esportato ✅";
  setTimeout(() => document.getElementById("exportMsg").textContent = "", 3000);
};

document.getElementById("exportPhasePNG").onclick = async () => {
  await exportPhasePNG();
  document.getElementById("exportMsg").textContent = "PNG esportato ✅";
  setTimeout(() => document.getElementById("exportMsg").textContent = "", 3000);
};

// Armoniche (con controllo esistenza)
const harmonicsBtn = document.getElementById("computeHarmonics");
if (harmonicsBtn) {
  harmonicsBtn.onclick = async () => {
    await computeHarmonics();

    HistoryTracker.record('compute_harmonics', {
      period: state.lastPeriod
    });
  };
}

// O-C Diagram (con controllo esistenza)
const ocBtn = document.getElementById("computeOC");
if (ocBtn) {
  ocBtn.onclick = async () => {
    await computeOC();

    HistoryTracker.record('compute_oc', {
      period: state.lastPeriod,
      epoch: parseFloat(document.getElementById('ocEpoch')?.value || state.jd[0])
    });
  };
}

//allienamento sessioni in fase (removed from UI)
const alignSessionsBtn = document.getElementById("alignSessions");
if (alignSessionsBtn) {
  alignSessionsBtn.onclick = () => {
    const P = parseFloat(document.getElementById("chosenP").value);
    if (!isFinite(P) || P <= 0) {
      alert("Imposta prima un periodo valido");
      return;
    }

    alignSessionsByPhaseMedian(P);
    drawLightcurve();
    updateCounters();

    HistoryTracker.record('align_sessions', {
      period: P,
      method: 'phase_median',
      sessions: state.activeSession.size
    });

    console.log("Auto offset:", Object.fromEntries(state.sessionAutoOffset));
  };
}

// Allineamento ZERO-POINT (definitivo) - ORA ASINCRONO!
document.getElementById("alignSessionsZP").onclick = async () => {
  try {
    await alignSessionsZeroPoint();
    // drawLightcurve() e updateCounters() sono già chiamati dentro alignSessionsZeroPoint()

    HistoryTracker.record('align_sessions', {
      method: 'zero_point_astropy',
      sessions: state.activeSession.size
    });
  } catch (error) {
    console.error("Errore durante l'allineamento zero-point:", error);
    // L'errore è già gestito dentro alignSessionsZeroPoint con alert
  }
};

// NUOVO: Allineamento a magnitudine specifica
const alignToMagBtn = document.getElementById("alignToMag");
if (alignToMagBtn) {
  alignToMagBtn.onclick = () => {
    const targetMag = parseFloat(document.getElementById("zeroMagRef").value);
    
    if (!isFinite(targetMag)) {
      alert("Inserisci una magnitudine valida");
      return;
    }
    
    // Funzione inline (non abbiamo alignSessionsToMag in math-logic)
    for (const sid of state.activeSession.keys()) {
      if (!state.activeSession.get(sid)) continue;
      
      // Raccogli magnitudini della sessione
      const mags = [];
      for (let i = 0; i < state.n; i++) {
        if (state.session[i] === sid && state.activePoint[i]) {
          mags.push(state.mag[i]);
        }
      }
      
      if (mags.length === 0) continue;
      
      // Calcola mediana
      mags.sort((a, b) => a - b);
      const median = mags[Math.floor(mags.length / 2)];
      
      // Shift necessario
      const shift = targetMag - median;
      
      // Applica come offset manuale
      const currentManual = state.sessionManualOffset.get(sid) || 0;
      state.sessionManualOffset.set(sid, currentManual + shift);
    }
    
    renderSessionList();
    drawLightcurve();
    updateCounters();
    
    alert(`Sessioni allineate a mag ${targetMag.toFixed(3)}`);
  };
}



// ============================================
// SALVATAGGIO STATO SU DATABASE (MariaDB)
// ============================================
document.getElementById("saveState").onclick = async () => {
  const payload = {
    n: state.n,
    active_bitset_b64: packActiveBitsetToBase64(state.activePoint),
    session_active: Object.fromEntries(state.activeSession),

    // ✅ CORREZIONE: usa i nomi corretti delle mappe
    session_auto_offset: Object.fromEntries(state.sessionAutoOffset),
    session_manual_offset: Object.fromEntries(state.sessionManualOffset),

    session_name: Object.fromEntries(state.sessionName),
    session_color: Object.fromEntries(state.sessionColor),
    detrend: { model: state.detrend.model },
    period: state.lastPeriod,
    phase_shift: state.phaseShift,
    phase_title: state.phaseTitle,
    phase_range: state.phaseRange,
    phase_period_label: state.phasePeriodLabel,

    // ✅ NUOVO: Aggiungi cronologia operazioni (come oggetto, non stringa)
    history: {
      export_date: new Date().toISOString(),
      history: HistoryTracker.history,
      version: '1.0'
    }
  };
  const r = await fetch("/agata/variable-stars/api/state/save", {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify(payload)
  });
  document.getElementById("stateMsg").textContent = (await r.json()).ok ? "Salvato ✅" : "Errore ❌";
};

// ============================================
// CARICAMENTO STATO DA DATABASE (MariaDB)
// ============================================
document.getElementById("loadState").onclick = async () => {
  const r = await fetch("/agata/variable-stars/api/state/load");
  const data = await r.json();
  if (!data.ok || !data.state) {
    document.getElementById("stateMsg").textContent = "Nessuno stato salvato";
    return;
  }
  const s = data.state;
  if (s.n !== state.n) {
    document.getElementById("stateMsg").textContent = "⚠️ Dati incompatibili";
    return;
  }
  
  // Ripristina stato
  state.activePoint = unpackActiveBitsetFromBase64(s.active_bitset_b64, s.n);
  state.activeSession = new Map(Object.entries(s.session_active).map(([k,v])=>[Number(k),v]));
  
  // ✅ CORREZIONE: ripristina entrambe le mappe offset
  state.sessionAutoOffset = new Map(
    Object.entries(s.session_auto_offset || {}).map(([k,v])=>[Number(k),v])
  );
  state.sessionManualOffset = new Map(
    Object.entries(s.session_manual_offset || {}).map(([k,v])=>[Number(k),v])
  );
  
  // Ripristina nomi e colori personalizzati
  if (s.session_name) {
    state.sessionName = new Map(Object.entries(s.session_name).map(([k,v])=>[Number(k),v]));
  }
  if (s.session_color) {
    state.sessionColor = new Map(Object.entries(s.session_color).map(([k,v])=>[Number(k),v]));
  }
  
  state.detrend.model = s.detrend?.model || "linear";
  document.getElementById("detrendModel").value = state.detrend.model;
  
  if (s.period) {
    state.lastPeriod = s.period;
    document.getElementById("chosenP").value = s.period;
  }
  if (s.phase_shift !== undefined) {
    state.phaseShift = s.phase_shift;
    document.getElementById("phaseShift").value = s.phase_shift;
  }
  if (s.phase_title) {
    state.phaseTitle = s.phase_title;
    if (document.getElementById("phaseCustomTitle")) {
      document.getElementById("phaseCustomTitle").value = s.phase_title;
    }
  }
  if (s.phase_range) {
    state.phaseRange = s.phase_range;
    if (document.getElementById("phaseRange")) {
      document.getElementById("phaseRange").value = s.phase_range;
    }
  }
  if (s.phase_period_label !== undefined) {
    state.phasePeriodLabel = s.phase_period_label;
    if (document.getElementById("phasePeriodLabel")) {
      document.getElementById("phasePeriodLabel").value = s.phase_period_label;
    }
  }

  // ✅ NUOVO: Ripristina cronologia operazioni se presente
  if (s.history) {
    try {
      // s.history può essere già un oggetto o una stringa JSON (dipende dal backend)
      const historyData = typeof s.history === 'string' ? JSON.parse(s.history) : s.history;
      if (historyData && historyData.history && Array.isArray(historyData.history)) {
        HistoryTracker.history = historyData.history;
        console.log(`📝 Cronologia ripristinata: ${historyData.history.length} operazioni`);
      }
    } catch (e) {
      console.warn('⚠️ Errore ripristino cronologia:', e);
    }
  }

  computeDetrendCoefficients();
  renderSessionList();
  drawLightcurve();
  updateCounters();

  // ✅ NUOVO: Ricalcola fase se il periodo è presente
  if (s.period) {
    goToPhaseTabAndUpdate(s.period);
  }

  document.getElementById("stateMsg").textContent = "Caricato ✅";
};

// ============================================
// SALVATAGGIO SU FILE JSON
// ============================================
const saveFileBtn = document.getElementById("saveFile");
if (saveFileBtn) {
  saveFileBtn.onclick = () => {
    const kindEl = document.getElementById("kind");
    const seedEl = document.getElementById("seed");
    const sessionsEl = document.getElementById("sessions");

    const fileData = {
      version: "1.0",
      timestamp: new Date().toISOString(),
      metadata: {
        kind: kindEl?.value || "",
        seed: seedEl?.value || "",
        sessions: sessionsEl?.value || ""
      },
    data: {
      n: state.n,
      jd: Array.from(state.jd),
      mag: Array.from(state.mag),
      session: Array.from(state.session),
      point_id: Array.from(state.pid)
    },
    state: {
      active_bitset_b64: packActiveBitsetToBase64(state.activePoint),
      session_active: Object.fromEntries(state.activeSession),
      
      // ✅ CORREZIONE: salva entrambe le mappe offset
      session_auto_offset: Object.fromEntries(state.sessionAutoOffset),
      session_manual_offset: Object.fromEntries(state.sessionManualOffset),
      
      session_name: Object.fromEntries(state.sessionName),
      session_color: Object.fromEntries(state.sessionColor),
      detrend: {
        model: state.detrend.model,
        coeff: Object.fromEntries(
          Array.from(state.detrend.coeff.entries()).map(([k, v]) => [k, v])
        )
      },
      period: state.lastPeriod,
      phase_shift: state.phaseShift,
      phase_title: state.phaseTitle,
      phase_range: state.phaseRange,
      phase_period_label: state.phasePeriodLabel,
      lock_phase_zoom: state.lockPhaseZoom,
      manual_amplitude: state.manualAmplitude,
      epoch: state.epoch
    }
  };
  
  const blob = new Blob([JSON.stringify(fileData, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `lightcurve_${new Date().toISOString().slice(0, 19).replace(/:/g, "-")}.json`;
  a.click();
  URL.revokeObjectURL(url);
  
  document.getElementById("fileMsg").textContent = "Progetto salvato ✅";
  setTimeout(() => { document.getElementById("fileMsg").textContent = ""; }, 3000);
  };
}

// ============================================
// CARICAMENTO DA FILE JSON
// ============================================
document.getElementById("loadFileInput").onchange = async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  
  try {
    const text = await file.text();
    const fileData = JSON.parse(text);
    
    if (!fileData.version) {
      throw new Error("Formato file non valido");
    }
    
    // Carica i dati raw
    state.n = fileData.data.n;
    state.jd = new Float64Array(fileData.data.jd);
    state.mag = new Float32Array(fileData.data.mag);
    state.session = new Int32Array(fileData.data.session);
    state.pid = new Int32Array(fileData.data.point_id);
    
    // Carica lo stato
    const s = fileData.state;
    state.activePoint = unpackActiveBitsetFromBase64(s.active_bitset_b64, state.n);
    state.activeSession = new Map(Object.entries(s.session_active).map(([k,v])=>[Number(k),v]));
    
    // ✅ CORREZIONE: carica entrambe le mappe offset
    state.sessionAutoOffset = new Map(
      Object.entries(s.session_auto_offset || {}).map(([k,v])=>[Number(k),v])
    );
    state.sessionManualOffset = new Map(
      Object.entries(s.session_manual_offset || {}).map(([k,v])=>[Number(k),v])
    );
    
    state.sessionName = new Map(Object.entries(s.session_name || {}).map(([k,v])=>[Number(k),v]));
    state.sessionColor = new Map(Object.entries(s.session_color || {}).map(([k,v])=>[Number(k),v]));
    
    // Detrend
    state.detrend.model = s.detrend.model;
    state.detrend.coeff = new Map(
      Object.entries(s.detrend.coeff || {}).map(([k, v]) => [Number(k), v])
    );
    document.getElementById("detrendModel").value = state.detrend.model;
    
    // Fase
    if (s.period) {
      state.lastPeriod = s.period;
      document.getElementById("chosenP").value = s.period;
    }
    if (s.phase_shift !== undefined) {
      state.phaseShift = s.phase_shift;
      document.getElementById("phaseShift").value = s.phase_shift;
    }
    if (s.phase_title) {
      state.phaseTitle = s.phase_title;
      document.getElementById("phaseCustomTitle").value = s.phase_title;
    }
    if (s.phase_range) {
      state.phaseRange = s.phase_range;
      document.getElementById("phaseRange").value = s.phase_range;
    }
    if (s.phase_period_label !== undefined) {
      state.phasePeriodLabel = s.phase_period_label;
      document.getElementById("phasePeriodLabel").value = s.phase_period_label;
    }

    // Ripristina lock zoom e manualAmplitude
    if (s.lock_phase_zoom !== undefined) {
      state.lockPhaseZoom = s.lock_phase_zoom;
      const lockZoomEl = document.getElementById("lockPhaseZoom");
      if (lockZoomEl) lockZoomEl.checked = s.lock_phase_zoom;
    }
    if (s.manual_amplitude) {
      state.manualAmplitude = s.manual_amplitude;
    }
    if (s.epoch !== undefined) {
      state.epoch = s.epoch;
    }

    // Aggiorna i campi di configurazione se presenti
    if (fileData.metadata) {
      const kindEl = document.getElementById("kind");
      const seedEl = document.getElementById("seed");
      const sessionsEl = document.getElementById("sessions");

      if (kindEl) kindEl.value = fileData.metadata.kind;
      if (seedEl) seedEl.value = fileData.metadata.seed;
      if (sessionsEl) sessionsEl.value = fileData.metadata.sessions;
    }
    
    // Ridisegna tutto
    renderSessionList();
    drawLightcurve();
    updateCounters();

    // Autoscale curva di luce (massimizza al caricamento)
    setTimeout(() => {
      Plotly.relayout("plotLC", {
        'yaxis.autorange': 'reversed',
        'xaxis.autorange': true
      });
    }, 100);

    // Se è presente un periodo, aggiorna la fase e l'Analisi di Supporto
    if (s.period) {
      // ✅ Sincronizza info-period (campo read-only in tab Analisi di Supporto)
      const infoPeriodEl = document.getElementById("info-period");
      if (infoPeriodEl) {
        infoPeriodEl.textContent = `${s.period.toFixed(6)} d`;
      }

      goToPhaseTabAndUpdate(s.period);

      // Assicura che il campo periodo in Analisi di Supporto venga aggiornato
      setTimeout(() => {
        if (typeof window.updateSupportPeriod === 'function') {
          window.updateSupportPeriod(s.period);
        }
      }, 100);
    }

    document.getElementById("fileMsg").textContent = `Caricato: ${file.name} ✅`;
    setTimeout(() => { document.getElementById("fileMsg").textContent = ""; }, 5000);
    
  } catch (error) {
    document.getElementById("fileMsg").textContent = `❌ Errore: ${error.message}`;
    console.error("Errore caricamento file:", error);
  }
  
  e.target.value = "";
};

document.getElementById("recalcDetrend").onclick = async () => {
  computeDetrendCoefficients();
  drawLightcurve();
  updateCounters();

  // Ricalcola estremi (detrend cambia le magnitudini)
  try {
    await computeExtremaPerSession();
    renderSessionList();
    console.log('✅ Estremi ricalcolati dopo detrend');
  } catch (error) {
    console.warn('⚠️ Errore ricalcolo estremi:', error);
  }

  HistoryTracker.record('detrend', {
    model: state.detrend.model,
    sessions: state.activeSession.size
  });

  // AUTOSCALE PERFETTO dopo 100ms
  setTimeout(() => {
    Plotly.relayout("plotLC", {
      'yaxis.autorange': 'reversed',
      'xaxis.autorange': true
    });
  }, 100);
};

// ============================================
// SIGMA CLIPPING - SETUP CONTROLLI
// ============================================

// Sync slider e input numerico (bidirezionale)
const sigmaValueSlider = document.getElementById("sigmaValue");
const sigmaNumberInput = document.getElementById("sigmaValueNumber");  // ✅ CORRETTO

if (sigmaValueSlider && sigmaNumberInput) {
  sigmaValueSlider.oninput = (e) => {
    const val = e.target.value;
    sigmaNumberInput.value = val;
    
    // Visual feedback sul colore dello slider
    const slider = e.target;
    const percent = ((val - 1) / 4) * 100;
    
    if (val < 2) {
      slider.style.background = `linear-gradient(to right, #ef4444 0%, #f59e0b ${percent}%, #e5e7eb ${percent}%)`;
    } else if (val < 3.5) {
      slider.style.background = `linear-gradient(to right, #f59e0b 0%, #facc15 ${percent}%, #e5e7eb ${percent}%)`;
    } else {
      slider.style.background = `linear-gradient(to right, #22c55e 0%, #10b981 ${percent}%, #e5e7eb ${percent}%)`;
    }
  };

  sigmaNumberInput.onchange = (e) => {
    const val = parseFloat(e.target.value);
    if (val >= 1 && val <= 5) {
      sigmaValueSlider.value = val;
      // Trigger visual feedback
      sigmaValueSlider.dispatchEvent(new Event('input'));
    } else {
      e.target.value = 3; // Reset a default se fuori range
    }
  };
}

// ============================================
// CONTROLLO DIMENSIONE PUNTI
// ============================================

// Sync slider e input numerico per dimensione marker (bidirezionale)
const markerSizeSlider = document.getElementById("markerSizeSlider");
const markerSizeNumber = document.getElementById("markerSizeNumber");

if (markerSizeSlider && markerSizeNumber) {
  // Quando lo slider cambia, aggiorna il numero E il grafico
  markerSizeSlider.oninput = (e) => {
    const val = parseFloat(e.target.value);
    markerSizeNumber.value = val;
    
    // Aggiorna lo stato
    state.currentMarkerSize = val;
    
    // Ridisegna i grafici
    drawLightcurve(getCurrentLCRange());
    
    // Se c'è un grafico di fase attivo, ridisegnalo
    if (state.lastPeriod) {
      updatePhaseViewFull();
    }
  };

  // Quando il numero cambia, aggiorna lo slider E il grafico
  markerSizeNumber.onchange = (e) => {
    const val = parseFloat(e.target.value);
    if (val >= 1 && val <= 15) {
      markerSizeSlider.value = val;
      state.currentMarkerSize = val;
      
      // Ridisegna i grafici
      drawLightcurve(getCurrentLCRange());
      
      // Se c'è un grafico di fase attivo, ridisegnalo
      if (state.lastPeriod) {
        updatePhaseViewFull();
      }
    } else {
      // Reset a default se fuori range
      e.target.value = 3;
      markerSizeSlider.value = 3;
      state.currentMarkerSize = 3;
    }
  };
}

// ============================================
// CALCOLA E EVIDENZIA OUTLIER (PER SESSIONE)
// ============================================

const highlightSigmaClipBtn = document.getElementById("highlightSigmaClip");
if (highlightSigmaClipBtn) {
  highlightSigmaClipBtn.onclick = async () => {
    const sigma = parseFloat(document.getElementById("sigmaValue").value);
    const infoDiv = document.getElementById("sigmaClipInfo");
    const resultsDiv = document.getElementById("sigmaClipResults");
    const button = highlightSigmaClipBtn;
    
    // FEEDBACK IMMEDIATO
    button.disabled = true;
    button.style.opacity = "0.6";
    button.innerHTML = '⏳ Calcolo in corso...';
    infoDiv.innerHTML = '<span style="color: #3b82f6;">🔄 Analizzando sessioni...</span>';
    resultsDiv.style.display = 'none';
    
    try {
      // Prepara dati attivi
      const activeData = [];
      for (let i = 0; i < state.n; i++) {
        if (state.activePoint[i] === 1 && state.activeSession.get(state.session[i])) {
          activeData.push({
            index: i,
            jd: state.jd[i],
            mag: state.mag[i],
            session_id: state.session[i]
          });
        }
      }
      
      if (activeData.length === 0) {
        throw new Error("Nessun punto attivo da analizzare");
      }
      
      // COSTRUISCI ARROW STREAM
      const jd64 = new Float64Array(activeData.map(d => d.jd));
      const mag32 = new Float32Array(activeData.map(d => d.mag));
      const sid32 = new Int32Array(activeData.map(d => d.session_id));
      
      const tbl = window.Arrow.tableFromArrays({ 
        jd: jd64, 
        mag: mag32,
        session_id: sid32
      });
      const arrowStream = window.Arrow.tableToIPC(tbl, "stream");
      
      // CHIAMATA API
      const res = await fetch(`/agata/variable-stars/api/sigma_clip.arrow?sigma=${sigma}`, {
        method: "POST",
        body: arrowStream
      });
      
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }
      
      const result = await res.json();
      
      // AGGIORNA STATE
      state.sigmaClipSuggested.clear();
      
      // Mappa indici dalla risposta agli indici originali
      for (const apiIndex of result.outlier_indices) {
        const originalIndex = activeData[apiIndex].index;
        state.sigmaClipSuggested.add(originalIndex);
      }
      
      // MOSTRA RISULTATI DETTAGLIATI PER SESSIONE
      if (result.n_outliers_total === 0) {
        infoDiv.innerHTML = `<span style="color: #22c55e;">✅ Nessun outlier trovato con σ=${sigma}</span>`;
        resultsDiv.style.display = 'none';
      } else {
        infoDiv.innerHTML = `<span style="color: #ef4444; font-size: 13px;">⚠️ Trovati <strong>${result.n_outliers_total}</strong> outlier in <strong>${Object.keys(result.session_stats).length}</strong> sessioni</span>`;
        
        // Render dettagli per sessione
        let html = '<div style="max-height: 300px; overflow-y: auto;">';
        html += `<div style="font-weight: 700; margin-bottom: 8px; padding-bottom: 6px; border-bottom: 2px solid #10b981;">📊 Dettaglio per Sessione (σ=${sigma})</div>`;
        
        for (const [sid, stats] of Object.entries(result.session_stats)) {
          const sessionName = nameForSession(parseInt(sid));
          const sessionColor = colorForSession(parseInt(sid));
          
          // Sessione analizzata
          const outlierColor = stats.n_outliers > 0 ? '#ef4444' : '#22c55e';
          const outlierIcon = stats.n_outliers > 0 ? '⚠️' : '✓';
          
          html += `
            <div style="padding: 8px; margin-bottom: 6px; background: ${stats.n_outliers > 0 ? '#fee2e2' : '#f0fdf4'}; border-radius: 4px; border-left: 3px solid ${outlierColor};">
              <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 4px;">
                <span style="width: 10px; height: 10px; background: ${sessionColor}; border-radius: 50%;"></span>
                <strong>${sessionName}</strong>
                <span style="margin-left: auto; color: ${outlierColor}; font-weight: 700;">${outlierIcon} ${stats.n_outliers}/${stats.n_total}</span>
              </div>
              
              <div style="font-size: 10px; line-height: 1.4; color: #374151;">
                <strong>Mediana:</strong> ${stats.median.toFixed(3)} mag<br>
                <strong>σ equiv:</strong> ${stats.sigma_equiv.toFixed(4)} mag<br>
                <strong>Range:</strong> [${stats.bounds[0].toFixed(3)}, ${stats.bounds[1].toFixed(3)}]<br>
                <strong>% outlier:</strong> ${stats.outlier_percentage.toFixed(1)}%
              </div>
            </div>
          `;
        }
        
        html += '</div>';
        
        resultsDiv.innerHTML = html;
        resultsDiv.style.display = 'block';
      }
      
      // RIDISEGNA GRAFICO CON EVIDENZIAZIONE
      drawLightcurve();
      updateCounters();

      HistoryTracker.record('sigma_clip', {
        sigma: sigma,
        outliers_found: result.n_outliers_total,
        sessions_analyzed: Object.keys(result.session_stats).length,
        percentage: (result.n_outliers_total / activeData.length * 100).toFixed(2)
      });
      
      // ANIMAZIONE SUCCESS
      button.style.animation = 'pulse 0.5s ease-in-out';
      setTimeout(() => {
        button.style.animation = '';
      }, 500);
      
    } catch (error) {
      console.error("Errore sigma clipping:", error);
      infoDiv.innerHTML = `<span style="color: #ef4444;">❌ Errore: ${error.message}</span>`;
      resultsDiv.style.display = 'none';
    } finally {
      // RIPRISTINA BOTTONE
      button.disabled = false;
      button.style.opacity = "1";
      button.innerHTML = '🔍 Evidenzia Outlier';
    }
  };
}

// ============================================
// RIMOZIONE PUNTI (COMBINATA)
// ============================================

const removeSelectedBtn = document.getElementById("removeSelected");
if (removeSelectedBtn) {
  // Sovrascrivi handler esistente
  removeSelectedBtn.onclick = async () => {
    const range = getCurrentLCRange();

    // UNISCI selezione manuale + sigma clipping
    const allToRemove = new Set([...state.selectedRaw, ...state.sigmaClipSuggested]);

    if (allToRemove.size === 0) {
      const infoDiv = document.getElementById("sigmaClipInfo");
      if (infoDiv) {
        infoDiv.innerHTML = '<span style="color: #f59e0b;">⚠️ Nessun punto selezionato</span>';
        setTimeout(() => {
          infoDiv.innerHTML = '';
        }, 2500);
      }
      return;
    }

    // CONTEGGIO DETTAGLIATO
    const nManual = state.selectedRaw.size;
    const nSigma = state.sigmaClipSuggested.size;
    const nOverlap = [...state.selectedRaw].filter(i => state.sigmaClipSuggested.has(i)).length;
    const nUnique = allToRemove.size;

    // RIMUOVI TUTTI
    for (const idx of allToRemove) {
      state.activePoint[idx] = 0;
    }

    // FEEDBACK DETTAGLIATO
    const infoDiv = document.getElementById("sigmaClipInfo");
    if (infoDiv) {
      let feedbackMsg = `<span style="color: #22c55e; font-weight: 700;">✓ Rimossi ${nUnique} punti</span>`;

      if (nManual > 0 && nSigma > 0) {
        feedbackMsg += `<br><span style="font-size: 11px;">(${nSigma} σ-clip + ${nManual} manuali`;
        if (nOverlap > 0) {
          feedbackMsg += `, ${nOverlap} in comune`;
        }
        feedbackMsg += `)</span>`;
      }

      infoDiv.innerHTML = feedbackMsg;
      setTimeout(() => {
        infoDiv.innerHTML = '';
      }, 4000);
    }

    // NASCONDI RISULTATI SIGMA
    const resultsDiv = document.getElementById("sigmaClipResults");
    if (resultsDiv) {
      resultsDiv.style.display = 'none';
    }

    // PULISCI SELEZIONI
    state.selectedRaw.clear();
    state.sigmaClipSuggested.clear();

    // RICALCOLA E RIDISEGNA
    invalidateSamplingCache();
    computeDetrendCoefficients();
    drawLightcurve();
    updateCounters();

    // Ricalcola estremi (rimossi punti)
    try {
      await computeExtremaPerSession();
      renderSessionList();
      console.log('✅ Estremi ricalcolati dopo rimozione punti');
    } catch (error) {
      console.warn('⚠️ Errore ricalcolo estremi:', error);
    }

    HistoryTracker.record('remove_points', {
      count: nUnique,
      manual_selection: nManual,
      sigma_clip: nSigma,
      overlap: nOverlap
    });
  };
}

function updateHistoryUI() {
  HistoryTracker.renderToHTML('#historyPanel');
}

// Listener per auto-update
document.addEventListener('historyUpdate', () => {
  updateHistoryUI();
});

// Export button
document.getElementById('exportHistory').onclick = () => {
  const json = HistoryTracker.exportJSON();
  
  // Download come file
  const blob = new Blob([json], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `aaaat_history_${Date.now()}.json`;
  a.click();
};

// Clear button
document.getElementById('clearHistory').onclick = () => {
  if (confirm('Cancellare cronologia?')) {
    HistoryTracker.clear();
    updateHistoryUI();
  }
};

// ============================================
// INIZIALIZZAZIONE CONTROLLI FASE
// ============================================
// Inizializza tutti gli handler per i controlli fase
// (shift, template, fine-tuning periodo, delta-P, sampling)
initializePhaseControls();

// ============================================
// INIZIALIZZAZIONE AI ADVISOR
// ============================================
initAIAdvisor();

// ============================================
// INIZIALIZZAZIONE VARIABILITY COMPARISON
// ============================================
initVariabilityComparison();

// ============================================
// INIZIALIZZAZIONE CATALOGS TAB
// ============================================
initCatalogs();

// ============================================
// INIZIALIZZAZIONE IMPORT CATALOGS TAB
// ============================================
initImportCatalogs();

// ============================================
// INIZIALIZZAZIONE SUPPORT ANALYSIS
// ============================================
initSupportAnalysis();

// ============================================
// AUTO-LOAD DA URL PARAMETER (gaia_id)
// ============================================
/**
 * Se l'URL contiene ?gaia_id=XXXXX, carica automaticamente la stella
 * Utile per link diretti dall'interfaccia admin
 */
(function autoLoadFromUrlParam() {
  const urlParams = new URLSearchParams(window.location.search);
  const gaiaIdFromUrl = urlParams.get('gaia_id');

  if (gaiaIdFromUrl) {
    console.log(`🚀 Auto-load da URL: gaia_id=${gaiaIdFromUrl}`);

    // La template initialization ha già impostato correttamente:
    // - dataSource a "db" (se gaia_id è presente)
    // - pre-riempito il gaiaId input
    // - mostrato il gaiaBlock
    // Non sovrascrivere le impostazioni del template!

    // Attendi che il DOM sia completamente caricato e poi carica i dati
    // Usiamo setTimeout per assicurarci che tutti gli altri listener siano pronti
    setTimeout(async () => {
      try {
        console.log(`📊 Caricamento automatico stella ${gaiaIdFromUrl}...`);
        await loadDataArrow();
        console.log(`✅ Stella ${gaiaIdFromUrl} caricata con successo`);
      } catch (error) {
        console.error(`❌ Errore caricamento automatico:`, error);
      }
    }, 500);
  }
})();

// ============================================
// EXPORT GLOBALE DELLO STATE
// ============================================
// Esponi lo state globalmente per i moduli che ne hanno bisogno
window.phaseAnalysisState = state;

// Export vuoto - main.js è un modulo che non esporta funzioni, solo inizializza
export {};

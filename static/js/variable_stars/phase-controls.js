/**
 * phase-controls.js - Gestione Controlli UI per Analisi in Fase
 *
 * Questo modulo gestisce tutti gli event handler e la logica UI
 * per i controlli relativi all'analisi in fase:
 *
 * - Phase shift (slider con preview throttled)
 * - Template overlay
 * - Fine-tuning periodo (slider, ±, ×2, ÷2)
 * - Confronto periodi (ΔP)
 * - Calcolo finale 100%
 * - Sampling intelligente
 *
 * DIPENDENZE:
 * - state.js: stato globale
 * - phase-analysis.js: computePhase(), computePhasePreviewOnly()
 * - phase-statistics.js: calculatePhaseStatistics(), renderPhaseStatistics()
 * - phase-delta.js: computePhaseDelta(), renderPhaseDelta()
 * - ephemeris.js: renderEphemeris()
 * - harmonics-analysis.js: syncHarmonicsPeriod()
 * - oc-analysis.js: syncOCPeriod()
 */

import { state, setActiveSamplingPercent } from './state.js';
import { computePhase, computePhasePreviewOnly } from './phase-analysis.js';
import { calculatePhaseStatistics, renderPhaseStatistics, overlayTemplate } from './phase-statistics.js';
import { renderEphemeris } from './ephemeris.js';
import { computePhaseDelta, renderPhaseDelta } from './phase-delta.js';
import { syncHarmonicsPeriod } from './harmonics-analysis.js';
import { syncOCPeriod } from './oc-analysis.js';

// =============================================================================
// UTILITÀ INTERNE
// =============================================================================

/**
 * Update completo: fase + statistiche + effemeridi (solo se visibili)
 * Usa questa quando serve ricalcolo completo
 */
function updatePhaseViewFull() {
  computePhase();
  const stats = calculatePhaseStatistics();
  state.phaseStats = stats;  // ✅ Salva statistiche in state per uso esterno (es: ricerca VSX)
  renderPhaseStatistics(stats);
  // Le effemeridi vengono aggiornate solo se visibili
  updateEphemerisIfVisible();
}

/**
 * Salta al tab fase e aggiorna tutto
 * @param {number} period - Periodo da impostare
 */
export function goToPhaseTabAndUpdate(period) {
  document.getElementById("chosenP").value = period;

  // ✅ RESET fine-tuning quando periodo cambia da fonte esterna
  resetPeriodFineTuning();

  // ✅ Aggiorna periodo in analisi di supporto
  if (typeof window.updateSupportPeriod === 'function') {
    window.updateSupportPeriod(period);
  }

  const phaseBtn = document.querySelector('.tab-btn[onclick*="tab-phase"]');
  if (phaseBtn) phaseBtn.click();

  requestAnimationFrame(() => {
    computePhase();
    Plotly.Plots.resize("plotPhase");

    // Calcola e mostra statistiche
    const stats = calculatePhaseStatistics();
    renderPhaseStatistics(stats);

    // Sincronizza periodo con altri tab
    syncHarmonicsPeriod();
    syncOCPeriod();
  });
}

// =============================================================================
// PHASE SHIFT SLIDER (con preview throttled)
// =============================================================================

/**
 * Setup handler per phase shift slider
 * - Durante drag: preview veloce (throttled a 60fps)
 * - Al rilascio: full update con statistiche
 */
export function setupPhaseShiftControls() {
  const phaseShiftSlider = document.getElementById("phaseShift");
  if (!phaseShiftSlider) return;

  let rafPending = false;

  // Preview durante drag (throttled)
  phaseShiftSlider.addEventListener("input", () => {
    if (rafPending) return;
    rafPending = true;

    requestAnimationFrame(() => {
      rafPending = false;
      computePhasePreviewOnly();
    });
  });

  // Full update al rilascio
  phaseShiftSlider.addEventListener("change", () => {
    updatePhaseViewFull();
  });

  console.log('✓ Phase shift controls initialized');
}

// =============================================================================
// CONTROLLI FASE (titolo, range, etichetta periodo)
// =============================================================================

/**
 * Setup handler per altri controlli fase
 */
export function setupPhaseDisplayControls() {
  const computePhaseBtn = document.getElementById("computePhase");
  const phaseCustomTitle = document.getElementById("phaseCustomTitle");
  const phaseRange = document.getElementById("phaseRange");
  const phasePeriodLabel = document.getElementById("phasePeriodLabel");
  const centerOnMinMax = document.getElementById("centerOnMinMax");
  const phaseShiftSlider = document.getElementById("phaseShift");
  const lockPhaseZoom = document.getElementById("lockPhaseZoom");

  if (computePhaseBtn) {
    computePhaseBtn.onclick = updatePhaseViewFull;
  }

  if (phaseCustomTitle) {
    phaseCustomTitle.addEventListener('change', updatePhaseViewFull);
  }

  if (phaseRange) {
    phaseRange.addEventListener('change', updatePhaseViewFull);
  }

  if (phasePeriodLabel) {
    phasePeriodLabel.addEventListener('change', updatePhaseViewFull);
  }

  // Handler per blocco zoom
  if (lockPhaseZoom) {
    lockPhaseZoom.addEventListener('change', (e) => {
      state.lockPhaseZoom = e.target.checked;

      if (state.lockPhaseZoom) {
        // Quando attiviamo il blocco, salva il range corrente
        const plotDiv = document.getElementById("plotPhase");
        if (plotDiv && plotDiv.layout && plotDiv.layout.yaxis && plotDiv.layout.yaxis.range) {
          state.savedPhaseRange = {
            yaxis: [...plotDiv.layout.yaxis.range]
          };
          console.log('🔒 Blocco zoom attivato. Range salvato:', state.savedPhaseRange.yaxis);
        }
      } else {
        // Quando disattiviamo, reset del range salvato
        state.savedPhaseRange = null;
        console.log('🔓 Blocco zoom disattivato. Autoscale ripristinato.');
      }
    });
  }

  // Handler per centratura automatica su min/max
  if (centerOnMinMax && phaseShiftSlider) {
    centerOnMinMax.addEventListener('change', (e) => {
      const mode = e.target.value;

      if (mode === '' || !state.lastPeriod || state.n === 0) {
        console.log('⚠️ Centra min/max: dati non disponibili');
        return;
      }

      const P = state.lastPeriod;
      const epoch = state.epoch || state.jd[0];
      const currentShift = parseFloat(phaseShiftSlider.value) || 0;

      console.log(`🎯 Centra su ${mode}: P=${P.toFixed(6)}, epoch=${epoch.toFixed(4)}, shift=${currentShift.toFixed(3)}`);

      // Calcola tutte le fasi e magnitudini dei punti attivi
      const phaseMagPairs = [];
      for (let i = 0; i < state.n; i++) {
        if (state.activePoint[i] === 0 || !state.activeSession.get(state.session[i])) continue;

        let phase = (((state.jd[i] - epoch) / P) + currentShift) % 1.0;
        if (phase < 0) phase += 1.0;

        const mag = state.mag[i];
        phaseMagPairs.push({ phase, mag });
      }

      if (phaseMagPairs.length === 0) {
        console.warn('⚠️ Nessun punto attivo per centratura');
        return;
      }

      // Trova min o max
      let targetPhase = 0;
      if (mode === 'min') {
        // Trova il punto con magnitudine massima (minimo di luminosità)
        const maxMag = Math.max(...phaseMagPairs.map(p => p.mag));
        const minPoint = phaseMagPairs.find(p => p.mag === maxMag);
        targetPhase = minPoint ? minPoint.phase : 0;
        console.log(`📍 Minimo trovato: mag=${maxMag.toFixed(3)}, fase=${targetPhase.toFixed(3)}`);
      } else if (mode === 'max') {
        // Trova il punto con magnitudine minima (massimo di luminosità)
        const minMag = Math.min(...phaseMagPairs.map(p => p.mag));
        const maxPoint = phaseMagPairs.find(p => p.mag === minMag);
        targetPhase = maxPoint ? maxPoint.phase : 0;
        console.log(`📍 Massimo trovato: mag=${minMag.toFixed(3)}, fase=${targetPhase.toFixed(3)}`);
      }

      // Calcola lo shift necessario per portare il target a fase 0
      // Normalizza tra 0 e 1
      let newShift = currentShift - targetPhase;
      while (newShift < 0) newShift += 1;
      while (newShift >= 1) newShift -= 1;

      console.log(`🔄 Nuovo shift: ${newShift.toFixed(3)}`);

      // Aggiorna lo slider
      phaseShiftSlider.value = newShift;

      // Aggiorna la vista
      updatePhaseViewFull();

      // Reset la selezione dopo l'applicazione
      setTimeout(() => {
        centerOnMinMax.value = '';
      }, 100);
    });
  }

  console.log('✓ Phase display controls initialized');
}

// =============================================================================
// TOGGLE EFFEMERIDI
// =============================================================================

/**
 * Aggiorna le effemeridi solo se sono visibili
 */
export function updateEphemerisIfVisible() {
  const ephemerisTable = document.getElementById("ephemerisTable");

  if (ephemerisTable && ephemerisTable.style.display !== 'none') {
    renderEphemeris();
  }
}

/**
 * Setup handler per toggle effemeridi
 */
export function setupEphemerisToggle() {
  const toggleBtn = document.getElementById("toggleEphemeris");
  const ephemerisTable = document.getElementById("ephemerisTable");

  if (toggleBtn && ephemerisTable) {
    toggleBtn.addEventListener('click', () => {
      const isVisible = ephemerisTable.style.display !== 'none';

      if (isVisible) {
        // Nascondi
        ephemerisTable.style.display = 'none';
        toggleBtn.textContent = 'Mostra';
      } else {
        // Mostra e calcola
        ephemerisTable.style.display = 'block';
        toggleBtn.textContent = 'Nascondi';
        renderEphemeris();
      }
    });
  }

  console.log('✓ Ephemeris toggle initialized');
}

// =============================================================================
// TEMPLATE OVERLAY
// =============================================================================

/**
 * Setup handler per template overlay
 */
export function setupTemplateControls() {
  const overlayTemplateBtn = document.getElementById("overlayTemplate");
  const templateSelect = document.getElementById("templateSelect");

  if (overlayTemplateBtn) {
    overlayTemplateBtn.addEventListener('click', () => {
      const templateKey = templateSelect.value;

      if (templateKey === "none") {
        // Rimuovi template e ricalcola solo fase
        computePhase();
        const stats = calculatePhaseStatistics();
        renderPhaseStatistics(stats);
      } else {
        // Applica template
        overlayTemplate(templateKey);
      }
    });
  }

  // Auto-reset template quando si cambia selezione
  if (templateSelect) {
    templateSelect.addEventListener('change', (e) => {
      if (e.target.value === "none") {
        // Reset: ridisegna senza template
        computePhase();
        const stats = calculatePhaseStatistics();
        renderPhaseStatistics(stats);
      }
    });
  }

  console.log('✓ Template overlay controls initialized');
}

// =============================================================================
// MOLTIPLICATORI PERIODO (×2, ÷2)
// =============================================================================

/**
 * Setup handler per raddoppio/dimezzamento periodo
 */
export function setupPeriodMultiplierControls() {
  const doublePeriodBtn = document.getElementById("doublePeriod");
  const halfPeriodBtn = document.getElementById("halfPeriod");

  if (doublePeriodBtn) {
    doublePeriodBtn.onclick = () => {
      const P = parseFloat(document.getElementById("chosenP").value);
      if (P && P > 0) {
        document.getElementById("chosenP").value = (P * 2).toFixed(6);

        // ✅ RESET reference per fine-tuning (funzione globale)
        resetPeriodFineTuning();

        updatePhaseViewFull();
      }
    };
  }

  if (halfPeriodBtn) {
    halfPeriodBtn.onclick = () => {
      const P = parseFloat(document.getElementById("chosenP").value);
      if (P && P > 0) {
        document.getElementById("chosenP").value = (P / 2).toFixed(6);

        // ✅ RESET reference per fine-tuning (funzione globale)
        resetPeriodFineTuning();

        updatePhaseViewFull();
      }
    };
  }

  console.log('✓ Period multiplier controls initialized');
}

// =============================================================================
// FINE-TUNING PERIODO (slider ±)
// =============================================================================

// ✅ FIX: Periodo di riferimento GLOBALE (accessibile da tutti i controlli)
let referencePeriod = null;

/**
 * Resetta lo stato del fine-tuning periodo
 * Chiamare ogni volta che il periodo cambia da fonte esterna
 */
export function resetPeriodFineTuning() {
  const periodSlider = document.getElementById("periodSlider");
  if (periodSlider) {
    periodSlider.value = 0;
  }
  referencePeriod = null;
}

/**
 * Setup handler per fine-tuning periodo con slider
 */
export function setupPeriodFineTuningControls() {
  const periodSlider = document.getElementById("periodSlider");
  const periodDeltaInput = document.getElementById("periodDelta");
  const periodPlusBtn = document.getElementById("periodPlus");
  const periodMinusBtn = document.getElementById("periodMinus");
  const periodPlusBigBtn = document.getElementById("periodPlusBig");
  const periodMinusBigBtn = document.getElementById("periodMinusBig");
  const periodResetBtn = document.getElementById("periodReset");
  const chosenPInput = document.getElementById("chosenP");

  if (!periodSlider || !chosenPInput) return;

  /**
   * Applica offset al periodo
   */
  function applyPeriodOffset(offset) {
    if (!referencePeriod) {
      referencePeriod = parseFloat(chosenPInput.value) || 0;
    }

    const deltaP = parseFloat(periodDeltaInput.value) || 0.0001;
    const newPeriod = referencePeriod + (offset * deltaP);

    if (newPeriod > 0) {
      chosenPInput.value = newPeriod.toFixed(7);

      // Solo ricalcolo fase (no statistiche durante drag)
      if (state.lastPeriod) {
        computePhase();
      }
    }
  }

  // Slider cambia valore
  periodSlider.oninput = (e) => {
    const offset = parseInt(e.target.value);
    applyPeriodOffset(offset);
  };

  // Reset reference quando torna a 0
  periodSlider.onchange = (e) => {
    if (e.target.value === '0') {
      referencePeriod = null;
    }
  };

  // Bottoni +/- singolo
  if (periodPlusBtn) {
    periodPlusBtn.onclick = () => {
      const current = parseInt(periodSlider.value);
      periodSlider.value = current + 1;
      applyPeriodOffset(current + 1);
    };
  }

  if (periodMinusBtn) {
    periodMinusBtn.onclick = () => {
      const current = parseInt(periodSlider.value);
      periodSlider.value = current - 1;
      applyPeriodOffset(current - 1);
    };
  }

  // Bottoni +/- grande (10×)
  if (periodPlusBigBtn) {
    periodPlusBigBtn.onclick = () => {
      const current = parseInt(periodSlider.value);
      periodSlider.value = current + 10;
      applyPeriodOffset(current + 10);
    };
  }

  if (periodMinusBigBtn) {
    periodMinusBigBtn.onclick = () => {
      const current = parseInt(periodSlider.value);
      periodSlider.value = current - 10;
      applyPeriodOffset(current - 10);
    };
  }

  // Reset slider
  if (periodResetBtn) {
    periodResetBtn.onclick = () => {
      resetPeriodFineTuning();

      // Visual feedback
      periodResetBtn.style.background = '#dbeafe';
      setTimeout(() => {
        periodResetBtn.style.background = '';
      }, 200);
    };
  }

  // Keyboard shortcuts
  setupPeriodKeyboardShortcuts({
    periodMinusBtn,
    periodPlusBtn,
    periodMinusBigBtn,
    periodPlusBigBtn,
    periodResetBtn
  });

  // ✅ FIX: Quando cambia manualmente il periodo (modifica + Enter)
  chosenPInput.addEventListener('change', () => {
    // Reset completo dello stato fine-tuning
    resetPeriodFineTuning();

    // Aggiorna anche il grafico
    if (state.lastPeriod) {
      updatePhaseViewFull();
    }
  });

  console.log('✓ Period fine-tuning controls initialized');
}

/**
 * Setup keyboard shortcuts per slider periodo
 */
function setupPeriodKeyboardShortcuts(buttons) {
  document.addEventListener('keydown', (e) => {
    // Solo se siamo nel tab fase
    const phaseTab = document.getElementById('tab-phase');
    if (!phaseTab || !phaseTab.classList.contains('active')) return;

    // Solo se non stiamo scrivendo in un input
    if (e.target.tagName === 'INPUT' && e.target.type === 'text') return;
    if (e.target.tagName === 'INPUT' && e.target.type === 'number') return;

    let handled = false;

    if (e.key === 'ArrowLeft') {
      if (e.shiftKey) {
        buttons.periodMinusBigBtn?.click();
      } else {
        buttons.periodMinusBtn?.click();
      }
      handled = true;
    } else if (e.key === 'ArrowRight') {
      if (e.shiftKey) {
        buttons.periodPlusBigBtn?.click();
      } else {
        buttons.periodPlusBtn?.click();
      }
      handled = true;
    } else if (e.key === 'Home') {
      buttons.periodResetBtn?.click();
      handled = true;
    }

    if (handled) {
      e.preventDefault();
      e.stopPropagation();
    }
  });
}

// =============================================================================
// CONFRONTO PERIODI (DELTA-P)
// =============================================================================

/**
 * Setup handler per confronto periodi
 */
export function setupDeltaPControls() {
  const computeDeltaPBtn = document.getElementById("computeDeltaP");
  const suggestDeltaPBtn = document.getElementById("suggestDeltaP");

  if (computeDeltaPBtn) {
    computeDeltaPBtn.onclick = () => {
      const P = parseFloat(document.getElementById("chosenP").value);
      const deltaP = parseFloat(document.getElementById("deltaP").value);
      const sampling = parseFloat(document.getElementById("deltaSampling").value) || 0.1;

      if (!P || !deltaP || deltaP <= 0) {
        alert("Imposta un periodo valido e un ΔP > 0");
        return;
      }

      // Prima aggiorna il grafico principale
      updatePhaseViewFull();

      // POI genera i grafici delta-P
      const results = computePhaseDelta(P, deltaP, sampling);
      renderPhaseDelta(results);

      // Setup click handlers per selezionare periodo
      setupDeltaPClickHandlers(results);
    };
  }

  if (suggestDeltaPBtn) {
    suggestDeltaPBtn.onclick = () => {
      const P = parseFloat(document.getElementById("chosenP").value);

      if (!P || P <= 0) {
        alert("Imposta prima un periodo valido");
        return;
      }

      // Criterio: ΔP = P / 100 per periodi > 1d
      //           ΔP = P / 50 per periodi brevi
      let suggestedDeltaP;

      if (P < 0.1) {
        // Periodi molto brevi (< 2.4h): 2% del periodo
        suggestedDeltaP = P * 0.02;
      } else if (P < 1) {
        // Periodi brevi (< 1d): 1% del periodo
        suggestedDeltaP = P * 0.01;
      } else {
        // Periodi lunghi (>= 1d): 0.5% del periodo
        suggestedDeltaP = P * 0.005;
      }

      // Arrotonda a una cifra ragionevole
      const magnitude = Math.floor(Math.log10(suggestedDeltaP));
      suggestedDeltaP = Math.round(suggestedDeltaP * Math.pow(10, -magnitude + 2)) / Math.pow(10, -magnitude + 2);

      document.getElementById("deltaP").value = suggestedDeltaP;

      // Feedback visivo
      const input = document.getElementById("deltaP");
      input.style.background = '#dbeafe';
      input.style.transition = 'background 0.3s';
      setTimeout(() => {
        input.style.background = '';
      }, 500);
    };
  }

  console.log('✓ Delta-P controls initialized');
}

/**
 * Setup click handlers per grafici delta-P
 */
function setupDeltaPClickHandlers(results) {
  setTimeout(() => {
    results.forEach(({ period }, idx) => {
      const plotDiv = document.getElementById(`deltaPlot${idx}`);
      if (plotDiv) {
        plotDiv.style.cursor = 'pointer';
        plotDiv.onclick = () => {
          document.getElementById("chosenP").value = period.toFixed(6);

          // ✅ RESET fine-tuning quando periodo cambia da delta-P
          resetPeriodFineTuning();

          // Feedback visivo
          plotDiv.style.background = '#dbeafe';
          setTimeout(() => plotDiv.style.background = '', 300);

          // Ricalcola TUTTO (grafico + statistiche + effemeridi)
          updatePhaseViewFull();

          // Rigenera delta-P con nuovo periodo
          const newDeltaP = parseFloat(document.getElementById("deltaP").value);
          const newResults = computePhaseDelta(period, newDeltaP, 0.1);
          renderPhaseDelta(newResults);

          // Scroll
          document.getElementById("plotPhase").scrollIntoView({
            behavior: 'smooth', block: 'start'
          });
        };
      }
    });
  }, 100);
}

// =============================================================================
// SAMPLING INTELLIGENTE
// =============================================================================

/**
 * Setup handler per sampling slider
 */
export function setupSamplingControls() {
  const samplingSlider = document.getElementById("samplingSlider");
  const samplingValue = document.getElementById("samplingValue");
  const samplingInfo = document.getElementById("samplingInfo");
  const samplingWarning = document.getElementById("samplingWarning");
  const finalCalc100Btn = document.getElementById("finalCalc100");

  if (samplingSlider && samplingValue) {
    samplingSlider.oninput = (e) => {
      const value = parseInt(e.target.value);
      setActiveSamplingPercent(value);
      samplingValue.textContent = `${value}%`;

      // Visual feedback colore
      updateSamplingSliderColor(e.target, value);

      // Warning
      if (samplingWarning) {
        samplingWarning.style.display = value < 100 ? 'block' : 'none';
      }

      // Info
      updateSamplingInfo(samplingInfo, value);
    };

    samplingSlider.onchange = () => {
      // Al rilascio slider, ricalcola tutto
      if (state.lastPeriod) {
        updatePhaseViewFull();
      }
    };
  }

  if (finalCalc100Btn) {
    finalCalc100Btn.onclick = () => {
      handleFinalCalculation100(samplingSlider, samplingValue, samplingWarning, samplingInfo, finalCalc100Btn);
    };
  }

  console.log('✓ Sampling controls initialized');
}

/**
 * Aggiorna colore slider sampling
 */
function updateSamplingSliderColor(slider, value) {
  const percent = value;
  if (value < 30) {
    slider.style.background = `linear-gradient(to right, #dc2626 0%, #dc2626 ${percent}%, #e5e7eb ${percent}%)`;
  } else if (value < 60) {
    slider.style.background = `linear-gradient(to right, #ea580c 0%, #ea580c ${percent}%, #e5e7eb ${percent}%)`;
  } else if (value < 100) {
    slider.style.background = `linear-gradient(to right, #ca8a04 0%, #ca8a04 ${percent}%, #e5e7eb ${percent}%)`;
  } else {
    slider.style.background = '#22c55e';
  }
}

/**
 * Aggiorna info sampling
 */
function updateSamplingInfo(samplingInfo, value) {
  if (!samplingInfo) return;

  const estimatedPoints = Math.floor(state.n * value / 100);
  samplingInfo.innerHTML = `<span style="color: #0ea5e9;">
    📊 Usando ~${estimatedPoints.toLocaleString()} punti su ${state.n.toLocaleString()} totali
  </span>`;
}

/**
 * Handler calcolo finale al 100%
 */
function handleFinalCalculation100(slider, display, warning, info, button) {
  setActiveSamplingPercent(100);
  if (slider) slider.value = 100;
  if (display) display.textContent = "100%";
  if (warning) warning.style.display = 'none';
  if (slider) slider.style.background = '#22c55e';

  if (info) {
    info.innerHTML = `<span style="color: #22c55e; font-weight: 600;">
      ✓ Calcolo finale con tutti i ${state.n.toLocaleString()} punti
    </span>`;
  }

  button.textContent = '⏳ Calcolando...';
  button.style.background = '#0ea5e9';

  setTimeout(() => {
    if (state.lastPeriod) {
      updatePhaseViewFull();
    }

    button.style.background = '#22c55e';
    button.textContent = '✓ Completato!';

    setTimeout(() => {
      button.textContent = '✓ Calcolo Finale 100%';
    }, 2000);
  }, 100);
}

// =============================================================================
// INIZIALIZZAZIONE GLOBALE
// =============================================================================

/**
 * Inizializza tutti i controlli fase
 * Chiamare una volta dopo il DOM ready
 */
export function initializePhaseControls() {
  console.log('🎛️ Initializing phase controls...');

  setupPhaseShiftControls();
  setupPhaseDisplayControls();
  setupEphemerisToggle();
  setupTemplateControls();
  setupPeriodMultiplierControls();
  setupPeriodFineTuningControls();
  setupDeltaPControls();
  setupSamplingControls();

  console.log('✅ Phase controls initialized successfully');
}

// =============================================================================
// EXPORT GLOBALE (per backward compatibility)
// =============================================================================

if (typeof window !== 'undefined') {
  window.goToPhaseTabAndUpdate = goToPhaseTabAndUpdate;
  window.initializePhaseControls = initializePhaseControls;
}

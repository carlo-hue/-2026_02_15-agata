// data-loader.js
import { state, rebuildDefaults, setActiveSamplingPercent } from './state.js';
import { renderSessionList, updateCounters } from './session-ui.js';
import { drawLightcurve } from './plots.js';
import { HistoryTracker } from './history-tracker.js';
import { computeExtremaPerSession } from './extrema-analysis.js';
import { logger as loggerFactory } from '../common/logger.js';

const logger = loggerFactory('DataLoader');

/**
 * Carica i dati della lightcurve in formato Arrow
 */
export async function loadDataArrow() {
  let url = "/agata/variable-stars/api/lightcurve.arrow";

  // Verifica se c'è un progetto precaricato (dall'admin)
  const projectIdInput = document.getElementById("projectId");
  if (projectIdInput && projectIdInput.value) {
    // Progetto precaricato da admin
    const projectId = projectIdInput.value;
    url += `?project_id=${encodeURIComponent(projectId)}`;

    // Salva project_id nello stato
    state.projectId = projectId;
    state.gaiaId = null; // Non usato più direttamente
    state.projectCode = null;
    state.projectTitle = null;
  } else {
    // Nessun progetto precaricato - usa selezione manuale
    let source = document.getElementById("dataSource")?.value || "myprojects";

    // Se c'è un gaia_id pre-riempito, forza dataSource a "db"
    const gaiaIdInput = document.getElementById("gaiaId");
    if (gaiaIdInput && gaiaIdInput.value && source !== "db") {
      source = "db";
      const dataSourceEl = document.getElementById("dataSource");
      if (dataSourceEl) dataSourceEl.value = "db";
    }

    if (source === "myprojects") {
      // Carica da progetto selezionato
      const projectId = window.selectedProjectId;
      if (!projectId) {
        alert("Seleziona un progetto dalla lista");
        return;
      }

      url += `?project_id=${encodeURIComponent(projectId)}`;

      // Salva info progetto
      const selectEl = document.getElementById("myProjectSelect");
      const opt = selectEl?.selectedOptions[0];
      if (opt && opt.value) {
        state.projectId = projectId;
        state.projectCode = opt.dataset.projectCode || null;
        state.projectTitle = opt.dataset.title || null;
        state.gaiaId = opt.dataset.gaiaId || null;
      }
    } else if (source === "db") {
      // Caricamento dati reali da GAIA ID (admin per esaminazione)
      const gaiaId = document.getElementById("gaiaId")?.value?.trim();
      if (!gaiaId) {
        alert("Inserisci un GAIA ID valido");
        return;
      }

      // Carica dati reali dal database per questa stella
      state.projectId = null;
      state.gaiaId = gaiaId;
      state.projectCode = null;
      state.projectTitle = null;

      url += `?gaia_id=${encodeURIComponent(gaiaId)}`;

      logger.info(`Caricamento dati DB per GAIA ID: ${gaiaId}`);
    } else {
      // Dati sintetici
      state.projectId = null;
      state.gaiaId = null;
      state.projectCode = null;
      state.projectTitle = null;

      const kind = document.getElementById("kind").value;
      const seed = document.getElementById("seed").value;
      const sessions = document.getElementById("sessions").value;

      url += `?kind=${encodeURIComponent(kind)}`
           + `&seed=${encodeURIComponent(seed)}`
           + `&sessions=${encodeURIComponent(sessions)}`;
    }
  }

  const r = await fetch(url);
  if (!r.ok) {
    alert("Errore nel caricamento dei dati");
    return;
  }

  const table = window.Arrow.tableFromIPC(
    new Uint8Array(await r.arrayBuffer())
  );

  // ---------------------------------
  // Popola lo state (immutato)
  // ---------------------------------
  state.n = table.numRows;
  state.jd = new Float64Array(table.getChild("jd").toArray());
  state.mag = new Float32Array(table.getChild("mag").toArray());
  state.session = new Int32Array(table.getChild("session_id").toArray());
  state.pid = new Int32Array(table.getChild("point_id").toArray());

  // Leggi nomi sessione se presenti
  if (table.schema.fields.some(f => f.name === "session_name")) {
    const names = table.getChild("session_name").toArray();
    // Mappa session_id → nome
    const nameMap = new Map();
    for (let i = 0; i < state.n; i++) {
      const sid = state.session[i];
      const name = names[i];
      if (!nameMap.has(sid) && name) {
        nameMap.set(sid, name);
      }
    }
    // Aggiorna state.sessionName E state.sessionNameFromDB
    nameMap.forEach((name, sid) => {
      state.sessionName.set(sid, name);
      state.sessionNameFromDB.set(sid, name);  // AGGIUNTO
    });
  }

  // ---------------------------------
  // Reset e rendering
  // ---------------------------------
  rebuildDefaults();
  renderSessionList();
  drawLightcurve();
  updateCounters();
  autoSetSampling();

  // ---------------------------------
  // Calcola estremi per sessione (in background)
  // ---------------------------------
  try {
    await computeExtremaPerSession();
    // Ri-renderizza lista sessioni per mostrare estremi
    renderSessionList();
    console.log('✅ Estremi calcolati e visualizzati');
  } catch (error) {
    console.warn('⚠️ Errore calcolo estremi (non bloccante):', error);
  }

  HistoryTracker.record('load_data', {
    project_id: state.projectId || null,
    project_code: state.projectCode || null,
    gaia_id: state.gaiaId || null,
    kind: !state.projectId ? document.getElementById("kind")?.value : null,
    sessions: state.activeSession.size,
    points: state.n
  });

  // Nascondi il loading indicator se visibile
  const loadingIndicator = document.getElementById("autoLoadingIndicator");
  if (loadingIndicator) {
    loadingIndicator.style.display = "none";
  }
}

/**
 * Imposta automaticamente sampling in base al numero di punti
 */
export function autoSetSampling() {
  const n = state.n;

  let recommendedPercent;
  let reason;

  if (n < 100000) {
    recommendedPercent = 100;
    reason = "Dataset piccolo - tutti i punti";
  } else if (n < 500000) {
    recommendedPercent = 60;
    reason = "Dataset medio - editing fluido";
  } else if (n < 1000000) {
    recommendedPercent = 30;
    reason = "Dataset grande - performance ottimale";
  } else {
    recommendedPercent = 10;
    reason = "Dataset enorme - esplorazione rapida";
  }

  setActiveSamplingPercent(recommendedPercent);

  // Aggiorna UI
  const slider = document.getElementById("samplingSlider");
  const display = document.getElementById("samplingValue");
  const info = document.getElementById("samplingInfo");
  const warning = document.getElementById("samplingWarning");

  if (slider) {
    slider.value = recommendedPercent;

    // Colore slider
    const percent = recommendedPercent;
    if (recommendedPercent < 30) {
      slider.style.background = `linear-gradient(to right, #dc2626 0%, #dc2626 ${percent}%, #e5e7eb ${percent}%)`;
    } else if (recommendedPercent < 60) {
      slider.style.background = `linear-gradient(to right, #ea580c 0%, #ea580c ${percent}%, #e5e7eb ${percent}%)`;
    } else if (recommendedPercent < 100) {
      slider.style.background = `linear-gradient(to right, #ca8a04 0%, #ca8a04 ${percent}%, #e5e7eb ${percent}%)`;
    } else {
      slider.style.background = '#22c55e';
    }
  }

  if (display) display.textContent = `${recommendedPercent}%`;

  if (info) {
    const estimatedPoints = Math.floor(n * recommendedPercent / 100);
    info.innerHTML = `<span style="color: #0ea5e9; font-weight: 600;">
      📊 Auto-impostato: ${estimatedPoints.toLocaleString()}/${n.toLocaleString()} punti
      <br><small>${reason}</small>
    </span>`;
  }

  if (warning) {
    warning.style.display = recommendedPercent < 100 ? 'block' : 'none';
  }

  console.log(`🎯 Auto-sampling: ${n.toLocaleString()} punti → ${recommendedPercent}%`);
}

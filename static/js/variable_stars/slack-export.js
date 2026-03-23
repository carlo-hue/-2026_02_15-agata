/**
 * slack-export.js - Gestione esportazione verso Slack
 *
 * Fornisce funzioni per inviare:
 * 1. Analisi in Fase: immagine PNG del diagramma + testo minimale
 * 2. Periodigramma: immagine PNG + valori testuali (min, max, periodi)
 * 3. Analisi di Supporto: dati completi formattati in testo
 *
 * Dipendenze:
 * - state.js: accesso ai dati e parametri globali
 * - phase-statistics.js: calculatePhaseStatistics()
 * - plots.js: Plotly charts
 */

import { state, nameForSession, getTotalOffset } from './state.js';
import { calculatePhaseStatistics } from './phase-statistics.js';
import { detrendValue } from './math-logic.js';

// =============================================================================
// 1. INVIO ANALISI IN FASE A SLACK
// =============================================================================

/**
 * Esporta l'analisi in fase a Slack
 * Invia: immagine PNG del diagramma + testo minimale
 */
export async function exportPhaseAnalysisToSlack() {
  if (!state.lastPeriod) {
    alert("❌ Calcola prima l'analisi in fase!");
    return;
  }

  // Estrai project_id dall'input nascosto
  const projectIdInput = document.getElementById("projectId");
  const projectId = projectIdInput?.value;

  if (!projectId) {
    alert("❌ Project ID non trovato!");
    return;
  }

  // Disabilita bottone durante invio
  const btn = document.getElementById("btn-slack-phase-analysis");
  if (btn) btn.disabled = true;

  try {
    // Genera PNG
    const pngData = await generatePhaseAnalysisPNG();
    if (!pngData) {
      alert("❌ Errore generazione PNG");
      return;
    }

    // Compila messaggio
    const message = buildPhaseAnalysisMessage();

    // Invia a backend per upload Slack
    const success = await sendImageAndMessageToSlack(
      projectId,
      'phase_analysis',
      pngData,
      message
    );

    if (success) {
      alert("✅ Analisi in Fase inviata a Slack!");
      if (btn) btn.classList.add('success');
      setTimeout(() => {
        if (btn) btn.classList.remove('success');
      }, 2000);
    } else {
      alert("❌ Errore invio a Slack");
    }
  } catch (error) {
    console.error("❌ Errore esportazione fase:", error);
    alert(`❌ Errore: ${error.message}`);
  } finally {
    if (btn) btn.disabled = false;
  }
}

/**
 * Genera PNG del diagramma in fase
 */
async function generatePhaseAnalysisPNG() {
  const gd = document.getElementById("plotPhase");
  if (!gd) {
    console.error("❌ Elemento plotPhase non trovato");
    return null;
  }

  const opts = {
    format: 'png',
    width: 1200,
    height: 800,
    scale: 2  // 2x per qualità migliore
  };

  try {
    return await Plotly.toImage(gd, opts);
  } catch (error) {
    console.error("❌ Errore generazione PNG fase:", error);
    return null;
  }
}

/**
 * Compila messaggio per Analisi in Fase
 */
function buildPhaseAnalysisMessage() {
  const P = state.lastPeriod;
  const stats = calculatePhaseStatistics();

  let message = `📊 *Analisi in Fase*\n`;
  message += `Inviato dall'editor AGATA\n\n`;
  message += `*Periodo:* ${P.toFixed(8)} giorni\n`;

  if (stats) {
    message += `*RMS:* ${stats.rms.toFixed(6)} mag\n`;
    message += `*χ² ridotto:* ${stats.reducedChiSq.toFixed(4)}\n`;
    message += `*Copertura fase:* ${(stats.coverage * 100).toFixed(1)}%\n`;
  }

  return message;
}

// =============================================================================
// 2. INVIO PERIODIGRAMMA A SLACK
// =============================================================================

/**
 * Esporta periodigramma a Slack
 * Invia: immagine PNG + valori testuali (min, max, periodi, prewhitening)
 */
export async function exportPeriodogramToSlack() {
  // Estrai project_id
  const projectIdInput = document.getElementById("projectId");
  const projectId = projectIdInput?.value;

  if (!projectId) {
    alert("❌ Project ID non trovato!");
    return;
  }

  // Disabilita bottone durante invio
  const btn = document.getElementById("btn-slack-periodogram");
  if (btn) btn.disabled = true;

  try {
    // Genera PNG del periodigramma
    const pngData = await generatePeriodogramPNG();
    if (!pngData) {
      alert("❌ Errore generazione PNG periodigramma");
      return;
    }

    // Compila messaggio con valori testuali
    const message = buildPeriodogramMessage();

    // Invia a Slack
    const success = await sendImageAndMessageToSlack(
      projectId,
      'periodogram',
      pngData,
      message
    );

    if (success) {
      alert("✅ Periodigramma inviato a Slack!");
      if (btn) btn.classList.add('success');
      setTimeout(() => {
        if (btn) btn.classList.remove('success');
      }, 2000);
    } else {
      alert("❌ Errore invio a Slack");
    }
  } catch (error) {
    console.error("❌ Errore esportazione periodigramma:", error);
    alert(`❌ Errore: ${error.message}`);
  } finally {
    if (btn) btn.disabled = false;
  }
}

/**
 * Genera PNG del periodigramma
 */
async function generatePeriodogramPNG() {
  const gd = document.getElementById("plotPeriod");
  if (!gd) {
    console.error("❌ Elemento plotPeriod non trovato");
    return null;
  }

  const opts = {
    format: 'png',
    width: 1200,
    height: 600,
    scale: 2
  };

  try {
    return await Plotly.toImage(gd, opts);
  } catch (error) {
    console.error("❌ Errore generazione PNG periodigramma:", error);
    return null;
  }
}

/**
 * Compila messaggio per Periodigramma
 */
function buildPeriodogramMessage() {
  const minP = parseFloat(document.getElementById("minP")?.value || 0.1);
  const maxP = parseFloat(document.getElementById("maxP")?.value || 15);
  const enablePrewhitening = document.getElementById("enablePrewhitening")?.checked || false;
  const nPeriods = document.getElementById("nPeriods")?.value || 3;

  // Estrai i picchi se presenti
  const peaksDiv = document.getElementById("peaks");
  const peaksText = peaksDiv?.innerText || "-";

  let message = `📈 *Periodigramma*\n`;
  message += `Inviato dall'editor AGATA\n\n`;
  message += `*Range Periodo:* ${minP.toFixed(3)} - ${maxP.toFixed(2)} giorni\n`;
  message += `*Pre-whitening:* ${enablePrewhitening ? "✅ Abilitato" : "❌ Disabilitato"}\n`;

  if (enablePrewhitening) {
    message += `*N. Periodi per pre-whitening:* ${nPeriods}\n`;
  }

  message += `\n*Periodi trovati:*\n`;
  message += peaksText;

  return message;
}

// =============================================================================
// 3. INVIO ANALISI DI SUPPORTO A SLACK
// =============================================================================

/**
 * Esporta Analisi di Supporto a Slack
 * Invia: dati completi formattati in testo
 */
export async function exportSupportAnalysisToSlack() {
  // Estrai project_id
  const projectIdInput = document.getElementById("projectId");
  const projectId = projectIdInput?.value;

  if (!projectId) {
    alert("❌ Project ID non trovato!");
    return;
  }

  // Disabilita bottone durante invio
  const btn = document.getElementById("btn-slack-support-analysis");
  if (btn) btn.disabled = true;

  try {
    // Compila messaggio completo
    const message = buildSupportAnalysisMessage();
    if (!message) {
      alert("❌ Errore compilazione dati supporto");
      return;
    }

    // Invia a Slack (senza immagine, solo testo)
    const success = await sendMessageToSlack(
      projectId,
      'support_analysis',
      message
    );

    if (success) {
      alert("✅ Analisi di Supporto inviata a Slack!");
      if (btn) btn.classList.add('success');
      setTimeout(() => {
        if (btn) btn.classList.remove('success');
      }, 2000);
    } else {
      alert("❌ Errore invio a Slack");
    }
  } catch (error) {
    console.error("❌ Errore esportazione supporto:", error);
    alert(`❌ Errore: ${error.message}`);
  } finally {
    if (btn) btn.disabled = false;
  }
}

/**
 * Compila messaggio completo per Analisi di Supporto
 */
function buildSupportAnalysisMessage() {
  // === SEZIONE 1: Informazioni Base ===
  const projectName = document.getElementById("info-project-name")?.innerText || "-";
  const gaiaId = document.getElementById("info-gaia-id")?.innerText || "-";
  const coords = document.getElementById("info-coords")?.innerText || "-";
  const period = document.getElementById("info-period")?.innerText || "-";

  // === SEZIONE 2: Parametri Fisici ===
  const spectralClass = document.getElementById("spectral_class")?.value || "-";
  const teff = document.getElementById("teff")?.value || "-";
  const distance = document.getElementById("distance")?.value || "-";
  const luminosity = document.getElementById("luminosity")?.value || "-";
  const radius = document.getElementById("radius")?.value || "-";
  const mass = document.getElementById("mass")?.value || "-";
  const colorBV = document.getElementById("color_bv")?.value || "-";
  const colorBPRP = document.getElementById("color_bprp")?.value || "-";
  const variableType = document.getElementById("variable_type")?.value || "-";
  const catalogIds = document.getElementById("catalog_identifiers")?.value || "-";
  const amplitude = document.getElementById("variability_amplitude")?.value || "-";
  const passband = document.getElementById("passband")?.value || "-";
  const epoch = document.getElementById("epoch")?.value || "-";

  // Compila messaggio strutturato
  let message = `📊 *Analisi di Supporto - Preparazione AAVSO/VSX*\n`;
  message += `Inviato dall'editor AGATA\n\n`;

  message += `*═══ INFORMAZIONI BASE ═══*\n`;
  message += `Nome Progetto: ${projectName}\n`;
  message += `Stella Gaia DR3: ${gaiaId}\n`;
  message += `Coordinate (RA, Dec): ${coords}\n`;
  message += `Periodo (dall'analisi in fase): ${period}\n\n`;

  message += `*═══ PARAMETRI FISICI STELLA ═══*\n`;
  message += `Classe Spettrale: ${spectralClass}\n`;
  message += `Teff (K): ${teff}\n`;
  message += `Distanza (pc): ${distance}\n`;
  message += `Luminosità (L☉): ${luminosity}\n`;
  message += `Raggio (R☉): ${radius}\n`;
  message += `Massa (M☉): ${mass}\n`;
  message += `Colore B-V: ${colorBV}\n`;
  message += `Colore BP-RP: ${colorBPRP}\n\n`;

  message += `*═══ TIPO DI VARIABILE ═══*\n`;
  message += `Tipo Proposto: ${variableType}\n\n`;

  message += `*═══ IDENTIFICATORI CATALOGHI ═══*\n`;
  if (catalogIds && catalogIds !== "-") {
    message += catalogIds.split('\n').map(id => `• ${id.trim()}`).join('\n') + '\n\n';
  } else {
    message += "-\n\n";
  }

  message += `*═══ PARAMETRI VARIABILITÀ ═══*\n`;
  message += `Ampiezza Variabilità (mag): ${amplitude}\n`;
  message += `Passband: ${passband}\n`;
  message += `Epoch (JD): ${epoch}\n`;

  return message;
}

// =============================================================================
// FUNZIONI BACKEND COMMUNICATION
// =============================================================================

/**
 * Invia immagine + messaggio a Slack via backend nel thread del progetto
 */
async function sendImageAndMessageToSlack(projectId, analysisType, imageData, message) {
  try {
    const formData = new FormData();
    formData.append('project_id', projectId);
    formData.append('analysis_type', analysisType);
    formData.append('message', message);

    // Converte data URL a blob
    const blob = await fetch(imageData).then(r => r.blob());
    formData.append('image', blob, `${analysisType}.png`);

    const response = await fetch('/agata/admin/api/slack-export', {
      method: 'POST',
      body: formData
    });

    const result = await response.json();

    if (!response.ok) {
      console.error("❌ Errore backend:", result);

      // Gestisci errori specifici
      if (result.error?.includes('No Slack thread')) {
        alert("❌ Errore: Il progetto deve essere creato prima di esportare a Slack");
      } else if (result.error?.includes('Slack not enabled')) {
        alert("❌ Errore: Slack non è abilitato per questa associazione");
      } else {
        alert(`❌ Errore: ${result.error || 'Errore sconosciuto'}`);
      }
      return false;
    }

    return true;
  } catch (error) {
    console.error("❌ Errore comunicazione backend:", error);
    alert(`❌ Errore: ${error.message}`);
    return false;
  }
}

/**
 * Invia solo messaggio a Slack via backend nel thread del progetto (per Analisi di Supporto)
 */
async function sendMessageToSlack(projectId, analysisType, message) {
  try {
    const response = await fetch('/agata/admin/api/slack-export', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        project_id: projectId,
        analysis_type: analysisType,
        message: message
      })
    });

    const result = await response.json();

    if (!response.ok) {
      console.error("❌ Errore backend:", result);

      // Gestisci errori specifici
      if (result.error?.includes('No Slack thread')) {
        alert("❌ Errore: Il progetto deve essere creato prima di esportare a Slack");
      } else if (result.error?.includes('Slack not enabled')) {
        alert("❌ Errore: Slack non è abilitato per questa associazione");
      } else {
        alert(`❌ Errore: ${result.error || 'Errore sconosciuto'}`);
      }
      return false;
    }

    return true;
  } catch (error) {
    console.error("❌ Errore comunicazione backend:", error);
    alert(`❌ Errore: ${error.message}`);
    return false;
  }
}

// =============================================================================
// INIT BOTTONI
// =============================================================================

/**
 * Inizializza event handler per bottoni Slack
 * Chiamare da main.js dopo DOM ready
 */
export function initSlackExportButtons() {
  // Bottone Analisi in Fase
  const btnPhase = document.getElementById("btn-slack-phase-analysis");
  if (btnPhase) {
    btnPhase.addEventListener('click', exportPhaseAnalysisToSlack);
  }

  // Bottone Periodigramma
  const btnPeriodogram = document.getElementById("btn-slack-periodogram");
  if (btnPeriodogram) {
    btnPeriodogram.addEventListener('click', exportPeriodogramToSlack);
  }

  // Bottone Analisi di Supporto
  const btnSupport = document.getElementById("btn-slack-support-analysis");
  if (btnSupport) {
    btnSupport.addEventListener('click', exportSupportAnalysisToSlack);
  }
}

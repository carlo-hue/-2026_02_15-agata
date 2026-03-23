// agata/static/js/variable_stars/variability-comparison.js
/**
 * Module per Analisi Comparativa Stelle Variabili
 *
 * Features:
 * - Ricerca stelle analoghe da Gaia DR3, VSX, ASAS-SN
 * - Display tabella analoghe con ranking similarità
 * - Generazione phased light curve comparison con χ² fit
 * - Cache management
 */

import { state } from './state.js';
import { logger as createLogger } from '../common/logger.js';

const LOG_PREFIX = '[VariabilityComparison]';
const logger = createLogger('VariabilityComparison');

// State
let analoguesData = null;
let selectedAnalogues = [];

/**
 * Inizializza il modulo di analisi comparativa
 * Usa event delegation per gestire buttons anche se il tab non è ancora visibile
 */
export function initVariabilityComparison() {
    console.log('[VariabilityComparison] INIT CALLED!');
    logger.info(` Initializing variability comparison module with event delegation`);

    // Event delegation sul document per gestire click sui button
    document.addEventListener('click', (e) => {
        console.log('[VariabilityComparison] Click detected on:', e.target);
        // Debug: log ogni click per capire cosa succede
        const targetId = e.target.id;
        const closestSearch = e.target.closest('#searchAnaloguesBtn');
        const closestPlot = e.target.closest('#plotPhasedComparisonBtn');
        const closestCache = e.target.closest('#clearCacheBtn');
        const closestCopy = e.target.closest('#copyFromStarBtn');

        // Copy From Star Button
        if (targetId === 'copyFromStarBtn' || closestCopy) {
            e.preventDefault();
            e.stopPropagation();
            logger.info(` Copy from star button clicked!`);
            handleCopyFromStar();
            return;
        }

        // Search Analogues Button
        if (targetId === 'searchAnaloguesBtn' || closestSearch) {
            e.preventDefault();
            e.stopPropagation();
            logger.info(` Search button clicked!`);
            handleSearchAnalogues();
            return;
        }

        // Plot Phased Comparison Button
        if (targetId === 'plotPhasedComparisonBtn' || closestPlot) {
            e.preventDefault();
            e.stopPropagation();
            logger.info(` Plot button clicked!`);
            handlePlotPhasedComparison();
            return;
        }

        // Clear Cache Button
        if (targetId === 'clearCacheBtn' || closestCache) {
            e.preventDefault();
            e.stopPropagation();
            logger.info(` Clear cache button clicked!`);
            handleClearCache();
            return;
        }
    }, true); // useCapture = true per intercettare prima

    // Esponi per debug
    window.variabilityComparisonTest = () => {
        console.log('[VariabilityComparison] Test function works!');
        handleSearchAnalogues();
    };

    console.log('[VariabilityComparison] Module initialized! Try window.variabilityComparisonTest()');
    logger.info(` Module initialized with event delegation`);
}

/**
 * Handler: Ricerca stelle analoghe
 */
async function handleSearchAnalogues() {
    console.log('[VariabilityComparison] handleSearchAnalogues called!');
    logger.info(` handleSearchAnalogues called!`);

    const projectId = document.getElementById('projectId')?.value;
    console.log('[VariabilityComparison] projectId:', projectId);

    if (!projectId) {
        console.warn('[VariabilityComparison] No project loaded');
        showError('Nessun progetto caricato. Carica prima un progetto dall\'admin.');
        return;
    }

    // ✅ Verifica che almeno periodo o ampiezza siano valorizzati
    const infoPeriodEl = document.getElementById('info-period');
    const amplitudeEl = document.getElementById('variability_amplitude');

    const hasPeriod = infoPeriodEl && infoPeriodEl.textContent && infoPeriodEl.textContent !== '-';
    const hasAmplitude = amplitudeEl && amplitudeEl.value && parseFloat(amplitudeEl.value) > 0;

    if (!hasPeriod && !hasAmplitude) {
        showError('❌ Compila almeno il Periodo o l\'Ampiezza di Variabilità nella sezione Parametri Fisici per cercare analoghe.');
        return;
    }

    // Recupera periodi dal periodogramma (optional - usa peaks già trovati se disponibili)
    const periods = getPeriods();

    logger.info(` Analogue search: hasPeriod=${hasPeriod}, hasAmplitude=${hasAmplitude}, periods=${periods ? periods.length : 0}`);

    logger.info(` Searching analogues for project ${projectId} with periods:`, periods);

    // UI loading
    const searchBtn = document.getElementById('searchAnaloguesBtn');
    const originalText = searchBtn.textContent;
    searchBtn.disabled = true;
    searchBtn.textContent = '🔍 Ricerca in corso...';

    const resultsDiv = document.getElementById('analoguesResults');
    resultsDiv.innerHTML = '<div class="loading-spinner">Interrogazione VSX (AAVSO Variable Star Index)...</div>';

    // Leggi parametri avanzati VSX dal form
    const topN = parseInt(document.getElementById('topN')?.value) || 10;

    // Magnitudine: 4 campi (min_mag_min, min_mag_max, max_mag_min, max_mag_max)
    const minMagMin = document.getElementById('minMagMin')?.value ? parseFloat(document.getElementById('minMagMin').value) : null;
    const minMagMax = document.getElementById('minMagMax')?.value ? parseFloat(document.getElementById('minMagMax').value) : null;
    const maxMagMin = document.getElementById('maxMagMin')?.value ? parseFloat(document.getElementById('maxMagMin').value) : null;
    const maxMagMax = document.getElementById('maxMagMax')?.value ? parseFloat(document.getElementById('maxMagMax').value) : null;

    const periodMin = document.getElementById('periodMin')?.value ? parseFloat(document.getElementById('periodMin').value) : null;
    const periodMax = document.getElementById('periodMax')?.value ? parseFloat(document.getElementById('periodMax').value) : null;
    const varType = document.getElementById('varType')?.value?.trim() || null;
    const specType = document.getElementById('specType')?.value?.trim() || null;

    logger.info(` Search params: topN=${topN}, minMag=[${minMagMin},${minMagMax}], maxMag=[${maxMagMin},${maxMagMax}], period=[${periodMin},${periodMax}], varType=${varType}, specType=${specType}`);

    try {
        const requestBody = {
            top_n: topN,
            min_mag_min: minMagMin,
            min_mag_max: minMagMax,
            max_mag_min: maxMagMin,
            max_mag_max: maxMagMax,
            period_min: periodMin,
            period_max: periodMax,
            vartype: varType,
            spec_type: specType
        };

        // Invia periods solo se period_min/max NON sono specificati
        // (per evitare confusione con VSX API)
        if (!periodMin && !periodMax && periods && periods.length > 0) {
            requestBody.periods = periods.slice(0, 3);
        }

        logger.info(` 📤 Request to API:`, requestBody);

        const response = await fetch(`/api/projects/${projectId}/variability/search-analogues`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });

        logger.info(` 📥 Response status: ${response.status} ${response.statusText}`);

        if (!response.ok) {
            const errorText = await response.text();
            logger.error(` ❌ Error response body:`, errorText);
            try {
                const error = JSON.parse(errorText);
                throw new Error(error.error || 'Errore nella ricerca analoghe');
            } catch (e) {
                throw new Error(`HTTP ${response.status}: ${errorText.substring(0, 100)}`);
            }
        }

        const data = await response.json();
        logger.info(` ✅ Response data:`, data);
        logger.info(` 📊 Found ${data.analogues_count} analogues`);

        analoguesData = data;
        displayAnalogues(data);

    } catch (error) {
        logger.error(` Error searching analogues:`, error);
        showError(`Errore: ${error.message}`);
        resultsDiv.innerHTML = '';
    } finally {
        searchBtn.disabled = false;
        searchBtn.textContent = originalText;
    }
}

/**
 * Display tabella stelle analoghe
 */
function displayAnalogues(data) {
    const resultsDiv = document.getElementById('analoguesResults');

    if (!data.analogues || data.analogues.length === 0) {
        resultsDiv.innerHTML = `
            <div class="info-box" style="background: #fef3c7; border-left: 3px solid #f59e0b;">
                ⚠️ Nessuna stella analoga trovata con i parametri specificati.
                <br><small>Prova ad aumentare le tolleranze o verifica i periodi.</small>
            </div>
        `;
        return;
    }

    // Header con statistiche ricerca
    const cached = data.cached ? '✓ Cache' : '🔄 Live';
    const sp = data.search_params;

    // Build parametri ricerca display
    let searchParamsDisplay = [];

    // Mostra range magnitudine se specificato
    if (sp.min_mag_min || sp.min_mag_max || sp.max_mag_min || sp.max_mag_max) {
        const minMagRange = sp.min_mag_min && sp.min_mag_max ? `${sp.min_mag_min.toFixed(2)}-${sp.min_mag_max.toFixed(2)}` : '-';
        const maxMagRange = sp.max_mag_min && sp.max_mag_max ? `${sp.max_mag_min.toFixed(2)}-${sp.max_mag_max.toFixed(2)}` : '-';
        searchParamsDisplay.push(`MinMag: ${minMagRange}, MaxMag: ${maxMagRange}`);
    } else if (sp.mag) {
        searchParamsDisplay.push(`Mag: ${sp.mag.toFixed(1)}`);
    }

    if (sp.period_min && sp.period_max) {
        searchParamsDisplay.push(`P: ${sp.period_min.toFixed(4)}-${sp.period_max.toFixed(4)} d`);
    } else if (sp.periods && sp.periods.length > 0) {
        searchParamsDisplay.push(`P: ${sp.periods.map(p => p.toFixed(4)).join(', ')} d`);
    }

    if (sp.vartype) {
        searchParamsDisplay.push(`Type: ${sp.vartype}`);
    }

    if (sp.spec_type) {
        searchParamsDisplay.push(`Spec: ${sp.spec_type}`);
    }

    if (sp.radius_deg) {
        searchParamsDisplay.push(`Raggio: ${sp.radius_deg}°`);
    }

    let html = `
        <div class="analogues-header" style="margin-bottom: 1rem; padding: 0.75rem; background: #e0f2fe; border-radius: 6px; display: flex; justify-content: space-between; align-items: center;">
            <div>
                <strong>Trovate ${data.analogues_count} stelle analoghe</strong>
                <div style="font-size: 0.85rem; color: #64748b; margin-top: 4px;">
                    Parametri VSX: ${searchParamsDisplay.join(' | ')}
                </div>
            </div>
            <div style="font-size: 0.85rem; color: #64748b;">
                ${cached}
            </div>
        </div>
    `;

    // Tabella analoghe
    html += `
        <table class="analogues-table" style="width: 100%; border-collapse: collapse; font-size: 0.9rem;">
            <thead>
                <tr style="background: #f1f5f9; border-bottom: 2px solid #cbd5e1;">
                    <th style="padding: 8px; text-align: left;">
                        <input type="checkbox" id="selectAllAnalogues" title="Seleziona tutte (max 3)">
                    </th>
                    <th style="padding: 8px; text-align: left;">Gaia ID / Nome</th>
                    <th style="padding: 8px; text-align: left;">Catalogo</th>
                    <th style="padding: 8px; text-align: left;">Tipo</th>
                    <th style="padding: 8px; text-align: center;">BP-RP</th>
                    <th style="padding: 8px; text-align: center;">Mag</th>
                    <th style="padding: 8px; text-align: center;">Periodo</th>
                    <th style="padding: 8px; text-align: center;">Similarità</th>
                </tr>
            </thead>
            <tbody>
    `;

    data.analogues.forEach((analogue, idx) => {
        const similarityPercent = (analogue.similarity_score * 100).toFixed(1);
        const similarityColor = analogue.similarity_score > 0.8 ? '#22c55e' :
                                analogue.similarity_score > 0.6 ? '#eab308' : '#64748b';

        html += `
            <tr style="border-bottom: 1px solid #e2e8f0;">
                <td style="padding: 8px;">
                    <input type="checkbox" class="analogue-checkbox"
                           data-gaia-id="${analogue.source_id}"
                           data-index="${idx}">
                </td>
                <td style="padding: 8px;">
                    <div style="font-weight: 500;">${analogue.source_id}</div>
                    ${analogue.name ? `<div style="font-size: 0.85rem; color: #64748b;">${analogue.name}</div>` : ''}
                </td>
                <td style="padding: 8px;">
                    <span class="badge" style="background: ${analogue.catalog === 'Gaia DR3' ? '#3b82f6' : '#8b5cf6'}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 0.75rem;">
                        ${analogue.catalog}
                    </span>
                </td>
                <td style="padding: 8px;">
                    ${analogue.var_type || '-'}
                    ${analogue.class_score ? `<br><small style="color: #64748b;">(${(analogue.class_score * 100).toFixed(0)}%)</small>` : ''}
                </td>
                <td style="padding: 8px; text-align: center;">${analogue.bp_rp?.toFixed(2) || '-'}</td>
                <td style="padding: 8px; text-align: center;">${analogue.mag?.toFixed(2) || '-'}</td>
                <td style="padding: 8px; text-align: center;">${analogue.period?.toFixed(4) || '-'} d</td>
                <td style="padding: 8px; text-align: center;">
                    <div style="font-weight: 600; color: ${similarityColor};">${similarityPercent}%</div>
                    <div style="width: 100%; height: 4px; background: #e2e8f0; border-radius: 2px; margin-top: 4px;">
                        <div style="width: ${similarityPercent}%; height: 100%; background: ${similarityColor}; border-radius: 2px;"></div>
                    </div>
                </td>
            </tr>
        `;
    });

    html += `
            </tbody>
        </table>
    `;

    // Istruzioni
    html += `
        <div class="info-box" style="margin-top: 1rem; font-size: 0.85rem; color: #64748b;">
            💡 <strong>Seleziona fino a 3 stelle</strong> per confrontare le phased light curves con χ² fit.
        </div>
    `;

    resultsDiv.innerHTML = html;

    // Listeners per checkboxes
    setupCheckboxListeners();
}

/**
 * Setup listeners per selezione analoghe
 */
function setupCheckboxListeners() {
    const checkboxes = document.querySelectorAll('.analogue-checkbox');
    const selectAll = document.getElementById('selectAllAnalogues');

    checkboxes.forEach(cb => {
        cb.addEventListener('change', (e) => {
            const gaiaId = e.target.dataset.gaiaId;

            if (e.target.checked) {
                // Max 3 selezioni
                if (selectedAnalogues.length >= 3) {
                    e.target.checked = false;
                    showError('Massimo 3 stelle selezionabili per il confronto.');
                    return;
                }
                selectedAnalogues.push(gaiaId);
            } else {
                selectedAnalogues = selectedAnalogues.filter(id => id !== gaiaId);
            }

            logger.info(` Selected analogues:`, selectedAnalogues);

            // Enable/disable plot button
            const plotBtn = document.getElementById('plotPhasedComparisonBtn');
            plotBtn.disabled = selectedAnalogues.length === 0;
        });
    });

    if (selectAll) {
        selectAll.addEventListener('change', (e) => {
            const checked = e.target.checked;
            selectedAnalogues = [];

            checkboxes.forEach((cb, idx) => {
                if (idx < 3) {  // Max 3
                    cb.checked = checked;
                    if (checked) {
                        selectedAnalogues.push(cb.dataset.gaiaId);
                    }
                }
            });

            const plotBtn = document.getElementById('plotPhasedComparisonBtn');
            plotBtn.disabled = selectedAnalogues.length === 0;
        });
    }
}

/**
 * Handler: Plot phased comparison
 */
async function handlePlotPhasedComparison() {
    const projectId = document.getElementById('projectId')?.value;

    if (!projectId) {
        showError('Nessun progetto caricato.');
        return;
    }

    if (selectedAnalogues.length === 0) {
        showError('Seleziona almeno una stella analoga.');
        return;
    }

    // Recupera periodo primario
    const periods = getPeriods();
    const periodo = periods[0];  // Usa periodo principale

    logger.info(` Plotting phased comparison: periodo=${periodo}, analogues=`, selectedAnalogues);

    // UI loading
    const plotBtn = document.getElementById('plotPhasedComparisonBtn');
    const originalText = plotBtn.textContent;
    plotBtn.disabled = true;
    plotBtn.textContent = '📊 Generazione plot...';

    const plotDiv = document.getElementById('phasedComparisonPlot');
    plotDiv.innerHTML = '<div class="loading-spinner">Generazione phased light curves con χ² fit...</div>';

    try {
        const response = await fetch(`/api/projects/${projectId}/variability/phased-comparison`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                periodo: periodo,
                analogue_gaia_ids: selectedAnalogues
                // Non specificare catalog per usare tutti i dati disponibili
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Errore generazione plot');
        }

        const data = await response.json();
        logger.info(` Plot generated:`, data);

        displayPhasedPlot(data);

    } catch (error) {
        logger.error(` Error generating plot:`, error);
        showError(`Errore: ${error.message}`);
        plotDiv.innerHTML = '';
    } finally {
        plotBtn.disabled = false;
        plotBtn.textContent = originalText;
    }
}

/**
 * Display phased comparison plot
 */
function displayPhasedPlot(data) {
    const plotDiv = document.getElementById('phasedComparisonPlot');

    const html = `
        <div class="plot-header" style="margin-bottom: 1rem; padding: 0.75rem; background: #f0f9ff; border-radius: 6px;">
            <strong>Phased Light Curve Comparison</strong>
            <div style="font-size: 0.85rem; color: #64748b; margin-top: 4px;">
                Periodo: ${data.periodo.toFixed(4)} d |
                Light curves: ${data.lc_count} |
                Modello: Fourier 2nd order
            </div>
        </div>
        <div class="plot-container" style="background: white; padding: 1rem; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
            <img src="${data.plot}" alt="Phased Comparison Plot" style="width: 100%; height: auto; border-radius: 4px;">
        </div>
        <div class="info-box" style="margin-top: 1rem; font-size: 0.85rem; color: #64748b;">
            📊 Ogni panel mostra la phased LC con fit χ² (linea rossa).
            Valori χ² bassi (<2) indicano buon fit periodico.
        </div>
    `;

    plotDiv.innerHTML = html;
}

/**
 * Handler: Clear cache
 */
async function handleClearCache() {
    const projectId = document.getElementById('projectId')?.value;

    if (!projectId) {
        showError('Nessun progetto caricato.');
        return;
    }

    if (!confirm('Vuoi pulire la cache per questo progetto? Le prossime query saranno più lente.')) {
        return;
    }

    logger.info(` Clearing cache for project ${projectId}`);

    const clearBtn = document.getElementById('clearCacheBtn');
    const originalText = clearBtn.textContent;
    clearBtn.disabled = true;
    clearBtn.textContent = '🧹 Pulizia...';

    try {
        const response = await fetch(`/api/projects/${projectId}/variability/clear-cache`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Errore pulizia cache');
        }

        const data = await response.json();
        logger.info(` Cache cleared:`, data);

        showSuccess(data.message || 'Cache pulita con successo');

    } catch (error) {
        logger.error(` Error clearing cache:`, error);
        showError(`Errore: ${error.message}`);
    } finally {
        clearBtn.disabled = false;
        clearBtn.textContent = originalText;
    }
}

/**
 * Recupera periodi dal periodogramma (usa state o UI)
 */
function getPeriods() {
    console.log('[VariabilityComparison] getPeriods called, checking state:', state);

    // Prova 1: da state.topPeriods
    if (state.topPeriods && state.topPeriods.length > 0) {
        console.log('[VariabilityComparison] Found topPeriods in state:', state.topPeriods);
        return state.topPeriods.slice(0, 3);
    }

    // Prova 2: da state.periodogramResult (alternativa)
    if (state.periodogramResult && state.periodogramResult.periods && state.periodogramResult.periods.length > 0) {
        console.log('[VariabilityComparison] Found periodogramResult in state:', state.periodogramResult.periods);
        return state.periodogramResult.periods.slice(0, 3);
    }

    // Prova 3: Leggi dai badge del periodogramma nell'UI
    const peakBadges = document.querySelectorAll('#peaks .peak-badge');
    if (peakBadges && peakBadges.length > 0) {
        const periods = Array.from(peakBadges)
            .slice(0, 3)
            .map(badge => {
                const text = badge.textContent || '';
                const match = text.match(/P[\d]:\s*([\d.]+)/);
                return match ? parseFloat(match[1]) : null;
            })
            .filter(p => p !== null);

        if (periods.length > 0) {
            console.log('[VariabilityComparison] Found periods from UI badges:', periods);
            return periods;
        }
    }

    // Prova 4: Fallback - input periodo principale
    const periodInput = document.getElementById('periodInput');
    if (periodInput && periodInput.value) {
        console.log('[VariabilityComparison] Found period from input:', periodInput.value);
        return [parseFloat(periodInput.value)];
    }

    console.warn('[VariabilityComparison] No periods found!');
    return [];
}

/**
 * Show error message
 */
function showError(message) {
    const errorDiv = document.getElementById('variabilityComparisonError');
    if (errorDiv) {
        errorDiv.innerHTML = `
            <div style="padding: 0.75rem; background: #fee2e2; border-left: 3px solid #dc2626; border-radius: 6px; margin-bottom: 1rem;">
                ⚠️ ${message}
            </div>
        `;
        setTimeout(() => { errorDiv.innerHTML = ''; }, 5000);
    }
}

/**
 * Show success message
 */
function showSuccess(message) {
    const errorDiv = document.getElementById('variabilityComparisonError');
    if (errorDiv) {
        errorDiv.innerHTML = `
            <div style="padding: 0.75rem; background: #d1fae5; border-left: 3px solid #10b981; border-radius: 6px; margin-bottom: 1rem;">
                ✓ ${message}
            </div>
        `;
        setTimeout(() => { errorDiv.innerHTML = ''; }, 3000);
    }
}

/**
 * Handler: Copia parametri dalla stella corrente
 * Popola i campi di ricerca VSX con i dati del progetto e del periodogramma
 */
function handleCopyFromStar() {
    logger.info(` Copying parameters from current star`);

    // Recupera dati dal form di supporto (se compilato)
    const spectralClass = document.getElementById('spectral_class')?.value;
    const variableType = document.getElementById('variable_type')?.value;

    // Prova a recuperare il periodo da Analisi di Supporto (campo in alto)
    let mainPeriod = null;
    const infoPeriodEl = document.getElementById('info-period');
    if (infoPeriodEl && infoPeriodEl.textContent && infoPeriodEl.textContent !== '-') {
        // Estrai il numero dal testo (es: "0.567890 d" → 0.567890)
        const periodText = infoPeriodEl.textContent.trim();
        mainPeriod = parseFloat(periodText);
    }

    // Se non trovato in Analisi di Supporto, prova dal periodogramma
    if (!mainPeriod) {
        const periods = getPeriods();
        if (periods && periods.length > 0) {
            mainPeriod = periods[0];
        }
    }

    // Popola periodo min/max basandosi sul periodo principale ±10%
    if (mainPeriod && isFinite(mainPeriod)) {
        const periodMin = mainPeriod * 0.9;
        const periodMax = mainPeriod * 1.1;

        const periodMinInput = document.getElementById('periodMin');
        const periodMaxInput = document.getElementById('periodMax');

        if (periodMinInput) periodMinInput.value = periodMin.toFixed(6);
        if (periodMaxInput) periodMaxInput.value = periodMax.toFixed(6);

        logger.info(` Set period range: ${periodMin.toFixed(6)} - ${periodMax.toFixed(6)} d`);
    } else {
        logger.warn(` No period found in Analisi di Supporto or Periodogramma`);
    }

    // Popola magnitudine se disponibile
    // Prova a ricavare dai dati della fase (phaseStats) o dal progetto
    const projectId = document.getElementById('projectId')?.value;
    if (projectId) {
        populateMagnitudeFromPhaseOrProject(projectId);
    }

    // Popola classe spettrale se disponibile nel form supporto
    if (spectralClass) {
        const specTypeInput = document.getElementById('specType');
        if (specTypeInput) {
            specTypeInput.value = spectralClass;
            logger.info(` Set spectral class: ${spectralClass}`);
        }
    }

    // Popola tipo variabile se disponibile nel form supporto
    if (variableType && variableType !== '') {
        const varTypeInput = document.getElementById('varType');
        if (varTypeInput) {
            // Cerca di mappare il nome completo all'abbreviazione GCVS
            const varTypeMapping = {
                'RR Lyrae': 'RR',
                'RRab': 'RRAB',
                'RRc': 'RRC',
                'RRd': 'RRD',
                'Classical Cepheid': 'DCEP',
                'Type I Cepheid': 'DCEP',
                'Type II Cepheid': 'CW',
                'Delta Scuti': 'DSCT',
                'SX Phoenicis': 'SXPHE',
                'Mira': 'M',
                'Semi-Regular': 'SR',
                'Irregular': 'L',
                'EA': 'EA',
                'EB': 'EB',
                'EW': 'EW',
                'Rotational': 'ROT',
                'BY Draconis': 'BY'
            };

            const gcvsType = varTypeMapping[variableType] || variableType;
            varTypeInput.value = gcvsType;
            logger.info(` Set variable type: ${gcvsType}`);
        }
    }

    showSuccess('Parametri copiati dalla stella corrente. Verifica e modifica se necessario prima di cercare.');
}

/**
 * Recupera magnitudine dal phase plot (se disponibile) o dal progetto via API
 * Popola i 4 campi: min_mag_min, min_mag_max, max_mag_min, max_mag_max
 */
async function populateMagnitudeFromPhaseOrProject(projectId) {
    try {
        // Priorità sorgenti magnitudine:
        // 1. state.manualAmplitude {min, max} — campo "Ampiezza ✏️" nella fase (sigma-clipped, più preciso)
        // 2. state.phaseStats {mag_min, mag_max} — calcolo automatico dalla fase
        // 3. magnitudine del progetto via API (fallback grezzo)

        let magMin = null;  // magnitudine più brillante (numero più piccolo)
        let magMax = null;  // magnitudine più debole (numero più grande)
        let source = null;

        if (state.manualAmplitude && state.manualAmplitude.min != null && state.manualAmplitude.max != null) {
            magMin = state.manualAmplitude.min;
            magMax = state.manualAmplitude.max;
            source = 'Ampiezza ✏️ (manuale)';
        } else if (state.phaseStats && state.phaseStats.mag_min != null && state.phaseStats.mag_max != null) {
            magMin = state.phaseStats.mag_min;
            magMax = state.phaseStats.mag_max;
            source = 'phaseStats (auto)';
        }

        if (magMin != null && magMax != null) {
            // Popola i 4 campi con tolleranza ±0.1 mag attorno ai valori della fase
            const minMagMinInput = document.getElementById('minMagMin');
            const minMagMaxInput = document.getElementById('minMagMax');
            const maxMagMinInput = document.getElementById('maxMagMin');
            const maxMagMaxInput = document.getElementById('maxMagMax');

            if (minMagMinInput) minMagMinInput.value = (magMin - 0.1).toFixed(2);
            if (minMagMaxInput) minMagMaxInput.value = (magMin + 0.1).toFixed(2);
            if (maxMagMinInput) maxMagMinInput.value = (magMax - 0.1).toFixed(2);
            if (maxMagMaxInput) maxMagMaxInput.value = (magMax + 0.1).toFixed(2);

            logger.info(` Set magnitude from ${source}: min=${magMin.toFixed(3)}, max=${magMax.toFixed(3)}`);
            return;
        }

        // Fallback: magnitudine dal progetto via API
        const response = await fetch(`/agata/admin/api/projects/${projectId}/support-analysis`);
        if (!response.ok) {
            logger.warn(` Could not fetch project magnitude: ${response.status}`);
            return;
        }

        const data = await response.json();
        const mag = data.project?.magnitude;

        if (mag) {
            const minMagMinInput = document.getElementById('minMagMin');
            const minMagMaxInput = document.getElementById('minMagMax');
            const maxMagMinInput = document.getElementById('maxMagMin');
            const maxMagMaxInput = document.getElementById('maxMagMax');

            if (minMagMinInput) minMagMinInput.value = (mag - 0.6).toFixed(2);
            if (minMagMaxInput) minMagMaxInput.value = (mag - 0.4).toFixed(2);
            if (maxMagMinInput) maxMagMinInput.value = (mag + 0.4).toFixed(2);
            if (maxMagMaxInput) maxMagMaxInput.value = (mag + 0.6).toFixed(2);

            logger.info(` Set magnitude from project API (fallback): mag=${mag}`);
        } else {
            logger.warn(` No magnitude source available. Fare prima l'analisi in fase.`);
        }
    } catch (error) {
        logger.error(` Error fetching magnitude:`, error);
    }
}

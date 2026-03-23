/**
 * Modulo Analisi di Supporto - gestione tab
 *
 * Gestisce:
 * - Caricamento/salvataggio dati supporto analisi
 * - Pre-popolazione campi da Gaia
 * - Query Knowledge Base per validazione
 * - Integrazione con periodogramma per periodo
 * - Invio in revisione con validazione campi
 */

import { exportSupportAnalysisToSlack } from './slack-export.js';

// State
let supportState = {
    projectId: null,
    formData: {},
    gaiaSuggestions: null,
    isDirty: false,
    isLoading: false
};

export function initSupportAnalysis() {
    console.log('[SupportAnalysis] Inizializzazione modulo');

    // Event listeners
    const saveBtn = document.getElementById('save-support-data');
    const resetBtn = document.getElementById('reset-support-form');
    const askKbBtn = document.getElementById('ask-kb-btn');
    const validateWithContextBtn = document.getElementById('validate-with-context-btn');
    const syncPhaseBtn = document.getElementById('sync-phase-to-support');

    if (saveBtn) {
        saveBtn.addEventListener('click', handleSaveData);
    }

    if (resetBtn) {
        resetBtn.addEventListener('click', handleResetForm);
    }

    if (askKbBtn) {
        askKbBtn.addEventListener('click', handleKBQuery);
    }

    if (validateWithContextBtn) {
        validateWithContextBtn.addEventListener('click', handleValidateWithContext);
    }

    if (syncPhaseBtn) {
        syncPhaseBtn.addEventListener('click', syncPhaseToSupport);
    }

    // Bottone "Invia in Revisione"
    const btnReview = document.getElementById('btn-invia-revisione');
    if (btnReview) {
        btnReview.addEventListener('click', handleInviaInRevisione);
    }

    // Suggested queries
    document.querySelectorAll('.btn-suggestion').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const query = e.target.dataset.query;
            if (query) {
                const input = document.getElementById('kb-query-input');
                if (input) {
                    input.value = query;
                }
            }
        });
    });

    // Auto-dirty tracking on change (debounced)
    const formInputs = document.querySelectorAll('#support-form input, #support-form textarea');
    formInputs.forEach(input => {
        input.addEventListener('input', debounce(() => {
            supportState.isDirty = true;
        }, 500));
    });

    // Variable type select - mostra/nascondi campo testo per "Altro"
    const variableTypeSelect = document.getElementById('variable_type');
    const variableTypeCustom = document.getElementById('variable_type_custom');

    if (variableTypeSelect && variableTypeCustom) {
        variableTypeSelect.addEventListener('change', (e) => {
            if (e.target.value === 'other') {
                variableTypeCustom.style.display = 'block';
                variableTypeCustom.focus();
            } else {
                variableTypeCustom.style.display = 'none';
                variableTypeCustom.value = '';
            }
        });
    }
}

export async function loadSupportData(projectId) {
    if (!projectId) {
        console.warn('[SupportAnalysis] loadSupportData chiamato senza projectId');
        return;
    }

    supportState.projectId = projectId;
    supportState.isLoading = true;

    try {
        const response = await fetch(`/agata/admin/api/projects/${projectId}/support-analysis`);

        if (!response.ok) {
            if (response.status === 403) {
                console.warn('[SupportAnalysis] Non autorizzato a caricare dati');
                return;
            }
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        console.log('[SupportAnalysis] Dati caricati:', data);

        // Popola informazioni base (readonly)
        const infoProjectName = document.getElementById('info-project-name');
        const infoGaiaId = document.getElementById('info-gaia-id');
        const infoCoords = document.getElementById('info-coords');

        if (infoProjectName) {
            infoProjectName.textContent = data.project.title || '-';
        }
        if (infoGaiaId) {
            infoGaiaId.textContent = data.project.gaia_id || '-';
        }
        if (infoCoords) {
            const ra = data.project.ra ? data.project.ra.toFixed(6) : '-';
            const dec = data.project.dec_deg ? data.project.dec_deg.toFixed(6) : '-';
            infoCoords.textContent = `${ra}, ${dec}`;
        }

        // Popola form editabile
        const fields = [
            'spectral_class', 'teff', 'distance', 'luminosity', 'radius', 'mass',
            'color_bv', 'color_bprp', 'variable_type', 'catalog_identifiers',
            'variability_amplitude', 'passband', 'epoch'
        ];

        fields.forEach(field => {
            const input = document.getElementById(field);
            if (input && data.support_data[field] !== null && data.support_data[field] !== undefined) {
                input.value = data.support_data[field];
                // Reset highlight se già salvato
                input.style.backgroundColor = '';
            }
        });

        // ✅ Sincronizza il periodo salvato dal DB su ENTRAMBI i campi
        if (data.support_data.period && data.support_data.period > 0) {
            const periodValue = parseFloat(data.support_data.period);
            // 1. Popola chosenP (campo di analisi in fase)
            const chosenPEl = document.getElementById('chosenP');
            if (chosenPEl) {
                chosenPEl.value = periodValue.toFixed(6);
            }
            // 2. Popola info-period (display read-only in Analisi di Supporto)
            const infoPeriodEl = document.getElementById('info-period');
            if (infoPeriodEl) {
                infoPeriodEl.textContent = `${periodValue.toFixed(6)} d`;
            }
            console.log('[SupportAnalysis] Periodo sincronizzato dal DB:', periodValue.toFixed(6));
        }

        // Salva suggerimenti Gaia nello state (NON pre-popolare automaticamente)
        if (data.gaia_suggestions) {
            supportState.gaiaSuggestions = data.gaia_suggestions;
            console.log('[SupportAnalysis] Suggerimenti Gaia disponibili (usa bottone per caricare)');
        }

        supportState.formData = data.support_data;
        supportState.isDirty = false;

        console.log('[SupportAnalysis] Dati caricati con successo');

    } catch (error) {
        console.error('[SupportAnalysis] Errore caricamento:', error);
        // Non mostrare alert per errori di autorizzazione
        if (!error.message.includes('403')) {
            alert('Errore durante il caricamento dei dati: ' + error.message);
        }
    } finally {
        supportState.isLoading = false;
    }
}

async function handleSaveData() {
    if (!supportState.projectId) {
        alert('Nessun progetto caricato');
        return;
    }

    const saveBtn = document.getElementById('save-support-data');
    if (!saveBtn) return;

    // Raccogli dati form
    const formData = {};
    const fields = [
        'spectral_class', 'teff', 'distance', 'luminosity', 'radius', 'mass',
        'color_bv', 'color_bprp', 'variable_type', 'catalog_identifiers',
        'variability_amplitude', 'passband', 'epoch'
    ];

    // ✅ Salva SOLO il periodo da info-period (campo read-only che contiene il periodo scelto dalla fase)
    const infoPeriodEl = document.getElementById('info-period');
    if (infoPeriodEl && infoPeriodEl.textContent && infoPeriodEl.textContent !== '-') {
        // Estrai il numero dalla stringa (es: "0.567890 d" -> 0.567890)
        const periodMatch = infoPeriodEl.textContent.trim().match(/^([\d.]+)/);
        if (periodMatch && periodMatch[1]) {
            formData['period'] = parseFloat(periodMatch[1]);
            console.log('[SupportAnalysis] Periodo salvato:', formData['period']);
        }
    }

    fields.forEach(field => {
        const input = document.getElementById(field);
        if (input) {
            let value = input.value.trim();

            // Se il campo è variable_type e il valore è "other", usa il campo custom
            if (field === 'variable_type' && value === 'other') {
                const customInput = document.getElementById('variable_type_custom');
                if (customInput && customInput.value.trim()) {
                    value = customInput.value.trim();
                } else {
                    value = null; // Se non ha compilato il campo custom, salva null
                }
            }

            formData[field] = value === '' ? null : value;
        }
    });

    console.log('[SupportAnalysis] Salvando dati:', formData);

    // Loading state
    const originalText = saveBtn.textContent;
    saveBtn.disabled = true;
    saveBtn.textContent = '⏳ Salvataggio...';

    try {
        const response = await fetch(`/agata/admin/api/projects/${supportState.projectId}/support-analysis`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(formData)
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.error || `HTTP ${response.status}`);
        }

        const result = await response.json();
        supportState.isDirty = false;

        // Rimuovi highlight da campi salvati
        fields.forEach(field => {
            const input = document.getElementById(field);
            if (input) {
                input.style.backgroundColor = '';
                input.removeAttribute('title');
            }
        });

        // Feedback visivo success
        saveBtn.textContent = '✅ Salvato!';
        saveBtn.style.background = '#28a745';

        setTimeout(() => {
            saveBtn.textContent = originalText;
            saveBtn.style.background = '';
            saveBtn.disabled = false;
        }, 2000);

        console.log('[SupportAnalysis] Dati salvati con successo');

    } catch (error) {
        console.error('[SupportAnalysis] Errore salvataggio:', error);
        alert('Errore durante il salvataggio: ' + error.message);

        saveBtn.textContent = originalText;
        saveBtn.disabled = false;
    }
}

function handleResetForm() {
    if (!supportState.isDirty || confirm('Vuoi davvero resettare il form? Le modifiche non salvate andranno perse.')) {
        loadSupportData(supportState.projectId);
    }
}

async function handleKBQuery() {
    const queryInput = document.getElementById('kb-query-input');
    const query = queryInput ? queryInput.value.trim() : '';

    if (!query) {
        alert('Inserisci una domanda per il Knowledge Base');
        return;
    }

    if (!supportState.projectId) {
        alert('Nessun progetto caricato');
        return;
    }

    const askBtn = document.getElementById('ask-kb-btn');
    const responseContainer = document.getElementById('kb-response-container');
    const responseText = document.getElementById('kb-response-text');

    if (!askBtn || !responseContainer || !responseText) {
        console.error('[SupportAnalysis] Elementi KB UI non trovati');
        return;
    }

    // Loading state
    askBtn.disabled = true;
    askBtn.textContent = '⏳ Ricerca in corso...';
    responseContainer.style.display = 'none';

    console.log('[SupportAnalysis] Esecuzione query KB:', query);
    console.log('[SupportAnalysis] Project ID:', supportState.projectId);
    console.log('[SupportAnalysis] URL:', `/agata/admin/api/projects/${supportState.projectId}/kb-query`);
    console.log('[SupportAnalysis] Payload:', JSON.stringify({ query }));
    console.log('[SupportAnalysis] Comando equivalente CLI:');
    console.log(`python -m agata.kb ask "${query}"`);

    try {
        const response = await fetch(`/agata/admin/api/projects/${supportState.projectId}/kb-query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.error || `HTTP ${response.status}`);
        }

        const data = await response.json();
        console.log('[SupportAnalysis] Risultati KB:', data);
        console.log('[SupportAnalysis] Numero risultati:', data.results ? data.results.length : 0);
        if (data.results && data.results.length > 0) {
            console.log('[SupportAnalysis] Primo risultato:', data.results[0]);
        }

        // Mostra risposta LLM (come da CLI) oppure fallback a risultati raw
        if (data.success && data.answer) {
            // Mostra risposta generata da Cerebras LLM
            const answerHTML = `
                <div class="kb-llm-answer">
                    <h4 style="color: #059669; margin-top: 0;">🤖 Risposta da Knowledge Base:</h4>
                    <div style="white-space: pre-wrap; line-height: 1.6;">${escapeHtml(data.answer)}</div>
                </div>
                ${data.results && data.results.length > 0 ? `
                    <details style="margin-top: 1.5rem;">
                        <summary style="cursor: pointer; font-weight: 600; color: #64748b;">📚 Fonti utilizzate (${data.results.length})</summary>
                        <div style="margin-top: 0.5rem;">
                            ${data.results.map((result, idx) => `
                                <div class="kb-source-item" style="padding: 0.5rem; border-left: 3px solid #e2e8f0; margin: 0.5rem 0;">
                                    <strong>${idx + 1}. ${escapeHtml(result.title || 'Risultato')}</strong>
                                    <small style="display: block; color: #64748b; margin-top: 0.25rem;">
                                        Da: ${escapeHtml(result.from || 'Unknown')} |
                                        ${result.date ? new Date(result.date).toLocaleDateString('it-IT') : 'Data sconosciuta'} |
                                        Rilevanza: ${(result.score * 100).toFixed(1)}%
                                    </small>
                                </div>
                            `).join('')}
                        </div>
                    </details>
                ` : ''}
            `;
            responseText.innerHTML = answerHTML;
            responseContainer.style.display = 'block';
        } else if (data.success && data.results && data.results.length > 0) {
            // Fallback: mostra risultati raw se LLM fallisce
            const resultsHTML = `
                <p style="color: #f59e0b; margin-bottom: 1rem;">⚠️ Impossibile generare risposta LLM. Ecco i risultati raw:</p>
                ${data.results.map((result, idx) => `
                    <div class="kb-result-item">
                        <strong>${idx + 1}. ${escapeHtml(result.title || 'Risultato')}</strong>
                        <p>${escapeHtml(result.content || result.text || 'Nessun contenuto')}</p>
                        ${result.source ? `<small>Fonte: ${escapeHtml(result.source)}</small>` : ''}
                        ${result.score ? `<small style="margin-left: 1rem;">Score: ${(result.score * 100).toFixed(1)}%</small>` : ''}
                    </div>
                `).join('')}
            `;
            responseText.innerHTML = resultsHTML;
            responseContainer.style.display = 'block';
        } else {
            responseText.innerHTML = '<p>Nessun risultato trovato nel Knowledge Base. Prova a riformulare la domanda o contatta l\'amministratore.</p>';
            responseContainer.style.display = 'block';
        }

    } catch (error) {
        console.error('[SupportAnalysis] Errore query KB:', error);
        responseText.innerHTML = `<p style="color: #dc3545;"><strong>Errore:</strong> ${escapeHtml(error.message)}</p>`;
        responseContainer.style.display = 'block';
    } finally {
        askBtn.disabled = false;
        askBtn.textContent = '🔍 Chiedi a KB';
    }
}

// Funzione per pre-popolare query KB con domanda di validazione completezza
function handleValidateWithContext() {
    if (!supportState.projectId) {
        alert('Nessun progetto caricato');
        return;
    }

    // Raccogli tutti i dati dal form
    const formData = collectFormData();

    // Verifica che variable_type sia compilato
    if (!formData.variable_type) {
        alert('Compila il tipo di variabile nel menu "Parametri Fisici Stella"');
        return;
    }

    // Verifica che il periodo sia stato scelto
    if (!formData.period) {
        alert('Scegli il periodo corretto nella fase "Analisi Periodogramma"');
        return;
    }

    console.log('[SupportAnalysis] Pre-popolo query KB con domanda validazione');
    console.log('[SupportAnalysis] Dati form:', formData);

    // Costruisci query dettagliata per KB
    const query = buildValidationQuery(formData);

    console.log('[SupportAnalysis] Query generata:', query);

    // Popola il campo input KB
    const queryInput = document.getElementById('kb-query-input');
    if (queryInput) {
        queryInput.value = query;
        queryInput.focus();
        queryInput.select();  // Seleziona il testo per facile modifica
        console.log('[SupportAnalysis] Query input pre-popolo completato');
    } else {
        console.error('[SupportAnalysis] Campo kb-query-input non trovato');
        alert('Elemento input KB non trovato. Contatta l\'amministratore.');
        return;
    }

    // Scroll al campo input
    const kbSection = document.querySelector('[id="kb-section"]');
    if (kbSection) {
        kbSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    // Feedback visivo
    const validateBtn = document.querySelector('[id="validate-with-context-btn"]');
    if (validateBtn) {
        const originalText = validateBtn.textContent;
        validateBtn.textContent = '✅ Query Generata!';
        validateBtn.style.background = '#10b981';
        setTimeout(() => {
            validateBtn.textContent = originalText;
            validateBtn.style.background = '';
        }, 2000);
    }
}

// Costruisce query dettagliata per validare completezza dati
function buildValidationQuery(formData) {
    const parts = [];

    parts.push(`Valida completezza dati per stella variabile ${formData.variable_type}`);
    parts.push('');

    // Sezione tipo variabile
    parts.push(`Tipo variabile: ${formData.variable_type}`);

    // Sezione periodo
    if (formData.period) {
        parts.push(`Periodo: ${formData.period.toFixed(6)} giorni`);
    }

    // Sezione ampiezza
    if (formData.variability_amplitude) {
        parts.push(`Ampiezza: ${formData.variability_amplitude} magnitudini`);
    }

    // Sezione identificatori
    parts.push('');
    parts.push('Identificatori attuali:');
    const identifiers = parseIdentifiers(formData.catalog_identifiers);
    parts.push(`  - Gaia ID: ${identifiers.gaia_id ? '✓ ' + identifiers.gaia_id : '✗ MANCANTE'}`);
    parts.push(`  - VSX ID: ${identifiers.vsx_id ? '✓ ' + identifiers.vsx_id : '✗ mancante'}`);
    parts.push(`  - AAVSO ID: ${identifiers.aavso_id ? '✓ ' + identifiers.aavso_id : '✗ mancante'}`);

    // Sezione passband
    if (formData.passband) {
        parts.push(`Passband: ${formData.passband}`);
    }

    // Sezione spectral class
    if (formData.spectral_class) {
        parts.push(`Classe spettrale: ${formData.spectral_class}`);
    }

    // Domande specifiche per completezza
    parts.push('');
    parts.push('Domande di validazione:');
    parts.push(`1. Quali identificatori sono obbligatori per ${formData.variable_type}?`);
    parts.push(`2. Quali cataloghi astronomici raccomandi per analizzare ${formData.variable_type}?`);
    parts.push(`3. Quale precisione periodo è richiesta per ${formData.variable_type}?`);
    if (formData.variability_amplitude) {
        parts.push(`4. L'ampiezza ${formData.variability_amplitude} mag è coerente con ${formData.variable_type}?`);
    }
    parts.push('5. Mi mancano identificatori critici? Se sì, quali e come trovarli?');

    return parts.join('\n');
}

// Helper: estrae identificatori dal campo catalog_identifiers
function parseIdentifiers(catalogIdentifiersText) {
    const result = {
        gaia_id: null,
        vsx_id: null,
        aavso_id: null
    };

    if (!catalogIdentifiersText) return result;

    const text = catalogIdentifiersText.toLowerCase();

    // Estrai VSX ID (formato: VSX J123456 o vsx-j123456)
    const vsxMatch = catalogIdentifiersText.match(/vsx[- ]?j[\da-z]+/i);
    if (vsxMatch) result.vsx_id = vsxMatch[0];

    // Estrai AAVSO ID (formato: 000-ABC-123)
    const aavsoMatch = catalogIdentifiersText.match(/\d{3}-[a-z]{3}-\d{3}/i);
    if (aavsoMatch) result.aavso_id = aavsoMatch[0];

    // Estrai Gaia ID (formato: Gaia DR3 123456 o 123456789012345)
    const gaiaMatch = catalogIdentifiersText.match(/(?:gaia[- ]?dr3[- ])?(\d{15,})/);
    if (gaiaMatch) result.gaia_id = `Gaia DR3 ${gaiaMatch[1]}`;

    return result;
}

// Helper: raccoglie dati dal form
function collectFormData() {
    // Estrai il periodo da info-period (span che contiene "0.567890 d")
    let period = null;
    const infoPeriodEl = document.getElementById('info-period');
    if (infoPeriodEl && infoPeriodEl.textContent && infoPeriodEl.textContent !== '-') {
        // Estrai il numero dalla stringa (es: "0.567890 d" -> 0.567890)
        const periodMatch = infoPeriodEl.textContent.trim().match(/^([\d.]+)/);
        if (periodMatch && periodMatch[1]) {
            period = parseFloat(periodMatch[1]);
        }
    }

    return {
        spectral_class: document.getElementById('spectral_class')?.value?.trim() || '',
        teff: document.getElementById('teff')?.value || '',
        distance: document.getElementById('distance')?.value || '',
        luminosity: document.getElementById('luminosity')?.value || '',
        radius: document.getElementById('radius')?.value || '',
        mass: document.getElementById('mass')?.value || '',
        color_bv: document.getElementById('color_bv')?.value || '',
        color_bprp: document.getElementById('color_bprp')?.value || '',
        variable_type: document.getElementById('variable_type')?.value?.trim() || '',
        catalog_identifiers: document.getElementById('catalog_identifiers')?.value?.trim() || '',
        variability_amplitude: document.getElementById('variability_amplitude')?.value || '',
        passband: document.getElementById('passband')?.value?.trim() || '',
        epoch: document.getElementById('epoch')?.value || '',
        period: period  // Periodo dalla fase di analisi
    };
}

// Utility: debounce
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Utility: escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}

// Auto-popolazione periodo dal tab analisi in fase
export function updatePeriodFromPhase(period) {
    const infoPeriod = document.getElementById('info-period');

    if (infoPeriod && period) {
        infoPeriod.textContent = `${period.toFixed(6)} d`;
        console.log('[SupportAnalysis] Periodo visualizzato dal tab fase:', period);
    }
}

// Auto-popolazione ampiezza dal campo ampiezza manuale
export function updateAmplitudeFromManual(manualAmplitude) {
    const amplitudeInput = document.getElementById('variability_amplitude');

    if (amplitudeInput && manualAmplitude && manualAmplitude.min !== null && manualAmplitude.max !== null) {
        const amplitude = manualAmplitude.max - manualAmplitude.min;
        if (!amplitudeInput.value || parseFloat(amplitudeInput.value) === 0) {
            amplitudeInput.value = amplitude.toFixed(3);
            amplitudeInput.style.backgroundColor = '#d4edda'; // verde chiaro
            amplitudeInput.title = 'Caricato da ampiezza manuale';
            console.log('[SupportAnalysis] Ampiezza caricata da manuale:', amplitude.toFixed(3));
        }
    }
}

// =============================================================================
// INVIA IN REVISIONE - Validazione e API call
// =============================================================================

/**
 * Valida i campi obbligatori per l'invio in revisione
 * @returns {Array<string>} Array di nomi di campi mancanti, vuoto se validazione OK
 */
function validateRequiredFieldsForReview() {
    const missingFields = [];

    // Controlla periodo (da info-period span)
    const infoPeriodEl = document.getElementById('info-period');
    if (!infoPeriodEl || !infoPeriodEl.textContent || infoPeriodEl.textContent === '-') {
        missingFields.push('Periodo');
    }

    // Controlla Tipo di Variabile Proposta
    const variableTypeEl = document.getElementById('variable_type');
    if (!variableTypeEl || !variableTypeEl.value || variableTypeEl.value.trim() === '') {
        missingFields.push('Tipo di Variabile Proposta');
    }

    // Controlla Identificatori Cataloghi
    const catalogIdEl = document.getElementById('catalog_identifiers');
    if (!catalogIdEl || !catalogIdEl.value || catalogIdEl.value.trim() === '') {
        missingFields.push('Identificatori Cataloghi');
    }

    // Controlla Ampiezza Variabilità
    const amplitudeEl = document.getElementById('variability_amplitude');
    if (!amplitudeEl || !amplitudeEl.value || amplitudeEl.value.trim() === '') {
        missingFields.push('Ampiezza Variabilità');
    }

    // Controlla Passband
    const passbandEl = document.getElementById('passband');
    if (!passbandEl || !passbandEl.value || passbandEl.value.trim() === '') {
        missingFields.push('Passband');
    }

    // Controlla Epoch (Tempo di massimo/minimo)
    const epochEl = document.getElementById('epoch');
    if (!epochEl || !epochEl.value || epochEl.value.trim() === '') {
        missingFields.push('Epoch (Tempo di massimo/minimo)');
    }

    return missingFields;
}

/**
 * Handler per il bottone "Invia in Revisione"
 * Valida campi → Chiama API send-to-review → Invia a Slack
 */
async function handleInviaInRevisione() {
    const btn = document.getElementById('btn-invia-revisione');
    if (!btn) return;

    // Disabilita bottone durante operazione
    btn.disabled = true;
    const originalText = btn.innerHTML;
    btn.innerHTML = '⏳ Invio in corso...';

    try {
        // 1. Valida campi obbligatori
        const missingFields = validateRequiredFieldsForReview();
        if (missingFields.length > 0) {
            alert(`❌ Campi obbligatori mancanti:\n\n${missingFields.map(f => `• ${f}`).join('\n')}`);
            return;
        }

        // 2. Recupera project_id
        const projectIdInput = document.getElementById('projectId');
        const projectId = projectIdInput?.value;
        if (!projectId) {
            alert('❌ Project ID non trovato!');
            return;
        }

        // 3. Chiama API backend per inviare in revisione
        const response = await fetch(`/agata/admin/api/projects/${projectId}/send-to-review`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const result = await response.json();

        if (!response.ok) {
            // Errore dal backend
            const errorMsg = result.error || 'Errore sconosciuto';
            alert(`❌ Errore: ${errorMsg}`);
            return;
        }

        // 4. Se OK, invia i dati a Slack
        await exportSupportAnalysisToSlack();

        // 5. Aggiorna bottone e UI
        btn.disabled = true;
        btn.innerHTML = '✓ Già in Revisione';
        btn.style.background = '#cbd5e1';
        btn.style.color = '#64748b';
        btn.style.cursor = 'not-allowed';

        alert('✅ Progetto inviato in revisione e dati inviati a Slack!');

    } catch (error) {
        console.error('❌ Errore invio revisione:', error);
        alert(`❌ Errore: ${error.message}`);
    } finally {
        if (btn.innerHTML === '⏳ Invio in corso...') {
            btn.disabled = false;
            btn.innerHTML = originalText;
        }
    }
}

// Export per debugging
window.supportAnalysisDebug = {
    getState: () => supportState,
    loadData: loadSupportData,
    saveData: handleSaveData,
    validateForReview: validateRequiredFieldsForReview
};

// Export funzioni globali per aggiornamento periodo e ampiezza
window.updateSupportPeriod = updatePeriodFromPhase;
window.updateSupportAmplitude = updateAmplitudeFromManual;

// Sincronizza periodo, ampiezza ed epoch dal tab Analisi in Fase al tab Analisi di Supporto
export function syncPhaseToSupport() {
    // Leggi i VALORI ATTUALI dal tab Analisi in Fase
    const chosenP = document.getElementById('chosenP')?.value;
    const amplitudeEl = document.getElementById('variability_amplitude');
    const epochEl = document.getElementById('epoch');

    // Ricava ampiezza dalle barre manuali (da state globale)
    const manualAmplitude = window.phaseAnalysisState?.manualAmplitude;
    const epoch = window.phaseAnalysisState?.epoch;

    let syncCount = 0;

    // 1. Sincronizza periodo
    if (chosenP && chosenP.trim()) {
        const period = parseFloat(chosenP);
        if (isFinite(period)) {
            const infoPeriod = document.getElementById('info-period');
            if (infoPeriod) {
                infoPeriod.textContent = `${period.toFixed(6)} d`;
                syncCount++;
            }
        }
    }

    // 2. Sincronizza ampiezza (dalle barre)
    if (manualAmplitude && manualAmplitude.min !== null && manualAmplitude.max !== null) {
        const amplitude = Math.abs(manualAmplitude.max - manualAmplitude.min);
        if (amplitudeEl && amplitude > 0) {
            amplitudeEl.value = amplitude.toFixed(3);
            amplitudeEl.style.backgroundColor = '#d4edda';
            amplitudeEl.title = 'Sincronizzato dall\'Analisi in Fase';
            syncCount++;
        }
    }

    // 3. Sincronizza epoch
    if (epoch !== null && epoch !== undefined && isFinite(epoch) && epochEl) {
        epochEl.value = epoch.toFixed(5);
        epochEl.style.backgroundColor = '#d4edda';
        epochEl.title = 'Sincronizzato dall\'Analisi in Fase';
        syncCount++;
    }

    // Feedback visivo
    const syncBtn = document.getElementById('sync-phase-to-support');
    if (syncBtn) {
        const originalText = syncBtn.textContent;
        syncBtn.style.background = syncCount > 0 ? '#10b981' : '#ef4444';
        syncBtn.textContent = syncCount > 0 ? `✅ ${syncCount}` : '❌';

        setTimeout(() => {
            syncBtn.textContent = originalText;
            syncBtn.style.background = '';
        }, 1500);
    }

    if (syncCount > 0) {
        supportState.isDirty = true;
    }
}

// Export per uso globale
window.syncPhaseToSupport = syncPhaseToSupport;


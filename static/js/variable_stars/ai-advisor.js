/**
 * ai-advisor.js - AI-powered analysis and recommendations
 *
 * Gestisce l'interazione con Claude AI per analisi intelligente delle curve di luce:
 * - Valutazione qualità sessioni
 * - Suggerimenti pre-processing
 * - Raccomandazioni periodigramma
 * - Classificazione stelle variabili
 */

import { state, nameForSession } from './state.js';
import { buildArrowStreamJDMag } from '../common/utils-arrow.js';
import { logger } from '../common/logger.js';

// Create logger for this module
const log = logger('AIAdvisor');

/**
 * Send Arrow request to backend
 * @param {string} url - API endpoint URL
 * @param {Object} data - Data object with jd, mag, session_id arrays
 * @param {Object} options - Request options (expectJson, etc.)
 * @returns {Promise<Object>} - Response data
 */
async function sendArrowRequest(url, data, options = {}) {
    const { expectJson = false } = options;

    // Build Arrow stream from data
    const stream = buildArrowStreamJDMag(data.jd, data.mag, data.session_id);

    // Send POST request
    const response = await fetch(url, {
        method: 'POST',
        body: stream,
        headers: {
            'Content-Type': 'application/vnd.apache.arrow.stream'
        }
    });

    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP ${response.status}: ${errorText}`);
    }

    // Parse response
    if (expectJson) {
        return await response.json();
    } else {
        return await response.arrayBuffer();
    }
}

/**
 * Stato modulo AI Advisor
 */
const aiState = {
    lastAnalysis: null,
    isAnalyzing: false
};

/**
 * Inizializza AI Advisor
 */
export function initAIAdvisor() {
    log.info('Inizializzazione AI Advisor');

    const btn = document.getElementById('runAIAnalysis');
    if (btn) {
        btn.addEventListener('click', runAIAnalysis);
    }

    // Se ci sono già dati, mostra empty state
    if (state.jd && state.jd.length > 0) {
        showEmptyState();
    }
}

/**
 * Esegue analisi AI sui dati correnti
 */
export async function runAIAnalysis() {
    log.info('Avvio analisi AI');

    // Verifica che ci siano dati
    if (!state.jd || state.jd.length === 0) {
        alert('Carica prima dei dati!');
        return;
    }

    if (aiState.isAnalyzing) {
        log.debug('Analisi già in corso, skip');
        return;
    }

    aiState.isAnalyzing = true;

    try {
        // Mostra loading state
        showLoadingState();

        // Prepara dati per invio
        const arrowData = {
            jd: state.jd,
            mag: state.mag,
            session_id: state.session
        };

        // Parametri query
        const params = new URLSearchParams();

        // Se abbiamo risultati periodigramma, includi
        if (state.periodogramResult && state.periodogramResult.periods) {
            params.set('has_periodogram', 'true');

            const periods = state.periodogramResult.periods.slice(0, 5); // Max 5
            const amplitudes = state.periodogramResult.amplitudes?.slice(0, 5) || [];

            params.set('periods', JSON.stringify(periods));
            params.set('amplitudes', JSON.stringify(amplitudes));
        }

        log.info(`Invio richiesta con ${state.jd.length} punti, ${state.uniqueSessions?.length || 0} sessioni`);

        // Chiama API
        const url = `/agata/variable-stars/api/analyze_with_llm.arrow?${params.toString()}`;
        const result = await sendArrowRequest(url, arrowData, { expectJson: true });

        log.info('Analisi completata', result);

        // Salva risultati
        aiState.lastAnalysis = result;

        // Mostra risultati
        displayAnalysisResults(result);

    } catch (error) {
        log.error('Errore analisi', error);
        showErrorState(error.message || 'Errore durante l\'analisi AI');
    } finally {
        aiState.isAnalyzing = false;
    }
}

/**
 * Mostra loading state
 */
function showLoadingState() {
    document.getElementById('aiEmptyState').style.display = 'none';
    document.getElementById('aiResults').style.display = 'none';
    document.getElementById('aiLoadingState').style.display = 'block';
}

/**
 * Mostra empty state
 */
function showEmptyState() {
    document.getElementById('aiLoadingState').style.display = 'none';
    document.getElementById('aiResults').style.display = 'none';
    document.getElementById('aiEmptyState').style.display = 'block';
}

/**
 * Mostra errore
 */
function showErrorState(message) {
    document.getElementById('aiLoadingState').style.display = 'none';
    document.getElementById('aiResults').style.display = 'none';

    const emptyState = document.getElementById('aiEmptyState');
    emptyState.style.display = 'block';
    emptyState.innerHTML = `
        <div style="font-size:64px; margin-bottom:20px;">⚠️</div>
        <h3 style="margin:0 0 12px 0; font-size:20px; color:#dc2626;">Errore Analisi</h3>
        <p style="margin:0; color:#64748b; font-size:14px;">${escapeHtml(message)}</p>
        <button onclick="location.reload()" style="margin-top:20px; padding:10px 20px; background:#6366f1; color:white; border:none; border-radius:6px; cursor:pointer;">
            Riprova
        </button>
    `;
}

/**
 * Visualizza risultati analisi
 */
function displayAnalysisResults(result) {
    log.debug('Rendering risultati');

    const analysis = result.analysis;

    // Nascondi loading/empty, mostra results
    document.getElementById('aiLoadingState').style.display = 'none';
    document.getElementById('aiEmptyState').style.display = 'none';
    document.getElementById('aiResults').style.display = 'block';

    // 1. Summary
    document.getElementById('aiSummaryText').textContent = result.summary || 'Analisi completata';

    // 2. Warnings (sostituisci ID sessioni con nomi)
    if (result.warnings && result.warnings.length > 0) {
        const warningsCard = document.getElementById('aiWarningsCard');
        const warningsList = document.getElementById('aiWarningsList');

        warningsCard.style.display = 'block';
        warningsList.innerHTML = result.warnings
            .map(w => {
                // Sostituisci "Sessione X:" con il nome della sessione
                let warning = w;
                const sessionMatch = warning.match(/Sessione (\d+):/);
                if (sessionMatch) {
                    const sessionId = parseInt(sessionMatch[1]);
                    const sessionName = nameForSession(sessionId);
                    warning = warning.replace(`Sessione ${sessionId}:`, `${sessionName}:`);
                }
                return `<li>${escapeHtml(warning)}</li>`;
            })
            .join('');
    } else {
        document.getElementById('aiWarningsCard').style.display = 'none';
    }

    // 3. Session Quality
    renderSessionQuality(analysis.session_quality);

    // 3b. Session Homogeneity (se ci sono più di 1 sessione)
    if (result.homogeneity && Object.keys(result.homogeneity).length > 0) {
        renderHomogeneityAnalysis(result.homogeneity);
    } else {
        document.getElementById('aiHomogeneityCard').style.display = 'none';
    }

    // 4. Preprocessing Suggestions
    renderPreprocessingSuggestions(analysis.preprocessing_suggestions);

    // 5. Periodogram Recommendations
    renderPeriodogramRecommendations(analysis.periodogram_recommendations);

    // 6. Variable Classification (se presente)
    if (analysis.variable_classification) {
        renderVariableClassification(analysis.variable_classification);
    } else {
        document.getElementById('aiClassificationCard').style.display = 'none';
    }

    log.debug('Risultati visualizzati');
}

/**
 * Render qualità sessioni
 */
function renderSessionQuality(sessionQuality) {
    if (!sessionQuality || !sessionQuality.sessions) {
        document.getElementById('aiSessionQuality').innerHTML = '<p style="color:#64748b;">Nessuna informazione disponibile</p>';
        return;
    }

    const sessions = sessionQuality.sessions;
    const overallScore = sessionQuality.overall_score || calculateOverallScore(sessions);

    // Trova sessioni problematiche (score < 5 = critiche, < 7 = medio-basse)
    const criticalSessions = Object.entries(sessions)
        .filter(([_, info]) => (info.score || 0) < 5)
        .map(([sid, _]) => parseInt(sid));

    const lowQualitySessions = Object.entries(sessions)
        .filter(([_, info]) => (info.score || 0) < 7)
        .map(([sid, _]) => parseInt(sid));

    let html = `
        <div style="background:#f8fafc; padding:16px; border-radius:8px; margin-bottom:16px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-weight:600; color:#475569;">Punteggio Globale:</span>
                <span style="font-size:24px; font-weight:700; color:${getScoreColor(overallScore)};">
                    ${overallScore.toFixed(1)}/10
                </span>
            </div>
        </div>
    `;

    // Bottoni per disabilitare sessioni problematiche
    if (criticalSessions.length > 0 || lowQualitySessions.length > 0) {
        html += `
            <div style="margin-bottom:16px; padding:12px; background:#fef2f2; border:1px solid #fca5a5; border-radius:8px;">
                <div style="margin-bottom:8px;">
                    <span style="font-size:13px; color:#991b1b; font-weight:600;">
                        ⚡ Azioni Rapide Sessioni
                    </span>
                </div>
                <div style="display:flex; gap:8px; flex-wrap:wrap;">
        `;

        if (criticalSessions.length > 0) {
            html += `
                    <button onclick="disableProblematicSessions(${JSON.stringify(criticalSessions)})"
                            class="btn-primary"
                            style="padding:6px 12px; font-size:12px; background:#dc2626;">
                        🗑️ Disabilita Critiche (&lt;5): ${criticalSessions.length}
                    </button>
            `;
        }

        if (lowQualitySessions.length > criticalSessions.length) {
            html += `
                    <button onclick="disableProblematicSessions(${JSON.stringify(lowQualitySessions)})"
                            class="btn-primary"
                            style="padding:6px 12px; font-size:12px; background:#f59e0b;">
                        ⚠️ Disabilita Medio-Basse (&lt;7): ${lowQualitySessions.length}
                    </button>
            `;
        }

        html += `
                </div>
            </div>
        `;
    }

    // Sessioni individuali
    Object.entries(sessions).forEach(([sid, info]) => {
        const score = info.score || 0;
        const scoreClass = score >= 7 ? 'high' : score >= 4 ? 'medium' : 'low';
        const sessionName = nameForSession(parseInt(sid));
        const isActive = state.activeSession.get(parseInt(sid)) !== false;

        html += `
            <div class="ai-session-item" style="${!isActive ? 'opacity:0.5; background:#f9fafb;' : ''}">
                <div>
                    <strong style="color:#1e293b;">
                        ${sessionName}
                        ${!isActive ? '<span style="color:#9ca3af; font-size:11px;">(disabilitata)</span>' : ''}
                        <a href="#" onclick="scrollToSession(${sid}); return false;"
                           style="margin-left:8px; color:#2563eb; text-decoration:none; font-size:11px;"
                           title="Vai alla sessione nella sidebar">
                            🔗
                        </a>
                    </strong>
                    ${info.issues && info.issues.length > 0 ? `
                        <ul style="margin:8px 0 0 0; padding-left:20px; font-size:13px; color:#64748b;">
                            ${info.issues.map(issue => `<li>${escapeHtml(issue)}</li>`).join('')}
                        </ul>
                    ` : ''}
                    ${info.recommendations && info.recommendations.length > 0 ? `
                        <div style="margin-top:8px; padding:8px; background:#f0f9ff; border-left:3px solid #3b82f6; border-radius:4px;">
                            <strong style="font-size:12px; color:#1e40af;">💡 Raccomandazioni:</strong>
                            <ul style="margin:4px 0 0 0; padding-left:20px; font-size:12px; color:#1e40af;">
                                ${info.recommendations.map(rec => `<li>${escapeHtml(rec)}</li>`).join('')}
                            </ul>
                        </div>
                    ` : ''}
                </div>
                <span class="ai-score-badge ai-score-${scoreClass}">
                    ${score.toFixed(1)}
                </span>
            </div>
        `;
    });

    document.getElementById('aiSessionQuality').innerHTML = html;
}

/**
 * Render analisi omogeneità tra sessioni
 */
function renderHomogeneityAnalysis(homogeneity) {
    log.debug('Rendering omogeneità', homogeneity);

    const card = document.getElementById('aiHomogeneityCard');
    const container = document.getElementById('aiHomogeneity');

    // Se non ci sono dati utili, nascondi
    if (!homogeneity || Object.keys(homogeneity).length === 0) {
        card.style.display = 'none';
        return;
    }

    card.style.display = 'block';

    let html = '';

    // 1. OFFSET SISTEMATICI
    if (homogeneity.offset_range !== undefined) {
        const offsetOk = homogeneity.offset_range < 0.2;
        const offsetColor = offsetOk ? '#10b981' : '#f59e0b';
        const offsetIcon = offsetOk ? '✓' : '⚠️';

        html += `
            <div style="background:#f8fafc; padding:14px; border-radius:8px; margin-bottom:12px; border-left:4px solid ${offsetColor};">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <strong style="color:#1e293b;">📊 Offset Magnitudine</strong>
                    <span style="font-size:18px; font-weight:700; color:${offsetColor};">
                        ${offsetIcon} ${homogeneity.offset_range.toFixed(3)} mag
                    </span>
                </div>
                <p style="margin:8px 0 0 0; font-size:13px; color:#64748b;">
                    ${offsetOk
                        ? 'Range di offset tra sessioni accettabile (<0.2 mag)'
                        : 'ATTENZIONE: Differenze sistematiche tra sessioni potrebbero indicare disomogeneità fotometrica. Considera zero-alignment.'
                    }
                </p>
            </div>
        `;
    }

    // 2. SCATTER FOTOMETRICO (MAD ratio)
    if (homogeneity.mad_ratio !== undefined && homogeneity.mad_ratio > 0) {
        const madOk = homogeneity.mad_ratio < 2.0;
        const madColor = madOk ? '#10b981' : '#f59e0b';
        const madIcon = madOk ? '✓' : '⚠️';

        html += `
            <div style="background:#f8fafc; padding:14px; border-radius:8px; margin-bottom:12px; border-left:4px solid ${madColor};">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <strong style="color:#1e293b;">📉 Variazione Scatter (MAD)</strong>
                    <span style="font-size:18px; font-weight:700; color:${madColor};">
                        ${madIcon} ${homogeneity.mad_ratio.toFixed(2)}x
                    </span>
                </div>
                <p style="margin:8px 0 0 0; font-size:13px; color:#64748b;">
                    ${madOk
                        ? 'Qualità fotometrica consistente tra sessioni'
                        : 'ATTENZIONE: Scatter fotometrico molto variabile tra sessioni. Alcune sessioni potrebbero avere dati di qualità inferiore.'
                    }
                </p>
            </div>
        `;
    }

    // 3. PERIODI SPURII
    if (homogeneity.spurious_period_warnings && homogeneity.spurious_period_warnings.length > 0) {
        html += `
            <div style="background:#fef2f2; padding:14px; border-radius:8px; margin-bottom:12px; border-left:4px solid #dc2626;">
                <strong style="color:#991b1b;">🚨 Periodi Sospetti Rilevati</strong>
                <p style="margin:6px 0; font-size:13px; color:#7f1d1d;">
                    I seguenti periodi sono vicini alla durata di singole sessioni e potrebbero essere artefatti:
                </p>
                <ul style="margin:8px 0 0 0; padding-left:20px; font-size:13px; color:#7f1d1d;">
        `;

        homogeneity.spurious_period_warnings.forEach(warning => {
            const sessionName = nameForSession(warning.session_id);
            html += `
                <li>
                    <strong>Periodo ${warning.period.toFixed(3)}d</strong> (rank #${warning.period_rank})
                    ≈ durata ${sessionName} (${warning.session_duration.toFixed(1)}d)
                </li>
            `;
        });

        html += `
                </ul>
                <p style="margin:8px 0 0 0; font-size:12px; color:#991b1b; font-style:italic;">
                    💡 Questi periodi potrebbero non essere reali variabilità stellari ma effetti di campionamento.
                </p>
            </div>
        `;
    }

    // 4. OUTLIER DOMINANTI
    if (homogeneity.outlier_analysis && Object.keys(homogeneity.outlier_analysis).length > 0) {
        html += `
            <div style="background:#fff7ed; padding:14px; border-radius:8px; margin-bottom:12px; border-left:4px solid #f59e0b;">
                <strong style="color:#92400e;">⚡ Sessioni con Outlier Eccessivi</strong>
                <p style="margin:6px 0; font-size:13px; color:#92400e;">
                    Le seguenti sessioni hanno più del 10% di punti outlier:
                </p>
                <ul style="margin:8px 0 0 0; padding-left:20px; font-size:13px; color:#92400e;">
        `;

        Object.entries(homogeneity.outlier_analysis).forEach(([sid, info]) => {
            const sessionName = nameForSession(parseInt(sid));
            const pct = (info.outlier_fraction * 100).toFixed(1);
            html += `
                <li>
                    <strong>${sessionName}</strong>: ${info.outlier_count} outlier (${pct}%)
                    <a href="#" onclick="scrollToSession(${sid}); return false;"
                       style="margin-left:8px; color:#2563eb; text-decoration:underline; font-size:12px;">
                        Vai alla sessione →
                    </a>
                </li>
            `;
        });

        html += `
                </ul>
            </div>
        `;
    }

    // 5. TABELLA MEDIANE PER SESSIONE (collapsable)
    if (homogeneity.session_medians && Object.keys(homogeneity.session_medians).length > 1) {
        html += `
            <details style="background:#f8fafc; padding:14px; border-radius:8px; margin-bottom:12px;">
                <summary style="cursor:pointer; font-weight:600; color:#475569;">
                    📋 Dettagli per Sessione (click per espandere)
                </summary>
                <table style="width:100%; margin-top:12px; font-size:13px; border-collapse:collapse;">
                    <thead>
                        <tr style="background:#e2e8f0; text-align:left;">
                            <th style="padding:8px;">Sessione</th>
                            <th style="padding:8px;">Mediana (mag)</th>
                            <th style="padding:8px;">MAD</th>
                            <th style="padding:8px;">Azioni</th>
                        </tr>
                    </thead>
                    <tbody>
        `;

        Object.entries(homogeneity.session_medians).forEach(([sid, median]) => {
            const sessionName = nameForSession(parseInt(sid));
            const mad = homogeneity.session_mads?.[sid] || 'N/A';
            const madStr = typeof mad === 'number' ? mad.toFixed(4) : mad;

            html += `
                <tr style="border-bottom:1px solid #e2e8f0;">
                    <td style="padding:8px;"><strong>${sessionName}</strong></td>
                    <td style="padding:8px;">${median.toFixed(4)}</td>
                    <td style="padding:8px;">${madStr}</td>
                    <td style="padding:8px;">
                        <a href="#" onclick="scrollToSession(${sid}); return false;"
                           style="color:#2563eb; text-decoration:underline; font-size:12px;">
                            Visualizza →
                        </a>
                    </td>
                </tr>
            `;
        });

        html += `
                    </tbody>
                </table>
            </details>
        `;
    }

    // Bottoni azioni rapide
    const lowScoreSessions = [];
    if (homogeneity.outlier_analysis) {
        Object.keys(homogeneity.outlier_analysis).forEach(sid => {
            lowScoreSessions.push(parseInt(sid));
        });
    }

    if (lowScoreSessions.length > 0) {
        html += `
            <div style="margin-top:16px; padding:12px; background:#f0f9ff; border:1px solid #3b82f6; border-radius:8px;">
                <strong style="color:#1e40af; font-size:14px;">⚡ Azioni Rapide</strong>
                <div style="display:flex; gap:8px; margin-top:10px; flex-wrap:wrap;">
                    <button onclick="disableProblematicSessions(${JSON.stringify(lowScoreSessions)})"
                            class="btn-primary"
                            style="padding:6px 12px; font-size:13px; background:#dc2626;">
                        🗑️ Disabilita Sessioni con Outlier Eccessivi
                    </button>
                </div>
            </div>
        `;
    }

    container.innerHTML = html;
}

/**
 * Scrolla alla sessione nella sidebar (helper function)
 */
window.scrollToSession = function(sessionId) {
    const checkbox = document.getElementById(`cb${sessionId}`);
    if (checkbox) {
        checkbox.scrollIntoView({ behavior: 'smooth', block: 'center' });
        // Highlight temporaneo
        const label = checkbox.parentElement;
        const originalBg = label.style.backgroundColor;
        label.style.backgroundColor = '#fef3c7';
        setTimeout(() => {
            label.style.backgroundColor = originalBg;
        }, 2000);
    } else {
        alert(`Sessione ${nameForSession(sessionId)} non trovata nella sidebar`);
    }
};

/**
 * Render suggerimenti preprocessing
 */
function renderPreprocessingSuggestions(suggestions) {
    if (!suggestions || suggestions.length === 0) {
        document.getElementById('aiPreprocessing').innerHTML = `
            <p style="color:#10b981; font-weight:500;">✓ Nessun preprocessing necessario - dati ottimali!</p>
        `;
        return;
    }

    // Ordina per priorità
    const priorityOrder = { high: 0, medium: 1, low: 2 };
    const sorted = [...suggestions].sort((a, b) =>
        priorityOrder[a.priority] - priorityOrder[b.priority]
    );

    let html = '';

    sorted.forEach(sug => {
        const priority = sug.priority || 'medium';
        const action = sug.action || 'Azione non specificata';
        const reason = sug.reason || '';
        const params = sug.parameters || {};

        html += `
            <div class="ai-suggestion ai-suggestion-${priority}">
                <div class="ai-suggestion-header">
                    <span class="ai-suggestion-action">${getActionIcon(action)} ${formatAction(action)}</span>
                    <span class="ai-priority-badge ai-priority-${priority}">${priority}</span>
                </div>
                <p style="margin:8px 0 0 0; color:#475569; font-size:14px; line-height:1.6;">
                    ${escapeHtml(reason)}
                </p>
                ${Object.keys(params).length > 0 ? `
                    <div style="margin-top:10px; padding:10px; background:#f8fafc; border-radius:6px; font-size:13px;">
                        <strong style="color:#64748b;">Parametri suggeriti:</strong>
                        <ul style="margin:6px 0 0 0; padding-left:20px; color:#64748b;">
                            ${Object.entries(params).map(([k, v]) => {
                                // Se il parametro è session_id, mostra il nome invece dell'ID
                                if (k === 'session_id' && typeof v === 'number') {
                                    return `<li><code>${k}</code>: ${nameForSession(v)} (ID: ${v})</li>`;
                                }
                                return `<li><code>${k}</code>: ${JSON.stringify(v)}</li>`;
                            }).join('')}
                        </ul>
                    </div>
                ` : ''}
            </div>
        `;
    });

    document.getElementById('aiPreprocessing').innerHTML = html;
}

/**
 * Render raccomandazioni periodigramma
 */
function renderPeriodogramRecommendations(recommendations) {
    if (!recommendations) {
        document.getElementById('aiPeriodogram').innerHTML = '<p style="color:#64748b;">Nessuna raccomandazione disponibile</p>';
        return;
    }

    const minP = recommendations.min_period || 0.1;
    const maxP = recommendations.max_period || 10;
    const reasoning = recommendations.reasoning || 'Nessuna motivazione fornita';

    const html = `
        <div style="background:#f0f9ff; border:2px solid #3b82f6; border-radius:10px; padding:16px; margin-bottom:12px;">
            <div style="display:flex; justify-content:space-around; margin-bottom:16px;">
                <div style="text-align:center;">
                    <div style="font-size:11px; color:#1e40af; font-weight:600; margin-bottom:4px;">MIN PERIODO</div>
                    <div style="font-size:24px; font-weight:700; color:#1e40af;">${minP.toFixed(4)}d</div>
                </div>
                <div style="width:2px; background:#3b82f6; opacity:0.3;"></div>
                <div style="text-align:center;">
                    <div style="font-size:11px; color:#1e40af; font-weight:600; margin-bottom:4px;">MAX PERIODO</div>
                    <div style="font-size:24px; font-weight:700; color:#1e40af;">${maxP.toFixed(4)}d</div>
                </div>
            </div>
            <div style="padding-top:12px; border-top:1px solid #bfdbfe;">
                <strong style="font-size:13px; color:#1e40af;">📝 Motivazione:</strong>
                <p style="margin:6px 0 0 0; color:#1e40af; font-size:13px; line-height:1.6;">
                    ${escapeHtml(reasoning)}
                </p>
            </div>
        </div>
        <button onclick="applyPeriodogramRecommendations(${minP}, ${maxP})"
                class="btn-primary"
                style="width:100%; padding:12px; font-size:14px; font-weight:600;">
            📈 Applica Range al Periodigramma
        </button>
    `;

    document.getElementById('aiPeriodogram').innerHTML = html;
}

/**
 * Render classificazione variabile
 */
function renderVariableClassification(classification) {
    if (!classification || !classification.type) {
        document.getElementById('aiClassificationCard').style.display = 'none';
        return;
    }

    document.getElementById('aiClassificationCard').style.display = 'block';

    const type = classification.type;
    const confidence = classification.confidence || 'medium';
    const reasoning = classification.reasoning || '';
    const alternatives = classification.alternative_types || [];

    const confidencePercent = confidence === 'high' ? 90 : confidence === 'medium' ? 60 : 30;

    const html = `
        <div class="ai-classification">
            <div class="ai-classification-type">⭐ ${escapeHtml(type)}</div>
            <div style="display:flex; align-items:center; gap:12px; margin-bottom:12px;">
                <span style="font-size:13px; font-weight:600; color:#1e40af;">Confidenza:</span>
                <div style="flex:1;">
                    <div class="ai-confidence-bar">
                        <div class="ai-confidence-fill" style="width:${confidencePercent}%;"></div>
                    </div>
                </div>
                <span style="font-size:14px; font-weight:700; color:#1e40af;">${confidencePercent}%</span>
            </div>
            <p style="margin:0; color:#1e40af; font-size:14px; line-height:1.6;">
                ${escapeHtml(reasoning)}
            </p>
            ${alternatives.length > 0 ? `
                <div style="margin-top:16px; padding-top:16px; border-top:1px solid #bfdbfe;">
                    <strong style="font-size:13px; color:#1e40af;">🔄 Tipi alternativi:</strong>
                    <div style="display:flex; gap:8px; margin-top:8px; flex-wrap:wrap;">
                        ${alternatives.map(alt => `
                            <span style="padding:6px 12px; background:white; border:1px solid #3b82f6; border-radius:20px; font-size:12px; color:#1e40af;">
                                ${escapeHtml(alt)}
                            </span>
                        `).join('')}
                    </div>
                </div>
            ` : ''}
        </div>
    `;

    document.getElementById('aiClassification').innerHTML = html;
}

/**
 * Applica range periodigramma suggerito
 */
window.applyPeriodogramRecommendations = function(minP, maxP) {
    log.info(`Applicazione range periodigramma: ${minP} - ${maxP}`);

    const minPInput = document.getElementById('minP');
    const maxPInput = document.getElementById('maxP');

    if (minPInput) minPInput.value = minP.toFixed(4);
    if (maxPInput) maxPInput.value = maxP.toFixed(4);

    // Switch al tab periodigramma
    const periodTab = document.querySelector('.tab-btn[onclick*="tab-period"]');
    if (periodTab) periodTab.click();

    alert('✓ Range periodigramma aggiornato!\nPremi "Calcola" per eseguire l\'analisi.');
};

/**
 * Disabilita automaticamente sessioni problematiche suggerite dall'AI
 */
window.disableProblematicSessions = function(sessionIds) {
    if (!sessionIds || sessionIds.length === 0) {
        return;
    }

    // Mostra conferma
    const sessionNames = sessionIds.map(sid => nameForSession(sid)).join(', ');
    const confirmed = confirm(
        `Vuoi disabilitare ${sessionIds.length} sessione/i problematiche?\n\n` +
        `Sessioni: ${sessionNames}\n\n` +
        `Potrai riattivarle manualmente dalla sidebar.`
    );

    if (!confirmed) {
        return;
    }

    log.info(`Disabilitazione automatica sessioni: ${sessionIds}`);

    // Disabilita sessioni
    let disabledCount = 0;
    sessionIds.forEach(sid => {
        const wasActive = state.activeSession.get(sid) !== false;
        if (wasActive) {
            state.activeSession.set(sid, false);
            disabledCount++;

            // Trova e deseleziona checkbox nella sidebar (id="cb${sid}")
            const checkbox = document.getElementById(`cb${sid}`);
            if (checkbox && checkbox.checked) {
                checkbox.checked = false;
                // Trigger evento change per aggiornare UI
                checkbox.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }
    });

    if (disabledCount > 0) {
        alert(`✓ ${disabledCount} sessione/i disabilitate con successo!\n\nI grafici sono stati aggiornati.`);

        // Re-render AI results per aggiornare lo stato visivo
        if (aiState.lastAnalysis) {
            displayAnalysisResults(aiState.lastAnalysis);
        }
    } else {
        alert('Tutte le sessioni selezionate erano già disabilitate.');
    }
};

/**
 * Utility: calcola punteggio globale da sessioni
 */
function calculateOverallScore(sessions) {
    const scores = Object.values(sessions)
        .map(s => s.score || 0)
        .filter(s => s > 0);

    if (scores.length === 0) return 5;

    return scores.reduce((a, b) => a + b, 0) / scores.length;
}

/**
 * Utility: colore score
 */
function getScoreColor(score) {
    if (score >= 7) return '#10b981';
    if (score >= 4) return '#f59e0b';
    return '#dc2626';
}

/**
 * Utility: icona azione
 */
function getActionIcon(action) {
    const icons = {
        zero_align: '🎯',
        detrending: '📉',
        sigma_clip: '🔍',
        remove_session: '🗑️',
        merge_sessions: '🔗'
    };
    return icons[action] || '⚙️';
}

/**
 * Utility: formatta nome azione
 */
function formatAction(action) {
    const names = {
        zero_align: 'Allineamento Zero-Point',
        detrending: 'Rimozione Trend',
        sigma_clip: 'Sigma Clipping',
        remove_session: 'Rimuovi Sessione',
        merge_sessions: 'Unisci Sessioni'
    };
    return names[action] || action.replace(/_/g, ' ');
}

/**
 * Utility: escape HTML
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Esporta stato AI per debugging
 */
export function getAIState() {
    return aiState;
}

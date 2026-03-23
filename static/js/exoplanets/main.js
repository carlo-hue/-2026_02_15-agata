/**
 * exoplanets/main.js - Logica Principale Modulo Esopianeti
 * 
 * Gestisce:
 * - Caricamento dati transiti
 * - Esecuzione BLS
 * - Validazione fisica
 * - Plot interattivi (Plotly)
 * 
 * Autore: AGATA Project Team
 * Data: 2026-01-03
 */

// =============================================================================
// STATE GLOBALE
// =============================================================================

const state = {
    data: null,          // Dati curve di luce
    blsResults: null,    // Risultati BLS
    validation: null,    // Risultati validazione
    ephemeris: null,     // Effemeridi calcolate
    transits: null,      // Transiti individuali
    dataSource: 'synthetic',  // 'synthetic' o 'upload'
    uploadedFile: null   // Dati file caricato
};


// =============================================================================
// UTILITY: API CALLS
// =============================================================================

async function apiCall(endpoint, method = 'GET', body = null) {
    /**
     * Wrapper per chiamate API.
     */
    const options = {
        method: method,
        headers: {
            'Content-Type': 'application/json'
        }
    };
    
    if (body) {
        options.body = JSON.stringify(body);
    }
    
    const response = await fetch(endpoint, options);
    
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || `HTTP ${response.status}`);
    }
    
    return await response.json();
}


// =============================================================================
// GESTIONE SORGENTI DATI
// =============================================================================

function toggleDataSource(source) {
    /**
     * Cambia sorgente dati (synthetic/upload).
     */
    state.dataSource = source;
    
    console.log(`Data source: ${source}`);
    
    if (source === 'synthetic') {
        // Mostra pannello synthetic
        document.getElementById('synthetic-controls').classList.remove('hidden');
        document.getElementById('upload-panel').classList.add('hidden');
    } else {
        // Mostra pannello upload
        document.getElementById('synthetic-controls').classList.add('hidden');
        document.getElementById('upload-panel').classList.remove('hidden');
    }
    
    // Reset dati
    state.data = null;
    state.blsResults = null;
    document.getElementById('bls-panel').classList.add('hidden');
    document.getElementById('results-panel').classList.add('hidden');
    document.getElementById('ephemeris-panel').classList.add('hidden');
}


// =============================================================================
// UPLOAD FILE
// =============================================================================

async function uploadFile() {
    /**
     * Upload e parse file osservazioni.
     */
    const fileInput = document.getElementById('file-input');
    const file = fileInput.files[0];
    
    if (!file) {
        alert('Seleziona un file!');
        return;
    }
    
    console.log(`Uploading file: ${file.name}, size: ${file.size} bytes`);
    
    // Show loading
    document.getElementById('upload-loading').classList.remove('hidden');
    document.getElementById('upload-results').classList.add('hidden');
    
    try {
        // Prepare form data
        const formData = new FormData();
        formData.append('file', file);
        
        // Upload
        const response = await fetch('/agata/exoplanets/api/upload', {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || `HTTP ${response.status}`);
        }
        
        const data = await response.json();
        
        console.log('Upload successful:', data);
        
        // Save to state
        state.uploadedFile = data;
        state.data = {
            jd: data.jd,
            flux: data.flux,
            n_points: data.metadata.n_points,
            params: {
                source: 'uploaded',
                filename: data.filename,
                ...data.metadata
            }
        };
        
        // Show results
        showUploadResults(data);
        
        // Plot preview
        plotLightcurve(state.data);
        
        // Enable BLS
        document.getElementById('bls-panel').classList.remove('hidden');
        
        // Auto-set period range based on baseline
        const baseline = data.metadata.baseline_days;
        document.getElementById('period-min').value = Math.max(0.5, baseline * 0.01).toFixed(1);
        document.getElementById('period-max').value = Math.min(baseline * 0.5, 30).toFixed(1);
        
    } catch (error) {
        console.error('Upload error:', error);
        alert(`Errore upload: ${error.message}`);
    } finally {
        document.getElementById('upload-loading').classList.add('hidden');
    }
}


function showUploadResults(data) {
    /**
     * Mostra risultati upload e validazione.
     */
    const meta = data.metadata;
    
    // Metadata grid
    const metadataDiv = document.getElementById('upload-metadata');
    metadataDiv.innerHTML = `
        <div class="meta-item">
            <span class="meta-label">File:</span>
            <span class="meta-value">${data.filename}</span>
        </div>
        <div class="meta-item">
            <span class="meta-label">Punti:</span>
            <span class="meta-value">${meta.n_points.toLocaleString()}</span>
        </div>
        <div class="meta-item">
            <span class="meta-label">Baseline:</span>
            <span class="meta-value">${meta.baseline_days.toFixed(1)} giorni</span>
        </div>
        <div class="meta-item">
            <span class="meta-label">Cadenza:</span>
            <span class="meta-value">${meta.median_cadence_minutes.toFixed(1)} min</span>
        </div>
        <div class="meta-item">
            <span class="meta-label">JD Range:</span>
            <span class="meta-value">${meta.jd_min.toFixed(2)} - ${meta.jd_max.toFixed(2)}</span>
        </div>
        <div class="meta-item">
            <span class="meta-label">Colonne:</span>
            <span class="meta-value">${meta.columns.join(', ')}</span>
        </div>
    `;
    
    // Validation warnings
    const validationDiv = document.getElementById('upload-validation');
    const val = data.validation;
    
    let validationHtml = '';
    
    if (val.is_valid) {
        validationHtml += '<div class="validation-success">✅ Dati validi per analisi</div>';
    } else {
        validationHtml += '<div class="validation-error">❌ Problemi con i dati</div>';
    }
    
    if (val.warnings.length > 0) {
        validationHtml += '<div class="warnings-list">';
        for (const warning of val.warnings) {
            const level = warning.startsWith('ERROR') ? 'error' : 
                         warning.startsWith('WARNING') ? 'warning' : 'info';
            validationHtml += `<div class="warning warning-${level}">${warning}</div>`;
        }
        validationHtml += '</div>';
    }
    
    validationDiv.innerHTML = validationHtml;
    
    // Show results panel
    document.getElementById('upload-results').classList.remove('hidden');
}


// =============================================================================
// CARICAMENTO DATI
// =============================================================================

async function loadData() {
    /**
     * Carica dati transiti esopianeti.
     */
    const planetType = document.getElementById('planet-type').value;
    const nTransits = parseInt(document.getElementById('n-transits').value);
    const seed = parseInt(document.getElementById('seed').value);
    
    console.log(`Loading data: ${planetType}, ${nTransits} transits, seed=${seed}`);
    
    // Show loading
    document.getElementById('loading').classList.remove('hidden');
    
    try {
        // API call
        const url = `/agata/exoplanets/api/lightcurve?planet_type=${planetType}&n_transits=${nTransits}&seed=${seed}`;
        const data = await apiCall(url);
        
        console.log(`Loaded ${data.n_points} points`);
        
        // Save to state
        state.data = data;
        
        // Plot lightcurve
        plotLightcurve(data);
        
        // Show stats
        showLightcurveStats(data);
        
        // Show BLS panel
        document.getElementById('bls-panel').classList.remove('hidden');
        
        // Auto-set period range based on planet type
        setPeriodRange(data.params);
        
        // Hide results from previous run
        document.getElementById('results-panel').classList.add('hidden');
        
    } catch (error) {
        console.error('Error loading data:', error);
        alert(`Errore caricamento dati: ${error.message}`);
    } finally {
        document.getElementById('loading').classList.add('hidden');
    }
}


function setPeriodRange(params) {
    /**
     * Imposta range periodi intelligente basato su parametri.
     */
    const truePeriod = params.period;
    
    // Range: ±50% del periodo vero
    const periodMin = Math.max(0.5, truePeriod * 0.5);
    const periodMax = truePeriod * 1.5;
    
    document.getElementById('period-min').value = periodMin.toFixed(1);
    document.getElementById('period-max').value = periodMax.toFixed(1);
    
    console.log(`Period range set: [${periodMin}, ${periodMax}] (true: ${truePeriod})`);
}


// =============================================================================
// BLS DETECTION
// =============================================================================

async function runBLS() {
    /**
     * Esegue Box Least Squares detection.
     */
    if (!state.data) {
        alert('Carica prima i dati!');
        return;
    }
    
    const periodMin = parseFloat(document.getElementById('period-min').value);
    const periodMax = parseFloat(document.getElementById('period-max').value);
    
    console.log(`Running BLS: P=[${periodMin}, ${periodMax}]`);
    
    // Show loading
    document.getElementById('bls-loading').classList.remove('hidden');
    
    try {
        // Prepare request
        const requestData = {
            jd: state.data.jd,
            flux: state.data.flux,
            period_min: periodMin,
            period_max: periodMax,
            duration_min: 0.01,
            duration_max: 0.2
        };
        
        // API call
        const results = await apiCall(
            '/agata/exoplanets/api/bls',
            'POST',
            requestData
        );
        
        console.log('BLS results:', results);
        
        // Save to state
        state.blsResults = results;
        
        // Plot results
        plotBLSPeriodogram(results);
        plotFoldedLightcurve(results);
        
        // Show results panel
        document.getElementById('results-panel').classList.remove('hidden');
        
        // Populate parameters table
        populateParametersTable(results);
        
        // Show ephemeris panel
        document.getElementById('ephemeris-panel').classList.remove('hidden');
        
        // Scroll to results
        document.getElementById('results-panel').scrollIntoView({ behavior: 'smooth' });
        
    } catch (error) {
        console.error('Error running BLS:', error);
        alert(`Errore BLS: ${error.message}`);
    } finally {
        document.getElementById('bls-loading').classList.add('hidden');
    }
}


// =============================================================================
// VALIDAZIONE FISICA
// =============================================================================

async function validatePlanet() {
    /**
     * Esegue validazione fisica parametri pianeta.
     */
    if (!state.blsResults) {
        alert('Esegui prima BLS!');
        return;
    }
    
    console.log('Validating planet parameters...');
    
    try {
        // Prepare request
        const requestData = {
            period: state.blsResults.best_period,
            depth: state.blsResults.best_depth,
            duration: state.blsResults.best_duration,
            stellar_mass: state.data.params.stellar_mass || 1.0,
            stellar_radius: state.data.params.stellar_radius || 1.0,
            stellar_teff: 5778  // Default Sun-like
        };
        
        // API call
        const validation = await apiCall(
            '/agata/exoplanets/api/validate',
            'POST',
            requestData
        );
        
        console.log('Validation results:', validation);
        
        // Save to state
        state.validation = validation;
        
        // Show validation results
        showValidation(validation);
        
    } catch (error) {
        console.error('Error validation:', error);
        alert(`Errore validazione: ${error.message}`);
    }
}


// =============================================================================
// PLOTTING
// =============================================================================

function plotLightcurve(data) {
    /**
     * Plot curva di luce completa.
     */
    const trace = {
        x: data.jd,
        y: data.flux,
        mode: 'markers',
        type: 'scatter',
        marker: {
            size: 3,
            color: '#3498db',
            opacity: 0.6
        },
        name: 'Flux'
    };
    
    const layout = {
        title: 'Curva di Luce - Transiti Esopianeti',
        xaxis: {
            title: 'Julian Date',
            gridcolor: '#ecf0f1'
        },
        yaxis: {
            title: 'Flusso Relativo',
            gridcolor: '#ecf0f1'
        },
        hovermode: 'closest',
        plot_bgcolor: '#fff',
        paper_bgcolor: '#fff'
    };
    
    const config = {
        responsive: true,
        displayModeBar: true,
        modeBarButtonsToRemove: ['lasso2d', 'select2d']
    };
    
    Plotly.newPlot('plot-lightcurve', [trace], layout, config);
}


function plotBLSPeriodogram(results) {
    /**
     * Plot periodogramma BLS.
     */
    // Trova picco
    const maxIdx = results.power.indexOf(Math.max(...results.power));
    const bestPeriod = results.periods[maxIdx];
    
    const trace = {
        x: results.periods,
        y: results.power,
        mode: 'lines',
        type: 'scatter',
        line: {
            color: '#e74c3c',
            width: 2
        },
        name: 'BLS Power'
    };
    
    // Marker per best period
    const markerTrace = {
        x: [bestPeriod],
        y: [results.power[maxIdx]],
        mode: 'markers',
        type: 'scatter',
        marker: {
            size: 12,
            color: '#27ae60',
            symbol: 'star'
        },
        name: `Best: ${bestPeriod.toFixed(4)}d`
    };
    
    const layout = {
        title: `BLS Periodogramma (SDE=${results.sde.toFixed(2)}, SNR=${results.snr.toFixed(2)})`,
        xaxis: {
            title: 'Periodo [giorni]',
            type: 'log',
            gridcolor: '#ecf0f1'
        },
        yaxis: {
            title: 'BLS Power',
            gridcolor: '#ecf0f1'
        },
        hovermode: 'closest',
        plot_bgcolor: '#fff',
        annotations: [{
            x: bestPeriod,
            y: results.power[maxIdx],
            text: `P=${bestPeriod.toFixed(4)}d`,
            showarrow: true,
            arrowhead: 2,
            ax: 40,
            ay: -40
        }]
    };
    
    const config = { responsive: true };
    
    Plotly.newPlot('plot-bls', [trace, markerTrace], layout, config);
}


function plotFoldedLightcurve(results) {
    /**
     * Plot curva foldato sul periodo rilevato.
     */
    const trace = {
        x: results.phase,
        y: results.flux_folded,
        mode: 'markers',
        type: 'scatter',
        marker: {
            size: 4,
            color: '#9b59b6',
            opacity: 0.5
        },
        name: 'Flux'
    };
    
    const layout = {
        title: `Curva Foldato (P=${results.best_period.toFixed(4)}d)`,
        xaxis: {
            title: 'Fase',
            range: [0, 1],
            gridcolor: '#ecf0f1'
        },
        yaxis: {
            title: 'Flusso Relativo',
            gridcolor: '#ecf0f1'
        },
        hovermode: 'closest',
        plot_bgcolor: '#fff',
        shapes: [{
            // Linea verticale a fase 0 (centro transito)
            type: 'line',
            x0: 0,
            x1: 0,
            y0: 0,
            y1: 1,
            yref: 'paper',
            line: {
                color: '#e74c3c',
                width: 2,
                dash: 'dash'
            }
        }]
    };
    
    const config = { responsive: true };
    
    Plotly.newPlot('plot-folded', [trace], layout, config);
}


// =============================================================================
// UI UPDATES
// =============================================================================

function showLightcurveStats(data) {
    /**
     * Mostra statistiche curva di luce.
     */
    const statsDiv = document.getElementById('lightcurve-stats');
    
    const fluxMean = data.flux.reduce((a, b) => a + b, 0) / data.flux.length;
    const fluxStd = Math.sqrt(
        data.flux.reduce((sum, x) => sum + Math.pow(x - fluxMean, 2), 0) / data.flux.length
    );
    const fluxMin = Math.min(...data.flux);
    
    const ppm = fluxStd * 1e6;
    
    statsDiv.innerHTML = `
        <h3>📊 Statistiche</h3>
        <div class="stats-grid">
            <div class="stat-item">
                <span class="stat-label">Punti:</span>
                <span class="stat-value">${data.n_points.toLocaleString()}</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">Rumore:</span>
                <span class="stat-value">${ppm.toFixed(0)} ppm</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">Baseline:</span>
                <span class="stat-value">${(data.jd[data.jd.length - 1] - data.jd[0]).toFixed(1)} giorni</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">Profondità attesa:</span>
                <span class="stat-value">${((1 - fluxMin) * 1e6).toFixed(0)} ppm</span>
            </div>
        </div>
    `;
    
    statsDiv.classList.remove('hidden');
}


function populateParametersTable(results) {
    /**
     * Popola tabella parametri rilevati.
     */
    const tbody = document.querySelector('#params-table tbody');
    
    const params = [
        { name: 'Periodo', value: results.best_period.toFixed(6), unit: 'giorni' },
        { name: 'Durata Transito', value: results.best_duration.toFixed(6), unit: 'giorni' },
        { name: 'Profondità', value: results.best_depth.toFixed(6), unit: 'ΔF/F' },
        { name: 'Profondità', value: (results.best_depth * 1e6).toFixed(0), unit: 'ppm' },
        { name: 'Epoca T₀', value: results.best_t0.toFixed(6), unit: 'JD' },
        { name: 'SDE', value: results.sde.toFixed(2), unit: '—' },
        { name: 'SNR', value: results.snr.toFixed(2), unit: '—' },
        { name: 'Numero Transiti', value: results.n_transits, unit: '—' },
        { name: 'Baseline', value: results.baseline_days.toFixed(1), unit: 'giorni' }
    ];
    
    tbody.innerHTML = params.map(p => `
        <tr>
            <td>${p.name}</td>
            <td class="value">${p.value}</td>
            <td>${p.unit}</td>
        </tr>
    `).join('');
}


function showValidation(validation) {
    /**
     * Mostra risultati validazione fisica.
     */
    const contentDiv = document.getElementById('validation-content');
    
    const phys = validation.physical_params;
    
    // Status badge
    const statusBadge = validation.is_valid
        ? '<span class="badge badge-success">✓ Valido</span>'
        : '<span class="badge badge-error">✗ Non Valido</span>';
    
    // Warnings
    const warningsHtml = validation.warnings.length > 0
        ? `
            <div class="warnings-list">
                ${validation.warnings.map(w => `
                    <div class="warning warning-${w.level}">
                        <strong>${w.level.toUpperCase()}:</strong> ${w.message}
                    </div>
                `).join('')}
            </div>
        `
        : '<p class="no-warnings">✓ Nessun warning</p>';
    
    // Parametri fisici
    const physHtml = `
        <div class="phys-params">
            <h4>Parametri Fisici Derivati</h4>
            <table>
                <tr>
                    <td>Raggio Pianeta:</td>
                    <td><strong>${phys.rp_rjup.toFixed(3)} R<sub>jup</sub></strong> = ${phys.rp_rearth.toFixed(2)} R<sub>⊕</sub></td>
                </tr>
                <tr>
                    <td>Semiasse Orbitale:</td>
                    <td><strong>${phys.a_au.toFixed(4)} AU</strong></td>
                </tr>
                <tr>
                    <td>Temperatura Equilibrio:</td>
                    <td><strong>${phys.teq_kelvin.toFixed(0)} K</strong></td>
                </tr>
                <tr>
                    <td>Velocità Orbitale:</td>
                    <td><strong>${phys.v_orbit_kms.toFixed(1)} km/s</strong></td>
                </tr>
                <tr>
                    <td>Classificazione:</td>
                    <td><strong class="planet-class">${phys.planet_class}</strong></td>
                </tr>
            </table>
        </div>
    `;
    
    contentDiv.innerHTML = `
        ${statusBadge}
        ${warningsHtml}
        ${physHtml}
    `;
}


// =============================================================================
// EFFEMERIDI
// =============================================================================

async function calculateEphemeris() {
    /**
     * Calcola effemeridi da transiti rilevati.
     */
    if (!state.blsResults) {
        alert('Esegui prima BLS!');
        return;
    }
    
    console.log('Calculating ephemeris...');
    
    // Show loading
    document.getElementById('ephemeris-loading').classList.remove('hidden');
    
    try {
        // Prepare request
        const requestData = {
            jd: state.data.jd,
            flux: state.data.flux,
            period: state.blsResults.best_period,
            t0: state.blsResults.best_t0,
            duration: state.blsResults.best_duration
        };
        
        // API call
        const results = await apiCall(
            '/agata/exoplanets/api/ephemeris',
            'POST',
            requestData
        );
        
        console.log('Ephemeris results:', results);
        
        // Save to state
        state.ephemeris = results.ephemeris;
        state.transits = results.transits;
        
        // Show ephemeris results
        showEphemerisResults(results);
        
        // Plot O-C
        plotOC(results.oc);
        
        // Show export button
        document.getElementById('btn-export-exoclock').classList.remove('hidden');
        
        // Scroll to results
        document.getElementById('ephemeris-results').scrollIntoView({ behavior: 'smooth' });
        
    } catch (error) {
        console.error('Error calculating ephemeris:', error);
        alert(`Errore calcolo effemeridi: ${error.message}`);
    } finally {
        document.getElementById('ephemeris-loading').classList.add('hidden');
    }
}


// =============================================================================
// EXPORT EXOCLOCK
// =============================================================================

async function exportExoClock() {
    /**
     * Esporta dati in formato ExoClock CSV.
     */
    if (!state.ephemeris || !state.transits) {
        alert('Calcola prima le effemeridi!');
        return;
    }
    
    console.log('Exporting ExoClock format...');
    
    try {
        // Prepare request
        const planetName = document.getElementById('planet-type').value.replace('_', ' ');
        
        const requestData = {
            transits: state.transits,
            ephemeris: state.ephemeris,
            planet_name: `Test_${planetName}`,
            observer: "AGATA",
            filter: "Clear"
        };
        
        // API call
        const response = await fetch('/agata/exoplanets/api/export/exoclock', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestData)
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        // Download file
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${planetName}_exoclock.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        
        console.log('Export completed');
        
        // Show success message
        alert('✓ File ExoClock scaricato!');
        
    } catch (error) {
        console.error('Error exporting:', error);
        alert(`Errore export: ${error.message}`);
    }
}


// =============================================================================
// PLOTTING - O-C DIAGRAM
// =============================================================================

function plotOC(ocData) {
    /**
     * Plot diagramma O-C.
     */
    // Separa transiti validi e invalidi
    const validIdx = ocData.is_valid.map((v, i) => v ? i : -1).filter(i => i !== -1);
    const invalidIdx = ocData.is_valid.map((v, i) => !v ? i : -1).filter(i => i !== -1);
    
    const traces = [];
    
    // Transiti validi
    if (validIdx.length > 0) {
        traces.push({
            x: validIdx.map(i => ocData.epochs[i]),
            y: validIdx.map(i => ocData.oc_minutes[i]),
            error_y: {
                type: 'data',
                array: validIdx.map(i => ocData.oc_err_minutes[i]),
                visible: true
            },
            mode: 'markers',
            type: 'scatter',
            marker: {
                size: 8,
                color: '#27ae60'
            },
            name: 'Validi'
        });
    }
    
    // Transiti invalidi
    if (invalidIdx.length > 0) {
        traces.push({
            x: invalidIdx.map(i => ocData.epochs[i]),
            y: invalidIdx.map(i => ocData.oc_minutes[i]),
            error_y: {
                type: 'data',
                array: invalidIdx.map(i => ocData.oc_err_minutes[i]),
                visible: true
            },
            mode: 'markers',
            type: 'scatter',
            marker: {
                size: 8,
                color: '#e74c3c',
                symbol: 'x'
            },
            name: 'Invalidi'
        });
    }
    
    // Linea zero
    traces.push({
        x: [Math.min(...ocData.epochs), Math.max(...ocData.epochs)],
        y: [0, 0],
        mode: 'lines',
        type: 'scatter',
        line: {
            color: '#95a5a6',
            width: 2,
            dash: 'dash'
        },
        name: 'O-C = 0',
        showlegend: false
    });
    
    const layout = {
        title: 'O-C Diagram (Observed - Calculated)',
        xaxis: {
            title: 'Epoca',
            gridcolor: '#ecf0f1'
        },
        yaxis: {
            title: 'O-C [minuti]',
            gridcolor: '#ecf0f1',
            zeroline: true,
            zerolinecolor: '#95a5a6'
        },
        hovermode: 'closest',
        plot_bgcolor: '#fff'
    };
    
    const config = { responsive: true };
    
    Plotly.newPlot('plot-oc', traces, layout, config);
}


// =============================================================================
// UI UPDATES - EPHEMERIS
// =============================================================================

function showEphemerisResults(results) {
    /**
     * Mostra risultati effemeridi.
     */
    const eph = results.ephemeris;
    
    // Valori effemeridi
    const valuesDiv = document.getElementById('ephemeris-values');
    valuesDiv.innerHTML = `
        <div class="ephemeris-grid">
            <div class="eph-item">
                <span class="eph-label">T₀ (Epoca Zero)</span>
                <span class="eph-value">${eph.t0.toFixed(6)} ± ${eph.t0_err_minutes.toFixed(2)} min</span>
            </div>
            <div class="eph-item">
                <span class="eph-label">Periodo (P)</span>
                <span class="eph-value">${eph.period.toFixed(6)} ± ${eph.period_err_seconds.toFixed(2)} sec</span>
            </div>
            <div class="eph-item">
                <span class="eph-label">Transiti Usati</span>
                <span class="eph-value">${eph.n_transits}</span>
            </div>
            <div class="eph-item">
                <span class="eph-label">RMS O-C</span>
                <span class="eph-value">${eph.rms_oc_minutes.toFixed(2)} min</span>
            </div>
            <div class="eph-item">
                <span class="eph-label">χ² Ridotto</span>
                <span class="eph-value">${eph.chi2_reduced.toFixed(2)}</span>
            </div>
        </div>
    `;
    
    // Tabella transiti
    const tbody = document.querySelector('#transits-table tbody');
    tbody.innerHTML = results.transits.map(t => `
        <tr class="${t.is_valid ? '' : 'invalid-transit'}">
            <td>${t.epoch}</td>
            <td>${t.t_mid.toFixed(6)}</td>
            <td>${(t.t_mid_err * 1440).toFixed(2)}</td>
            <td>${results.oc.oc_minutes[t.epoch].toFixed(2)}</td>
            <td>${t.snr.toFixed(1)}</td>
            <td>${t.is_valid ? '✓' : '✗'}</td>
        </tr>
    `).join('');
    
    // Show results
    document.getElementById('ephemeris-results').classList.remove('hidden');
}


// =============================================================================
// EVENT LISTENERS
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    console.log('🪐 Exoplanets module loaded');
    
    // Data source selection
    document.querySelectorAll('input[name="data-source"]').forEach(radio => {
        radio.addEventListener('change', (e) => {
            toggleDataSource(e.target.value);
        });
    });
    
    // File selection
    document.getElementById('btn-select-file').addEventListener('click', () => {
        document.getElementById('file-input').click();
    });
    
    document.getElementById('file-input').addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            document.getElementById('filename').textContent = file.name;
            document.getElementById('file-selected').classList.remove('hidden');
        }
    });
    
    // Upload button
    document.getElementById('btn-upload').addEventListener('click', uploadFile);
    
    // Load data button (synthetic)
    document.getElementById('btn-load').addEventListener('click', loadData);
    
    // BLS button
    document.getElementById('btn-bls').addEventListener('click', runBLS);
    
    // Validate button
    document.getElementById('btn-validate').addEventListener('click', validatePlanet);
    
    // Ephemeris button
    document.getElementById('btn-ephemeris').addEventListener('click', calculateEphemeris);
    
    // Export button
    document.getElementById('btn-export-exoclock').addEventListener('click', exportExoClock);
    
    // Enter key shortcuts
    document.getElementById('planet-type').addEventListener('keypress', e => {
        if (e.key === 'Enter') loadData();
    });
    
    console.log('✓ Event listeners registered');
});


// =============================================================================
// EXPORT (se serve per altri moduli)
// =============================================================================

export { loadData, runBLS, validatePlanet, calculateEphemeris, exportExoClock, uploadFile };
// math-logic-corrected.js - Correzioni scientifiche per detrending e allineamenti
import { state, invalidateSamplingCache } from './state.js';
import { renderSessionList, updateCounters } from './session-ui.js';
import { drawLightcurve } from './plots.js';
import { computePhase, invalidateEpoch } from './phase-analysis.js';
import { calculatePhaseStatistics, renderPhaseStatistics } from './phase-statistics.js';
import { updateEphemerisIfVisible } from './phase-controls.js';
import { buildArrowStreamJDMag } from '../common/utils-arrow.js';

/**
 * Mediana robusta
 * @param {Array<number>} arr - Array di numeri
 * @returns {number} - Mediana
 */
export function median(arr) {
  if (arr.length === 0) return 0;
  const v = [...arr].sort((a, b) => a - b);
  const m = Math.floor(v.length / 2);
  return v.length % 2 ? v[m] : 0.5 * (v[m - 1] + v[m]);
}

/**
 * MAD (Median Absolute Deviation) - stimatore robusto della dispersione
 * Conversione a sigma: σ ≈ 1.4826 × MAD
 */
export function mad(arr) {
  if (arr.length === 0) return 0;
  const med = median(arr);
  const absDevs = arr.map(v => Math.abs(v - med));
  return median(absDevs);
}

/**
 * Ricalcola l'ampiezza manuale (✏️) usando percentili robusti sui dati correnti
 * Rimuove solo lo 0.5% estremo su ogni lato (outlier veramente estremi)
 * Aggiorna state.manualAmplitude con i nuovi valori min/max
 * @returns {Object} - {min, max, amplitude} - Nuova ampiezza manuale
 */
export function recalculateManualAmplitude() {
  // Raccoglie magnitudini corrette (detrend + offset)
  const mags = [];

  for (let i = 0; i < state.n; i++) {
    if (state.activePoint[i] === 0) continue;
    const sid = state.session[i];
    if (!state.activeSession.get(sid)) continue;

    // Magnitudine corretta (detrend + offset totale)
    const magCorrected = state.mag[i] - detrendValue(sid, state.jd[i]) +
                        (state.sessionAutoOffset.get(sid) || 0) +
                        (state.sessionManualOffset.get(sid) || 0);
    mags.push(magCorrected);
  }

  if (mags.length === 0) {
    console.warn('⚠️ Nessun punto attivo');
    return null;
  }

  // ✅ USA PERCENTILI ROBUSTI invece di sigma clipping aggressivo
  // Rimuovi solo 0.5% estremi su ogni lato (outlier veramente estremi)
  mags.sort((a, b) => a - b);

  const p005 = Math.floor(mags.length * 0.005);
  const p995 = Math.ceil(mags.length * 0.995);

  // Prendi min/max escludendo solo gli estremi 0.5%
  const magMin = mags[p005];
  const magMax = mags[p995 - 1];

  const amplitude = magMax - magMin;
  const outliers = p005 + (mags.length - p995);

  // ✅ AGGIORNA state.manualAmplitude
  state.manualAmplitude = {
    min: magMin,
    max: magMax
  };

  console.log(`📊 Ampiezza manuale ricalcolata: ${amplitude.toFixed(3)} mag [${magMin.toFixed(3)}, ${magMax.toFixed(3)}] (${mags.length - outliers} punti utilizzati, ${outliers} outlier rimossi)`);

  return { min: magMin, max: magMax, amplitude };
}

/**
 * Calcola il range ottimale per gli slider offset basandosi sull'ampiezza attuale
 * @returns {Object} - {min, max} - Range calcolato per slider
 */
export function calculateGlobalSliderRange() {
  let amplitude;

  // Usa ampiezza manuale se presente, altrimenti automatica
  if (state.manualAmplitude && state.manualAmplitude.min !== null && state.manualAmplitude.max !== null) {
    amplitude = state.manualAmplitude.max - state.manualAmplitude.min;
  } else {
    // Fallback: calcola ampiezza automatica dai dati correnti
    const mags = [];
    for (let i = 0; i < state.n; i++) {
      if (state.activePoint[i] === 0) continue;
      const sid = state.session[i];
      if (!state.activeSession.get(sid)) continue;
      const magCorrected = state.mag[i] - detrendValue(sid, state.jd[i]) +
                          (state.sessionAutoOffset.get(sid) || 0) +
                          (state.sessionManualOffset.get(sid) || 0);
      mags.push(magCorrected);
    }

    if (mags.length === 0) {
      return { min: -2, max: 2 };
    }

    let magMin = mags[0];
    let magMax = mags[0];
    for (let i = 1; i < mags.length; i++) {
      if (mags[i] < magMin) magMin = mags[i];
      if (mags[i] > magMax) magMax = mags[i];
    }
    amplitude = magMax - magMin;
  }

  // Range slider = ampiezza * 1.5 (50% di margine per permettere aggiustamenti)
  const halfRange = Math.ceil((amplitude * 1.5) / 2 * 2) / 2;
  const min = Math.max(-halfRange, -5);
  const max = Math.min(halfRange, 5);

  return { min, max };
}

/**
 * ✅ CORREZIONE: Detrend value con tempo relativo
 * Evita problemi numerici con JD grandi (~2460000)
 */
export function detrendValue(sid, jd) {
  const model = state.detrend.model;
  if (model === "none") return 0.0;
  
  const c = state.detrend.coeff.get(sid);
  if (!c) return 0.0;
  
  // ✅ Usa tempo relativo a t0
  const t = jd - c.t0;
  
  if (model === "linear") {
    return c.a * t + c.b;
  }
  
  if (model === "quadratic") {
    return c.a * t * t + c.b * t + c.c;
  }
  
  return 0.0;
}

/**
 * ✅ CORREZIONE: Calcolo coefficienti detrend con:
 * 1. Tempo relativo (non JD assoluto)
 * 2. Test F per significatività del trend
 * 3. Validazione statistica
 */
export function computeDetrendCoefficients() {
  state.detrend.model = document.getElementById("detrendModel").value;
  state.detrend.coeff.clear();
  
  if (state.detrend.model === "none") {
    console.log("Detrend: none");
    return;
  }

  const acc = new Map();
  
  // Accumula statistiche per sessione
  for (let i = 0; i < state.n; i++) {
    if (state.activePoint[i] === 0) continue;
    
    const sid = state.session[i];
    if (!state.activeSession.get(sid)) continue;
    
    // ✅ Inizializza con t0 (epoca locale della sessione)
    if (!acc.has(sid)) {
      acc.set(sid, {
        n: 0,
        t0: state.jd[i],  // ⬅️ NUOVO: riferimento temporale
        sx: 0, sy: 0, sxx: 0, sxy: 0,
        sx2: 0, sx3: 0, sx4: 0, sx2y: 0,
        rawData: [] // Per test statistici
      });
    }
    
    const a = acc.get(sid);
    const t = state.jd[i] - a.t0;  // ⬅️ Tempo relativo
    const y = state.mag[i];
    
    a.n++;
    a.sx += t;
    a.sy += y;
    a.sxx += t * t;
    a.sxy += t * y;
    
    if (state.detrend.model === "quadratic") {
      a.sx2 += t * t;
      a.sx3 += t * t * t;
      a.sx4 += t * t * t * t;
      a.sx2y += t * t * y;
    }
    
    a.rawData.push({ t, y });
  }

  // Calcola coefficienti per ciascuna sessione
  for (const [sid, a] of acc.entries()) {
    
    if (state.detrend.model === "linear") {
      const result = computeLinearDetrendWithValidation(a);
      state.detrend.coeff.set(sid, result);
      
    } else if (state.detrend.model === "quadratic") {
      const result = computeQuadraticDetrend(a);
      state.detrend.coeff.set(sid, result);
    }
  }
  
  console.log("Detrend coefficients computed:", 
    Object.fromEntries(
      Array.from(state.detrend.coeff.entries()).map(([k, v]) => 
        [k, { model: state.detrend.model, significant: v.significant, R2: v.rSquared?.toFixed(3) }]
      )
    )
  );
}

/**
 * ✅ Detrend lineare con test F per significatività
 */
function computeLinearDetrendWithValidation(a) {
  const { n, sx, sy, sxx, sxy, t0, rawData } = a;
  
  if (n < 3) {
    // Troppo pochi punti: usa solo media
    return { a: 0, b: sy / n, t0, significant: false, rSquared: 0 };
  }
  
  // Least squares
  const denom = (n * sxx - sx * sx);
  
  if (Math.abs(denom) < 1e-12) {
    // Matrice singolare: usa media
    console.warn(`Session ${a.t0}: singular matrix in detrend`);
    return { a: 0, b: sy / n, t0, significant: false, rSquared: 0 };
  }
  
  const slope = (n * sxy - sx * sy) / denom;
  const intercept = (sy - slope * sx) / n;
  
  // ✅ Test F per significatività del trend
  const yMean = sy / n;
  let ssRes = 0;  // Sum of squared residuals
  let ssTot = 0;  // Total sum of squares
  
  for (const { t, y } of rawData) {
    const yPred = slope * t + intercept;
    ssRes += (y - yPred) ** 2;
    ssTot += (y - yMean) ** 2;
  }
  
  if (ssTot < 1e-12) {
    // Dati costanti
    return { a: 0, b: yMean, t0, significant: false, rSquared: 0 };
  }
  
  const rSquared = 1 - (ssRes / ssTot);
  
  // F-statistic: F = (SSreg / df_reg) / (SSres / df_res)
  // df_reg = 1 (un parametro: slope)
  // df_res = n - 2
  const ssReg = ssTot - ssRes;
  const fStat = (ssReg / 1) / (ssRes / (n - 2));
  
  // F-critical per α = 0.05, df1=1, df2=n-2
  // Approssimazione: F_crit ≈ 4 per n > 10
  const fCritical = 4.0;
  const significant = fStat > fCritical && rSquared > 0.1;
  
  if (!significant) {
    console.warn(
      `Session at t0=${t0.toFixed(1)}: trend not significant ` +
      `(R²=${rSquared.toFixed(3)}, F=${fStat.toFixed(1)}). Using mean only.`
    );
    return { a: 0, b: yMean, t0, significant: false, rSquared };
  }
  
  console.log(
    `Session at t0=${t0.toFixed(1)}: linear trend ` +
    `(slope=${slope.toExponential(3)}, R²=${rSquared.toFixed(3)}, F=${fStat.toFixed(1)})`
  );
  
  return { 
    a: slope, 
    b: intercept, 
    t0, 
    significant: true, 
    rSquared,
    fStat
  };
}

/**
 * Detrend quadratico
 */
function computeQuadraticDetrend(a) {
  const { n, sx, sy, sx2, sx3, sx4, sxy, sx2y, t0, rawData } = a;
  
  if (n < 4) {
    return { a: 0, b: 0, c: sy / n, t0, significant: false };
  }
  
  // Risolvi sistema 3x3
  const sol = solve3x3(
    [[sx4, sx3, sx2], 
     [sx3, sx2, sx], 
     [sx2, sx, n]], 
    [sx2y, sxy, sy]
  );
  
  if (!sol) {
    console.warn(`Session at t0=${t0.toFixed(1)}: quadratic detrend failed, using mean`);
    return { a: 0, b: 0, c: sy / n, t0, significant: false };
  }
  
  // Calcola R²
  const yMean = sy / n;
  let ssRes = 0;
  let ssTot = 0;
  
  for (const { t, y } of rawData) {
    const yPred = sol[0] * t * t + sol[1] * t + sol[2];
    ssRes += (y - yPred) ** 2;
    ssTot += (y - yMean) ** 2;
  }
  
  const rSquared = ssTot > 1e-12 ? 1 - (ssRes / ssTot) : 0;
  
  return { 
    a: sol[0], 
    b: sol[1], 
    c: sol[2], 
    t0, 
    significant: rSquared > 0.15,
    rSquared
  };
}

/**
 * Risoluzione sistema lineare 3x3 con eliminazione di Gauss
 */
function solve3x3(A, b) {
  const M = A.map((row, i) => [...row, b[i]]);
  
  // Eliminazione di Gauss con pivot parziale
  for (let col = 0; col < 3; col++) {
    // Trova pivot
    let pivot = col;
    for (let r = col + 1; r < 3; r++) {
      if (Math.abs(M[r][col]) > Math.abs(M[pivot][col])) {
        pivot = r;
      }
    }
    
    if (Math.abs(M[pivot][col]) < 1e-18) {
      console.warn("Singular matrix in solve3x3");
      return null;
    }
    
    // Scambia righe
    [M[pivot], M[col]] = [M[col], M[pivot]];
    
    // Normalizza riga pivot
    const div = M[col][col];
    for (let c = col; c < 4; c++) {
      M[col][c] /= div;
    }
    
    // Elimina colonna sotto
    for (let r = 0; r < 3; r++) {
      if (r === col) continue;
      const f = M[r][col];
      for (let c = col; c < 4; c++) {
        M[r][c] -= f * M[col][c];
      }
    }
  }
  
  return [M[0][3], M[1][3], M[2][3]];
}

/**
 * ✅ ALLINEAMENTO ZERO-POINT SCIENTIFICO con ASTROPY
 * Usa endpoint Python con astropy.stats per calibrazione robusta e pesata
 *
 * Metodo:
 * 1. Prepara dati con detrending applicato
 * 2. Invia al backend Python via Arrow IPC
 * 3. Backend usa astropy.stats.sigma_clipped_stats + mad_std
 * 4. Calcola mediana globale pesata (peso = N/σ²)
 * 5. Ritorna offset per ogni sessione con test significatività
 *
 * Riferimenti:
 * - Stetson 1996, PASP 108, 851
 * - Astropy documentation: https://docs.astropy.org/en/stable/stats/
 */
export async function alignSessionsZeroPoint() {
  console.log("🔬 Allineamento zero-point scientifico con Astropy...");

  // 1. Prepara dati per backend (con detrending già applicato)
  const jdArr = [];
  const magArr = [];
  const sidArr = [];

  for (let i = 0; i < state.n; i++) {
    if (state.activePoint[i] === 1 && state.activeSession.get(state.session[i])) {
      const sid = state.session[i];
      const jd = state.jd[i];

      // Applica detrending PRIMA di inviare al backend
      const magDetrended = state.mag[i] - detrendValue(sid, jd);

      jdArr.push(jd);
      magArr.push(magDetrended);
      sidArr.push(sid);
    }
  }

  if (jdArr.length < 10) {
    console.warn("⚠️ Troppo pochi punti per allineamento zero-point");
    alert("Troppo pochi punti attivi per allineamento zero-point (minimo 10 richiesti)");
    return;
  }

  console.log(`📊 Inviando ${jdArr.length} punti da ${state.activeSession.size} sessioni al backend...`);

  try {
    // 2. Costruisci payload Arrow IPC
    const arrowStream = buildArrowStreamJDMag(
      new Float64Array(jdArr),
      new Float32Array(magArr),
      new Int32Array(sidArr)
    );

    // 3. Chiamata al backend Python (con astropy)
    const response = await fetch('/agata/variable-stars/api/align_zeropoint.arrow?sigma=3.0&max_iters=5', {
      method: 'POST',
      body: arrowStream,
      headers: {
        'Content-Type': 'application/vnd.apache.arrow.stream'
      }
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error || `HTTP ${response.status}`);
    }

    const result = await response.json();

    console.log("✅ Risultati allineamento dal backend:");
    console.log(`   Riferimento globale: ${result.global_reference.toFixed(4)} mag`);
    console.log(`   Algoritmo: ${result.algorithm}`);

    // 4. Applica offset calcolati da astropy
    let nSignificant = 0;
    let nInsignificant = 0;

    for (const [sidStr, offset] of Object.entries(result.session_offsets)) {
      const sid = parseInt(sidStr);
      const stats = result.session_stats[sidStr];

      if (stats.skipped) {
        console.log(`   S${sid}: SKIPPED - ${stats.reason}`);
        state.sessionAutoOffset.set(sid, 0);
        continue;
      }

      state.sessionAutoOffset.set(sid, offset);

      const significant = stats.significant !== false; // default true se manca
      if (significant && Math.abs(offset) > 1e-6) {
        nSignificant++;
        console.log(`   S${sid}: offset = ${offset.toFixed(4)} mag ✓ SIGNIFICATIVO`);
        console.log(`          (mediana: ${stats.median_before.toFixed(4)} → ${stats.median_after.toFixed(4)}, σ=${stats.sigma_equiv.toFixed(4)}, N=${stats.n_points})`);
      } else {
        nInsignificant++;
        console.log(`   S${sid}: offset = ${offset.toFixed(4)} mag (non significativo, σ_med=${stats.sigma_median?.toFixed(4) || 'N/A'})`);
      }
    }

    console.log(`\n📈 Riepilogo: ${nSignificant} offset significativi, ${nInsignificant} non significativi`);

    // 5. Aggiorna UI
    invalidateSamplingCache();
    invalidateEpoch();
    renderSessionList();
    drawLightcurve();
    updateCounters();

    // 6. Se c'è un'analisi in fase attiva, aggiorna anche quella
    if (state.lastPeriod) {
      computePhase();
      const stats = calculatePhaseStatistics();
      renderPhaseStatistics(stats);
      // Le effemeridi vengono aggiornate solo se visibili (gestito dal toggle)
      updateEphemerisIfVisible();
    }

    console.log("✅ Allineamento zero-point completato con successo!");

  } catch (error) {
    console.error("❌ Errore allineamento zero-point:", error);
    alert(`Errore allineamento zero-point: ${error.message}\n\nVerifica la console per dettagli.`);
    throw error;
  }
}

/**
 * ✅ CORREZIONE: Allineamento in fase con:
 * 1. Outlier rejection nei bin
 * 2. Test significatività offset
 * 3. Pesatura robusta
 */
export function alignSessionsByPhaseMedian(P, nBins = 40) {
  if (!isFinite(P) || P <= 0) {
    console.error("Periodo non valido per allineamento in fase");
    return;
  }

  console.log(`Allineamento in fase: P=${P.toFixed(6)} d, ${nBins} bins`);

  // Bins di fase
  const bins = Array.from({ length: nBins }, () => []);

  // ✅ Usa epoca corretta
  const T0 = state.epoch || state.jd[0];

  // Costruisci curva di riferimento globale
  for (let i = 0; i < state.n; i++) {
    if (state.activePoint[i] === 0) continue;

    const sid = state.session[i];
    if (!state.activeSession.get(sid)) continue;

    // Fase corretta
    let phi = ((state.jd[i] - T0) / P) % 1;
    if (phi < 0) phi += 1;

    const b = Math.floor(phi * nBins) % nBins;
    const mag = state.mag[i] - detrendValue(sid, state.jd[i]);
    
    bins[b].push(mag);
  }

  // ✅ Mediana robusta con outlier rejection (3σ-clip)
  const ref = bins.map(b => {
    if (b.length < 3) return null;
    
    // Prima passata: mediana grezza
    const med = median(b);
    const medianAD = mad(b);
    const sigma = 1.4826 * medianAD;
    
    // Seconda passata: rimuovi outlier
    const clean = b.filter(v => Math.abs(v - med) < 3 * sigma);
    
    if (clean.length < 3) return null;
    
    return median(clean);
  });

  // Calcola offset per sessione
  for (const sid of state.activeSession.keys()) {
    if (!state.activeSession.get(sid)) continue;

    const diffs = [];

    for (let i = 0; i < state.n; i++) {
      if (state.activePoint[i] === 0 || state.session[i] !== sid) continue;

      let phi = ((state.jd[i] - T0) / P) % 1;
      if (phi < 0) phi += 1;

      const b = Math.floor(phi * nBins) % nBins;
      if (ref[b] === null) continue;

      const mag = state.mag[i] - detrendValue(sid, state.jd[i]);
      diffs.push(mag - ref[b]);
    }

    if (diffs.length > 10) {
      const offset = -median(diffs);
      const medianAD = mad(diffs);
      const sigma = 1.4826 * medianAD;
      
      // ✅ Test significatività
      const significant = Math.abs(offset) > 3 * sigma / Math.sqrt(diffs.length);
      
      if (significant) {
        state.sessionAutoOffset.set(sid, offset);
        console.log(`  S${sid}: offset = ${offset.toFixed(4)} mag (σ=${sigma.toFixed(3)}, significativo)`);
      } else {
        state.sessionAutoOffset.set(sid, 0);
        console.log(`  S${sid}: offset = ${offset.toFixed(4)} mag (non significativo)`);
      }
    }
  }
}

/**
 * Costruisce array tipizzati per analisi (periodogramma, fase)
 * Include detrending e offset
 */
export function buildAnalysisArraysTyped() {
  let m = 0;
  
  // Conta punti attivi
  for (let i = 0; i < state.n; i++) {
    if (state.activePoint[i] === 1 && state.activeSession.get(state.session[i])) {
      m++;
    }
  }
  
  const jd = new Float64Array(m);
  const mag = new Float32Array(m);
  let j = 0;
  
  for (let i = 0; i < state.n; i++) {
    if (state.activePoint[i] === 0 || !state.activeSession.get(state.session[i])) {
      continue;
    }
    
    const sid = state.session[i];
    jd[j] = state.jd[i];
    
    // Applica detrend e offset
    const auto = state.sessionAutoOffset.get(sid) || 0;
    const manual = state.sessionManualOffset.get(sid) || 0;
    
    mag[j] = (state.mag[i] - detrendValue(sid, state.jd[i])) + auto + manual;
    
    j++;
  }
  
  return { jd, mag };
}

export function alignSessionsToMag(targetMag) {
  if (!targetMag || !isFinite(targetMag)) {
    alert("Inserisci una magnitudine valida");
    return;
  }
  
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
  
  console.log("Allineamento completato a mag:", targetMag);
}
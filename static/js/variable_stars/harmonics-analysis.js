//harmonics-analysis.js
import { state, colorForSession, nameForSession, getTotalOffset } from './state.js';
import { detrendValue } from './math-logic.js';

let selectedHarmonic = null;


// FFT ottimizzata (iterativa, più veloce della ricorsiva)
function fft(real) {
  const n = real.length;
  if (n <= 1) return real.map(r => ({ re: r, im: 0 }));
  
  // Pad to power of 2
  const N = Math.pow(2, Math.ceil(Math.log2(n)));
  const x = new Array(N);
  for (let i = 0; i < n; i++) {
    x[i] = { re: real[i], im: 0 };
  }
  for (let i = n; i < N; i++) {
    x[i] = { re: 0, im: 0 };
  }
  
  // Bit-reversal permutation
  const bits = Math.log2(N);
  for (let i = 0; i < N; i++) {
    const rev = bitReverse(i, bits);
    if (rev > i) {
      [x[i], x[rev]] = [x[rev], x[i]];
    }
  }
  
  // FFT iterativa (Cooley-Tukey)
  for (let size = 2; size <= N; size *= 2) {
    const halfSize = size / 2;
    const angle = -2 * Math.PI / size;
    
    for (let i = 0; i < N; i += size) {
      for (let k = 0; k < halfSize; k++) {
        const theta = angle * k;
        const wRe = Math.cos(theta);
        const wIm = Math.sin(theta);
        
        const even = x[i + k];
        const odd = x[i + k + halfSize];
        
        const tRe = wRe * odd.re - wIm * odd.im;
        const tIm = wRe * odd.im + wIm * odd.re;
        
        x[i + k] = {
          re: even.re + tRe,
          im: even.im + tIm
        };
        x[i + k + halfSize] = {
          re: even.re - tRe,
          im: even.im - tIm
        };
      }
    }
  }
  
  return x;
}

function bitReverse(n, bits) {
  let reversed = 0;
  for (let i = 0; i < bits; i++) {
    reversed = (reversed << 1) | (n & 1);
    n >>= 1;
  }
  return reversed;
}

// Calcola magnitudine dello spettro
function magnitude(complex) {
  return complex.map(c => Math.sqrt(c.re * c.re + c.im * c.im));
}

// STRATEGIA 1: Binning in fase (riduce drasticamente i dati)
function binDataInPhase(data, nBins = 2048) {
  const bins = new Array(nBins);
  const counts = new Array(nBins).fill(0);
  
  for (let i = 0; i < nBins; i++) {
    bins[i] = { phase: i / nBins, mag: 0 };
  }
  
  // Accumula in bin
  data.forEach(d => {
    const binIdx = Math.floor(d.phase * nBins) % nBins;
    bins[binIdx].mag += d.mag;
    counts[binIdx]++;
  });
  
  // Media per bin
  for (let i = 0; i < nBins; i++) {
    if (counts[i] > 0) {
      bins[i].mag /= counts[i];
    } else {
      // Interpola da bin vicini se vuoto
      let left = i - 1, right = i + 1;
      while (left >= 0 && counts[left] === 0) left--;
      while (right < nBins && counts[right] === 0) right++;
      
      if (left >= 0 && right < nBins) {
        const t = (i - left) / (right - left);
        bins[i].mag = bins[left].mag + t * (bins[right].mag - bins[left].mag);
      } else if (left >= 0) {
        bins[i].mag = bins[left].mag;
      } else if (right < nBins) {
        bins[i].mag = bins[right].mag;
      }
    }
  }
  
  return bins;
}

// Identifica armoniche (multipli del periodo fondamentale)
function identifyHarmonics(spectrum, fundamental, nHarmonics) {
  const harmonics = [];
  
  for (let n = 1; n <= nHarmonics; n++) {
    const targetFreq = n * fundamental;
    const searchIdx = Math.round(targetFreq * spectrum.length);
    let maxIdx = searchIdx;
    let maxVal = spectrum[searchIdx] || 0;
    
    // Cerca in un range ±5% intorno alla frequenza attesa
    const range = Math.ceil(spectrum.length * 0.05);
    for (let i = Math.max(0, searchIdx - range); i < Math.min(spectrum.length, searchIdx + range); i++) {
      if (spectrum[i] > maxVal) {
        maxVal = spectrum[i];
        maxIdx = i;
      }
    }
    
    const freq = maxIdx / spectrum.length;
    const amplitude = maxVal;
    const avgPower = spectrum.reduce((a, b) => a + b, 0) / spectrum.length;
    
    harmonics.push({
      n: n,
      frequency: freq,
      period: freq > 0 ? 1 / freq : 0,
      amplitude: amplitude,
      snr: amplitude / avgPower
    });
  }
  
  return harmonics;
}

// Fit multi-sinusoidale
function fitMultiSine(phases, mags, harmonics) {
  const n = phases.length;
  if (n === 0) return { residuals: [], rms: 0, params: {} };
  
  // A0 (offset)
  const A0 = mags.reduce((a, b) => a + b, 0) / n;
  
  // Per ogni armonica, stima ampiezza e fase
  const params = { A0 };
  const fitted = new Array(n).fill(A0);
  
  harmonics.slice(0, 3).forEach((h) => {
    // Stima ampiezza tramite correlazione
    let sumCos = 0, sumSin = 0;
    for (let i = 0; i < n; i++) {
      const angle = 2 * Math.PI * h.n * phases[i];
      sumCos += (mags[i] - A0) * Math.cos(angle);
      sumSin += (mags[i] - A0) * Math.sin(angle);
    }
    const Ai = 2 * Math.sqrt(sumCos * sumCos + sumSin * sumSin) / n;
    const phi = Math.atan2(sumSin, sumCos);
    
    // ✅ CORREZIONE: sintassi corretta per chiavi dinamiche
    params[`A${h.n}`] = Ai;
    params[`phi${h.n}`] = phi;
    
    // Aggiungi al fit
    for (let i = 0; i < n; i++) {
      fitted[i] += Ai * Math.sin(2 * Math.PI * h.n * phases[i] + phi);
    }
  });
  
  // Residui
  const residuals = mags.map((m, i) => m - fitted[i]);
  const rms = Math.sqrt(residuals.reduce((a, b) => a + b * b, 0) / n);
  
  return { residuals, rms, params, fitted };
}

function highlightFFT(n) {
  const gd = document.getElementById("plotFFT");
  if (!gd || !gd.data?.length) return;
  const f = n; // n × f0, con f0 = 1
  const maxY = Math.max(...gd.data[0].y);
  const markerTrace = {
    x: [f],
    y: [maxY],
    type: "scatter",
    mode: "markers",
    marker: {
      size: 12,
      color: "#ef4444",
      symbol: "star"
    },
    name: `Armonica ${n}`
  };
  Plotly.react("plotFFT", [...gd.data, markerTrace], gd.layout);
}

function overlayPhaseHarmonic(n, params) {
  const gd = document.getElementById("plotPhase");
  // ✅ CORREZIONE: sintassi corretta per accesso proprietà
  if (!gd || !params[`A${n}`]) return;
  
  const A = params[`A${n}`];
  const phi = params[`phi${n}`];
  const x = [];
  const y = [];
  const steps = 400;
  for (let i = 0; i <= steps; i++) {
    const phase = i / steps;
    x.push(phase);
    y.push(params.A0 + A * Math.sin(2 * Math.PI * n * phase + phi));
  }
  const trace = {
    x,
    y,
    type: "scatter",
    mode: "lines",
    line: { color: "#ef4444", width: 2 },
    name: `${n}× f₀`,
  };
  Plotly.react("plotPhase", [...gd.data, trace], gd.layout);
}

// Funzione principale: analisi armonica OTTIMIZZATA
export async function computeHarmonics() {
  const P = state.lastPeriod;
  if (!P || P <= 0) {
    alert("Calcola prima l'analisi in fase!");
    return;
  }
  
  const shift = state.phaseShift;
  const nHarmonics = parseInt(document.getElementById("nHarmonics")?.value) || 5;
  
  // Mostra feedback
  const statusDiv = document.getElementById("harmonicsList");
  if (statusDiv) statusDiv.innerHTML = '<div style="padding: 20px; text-align: center;"><div style="font-size: 14px;">⏳ Elaborazione...</div></div>';
  
  // Raccogli dati in fase
  const data = [];
  for (let i = 0; i < state.n; i++) {
    if (state.activePoint[i] === 0) continue;
    const sid = state.session[i];
    if (!state.activeSession.get(sid)) continue;
    
    let phase = ((state.jd[i] / P) + shift) % 1.0;
    if (phase < 0) phase += 1.0;
    
    const mag = (state.mag[i] - detrendValue(sid, state.jd[i])) + getTotalOffset(sid);
    data.push({ phase, mag, sid });
  }
  
  if (data.length < 10) {
    alert("Dati insufficienti per FFT!");
    return;
  }
  
  console.log(`📊 Dati originali: ${data.length} punti`);
  
  // STRATEGIA: Binning in fase (riduce da 500k a 2048 punti)
  const nBins = Number(document.getElementById("fftBins")?.value) || 2048;
  if (nBins > 8192 && data.length > 200000) {
    alert("⚠️ Troppi bin per il numero di punti. Riduci i bin FFT.");
    return;
  }
  const binnedData = binDataInPhase(data, nBins);
  
  console.log(`📉 Dopo binning: ${binnedData.length} bin`);
  
  // Prepara per FFT
  const mags = binnedData.map(d => d.mag);
  const mean = mags.reduce((a, b) => a + b, 0) / mags.length;
  const centered = mags.map(m => m - mean);
  
  // FFT (ora su 2048 punti invece di 500k!)
  console.time('FFT');
  const spectrum = magnitude(fft(centered));
  console.timeEnd('FFT');
  
  const halfSpectrum = spectrum.slice(0, Math.floor(spectrum.length / 2));
  
  // Identifica armoniche
  const fundamental = 1.0;
  const harmonics = identifyHarmonics(halfSpectrum, fundamental, nHarmonics);
  
  // Fit multi-sinusoidale (su dati binned)
  const phases = binnedData.map(d => d.phase);
  const magsBinned = binnedData.map(d => d.mag);
  const { residuals, rms, params, fitted } = fitMultiSine(phases, magsBinned, harmonics);
  
  // Plot FFT
  const freqs = halfSpectrum.map((_, i) => i / spectrum.length);
  
  // Filtra solo frequenze significative per visualizzazione
  const maxFreqToShow = Math.max(5, nHarmonics * 1.2);
  const filteredFreqs = [];
  const filteredSpectrum = [];
  for (let i = 0; i < freqs.length; i++) {
    if (freqs[i] <= maxFreqToShow) {
      filteredFreqs.push(freqs[i]);
      filteredSpectrum.push(halfSpectrum[i]);
    }
  }
  
  Plotly.react("plotFFT", [{
    x: filteredFreqs,
    y: filteredSpectrum,
    type: "scatter",
    mode: "lines",
    line: { color: "#3b82f6", width: 2 },
    name: "Power Spectrum"
  }], {
    title: "FFT del Segnale in Fase",
    xaxis: { title: "Frequenza (cicli/fase)" },
    yaxis: {
      title: "Ampiezza (log)",
      type: "log",
      autorange: true,
      showlegend: false
    }  
  });
  
  // Plot residui (downsample se troppi punti)
  const maxResPoints = 5000;
  const resStep = Math.max(1, Math.floor(residuals.length / maxResPoints));
  const sampledPhases = phases.filter((_, i) => i % resStep === 0);
  const sampledResiduals = residuals.filter((_, i) => i % resStep === 0);
  
  const resTrace = {
    x: sampledPhases,
    y: sampledResiduals,
    type: "scattergl",
    mode: "markers",
    marker: { size: 3, color: "#64748b", opacity: 0.6 },
    name: "Residui"
  };
  
  Plotly.react("plotResiduals", [resTrace], {
    title: `Residui del Fit (RMS = ${rms.toFixed(4)} mag)`,
    xaxis: { title: "Fase", range: [0, 1] },
    yaxis: { title: "O - C (mag)", zeroline: true, zerolinecolor: "#ef4444" },
    showlegend: false
  });
  
  // Lista armoniche
  renderHarmonicsList(harmonics, params, data.length, binnedData.length);
}

function renderHarmonicsList(harmonics, params, nOriginal, nBinned) {
  const div = document.getElementById("harmonicsList");
  if (!div) return;
  
  let html = '<div style="display: flex; flex-direction: column; gap: 8px;">';
  
  // Info sul binning
  html += `
    <div style="padding: 8px; background: #f0f9ff; border-radius: 6px; font-size: 11px; margin-bottom: 8px;">
      <strong>📊 Dati:</strong> ${nOriginal.toLocaleString()} → ${nBinned} bin
    </div>
  `;
  
  harmonics.forEach(h => {
    // ✅ CORREZIONE: sintassi corretta per accesso proprietà
    const A = params[`A${h.n}`] || 0;
    const phi = params[`phi${h.n}`] || 0;
    
    html += `
      <div
        class="harmonic-item"
        data-n="${h.n}"
        style="
          cursor:pointer;
          padding: 8px;
          background: ${h.snr > 3 ? '#dcfce7' : '#fef3c7'};
          border-radius: 6px;
          border: 2px solid transparent;
        "
      >
        <div style="font-weight:600; margin-bottom:4px;">
          ${h.n}× f₀ ${h.snr > 3 ? '⭐' : ''}
        </div>
        <div style="font-size:11px;">
          A = ${A.toFixed(4)} mag<br>
          φ = ${phi.toFixed(2)} rad<br>
          SNR = ${h.snr.toFixed(1)}
        </div>
      </div>
    `;
  });
  
  html += '</div>';
  div.innerHTML = html;
  div.querySelectorAll('.harmonic-item').forEach(el => {
    el.onclick = () => {
      selectedHarmonic = Number(el.dataset.n);
      highlightFFT(selectedHarmonic);
      overlayPhaseHarmonic(selectedHarmonic, params);
    };
  });
}

export function syncHarmonicsPeriod() {
  const el = document.getElementById("harmonicsPeriod");
  if (!el) return;
  el.value = state.lastPeriod || "";
}
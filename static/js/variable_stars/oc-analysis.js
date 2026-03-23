import { state, colorForSession, nameForSession, getTotalOffset } from './state.js';
import { detrendValue } from './math-logic.js';


/* =========================================================
   Utility matematiche
   ========================================================= */

// Fit lineare y = a + b x
function linearFit(x, y) {
  const n = x.length;
  let sx = 0, sy = 0, sxx = 0, sxy = 0;

  for (let i = 0; i < n; i++) {
    sx += x[i];
    sy += y[i];
    sxx += x[i] * x[i];
    sxy += x[i] * y[i];
  }

  const b = (n * sxy - sx * sy) / (n * sxx - sx * sx);
  const a = (sy - b * sx) / n;

  const ymean = sy / n;
  let ssr = 0, sst = 0;
  for (let i = 0; i < n; i++) {
    const yf = a + b * x[i];
    ssr += (y[i] - yf) ** 2;
    sst += (y[i] - ymean) ** 2;
  }

  return { a, b, r2: 1 - ssr / sst };
}

// Fit quadratico y = a + b x + c x²
function quadraticFit(x, y) {
  const n = x.length;
  let sx = 0, sx2 = 0, sx3 = 0, sx4 = 0;
  let sy = 0, sxy = 0, sx2y = 0;

  for (let i = 0; i < n; i++) {
    const xi = x[i], yi = y[i];
    const xi2 = xi * xi;

    sx += xi;
    sx2 += xi2;
    sx3 += xi2 * xi;
    sx4 += xi2 * xi2;
    sy += yi;
    sxy += xi * yi;
    sx2y += xi2 * yi;
  }

  const A = [
    [n, sx, sx2],
    [sx, sx2, sx3],
    [sx2, sx3, sx4]
  ];
  const B = [sy, sxy, sx2y];

  const sol = solve3x3(A, B);
  if (!sol) return null;

  const [a, b, c] = sol;

  const ymean = sy / n;
  let ssr = 0, sst = 0;
  for (let i = 0; i < n; i++) {
    const yf = a + b * x[i] + c * x[i] * x[i];
    ssr += (y[i] - yf) ** 2;
    sst += (y[i] - ymean) ** 2;
  }

  return { a, b, c, r2: 1 - ssr / sst };
}

// Risolutore 3x3 (Gauss)
function solve3x3(A, b) {
  const M = A.map((r, i) => [...r, b[i]]);

  for (let c = 0; c < 3; c++) {
    let p = c;
    for (let r = c + 1; r < 3; r++) {
      if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r;
    }
    if (Math.abs(M[p][c]) < 1e-14) return null;

    [M[c], M[p]] = [M[p], M[c]];
    const d = M[c][c];
    for (let j = c; j < 4; j++) M[c][j] /= d;

    for (let r = 0; r < 3; r++) {
      if (r === c) continue;
      const f = M[r][c];
      for (let j = c; j < 4; j++) {
        M[r][j] -= f * M[c][j];
      }
    }
  }

  return [M[0][3], M[1][3], M[2][3]];
}

/* =========================================================
   O–C ANALYSIS
   ========================================================= */

export function computeOC() {
  const P = state.lastPeriod;
  if (!P || P <= 0) {
    alert("Calcola prima il periodo.");
    return;
  }

  const jd0Input = document.getElementById("ocEpoch");
  if (!jd0Input) {
    console.warn("Campo ocEpoch non trovato");
    return;
  }

  let jd0 = parseFloat(jd0Input.value);

  /* ---------- 1. trova massimi per sessione ---------- */

  const maxima = new Map();

  for (let i = 0; i < state.n; i++) {
    if (state.activePoint[i] === 0) continue;
    const sid = state.session[i];
    if (!state.activeSession.get(sid)) continue;

    const jd = state.jd[i];
    const mag = (state.mag[i] - detrendValue(sid, jd)) + getTotalOffset(sid);

    if (!maxima.has(sid)) {
      maxima.set(sid, { jd, mag });
    } else {
      // RR Lyrae: massimo = magnitudine minima
      if (mag < maxima.get(sid).mag) {
        maxima.set(sid, { jd, mag });
      }
    }
  }

  if (maxima.size < 3) {
    alert("Numero di sessioni insufficiente per O–C");
    return;
  }

  /* ---------- 2. jd0 automatico ---------- */

  if (!isFinite(jd0)) {
    jd0 = Math.min(...[...maxima.values()].map(v => v.jd));
    jd0Input.value = jd0.toFixed(6);
  }

  /* ---------- 3. costruisci O–C ---------- */

  const data = [];
  maxima.forEach((v, sid) => {
    const E = Math.round((v.jd - jd0) / P);
    const calc = jd0 + E * P;
    const oc = (v.jd - calc) * 24 * 60; // minuti

    data.push({ sid, epoch: E, oc });
  });

  const epochs = data.map(d => d.epoch);
  const ocs = data.map(d => d.oc);

  /* ---------- 4. fit ---------- */

  const model = document.getElementById("ocModel")?.value || "linear";
  let fit = null;
  let fitLine = [];

  if (model === "linear") {
    fit = linearFit(epochs, ocs);

    const e0 = Math.min(...epochs);
    const e1 = Math.max(...epochs);
    fitLine = [
      { x: e0, y: fit.a + fit.b * e0 },
      { x: e1, y: fit.a + fit.b * e1 }
    ];

    fit.dPdt = (fit.b / (24 * 60)) * P;
    fit.dPdt_year = fit.dPdt * 365.25 * 86400;
  }

  if (model === "quadratic") {
    fit = quadraticFit(epochs, ocs);
    if (fit) {
      const e0 = Math.min(...epochs);
      const e1 = Math.max(...epochs);
      for (let e = e0; e <= e1; e += (e1 - e0) / 100) {
        fitLine.push({ x: e, y: fit.a + fit.b * e + fit.c * e * e });
      }

      const mid = 0.5 * (e0 + e1);
      const dOCdE = fit.b + 2 * fit.c * mid;
      fit.dPdt = (dOCdE / (24 * 60)) * P;
      fit.dPdt_year = fit.dPdt * 365.25 * 86400;
    }
  }

  /* ---------- 5. plot ---------- */

  const traces = [];

  data.forEach(d => {
    traces.push({
      x: [d.epoch],
      y: [d.oc],
      type: "scatter",
      mode: "markers",
      marker: {
        size: 7,
        color: colorForSession(d.sid)
      },
      name: nameForSession(d.sid),
      showlegend: false
    });
  });

  if (fitLine.length) {
    traces.push({
      x: fitLine.map(p => p.x),
      y: fitLine.map(p => p.y),
      mode: "lines",
      line: { color: "#ef4444", width: 2 },
      name: "Fit"
    });
  }

  Plotly.react("plotOC", traces, {
    title: "O–C Diagram",
    xaxis: { title: "Epoca (E)" },
    yaxis: { title: "O − C (min)", zeroline: true },
    showlegend: false
  });

  renderOCStats(fit, model, data.length);
}

/* =========================================================
   STATISTICHE
   ========================================================= */

function renderOCStats(fit, model, n) {
  const div = document.getElementById("ocStats");
  if (!div) return;

  let html = `<div><strong>Punti:</strong> ${n}</div>`;
  html += `<div><strong>Modello:</strong> ${model}</div>`;

  if (fit) {
    html += `<div><strong>R²:</strong> ${fit.r2?.toFixed(4)}</div>`;
    if (fit.dPdt_year !== undefined) {
      html += `
        <div style="margin-top:6px;">
          <strong>dP/dt:</strong><br>
          ${fit.dPdt.toExponential(3)} d/d<br>
          ${fit.dPdt_year.toFixed(4)} s/anno
        </div>`;
    }
  }

  div.innerHTML = html;
}

/* =========================================================
   SYNC
   ========================================================= */

export function syncOCPeriod() {
  const el = document.getElementById("ocPeriod");
  if (el) el.value = state.lastPeriod || "";
}

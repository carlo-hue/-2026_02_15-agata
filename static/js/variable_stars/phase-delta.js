// phase-delta.js
import { state, colorForSession, nameForSession, getTotalOffset } from './state.js';
import { CONFIG } from './config.js';
import { detrendValue } from './math-logic.js'; 

export function computePhaseDelta(P, deltaP, sampleFraction = 0.1) {
  if (!P || deltaP <= 0) return [];
  
  const periods = [
    { value: P - 2 * deltaP, label: 'P - 2ΔP' },
    { value: P - deltaP, label: 'P - ΔP' },
    { value: P + deltaP, label: 'P + ΔP' },
    { value: P + 2 * deltaP, label: 'P + 2ΔP' }
  ].filter(p => p.value > 0);
  
  const shift = state.phaseShift || 0;
  const jd0 = state.epoch || state.jd[0];  // ✅ USA state.epoch se disponibile
  const results = [];
  
  for (const { value: testP, label } of periods) {
    const traces = [];
    
    // Per ogni sessione attiva
    for (const sid of state.activeSession.keys()) {
      if (!state.activeSession.get(sid)) continue;
      
      const xArr = [];
      const yArr = [];
      
      // Sampling per performance
      const step = Math.max(1, Math.floor(1 / sampleFraction));
      
      for (let i = 0; i < state.n; i += step) {
        if (state.session[i] !== sid || !state.activePoint[i]) continue;
        
        let phase = (((state.jd[i] - jd0) / testP) + shift) % 1.0;
        if (phase < 0) phase += 1.0;
        
        // ✅ FIX: USA DETRENDING come computePhase()
        const yval = (state.mag[i] - detrendValue(sid, state.jd[i])) + getTotalOffset(sid);
        
        // Duplica punti per range -1 a 1
        xArr.push(phase - 1.0);
        yArr.push(yval);
        xArr.push(phase);
        yArr.push(yval);
        xArr.push(phase + 1.0);
        yArr.push(yval);
      }
      
      if (xArr.length > 0) {
        traces.push({
          x: xArr,
          y: yArr,
          type: 'scattergl',
          mode: 'markers',
          marker: { size: state.currentMarkerSize, color: colorForSession(sid), opacity: 0.6 },
          name: nameForSession(sid),
          showlegend: false
        });
      }
    }
    
    results.push({ period: testP, label, traces });
  }
  
  return results;
}

export function renderPhaseDelta(results) {
  const container = document.getElementById('phaseDeltaGrid');
  if (!container) {
    console.error("Container phaseDeltaGrid non trovato!");
    return;
  }
  
  container.innerHTML = '';
  
  if (results.length === 0) {
    container.innerHTML = '<div style="padding: 20px; text-align: center; color: #64748b;">Nessun periodo da confrontare</div>';
    return;
  }
  
  results.forEach(({ period, label, traces }, idx) => {
    const plotDiv = document.createElement('div');
    plotDiv.className = 'delta-p-plot';
    plotDiv.id = `deltaPlot${idx}`;
    
    const header = document.createElement('div');
    header.className = 'delta-p-header';
    header.textContent = `${label} = ${period.toFixed(6)}d`;
    
    const chartDiv = document.createElement('div');
    chartDiv.style.flex = '1';
    chartDiv.style.minHeight = '0';
    
    plotDiv.appendChild(header);
    plotDiv.appendChild(chartDiv);
    container.appendChild(plotDiv);
    
    const layout = {
      title: '',
      xaxis: { title: 'Fase', range: [-1, 1], fixedrange: false },
      yaxis: { title: 'Mag', autorange: 'reversed', fixedrange: false },
      margin: { l: 45, r: 15, t: 5, b: 35 },
      showlegend: false,
      hovermode: 'closest'
    };
    
    Plotly.newPlot(chartDiv, traces, layout, { 
      responsive: true,
      displayModeBar: false
    });
  });
}

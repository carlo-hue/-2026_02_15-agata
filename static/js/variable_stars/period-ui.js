// period-ui.js

/**
 * Renderizza i picchi del periodogramma con statistiche di qualità
 * @param {Array} peaks - Array di oggetti con {period, power, snr, fap}
 * @param {Function} onSelect - Callback chiamata quando si clicca su un periodo
 */
export function renderPeriodPeaks(peaks, onSelect) {
  const box = document.getElementById("peaks");
  box.innerHTML = "";

  peaks.forEach((p, idx) => {
    const div = document.createElement("div");
    div.className = "peak-item";
    div.style.cursor = "pointer";

    // Determina il badge di qualità basato su FAP
    let qualityBadge = "";
    let qualityColor = "";
    if (p.fap < 1e-3) {
      qualityBadge = "⭐ Eccellente";
      qualityColor = "#22c55e";
    } else if (p.fap < 1e-2) {
      qualityBadge = "✓ Buono";
      qualityColor = "#facc15";
    } else {
      qualityBadge = "⚠ Da verificare";
      qualityColor = "#f97316";
    }

    div.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
        <strong style="font-size: 14px;">#${idx + 1} P = ${p.period.toFixed(6)} d</strong>
        <span style="background: ${qualityColor}; color: #000; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 600;">${qualityBadge}</span>
      </div>
      <div style="font-size: 11px; opacity: 0.9; line-height: 1.4;">
        Power: <strong>${p.power.toFixed(3)}</strong> |
        SNR: <strong>${p.snr.toFixed(1)}</strong><br>
        FAP: <strong>${p.fap.toExponential(2)}</strong>
      </div>
    `;
    div.onclick = () => onSelect(p.period);
    box.appendChild(div);
  });
}

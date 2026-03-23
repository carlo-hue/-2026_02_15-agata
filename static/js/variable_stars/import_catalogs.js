/**
 * Import Catalogs Tab - Ricerca e importazione cataloghi fotometrici
 *
 * Supports: TESS QLP, ZTF
 *
 * API Endpoints:
 * - POST /agata/admin/api/catalogs/tess/qlp/search-sectors - Search TESS QLP sectors by Gaia ID
 * - POST /agata/admin/api/catalogs/tess/qlp/download-sector - Download and import sector
 * - POST /agata/admin/api/catalogs/ztf/search-and-import - Search and import ZTF data
 */

export function initImportCatalogs() {
  console.log('[ImportCatalogs] Module initialized');

  // Popola Gaia ID dal progetto
  const gaiaIdInput = document.getElementById('import-gaia-id');
  if (!gaiaIdInput) return;

  const projectGaiaId = document.getElementById('projectGaiaId')?.value;
  const urlParams = new URLSearchParams(window.location.search);
  const urlGaiaId = urlParams.get('gaia_id');

  const gaiaId = projectGaiaId || urlGaiaId;
  if (gaiaId) {
    gaiaIdInput.value = gaiaId;
    console.log(`[ImportCatalogs] Gaia ID loaded: ${gaiaId}`);
  }
}

/**
 * Main search function - dispatches to TESS or ZTF based on dropdown selection
 */
window.searchImportCatalogs = async function() {
  const catalog = document.getElementById('import-catalog-select')?.value || 'TESS';

  if (catalog === 'ZTF') {
    await searchZTF();
  } else {
    await searchTESS();
  }
};

/**
 * Search TESS QLP sectors by Gaia ID
 */
async function searchTESS() {
  const gaiaId = document.getElementById('import-gaia-id')?.value;
  const resultsDiv = document.getElementById('import-results');
  const searchBtn = document.getElementById('import-search-btn');

  if (!gaiaId) {
    showImportStatus('error', 'Gaia ID mancante');
    return;
  }

  searchBtn.disabled = true;
  searchBtn.style.opacity = '0.6';
  searchBtn.textContent = 'Ricerca in corso...';
  showImportStatus('info', 'Step 1/2: Ricerca settori QLP disponibili su MAST...');
  resultsDiv.innerHTML = '<p style="color: #999; text-align: center; padding: 2rem;">Interrogazione archivio TESS su MAST...</p>';

  try {
    const response = await fetch('/agata/admin/api/catalogs/tess/qlp/search-sectors', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ gaia_id: gaiaId })
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.error || `HTTP ${response.status}`);
    }

    const data = await response.json();
    if (!data.success) {
      throw new Error(data.error || 'Search failed');
    }

    // Store lcfs_serialized for download step
    window.lcfsSerializedData = data.lcfs_serialized;
    console.log('[ImportCatalogs] Stored lcfs_serialized for download (', data.lcfs_serialized?.length, 'bytes)');

    displayTESSResults(data, gaiaId);
    showImportStatus('success', 'Step 2/2: Seleziona uno o piu settori da scaricare');

  } catch (error) {
    console.error('[ImportCatalogs] TESS search error:', error);
    showImportStatus('error', `Errore: ${error.message}`);
    resultsDiv.innerHTML = `
      <div style="padding: 2rem; text-align: center;">
        <p style="color: #dc2626; font-weight: 600;">Errore durante la ricerca TESS</p>
        <p style="color: #666; font-size: 0.9rem;">${error.message}</p>
      </div>
    `;
  } finally {
    searchBtn.disabled = false;
    searchBtn.style.opacity = '1';
    searchBtn.textContent = 'Cerca';
  }
}

/**
 * Search and import ZTF data by Gaia ID (single step)
 */
async function searchZTF() {
  const gaiaId = document.getElementById('import-gaia-id')?.value;
  const resultsDiv = document.getElementById('import-results');
  const searchBtn = document.getElementById('import-search-btn');

  if (!gaiaId) {
    showImportStatus('error', 'Gaia ID mancante');
    return;
  }

  searchBtn.disabled = true;
  searchBtn.style.opacity = '0.6';
  searchBtn.textContent = 'Ricerca ZTF in corso...';
  showImportStatus('info', 'Ricerca e import dati ZTF da IRSA...');
  resultsDiv.innerHTML = '<p style="color: #999; text-align: center; padding: 2rem;">Interrogazione archivio ZTF su IRSA...</p>';

  try {
    const response = await fetch('/agata/admin/api/catalogs/ztf/search-and-import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ gaia_id: gaiaId })
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.error || `HTTP ${response.status}`);
    }

    const data = await response.json();
    if (!data.success) {
      throw new Error(data.error || 'Import failed');
    }

    displayZTFResults(data, gaiaId);
    showImportStatus('success', `Import ZTF completato: ${data.total_points} punti importati`);

  } catch (error) {
    console.error('[ImportCatalogs] ZTF error:', error);
    showImportStatus('error', `Errore ZTF: ${error.message}`);
    resultsDiv.innerHTML = `
      <div style="padding: 2rem; text-align: center;">
        <p style="color: #dc2626; font-weight: 600;">Errore durante la ricerca ZTF</p>
        <p style="color: #666; font-size: 0.9rem;">${error.message}</p>
      </div>
    `;
  } finally {
    searchBtn.disabled = false;
    searchBtn.style.opacity = '1';
    searchBtn.textContent = 'Cerca';
  }
}

/**
 * Show status message (info/success/error)
 */
function showImportStatus(type, message) {
  const statusDiv = document.getElementById('import-status');
  if (!statusDiv) return;

  const colors = {
    info: { bg: '#dbeafe', text: '#1e40af' },
    success: { bg: '#d1fae5', text: '#065f46' },
    error: { bg: '#fee2e2', text: '#991b1b' }
  };

  const color = colors[type] || colors.info;
  statusDiv.style.background = color.bg;
  statusDiv.style.color = color.text;
  statusDiv.style.border = `1px solid ${color.text}`;
  statusDiv.textContent = message;
  statusDiv.style.display = 'block';
}

/**
 * Display TESS QLP search results with sector options
 */
function displayTESSResults(data, gaiaId) {
  const resultsDiv = document.getElementById('import-results');
  if (!resultsDiv) return;

  let html = '<div style="display: flex; flex-direction: column; gap: 1.5rem;">';

  // Target Info
  html += `
    <div style="padding: 1rem; background: #f9fafb; border-radius: 6px; border: 1px solid #e5e7eb;">
      <h5 style="margin: 0 0 0.75rem 0; color: #374151;">Target TESS</h5>
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.5rem; font-size: 0.9rem;">
        <div><strong>Gaia ID:</strong> <code>${data.gaia_id}</code></div>
        <div><strong>TIC ID:</strong> <code>${data.tic_id}</code></div>
        <div><strong>TESS Mag:</strong> ${data.tmag?.toFixed(2) || 'N/A'}</div>
        <div><strong>Settori:</strong> ${data.sectors?.length || 0}</div>
      </div>
    </div>
  `;

  // Sector Options (Checkboxes)
  if (data.sectors && data.sectors.length > 0) {
    html += `
      <div style="padding: 1rem; border: 1px solid var(--border); border-radius: 6px; background: white;">
        <h5 style="margin: 0 0 1rem 0; color: #374151;">Seleziona settori da importare</h5>
        <div style="display: flex; flex-direction: column; gap: 0.75rem;">
    `;

    for (const sectorInfo of data.sectors) {
      const sector = sectorInfo.sector;
      const idx = sectorInfo.idx;

      html += `
        <label style="display: flex; align-items: center; gap: 0.75rem; padding: 0.75rem; background: #f9fafb; border-radius: 4px; cursor: pointer; border: 1px solid #e5e7eb; transition: all 0.2s;">
          <input type="checkbox" name="import-sectors" value="${sector}" data-idx="${idx}" style="cursor: pointer;" onchange="updateImportSummary()">
          <div style="flex-grow: 1;">
            <strong>Settore ${sector}</strong>
            <div style="font-size: 0.85rem; color: #666;">
              TESS QLP dati completi
            </div>
          </div>
        </label>
      `;
    }

    html += `
        </div>
        <div style="margin-top: 1rem; padding-top: 1rem; border-top: 1px solid #e5e7eb;">
          <button
            id="import-execute-btn"
            style="padding: 0.75rem 1.5rem; background: #10b981; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: 600; transition: opacity 0.2s;"
            onclick="executeImport('${data.gaia_id}', ${data.tic_id})"
          >
            Importa settori selezionati
          </button>
          <span id="import-summary" style="margin-left: 1rem; color: #666; font-size: 0.9rem;"></span>
        </div>
      </div>
    `;
  } else {
    html += `
      <div style="padding: 2rem; text-align: center; background: #fef3c7; border-radius: 6px; border: 1px solid #fcd34d;">
        <p style="color: #92400e; margin: 0;">Nessun settore QLP disponibile per questa stella</p>
        <p style="color: #b45309; font-size: 0.9rem; margin: 0.5rem 0 0 0;">Prova con un Gaia ID diverso</p>
      </div>
    `;
  }

  html += '</div>';
  resultsDiv.innerHTML = html;
  updateImportSummary();
}

/**
 * Display ZTF import results (already imported in single step)
 */
function displayZTFResults(data, gaiaId) {
  const resultsDiv = document.getElementById('import-results');
  if (!resultsDiv) return;

  let html = '<div style="display: flex; flex-direction: column; gap: 1.5rem;">';

  // Target Info
  html += `
    <div style="padding: 1rem; background: #f9fafb; border-radius: 6px; border: 1px solid #e5e7eb;">
      <h5 style="margin: 0 0 0.75rem 0; color: #374151;">Target ZTF</h5>
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.5rem; font-size: 0.9rem;">
        <div><strong>Gaia ID:</strong> <code>${data.gaia_id}</code></div>
        <div><strong>RA:</strong> ${data.ra?.toFixed(6) || 'N/A'}</div>
        <div><strong>Dec:</strong> ${data.dec?.toFixed(6) || 'N/A'}</div>
        <div><strong>Punti totali:</strong> ${data.total_points}</div>
      </div>
    </div>
  `;

  // Band breakdown
  if (data.bands && Object.keys(data.bands).length > 0) {
    html += `
      <div style="padding: 1rem; border: 1px solid #6ee7b7; border-radius: 6px; background: #d1fae5;">
        <h5 style="margin: 0 0 0.75rem 0; color: #065f46;">Import completato</h5>
        <div style="display: flex; gap: 1rem; flex-wrap: wrap;">
    `;

    const bandColors = { 'ZTFg': '#22c55e', 'ZTFr': '#ef4444', 'ZTFi': '#a855f7' };

    for (const [band, count] of Object.entries(data.bands)) {
      const color = bandColors[band] || '#6b7280';
      html += `
        <div style="padding: 0.75rem 1.25rem; background: white; border-radius: 6px; border-left: 4px solid ${color}; min-width: 120px;">
          <div style="font-weight: 600; color: ${color};">${band}</div>
          <div style="font-size: 1.2rem; font-weight: 700; color: #374151;">${count}</div>
          <div style="font-size: 0.8rem; color: #666;">punti</div>
        </div>
      `;
    }

    html += '</div>';

    // Time and magnitude range
    if (data.time_range && data.time_range.span_days) {
      html += `
        <div style="margin-top: 0.75rem; font-size: 0.85rem; color: #047857;">
          Copertura temporale: ${data.time_range.span_days.toFixed(0)} giorni |
          Range magnitudine: ${data.mag_range?.min?.toFixed(2) || '?'} - ${data.mag_range?.max?.toFixed(2) || '?'}
        </div>
      `;
    }

    html += '</div>';
  }

  // Project link
  if (data.project_code) {
    html += `
      <div style="padding: 0.75rem 1rem; background: #dbeafe; border-radius: 6px; font-size: 0.9rem; color: #1e40af;">
        Dati collegati al progetto <strong>${data.project_code}</strong>
      </div>
    `;
  }

  html += '</div>';
  resultsDiv.innerHTML = html;
}

/**
 * Update import summary (count selected sectors) - TESS only
 */
window.updateImportSummary = function() {
  const checkboxes = document.querySelectorAll('input[name="import-sectors"]:checked');
  const summarySpan = document.getElementById('import-summary');

  if (summarySpan) {
    const count = checkboxes.length;
    const label = count === 1 ? 'settore' : 'settori';
    summarySpan.textContent = count > 0 ? `${count} ${label} selezionati` : 'Nessun settore selezionato';
  }
};

/**
 * Execute TESS import - Download and process selected sectors
 */
window.executeImport = async function(gaiaId, ticId) {
  const selectedSectors = Array.from(
    document.querySelectorAll('input[name="import-sectors"]:checked')
  ).map(cb => ({
    sector: parseInt(cb.value),
    idx: parseInt(cb.dataset.idx)
  }));

  if (selectedSectors.length === 0) {
    showImportStatus('error', 'Seleziona almeno un settore');
    return;
  }

  const resultsDiv = document.getElementById('import-results');
  const execBtn = document.getElementById('import-execute-btn');

  execBtn.disabled = true;
  execBtn.style.opacity = '0.6';
  execBtn.textContent = 'Import in corso...';

  showImportStatus('info', `Download e import dei file in corso (${selectedSectors.length} settori)...`);

  let totalImported = 0;
  let errors = [];

  try {
    // Download each sector sequentially
    for (let i = 0; i < selectedSectors.length; i++) {
      const sectorInfo = selectedSectors[i];
      const progress = `${i + 1}/${selectedSectors.length}`;

      showImportStatus('info', `[${progress}] Download settore ${sectorInfo.sector}...`);

      try {
        const downloadPayload = {
          gaia_id: gaiaId,
          tic_id: ticId,
          sector: sectorInfo.sector,
          sector_idx: sectorInfo.idx
        };

        // Include serialized SearchResult if available (optimization)
        if (window.lcfsSerializedData) {
          downloadPayload.lcfs_serialized = window.lcfsSerializedData;
          console.log('[ImportCatalogs] Using cached lcfs_serialized (skips Lightkurve search)');
        }

        const response = await fetch('/agata/admin/api/catalogs/tess/qlp/download-sector', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(downloadPayload)
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.error || `HTTP ${response.status}`);
        }

        const result = await response.json();

        if (result.success) {
          totalImported += result.points_imported || 0;
          showImportStatus('info', `[${progress}] Settore ${sectorInfo.sector}: ${result.points_imported} punti importati`);
        } else {
          errors.push(`Settore ${sectorInfo.sector}: ${result.error || 'Import failed'}`);
        }
      } catch (error) {
        errors.push(`Settore ${sectorInfo.sector}: ${error.message}`);
      }
    }

    // Show final result
    if (totalImported > 0) {
      showImportStatus('success', `Import completato! ${totalImported} punti fotometrici importati`);
      resultsDiv.innerHTML = `
        <div style="padding: 1.5rem; background: #d1fae5; border-radius: 6px; border: 1px solid #6ee7b7; text-align: center;">
          <h5 style="color: #065f46; margin: 0 0 0.5rem 0;">Import Completato</h5>
          <p style="color: #047857; margin: 0;">
            ${totalImported} punti fotometrici importati da ${selectedSectors.length} settori
          </p>
        </div>
      `;
    } else if (errors.length > 0) {
      showImportStatus('error', `Errori durante l'import`);
      resultsDiv.innerHTML = `
        <div style="padding: 1.5rem; background: #fee2e2; border-radius: 6px; border: 1px solid #fca5a5;">
          <h5 style="color: #991b1b; margin: 0 0 0.5rem 0;">Errori</h5>
          <ul style="margin: 0; color: #7f1d1d;">
            ${errors.map(e => `<li>${e}</li>`).join('')}
          </ul>
        </div>
      `;
    } else {
      showImportStatus('error', 'Nessun punto importato');
    }

  } catch (error) {
    console.error('[ImportCatalogs] Import error:', error);
    showImportStatus('error', `Errore durante l'import: ${error.message}`);
  } finally {
    execBtn.disabled = false;
    execBtn.style.opacity = '1';
    execBtn.textContent = 'Importa settori selezionati';
  }
};

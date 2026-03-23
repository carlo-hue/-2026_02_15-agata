/**
 * Catalog Tab - Interrogazione cataloghi esterni via Gaia ID
 *
 * Module responsibilities:
 * - Populate Gaia ID from project data
 * - Handle catalog query API calls
 * - Render results in structured format
 * - Display cache status and error messages
 */

export function initCatalogs() {
  console.log('[Catalogs] Module initialized');

  // Popola Gaia ID da progetto o URL query parameter
  const gaiaIdInput = document.getElementById('catalog-gaia-id');
  if (!gaiaIdInput) return;

  // Priorità 1: Gaia ID da hidden input (project.gaia_id)
  const projectGaiaId = document.getElementById('projectGaiaId')?.value;

  // Priorità 2: Gaia ID da URL query parameter (?gaia_id=...)
  const urlParams = new URLSearchParams(window.location.search);
  const urlGaiaId = urlParams.get('gaia_id');

  const gaiaId = projectGaiaId || urlGaiaId;

  if (gaiaId) {
    gaiaIdInput.value = gaiaId;
    console.log(`[Catalogs] Gaia ID loaded: ${gaiaId} (source: ${projectGaiaId ? 'project' : 'URL'})`);
  } else {
    console.warn('[Catalogs] Gaia ID not found in project or URL');
  }

  // Setup auto-refresh listener for cone radius changes
  const coneRadiusInput = document.getElementById('catalog-cone-radius');
  const refreshCheckbox = document.getElementById('catalog-refresh');

  if (coneRadiusInput && refreshCheckbox) {
    coneRadiusInput.addEventListener('change', () => {
      refreshCheckbox.checked = true;
      showStatus('info', '🔄 Force Refresh attivato automaticamente (raggio modificato)');
    });
  }
}

/**
 * Query catalogs - Main API call handler
 * Called by onclick from template button
 */
window.queryCatalogs = async function() {
  const gaiaId = document.getElementById('catalog-gaia-id')?.value;
  const context = document.getElementById('catalog-context')?.value || 'identificativi';
  const refresh = document.getElementById('catalog-refresh')?.checked || false;
  const coneRadiusInput = document.getElementById('catalog-cone-radius');
  const coneRadius = coneRadiusInput ? parseFloat(coneRadiusInput.value) : null;
  const statusDiv = document.getElementById('catalog-status');
  const resultsDiv = document.getElementById('catalog-results');
  const queryBtn = document.getElementById('catalog-query-btn');

  // Validation
  if (!gaiaId) {
    showStatus('error', '⚠️ Gaia ID mancante - impossibile interrogare i cataloghi');
    return;
  }

  if (coneRadius !== null && (isNaN(coneRadius) || coneRadius <= 0)) {
    showStatus('error', '⚠️ Raggio cono non valido (deve essere > 0)');
    return;
  }

  // Loading state
  queryBtn.disabled = true;
  queryBtn.style.opacity = '0.6';
  queryBtn.textContent = '⏳ Interrogazione in corso...';
  const radiusDisplay = coneRadius ? coneRadius.toFixed(1) : '5';
  showStatus('info', `🔍 Interrogazione con contesto: ${context}, raggio ${radiusDisplay}"...`);
  resultsDiv.innerHTML = '<p style="color: #999; text-align: center; padding: 2rem;">⏳ Caricamento...</p>';

  try {
    const requestBody = {
      gaia_id: gaiaId,
      context: context,
      refresh: refresh
    };

    // Include cone_radius only if provided (superuser)
    if (coneRadius !== null) {
      requestBody.cone_radius = coneRadius;
    }

    const response = await fetch('/agata/catalog/api/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody)
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();
    displayResults(data);
    showStatus('success', `✅ Query completata (Request ID: ${data.request_id.substring(0, 8)}...)`);

  } catch (error) {
    console.error('[Catalogs] Query error:', error);
    showStatus('error', `❌ Errore: ${error.message}`);
    resultsDiv.innerHTML = `
      <div style="padding: 2rem; text-align: center;">
        <p style="color: #dc2626; font-weight: 600; margin-bottom: 0.5rem;">❌ Errore durante la query</p>
        <p style="color: #666; font-size: 0.9rem;">${error.message}</p>
      </div>
    `;
  } finally {
    queryBtn.disabled = false;
    queryBtn.style.opacity = '1';
    queryBtn.textContent = '🔍 Cerca';
  }
};

/**
 * Show status message (info/success/error)
 */
function showStatus(type, message) {
  const statusDiv = document.getElementById('catalog-status');
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
 * Display query results in structured format
 */
function displayResults(data) {
  const resultsDiv = document.getElementById('catalog-results');
  if (!resultsDiv) return;

  // Collect all attributes from all catalogs
  const allAttributes = collectAllAttributes(data.results_by_context);
  const catalogsSummary = collectCatalogsSummary(data.results_by_context);

  // Target Info Card with export button and controls
  let html = `
    <div style="padding: 1rem; background: #f9fafb; border-radius: 6px; border: 1px solid #e5e7eb; margin-bottom: 1rem;">
      <!-- Row 1: Title + Export Button -->
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
        <h4 style="margin: 0; color: #374151;">🎯 Target Risolto</h4>
        <button
          onclick="exportCatalogData()"
          style="padding: 0.5rem 1rem; background: #10b981; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: 600; font-size: 0.85rem; transition: background 0.2s;"
          onmouseover="this.style.background='#059669'"
          onmouseout="this.style.background='#10b981'"
        >
          📋 Esporta Testo
        </button>
      </div>

      <!-- Row 2: Target coordinates -->
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.5rem; font-size: 0.9rem; margin-bottom: 1rem;">
        <div><strong>Gaia ID:</strong> <code style="background: white; padding: 2px 6px; border-radius: 3px;">${data.resolved_target.gaia_id}</code></div>
        <div><strong>Release:</strong> ${data.resolved_target.gaia_release_used.toUpperCase()}</div>
        <div><strong>RA:</strong> ${data.resolved_target.ra_deg.toFixed(6)}°</div>
        <div><strong>Dec:</strong> ${data.resolved_target.dec_deg.toFixed(6)}°</div>
      </div>

      <!-- Row 3: Filter and Sort controls -->
      <div style="display: flex; gap: 1rem; align-items: center; flex-wrap: wrap; padding-top: 1rem; border-top: 1px solid #e5e7eb;">
        <div style="flex: 1; min-width: 200px;">
          <input
            type="text"
            id="catalog-table-filter"
            placeholder="🔍 Filtra per attributo, catalogo, valore..."
            style="width: 100%; padding: 0.5rem; border: 1px solid #d1d5db; border-radius: 4px; font-size: 0.85rem;"
            oninput="filterCatalogTable()"
          />
        </div>
        <div>
          <label style="font-size: 0.85rem; color: #6b7280; margin-right: 0.5rem;">Ordina per:</label>
          <select
            id="catalog-table-sort"
            style="padding: 0.5rem; border: 1px solid #d1d5db; border-radius: 4px; font-size: 0.85rem;"
            onchange="sortCatalogTable()"
          >
            <option value="catalog">Catalogo</option>
            <option value="attribute">Attributo (A-Z)</option>
            <option value="context">Contesto</option>
          </select>
        </div>
      </div>
    </div>
  `;

  // Render unified table (without filter/sort controls)
  html += renderUnifiedTable(allAttributes, catalogsSummary, true);

  resultsDiv.innerHTML = html;

  // Store attributes globally for export
  window.catalogResultsData = {
    target: data.resolved_target,
    attributes: allAttributes
  };
}

/**
 * Collect all attributes from all catalogs into a unified array
 */
function collectAllAttributes(resultsByContext) {
  const attributes = [];

  for (const [contextName, catalogs] of Object.entries(resultsByContext)) {
    for (const catalog of catalogs) {
      if ((catalog.status === 'ok' || catalog.status === 'multi_match') && catalog.payload) {
        const excludeFields = ['_candidates', '_RAJ2000', '_DEJ2000', '_r', 'recno', '_distance_arcsec'];
        const catalogInfo = getCatalogReference(catalog.catalog_id);

        // Get configured attributes from CSV (via backend)
        const configuredAttrs = catalog.configured_attributes || [];

        // Filter function: include only configured attributes (if list exists) or all (if empty)
        const shouldInclude = (attr) => {
          if (excludeFields.includes(attr)) return false;
          if (configuredAttrs.length === 0) return true; // Empty = show all (fallback)
          return configuredAttrs.includes(attr);
        };

        // Check if payload has _candidates array (multi-match case)
        if (catalog.payload._candidates && Array.isArray(catalog.payload._candidates)) {
          // Multi-match: iterate through all candidates
          for (let i = 0; i < catalog.payload._candidates.length; i++) {
            const candidate = catalog.payload._candidates[i];
            const matchLabel = catalog.payload._candidates.length > 1 ? ` (match ${i + 1}/${catalog.payload._candidates.length})` : '';

            for (const [attr, value] of Object.entries(candidate)) {
              if (shouldInclude(attr) && value !== null && value !== undefined) {
                attributes.push({
                  catalogId: catalog.catalog_id,
                  catalogLabel: catalogInfo.label + matchLabel || catalog.catalog_id,
                  attribute: attr,
                  value: value,
                  reference: catalogInfo.reference || '',
                  context: contextName
                });
              }
            }
          }
        } else {
          // Single match: use payload directly
          for (const [attr, value] of Object.entries(catalog.payload)) {
            if (shouldInclude(attr) && value !== null && value !== undefined) {
              attributes.push({
                catalogId: catalog.catalog_id,
                catalogLabel: catalogInfo.label || catalog.catalog_id,
                attribute: attr,
                value: value,
                reference: catalogInfo.reference || '',
                context: contextName
              });
            }
          }
        }
      }
    }
  }

  return attributes;
}

/**
 * Collect catalogs summary (status, matches count)
 */
function collectCatalogsSummary(resultsByContext) {
  const summary = [];

  for (const [contextName, catalogs] of Object.entries(resultsByContext)) {
    for (const catalog of catalogs) {
      summary.push({
        catalogId: catalog.catalog_id,
        catalogLabel: getCatalogReference(catalog.catalog_id).label || catalog.catalog_id,
        context: contextName,
        status: catalog.status,
        matchesCount: catalog.matches_count,
        fromCache: catalog.from_cache,
        errorMessage: catalog.error_message
      });
    }
  }

  return summary;
}

/**
 * Render unified table with all attributes from all catalogs
 * @param {Array} attributes - All collected attributes
 * @param {Array} catalogsSummary - Summary with status info per catalog
 * @param {boolean} skipControls - If true, skips rendering filter/sort controls (moved to target box)
 */
function renderUnifiedTable(attributes, catalogsSummary, skipControls = false) {
  if (attributes.length === 0) {
    return '<p style="color: #999; font-style: italic; text-align: center; padding: 2rem;">Nessun attributo trovato nei cataloghi.</p>';
  }

  // Create lookup map: catalog_id -> status info
  const catalogStatusMap = {};
  catalogsSummary.forEach(cat => {
    catalogStatusMap[cat.catalogId] = {
      status: cat.status,
      matchesCount: cat.matchesCount,
      fromCache: cat.fromCache
    };
  });

  let html = `
    <div style="background: white; border: 1px solid #e5e7eb; border-radius: 6px; margin-bottom: 1rem;">
      <!-- Table -->
      <div style="overflow-x: auto;">
        <table id="catalog-unified-table" style="width: 100%; border-collapse: collapse; font-size: 0.85rem;">
          <thead>
            <tr style="background: #f3f4f6; border-bottom: 2px solid #d1d5db;">
              <th style="padding: 0.5rem; text-align: left; font-weight: 600; width: 16%;">Catalogo</th>
              <th style="padding: 0.5rem; text-align: left; font-weight: 600; width: 13%;">Contesto</th>
              <th style="padding: 0.5rem; text-align: center; font-weight: 600; width: 10%;">Match</th>
              <th style="padding: 0.5rem; text-align: left; font-weight: 600; width: 15%;">Attributo</th>
              <th style="padding: 0.5rem; text-align: left; font-weight: 600; width: 10%;">Valore</th>
              <th style="padding: 0.5rem; text-align: left; font-weight: 600; width: 28%;">Reference</th>
              <th style="padding: 0.5rem; text-align: center; font-weight: 600; width: 8%;">Azione</th>
            </tr>
          </thead>
          <tbody id="catalog-table-body">
  `;

  // Store original data for filtering/sorting
  window.catalogTableData = attributes;
  window.catalogStatusMap = catalogStatusMap;

  for (const item of attributes) {
    const statusInfo = catalogStatusMap[item.catalogId] || {};
    html += renderTableRow(item, statusInfo);
  }

  html += `
          </tbody>
        </table>
      </div>

      <!-- Footer with count -->
      <div style="padding: 0.75rem; border-top: 1px solid #e5e7eb; background: #f9fafb; font-size: 0.85rem; color: #6b7280;">
        <span id="catalog-table-count">${attributes.length}</span> attributi totali
      </div>
    </div>
  `;

  return html;
}

/**
 * Render single table row
 * @param {Object} item - Attribute item
 * @param {Object} statusInfo - Status info from catalog summary (status, matchesCount, fromCache)
 */
function renderTableRow(item, statusInfo = {}) {
  const displayValue = formatAttributeValue(item.value, item.attribute);
  const contextLabel = item.context.replace(/_/g, ' ');

  // Match type badge
  let matchBadge = '';
  if (statusInfo.status === 'ok') {
    matchBadge = '<span style="padding: 2px 8px; background: #d1fae5; color: #065f46; border-radius: 3px; font-size: 0.75rem; font-weight: 600;">✓ Singolo</span>';
  } else if (statusInfo.status === 'multi_match') {
    matchBadge = '<span style="padding: 2px 8px; background: #fef3c7; color: #92400e; border-radius: 3px; font-size: 0.75rem; font-weight: 600;">⚠️ Multi</span>';
  }

  // Cache badge (optional, shown inline with match)
  const cacheBadge = statusInfo.fromCache
    ? '<span style="padding: 2px 6px; background: #dbeafe; color: #1e40af; border-radius: 3px; font-size: 0.7rem; margin-left: 4px;">📦</span>'
    : '';

  return `
    <tr class="catalog-table-row" data-catalog="${item.catalogId}" data-attribute="${item.attribute}" data-context="${item.context}">
      <td style="padding: 0.5rem; border-bottom: 1px solid #e5e7eb; color: #374151; font-size: 0.85em;">
        ${item.catalogId}
      </td>
      <td style="padding: 0.5rem; border-bottom: 1px solid #e5e7eb; color: #6b7280; font-size: 0.85em; text-transform: capitalize;">
        ${contextLabel}
      </td>
      <td style="padding: 0.5rem; border-bottom: 1px solid #e5e7eb; text-align: center;">
        ${matchBadge}${cacheBadge}
      </td>
      <td style="padding: 0.5rem; border-bottom: 1px solid #e5e7eb;">
        <code style="background: #f9fafb; padding: 2px 6px; border-radius: 3px; font-size: 0.85em; color: #1f2937;">${item.attribute}</code>
      </td>
      <td style="padding: 0.5rem; border-bottom: 1px solid #e5e7eb; color: #1f2937;">
        ${displayValue}
      </td>
      <td style="padding: 0.5rem; border-bottom: 1px solid #e5e7eb; color: #6b7280; font-size: 0.8em;">
        ${item.reference || item.catalogLabel}
      </td>
      <td style="padding: 0.5rem; border-bottom: 1px solid #e5e7eb; text-align: center;">
        <button
          onclick="importAttribute('${item.catalogId}', '${item.attribute}', ${JSON.stringify(item.value).replace(/"/g, '&quot;')})"
          style="padding: 0.25rem 0.5rem; background: #3b82f6; color: white; border: none; border-radius: 3px; cursor: pointer; font-size: 0.75rem;"
          title="Importa nel progetto"
        >
          📥
        </button>
      </td>
    </tr>
  `;
}

/**
 * Import attribute value from catalog to support analysis form
 * Shows a popup allowing user to choose target field
 */
window.importAttribute = function(catalogId, attributeName, value) {
  // Check if attribute is magnitude-related
  const magAttributes = ['mag', 'Vmag', 'V_mag', 'Magnitude', 'MAG', 'V', 'Gmag', 'G_mag'];
  const isMagnitude = magAttributes.includes(attributeName);

  // List of available fields in support form
  const availableFields = [
    { id: 'spectral_class', label: 'Classe Spettrale', type: 'text', example: 'G2V, M3III' },
    { id: 'teff', label: 'Teff (K)', type: 'text', example: '5778' },
    { id: 'distance', label: 'Distanza (pc)', type: 'text', example: '10.5' },
    { id: 'luminosity', label: isMagnitude ? 'Luminosità (mag)' : 'Luminosità (L☉)', type: 'text', example: isMagnitude ? '10.5' : '1.0' },
    { id: 'radius', label: 'Raggio (R☉)', type: 'text', example: '1.0' },
    { id: 'mass', label: 'Massa (M☉)', type: 'text', example: '1.0' },
    { id: 'color_bv', label: 'Colore B-V', type: 'text', example: '0.656' },
    { id: 'color_bprp', label: 'Colore BP-RP', type: 'text', example: '1.234' },
    { id: 'passband', label: 'Passband', type: 'text', example: 'V, G, R' },
    { id: 'catalog_identifiers', label: 'Identificatori Altri Cataloghi', type: 'textarea', example: 'VSX J123456.7+123456' },
  ];

  // Suggest best field based on attribute name
  const suggestedFieldId = suggestFieldForAttribute(attributeName);

  // Show popup dialog (pass catalogId separately)
  showFieldSelectorPopup(attributeName, value, catalogId, availableFields, suggestedFieldId);
};

/**
 * Suggest best field for an attribute
 */
function suggestFieldForAttribute(attributeName) {
  const suggestions = {
    'Sp': 'spectral_class', 'SpType': 'spectral_class', 'Spectral_Type': 'spectral_class', 'SPTYPE': 'spectral_class',
    'Teff': 'teff', 'Teff_K': 'teff', 'TEFF': 'teff', 'Temperature': 'teff',
    'Plx': 'distance', 'parallax': 'distance', 'Distance_pc': 'distance', 'distance_pc': 'distance',
    'Lbol': 'luminosity', 'Luminosity': 'luminosity', 'L_L0': 'luminosity', 'logL': 'luminosity',
    'mag': 'luminosity', 'Vmag': 'luminosity', 'V_mag': 'luminosity', 'Magnitude': 'luminosity', 'MAG': 'luminosity', 'V': 'luminosity', 'Gmag': 'luminosity', 'G_mag': 'luminosity',
    'R_Rsun': 'radius', 'Radius': 'radius', 'Rad_Rsun': 'radius', 'logR': 'radius',
    'M': 'mass', 'Mass': 'mass', 'M_Msun': 'mass', 'Msun': 'mass', 'logM': 'mass',
    'B_V': 'color_bv', 'BV': 'color_bv', 'B-V': 'color_bv', 'bmag-vmag': 'color_bv',
    'BP_RP': 'color_bprp', 'BP-RP': 'color_bprp', 'Bp_Rp': 'color_bprp', 'bpmag-rpmag': 'color_bprp',
    'identifier': 'catalog_identifiers', 'Identifier': 'catalog_identifiers', 'DESIGNATION': 'catalog_identifiers',
    'Name': 'catalog_identifiers', 'VSX': 'catalog_identifiers', 'VSX_Name': 'catalog_identifiers',
  };
  return suggestions[attributeName] || null;
}

/**
 * Show field selector popup dialog
 */
function showFieldSelectorPopup(attributeName, value, catalogId, availableFields, suggestedFieldId) {
  // Create modal backdrop
  const backdrop = document.createElement('div');
  backdrop.id = 'import-modal-backdrop';
  backdrop.style.cssText = `
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.5);
    z-index: 9998;
    display: flex;
    align-items: center;
    justify-content: center;
  `;

  // Create modal dialog
  const modal = document.createElement('div');
  modal.id = 'import-modal';
  modal.style.cssText = `
    background: white;
    border-radius: 8px;
    box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
    max-width: 600px;
    width: 90%;
    max-height: 80vh;
    overflow-y: auto;
    z-index: 9999;
    animation: modalSlideIn 0.3s ease-out;
  `;

  // Add animation keyframes if not present
  if (!document.getElementById('import-modal-styles')) {
    const style = document.createElement('style');
    style.id = 'import-modal-styles';
    style.textContent = `
      @keyframes modalSlideIn {
        from {
          transform: scale(0.95);
          opacity: 0;
        }
        to {
          transform: scale(1);
          opacity: 1;
        }
      }
    `;
    document.head.appendChild(style);
  }

  // Build modal content
  let html = `
    <div style="padding: 2rem;">
      <h2 style="margin: 0 0 0.5rem 0; font-size: 1.5rem; color: #1f2937;">
        📥 Importa Valore Catalogo
      </h2>
      <p style="margin: 0 0 1.5rem 0; color: #6b7280; font-size: 0.95rem;">
        Scegli dove importare il valore dal catalogo <strong>${catalogId}</strong>
      </p>

      <!-- Value preview -->
      <div style="padding: 1rem; background: #f3f4f6; border-radius: 6px; margin-bottom: 1.5rem; border-left: 4px solid #3b82f6;">
        <div style="font-size: 0.85rem; color: #6b7280; margin-bottom: 0.25rem;"><strong>Attributo:</strong> ${attributeName}</div>
        <div style="font-size: 0.85rem; color: #6b7280; margin-bottom: 0.5rem;"><strong>Valore originale:</strong> <code style="background: white; padding: 2px 6px; border-radius: 3px; font-family: monospace;">${value}</code></div>
        <div style="font-size: 0.85rem; color: #1f2937; background: white; padding: 0.5rem; border-radius: 4px; font-family: monospace;">
          <strong>Valore da importare:</strong><br>
          "${String(value).trim()} (${catalogId})"
        </div>
      </div>

      <!-- Field selector -->
      <div style="margin-bottom: 1.5rem;">
        <label style="display: block; font-weight: 600; color: #374151; margin-bottom: 0.75rem;">
          Seleziona il campo di destinazione:
        </label>
        <div style="display: grid; gap: 0.5rem;">
  `;

  // Generate radio buttons for each field
  for (const field of availableFields) {
    const isChecked = field.id === suggestedFieldId ? 'checked' : '';
    const isSuggested = field.id === suggestedFieldId;
    const badge = isSuggested ? ' <span style="margin-left: 0.5rem; padding: 2px 8px; background: #dbeafe; color: #1e40af; border-radius: 3px; font-size: 0.75rem; font-weight: 600;">✓ Suggerito</span>' : '';

    // Get current value of the field for preview
    const currentField = document.getElementById(field.id);
    const currentValue = currentField ? (currentField.value || '-') : '-';
    const currentValueStr = currentValue === '-' ? '<span style="color: #9ca3af; font-style: italic;">vuoto</span>' : `<code style="background: white; padding: 2px 4px; border-radius: 2px; font-family: monospace;">${currentValue}</code>`;

    html += `
      <label style="display: flex; align-items: center; padding: 0.75rem; border: 2px solid ${isSuggested ? '#3b82f6' : '#e5e7eb'}; border-radius: 6px; cursor: pointer; background: ${isSuggested ? '#eff6ff' : 'white'}; transition: all 0.2s;">
        <input type="radio" name="target-field" value="${field.id}" ${isChecked} style="margin-right: 0.75rem; cursor: pointer; width: 18px; height: 18px;">
        <div style="flex: 1;">
          <div style="font-weight: 600; color: #1f2937;">${field.label}</div>
          <div style="font-size: 0.8rem; color: #6b7280;">Tipo: <strong>${field.type}</strong> | Valore attuale: ${currentValueStr}</div>
        </div>${badge}
      </label>
    `;
  }

  html += `
        </div>
      </div>

      <!-- Action buttons -->
      <div style="display: flex; gap: 1rem; justify-content: flex-end;">
        <button id="import-cancel-btn" style="padding: 0.75rem 1.5rem; background: #e5e7eb; color: #374151; border: none; border-radius: 6px; font-weight: 600; cursor: pointer; font-size: 0.95rem; transition: all 0.2s;">
          ❌ Annulla
        </button>
        <button id="import-confirm-btn" style="padding: 0.75rem 1.5rem; background: #10b981; color: white; border: none; border-radius: 6px; font-weight: 600; cursor: pointer; font-size: 0.95rem; transition: all 0.2s;">
          ✅ Importa
        </button>
      </div>
    </div>
  `;

  modal.innerHTML = html;
  backdrop.appendChild(modal);
  document.body.appendChild(backdrop);

  // Handle close button
  document.getElementById('import-cancel-btn').onclick = () => {
    backdrop.remove();
  };

  // Handle confirm button
  document.getElementById('import-confirm-btn').onclick = () => {
    const selectedField = document.querySelector('input[name="target-field"]:checked');
    if (!selectedField) {
      alert('⚠️ Seleziona un campo di destinazione');
      return;
    }

    const fieldId = selectedField.value;
    const field = document.getElementById(fieldId);

    if (!field) {
      alert(`❌ Campo non trovato: ${fieldId}`);
      backdrop.remove();
      return;
    }

    // Import the value (pass catalogId for proper formatting)
    performImport(field, fieldId, value, catalogId);
    backdrop.remove();
  };

  // Close on backdrop click
  backdrop.onclick = (e) => {
    if (e.target === backdrop) {
      backdrop.remove();
    }
  };
}

/**
 * Perform the actual import
 */
function performImport(field, fieldId, value, catalogId) {
  // Format the value with catalog reference: "value (catalogId)"
  const formattedValue = String(value).trim() + ` (${catalogId})`;

  // Handle different field types
  if (field.tagName === 'TEXTAREA' || fieldId === 'catalog_identifiers') {
    // Textarea: append new value (one per line)
    const currentText = field.value.trim();
    if (currentText) {
      field.value = currentText + '\n' + formattedValue;
    } else {
      field.value = formattedValue;
    }
    showNotification(`✅ Identificatore aggiunto: ${formattedValue}`, 'success');
  } else {
    // Input field: replace with the full formatted value (including catalog reference)
    const oldValue = field.value;
    field.value = formattedValue;

    if (oldValue) {
      showNotification(`✅ Importato: "${formattedValue}" (precedente: "${oldValue}")`, 'info');
    } else {
      showNotification(`✅ Importato: "${formattedValue}"`, 'success');
    }
  }
}

/**
 * Show notification message
 */
function showNotification(message, type = 'info') {
  const notification = document.createElement('div');
  notification.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    padding: 1rem 1.5rem;
    background: ${type === 'success' ? '#d1fae5' : type === 'info' ? '#dbeafe' : '#fee2e2'};
    color: ${type === 'success' ? '#065f46' : type === 'info' ? '#1e40af' : '#991b1b'};
    border: 1px solid ${type === 'success' ? '#6ee7b7' : type === 'info' ? '#93c5fd' : '#fca5a5'};
    border-radius: 6px;
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    z-index: 10000;
    font-weight: 500;
    animation: slideIn 0.3s ease-out;
  `;

  // Add animation keyframes if not already present
  if (!document.getElementById('notification-styles')) {
    const style = document.createElement('style');
    style.id = 'notification-styles';
    style.textContent = `
      @keyframes slideIn {
        from {
          transform: translateX(400px);
          opacity: 0;
        }
        to {
          transform: translateX(0);
          opacity: 1;
        }
      }
      @keyframes slideOut {
        from {
          transform: translateX(0);
          opacity: 1;
        }
        to {
          transform: translateX(400px);
          opacity: 0;
        }
      }
    `;
    document.head.appendChild(style);
  }

  document.body.appendChild(notification);
  notification.textContent = message;

  // Auto-remove after 3 seconds
  setTimeout(() => {
    notification.style.animation = 'slideOut 0.3s ease-out';
    setTimeout(() => {
      notification.remove();
    }, 300);
  }, 3000);
}

/**
 * Filter catalog table by search term
 */
window.filterCatalogTable = function() {
  const filterInput = document.getElementById('catalog-table-filter');
  const filter = filterInput.value.toLowerCase();
  const rows = document.querySelectorAll('.catalog-table-row');
  let visibleCount = 0;

  rows.forEach(row => {
    const catalog = row.getAttribute('data-catalog').toLowerCase();
    const attribute = row.getAttribute('data-attribute').toLowerCase();
    const text = row.textContent.toLowerCase();

    if (catalog.includes(filter) || attribute.includes(filter) || text.includes(filter)) {
      row.style.display = '';
      visibleCount++;
    } else {
      row.style.display = 'none';
    }
  });

  document.getElementById('catalog-table-count').textContent = visibleCount;
};

/**
 * Sort catalog table
 */
window.sortCatalogTable = function() {
  const sortSelect = document.getElementById('catalog-table-sort');
  const sortBy = sortSelect.value;
  const tbody = document.getElementById('catalog-table-body');
  const rows = Array.from(tbody.querySelectorAll('.catalog-table-row'));

  rows.sort((a, b) => {
    let aVal, bVal;

    switch (sortBy) {
      case 'catalog':
        aVal = a.getAttribute('data-catalog');
        bVal = b.getAttribute('data-catalog');
        break;
      case 'attribute':
        aVal = a.getAttribute('data-attribute');
        bVal = b.getAttribute('data-attribute');
        break;
      case 'context':
        aVal = a.getAttribute('data-context');
        bVal = b.getAttribute('data-context');
        break;
      default:
        return 0;
    }

    return aVal.localeCompare(bVal);
  });

  // Re-append sorted rows
  rows.forEach(row => tbody.appendChild(row));
};

/**
 * Render catalogs summary section
 */
function renderCatalogsSummary(summary) {
  // Filter to show only catalogs with matches (OK or multi_match status)
  const successfulCatalogs = summary.filter(item => item.status === 'ok' || item.status === 'multi_match');

  if (successfulCatalogs.length === 0) {
    return `
      <div style="background: white; border: 1px solid #e5e7eb; border-radius: 6px; padding: 1rem;">
        <h4 style="margin: 0 0 0.5rem 0; color: #374151;">📚 Riepilogo Cataloghi</h4>
        <p style="color: #6b7280; font-size: 0.85rem; margin: 0;">Nessun catalogo ha restituito risultati.</p>
      </div>
    `;
  }

  let html = `
    <div style="background: white; border: 1px solid #e5e7eb; border-radius: 6px; padding: 1rem;">
      <h4 style="margin: 0 0 1rem 0; color: #374151;">📚 Riepilogo Cataloghi con Risultati</h4>
      <div style="display: grid; gap: 0.5rem;">
  `;

  for (const item of successfulCatalogs) {
    const statusConfig = {
      ok: { icon: '✅', color: '#10b981', label: 'OK' },
      no_match: { icon: '❌', color: '#6b7280', label: 'No Match' },
      multi_match: { icon: '⚠️', color: '#f59e0b', label: 'Multi Match' },
      error: { icon: '🚫', color: '#ef4444', label: 'Error' },
      timeout: { icon: '⏱️', color: '#f97316', label: 'Timeout' }
    };

    const config = statusConfig[item.status] || { icon: '❓', color: '#6b7280', label: item.status };

    html += `
      <div style="padding: 0.5rem; background: #f9fafb; border-left: 3px solid ${config.color}; border-radius: 3px; display: flex; justify-content: space-between; align-items: center; font-size: 0.85rem;">
        <div>
          <strong style="color: #374151;">${item.catalogLabel}</strong>
          <span style="color: #9ca3af; margin-left: 0.5rem; font-size: 0.8em;">(${item.catalogId})</span>
          ${item.errorMessage ? `<div style="color: #dc2626; font-size: 0.8em; margin-top: 0.25rem;">⚠️ ${item.errorMessage}</div>` : ''}
        </div>
        <div style="display: flex; gap: 0.5rem; align-items: center;">
          ${item.fromCache ? '<span style="padding: 2px 6px; background: #dbeafe; color: #1e40af; border-radius: 3px; font-size: 0.75rem;">📦 Cache</span>' : ''}
          <span style="color: ${config.color}; font-weight: 600;">${config.icon} ${config.label}</span>
          ${item.status === 'ok' ? `<span style="color: #6b7280;">(${item.matchesCount} match)</span>` : ''}
        </div>
      </div>
    `;
  }

  html += `
      </div>
    </div>
  `;

  return html;
}


/**
 * Format attribute value for display
 */
function formatAttributeValue(value, attribute) {
  if (value === null || value === undefined) {
    return '<span style="color: #9ca3af; font-style: italic;">null</span>';
  }

  if (typeof value === 'number') {
    // Format numbers with max 6 decimals
    let formatted = value.toFixed(6).replace(/\.?0+$/, '');

    // Add units for distance
    if (attribute === '_distance_arcsec') {
      formatted += ' "';  // arcsec symbol
    }

    return formatted;
  }

  if (typeof value === 'string') {
    return value;
  }

  if (typeof value === 'boolean') {
    return value ? '✓' : '✗';
  }

  // Fallback for arrays/objects
  return JSON.stringify(value);
}

/**
 * Get catalog reference information
 */
function getCatalogReference(catalogId) {
  // Static catalog info (could be loaded from API in future)
  const catalogInfo = {
    'I/355/gaiadr3': { label: 'Gaia DR3', reference: 'Gaia Collaboration, 2023' },
    'I/345/gaia2': { label: 'Gaia DR2', reference: 'Gaia Collaboration, 2018' },
    'IV/38/tic': { label: 'TESS Input Catalog', reference: 'Stassun et al., 2019' },
    'IV/39/tic82': { label: 'TESS Input Catalog v8.2', reference: 'Stassun et al., 2019' },
    'II/246/out': { label: '2MASS', reference: 'Skrutskie et al., 2006' },
    'I/239/tyc_main': { label: 'Tycho-2', reference: 'Høg et al., 2000' },
    'I/252/out': { label: 'UCAC2', reference: 'Zacharias et al., 2004' },
    'I/284/out': { label: 'USNO-B1.0', reference: 'Monet et al., 2003' },
    'I/322A/out': { label: 'UCAC4', reference: 'Zacharias et al., 2013' },
    'I/305/out': { label: 'DENIS', reference: 'DENIS Consortium, 2005' },
    'I/354/starhorse2021': { label: 'StarHorse', reference: 'Anders et al., 2022' },
    'V/15/catalog': { label: 'VSX', reference: 'Watson et al., 2006' }
  };

  return catalogInfo[catalogId] || { label: catalogId, reference: '' };
}


/**
 * Export catalog data as text (popup)
 */
window.exportCatalogData = function() {
  if (!window.catalogResultsData) {
    alert('Nessun dato disponibile per l\'esportazione');
    return;
  }

  const { target, attributes } = window.catalogResultsData;

  // Build text output
  let text = '═══════════════════════════════════════════\n';
  text += '  CATALOGHI ESTERNI - ESPORTAZIONE DATI\n';
  text += '═══════════════════════════════════════════\n\n';

  // Target info
  text += '🎯 TARGET RISOLTO\n';
  text += '─────────────────────────────────────────\n';
  text += `Gaia ID:  ${target.gaia_id}\n`;
  text += `Release:  ${target.gaia_release_used.toUpperCase()}\n`;
  text += `RA:       ${target.ra_deg.toFixed(6)}°\n`;
  text += `Dec:      ${target.dec_deg.toFixed(6)}°\n\n`;

  // Group by context
  const byContext = {};
  attributes.forEach(attr => {
    if (!byContext[attr.context]) {
      byContext[attr.context] = [];
    }
    byContext[attr.context].push(attr);
  });

  // Export each context
  text += '📚 ATTRIBUTI PER CONTESTO\n';
  text += '─────────────────────────────────────────\n\n';

  for (const [contextName, contextAttrs] of Object.entries(byContext)) {
    text += `Contesto: ${contextName.replace(/_/g, ' ')}\n\n`;

    // Find longest attribute name for alignment
    const maxAttrLength = Math.max(...contextAttrs.map(a => a.attribute.length), 15);

    contextAttrs.forEach(attr => {
      const value = attr.value === null || attr.value === undefined
        ? 'null'
        : (typeof attr.value === 'number' ? attr.value.toFixed(6).replace(/\.?0+$/, '') : attr.value);
      text += `${attr.attribute.padEnd(maxAttrLength)} = ${value}\n`;
    });

    text += '\n';
  }

  text += '─────────────────────────────────────────\n';
  text += `Totale attributi: ${attributes.length}\n`;
  text += `Data esportazione: ${new Date().toLocaleString('it-IT')}\n`;

  // Show in popup with copy functionality
  const popup = window.open('', 'CatalogExport', 'width=700,height=600,scrollbars=yes');
  if (!popup) {
    alert('Popup bloccato dal browser. Abilita i popup per questa pagina.');
    return;
  }

  popup.document.write(`
    <!DOCTYPE html>
    <html>
    <head>
      <title>Esportazione Cataloghi</title>
      <style>
        body { font-family: 'Courier New', monospace; padding: 20px; background: #1e293b; color: #e2e8f0; }
        pre { white-space: pre-wrap; word-wrap: break-word; background: #0f172a; padding: 20px; border-radius: 8px; border: 1px solid #334155; line-height: 1.6; }
        button { padding: 10px 20px; background: #10b981; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 14px; margin-bottom: 15px; }
        button:hover { background: #059669; }
        .success { background: #065f46; color: #d1fae5; padding: 10px; border-radius: 6px; margin-bottom: 15px; display: none; }
      </style>
    </head>
    <body>
      <button onclick="copyToClipboard()">📋 Copia negli Appunti</button>
      <div class="success" id="success">✅ Copiato negli appunti!</div>
      <pre id="content">${text.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre>
      <script>
        function copyToClipboard() {
          const content = document.getElementById('content').textContent;
          navigator.clipboard.writeText(content).then(() => {
            const success = document.getElementById('success');
            success.style.display = 'block';
            setTimeout(() => { success.style.display = 'none'; }, 3000);
          }).catch(err => {
            alert('Errore durante la copia: ' + err);
          });
        }
      </script>
    </body>
    </html>
  `);
  popup.document.close();
};


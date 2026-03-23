// Auto-save Science Data Form
let scienceDataSaveTimeout = null;
const AUTOSAVE_DELAY = 2000; // 2 seconds

function initScienceDataAutosave() {
    const form = document.getElementById('scienceDataForm');
    if (!form) return;

    const inputs = form.querySelectorAll('input, select, textarea');

    inputs.forEach(input => {
        input.addEventListener('input', () => {
            clearTimeout(scienceDataSaveTimeout);
            updateScienceDataStatus('editing');

            scienceDataSaveTimeout = setTimeout(() => {
                saveScienceData();
            }, AUTOSAVE_DELAY);
        });
    });
}

async function saveScienceData() {
    const form = document.getElementById('scienceDataForm');
    const formData = new FormData(form);
    const data = {};

    formData.forEach((value, key) => {
        if (value) {
            data[key] = value;
        }
    });

    // Skip if no data
    if (Object.keys(data).length === 0) {
        return;
    }

    updateScienceDataStatus('saving');

    try {
        await apiCall(`/api/projects/${PROJECT_ID}/science-data`, 'PUT', data);
        updateScienceDataStatus('saved');

        setTimeout(() => {
            updateScienceDataStatus('');
        }, 3000);
    } catch (error) {
        console.error('Error saving science data:', error);
        updateScienceDataStatus('error');
    }
}

function updateScienceDataStatus(status) {
    const indicator = document.getElementById('scienceDataStatus');
    if (!indicator) return;

    switch (status) {
        case 'editing':
            indicator.className = 'autosave-indicator';
            indicator.innerHTML = '<i class="fas fa-pencil-alt"></i> Modifiche...';
            break;
        case 'saving':
            indicator.className = 'autosave-indicator saving';
            indicator.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Salvataggio...';
            break;
        case 'saved':
            indicator.className = 'autosave-indicator saved';
            indicator.innerHTML = '<i class="fas fa-check"></i> Salvato';
            break;
        case 'error':
            indicator.className = 'autosave-indicator text-danger';
            indicator.innerHTML = '<i class="fas fa-exclamation-circle"></i> Errore';
            break;
        default:
            indicator.className = 'autosave-indicator';
            indicator.innerHTML = '';
    }
}

// Update section after refresh
function updateScienceDataSection(scienceData) {
    if (!scienceData) return;

    const fields = ['classification', 'period_days', 'period_uncertainty',
                   'confidence_level', 'dataset_drive_url', 'scientific_notes'];

    fields.forEach(field => {
        const input = document.getElementById(field);
        if (input && scienceData[field] !== undefined) {
            input.value = scienceData[field] || '';
        }
    });
}

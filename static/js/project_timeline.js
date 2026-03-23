// Timeline already implemented in component HTML
// This file is a placeholder for additional timeline functionality

function updateInfoSection(data) {
    // Update info section dynamically if needed
    // Most info is static, so minimal updates needed
}

function updateOutputsSection(outputs) {
    const container = document.getElementById('outputsList');
    if (!container) return;

    if (!outputs || outputs.length === 0) {
        container.innerHTML = '<p class="text-muted mb-0"><i class="fas fa-info-circle"></i> Nessun output caricato</p>';
        return;
    }

    let html = '<div class="table-responsive"><table class="table table-hover"><thead><tr>';
    html += '<th>Tipo</th><th>File</th><th>Descrizione</th><th>Versione</th><th>Data</th><th>Azioni</th>';
    html += '</tr></thead><tbody>';

    outputs.forEach(output => {
        html += `<tr>
            <td><span class="badge badge-secondary">${output.type}</span></td>
            <td><i class="fas fa-file"></i> ${output.file_name}</td>
            <td><small class="text-muted">${output.description || '-'}</small></td>
            <td>v${output.version} ${output.is_current ? '<span class="badge badge-success badge-sm">current</span>' : ''}</td>
            <td><small>${new Date(output.uploaded_at).toLocaleDateString('it-IT')}</small></td>
            <td><a href="${output.file_url}" target="_blank" class="btn btn-sm btn-outline-primary">
                <i class="fas fa-external-link-alt"></i>
            </a></td>
        </tr>`;
    });

    html += '</tbody></table></div>';
    container.innerHTML = html;
}

function updateSlackSection(slack) {
    // Slack section updates handled by backend re-render
    // This is a placeholder for dynamic updates
}

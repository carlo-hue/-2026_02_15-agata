// Project Modals JavaScript
// Most modal functionality is already in project_modals.html inline script
// This file serves as a placeholder for additional modal functionality

// Helper to reset modal forms
function resetModalForm(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;

    const form = modal.querySelector('form');
    if (form) {
        form.reset();
    }
}

// Reset forms when modals are hidden
['assignModal', 'cancelModal', 'closeModal', 'uploadOutputModal'].forEach(modalId => {
    const modal = document.getElementById(modalId);
    if (modal) {
        $(modal).on('hidden.bs.modal', function() {
            resetModalForm(modalId);
        });
    }
});

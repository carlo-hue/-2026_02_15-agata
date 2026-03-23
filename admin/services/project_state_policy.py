# agata/admin/services/project_state_policy.py
"""
Project State Policy - Policy centralizzata per validazione transizioni di stato

Questo modulo è l'unica fonte di verità per:
- Quali azioni sono consentite per ogni stato
- Chi può eseguire ogni azione
- Validazione business logic delle transizioni

PRINCIPIO: Un bottone visibile = azione consentita ORA
(no bottoni disabled in UI, solo bottoni per azioni valide)
"""
from typing import List, Dict, Set, Optional
from agata.auth_models import Project, User


# ============================================================================
# MAPPA STATO → AZIONI CONSENTITE (Unica fonte di verità)
# ============================================================================

ALLOWED_ACTIONS: Dict[str, List[str]] = {
    "incoming": [
        "cancel"  # Solo annullamento possibile per progetti in arrivo
    ],
    "available": [
        "assign"  # Assegna a un analista
    ],
    "assigned": [
        "reassign",        # Riassegna a altro analista
        "send_to_review",  # Invia in revisione
        "cancel"           # Annulla progetto
    ],
    "in_review": [
        "revert_to_assigned",  # Riporta in assigned per correzioni
        "close"                # Chiudi progetto (accettato/completato)
    ],
    "submitted_aavso": [
        # Nessuna azione permessa - in attesa risposta AAVSO
    ],
    "accepted_aavso": [
        "close"  # Chiudi progetto dopo accettazione AAVSO
    ],
    "rejected_aavso": [
        "reassign",  # Riassegna per correzioni
        "cancel"     # Annulla se non recuperabile
    ],
    "cancelled": [
        # Stato finale - nessuna azione permessa
    ]
}


# ============================================================================
# PERMESSI PER RUOLO
# ============================================================================

# Azioni che ogni ruolo può eseguire (indipendentemente dallo stato)
ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    "superuser": {
        # Superuser può fare tutto
        "assign", "reassign", "send_to_review", "revert_to_assigned",
        "cancel", "close", "promote_to_channel"
    },
    "admin": {
        # Admin associazione può fare quasi tutto nella sua associazione
        "assign", "reassign", "send_to_review", "revert_to_assigned",
        "cancel", "close", "promote_to_channel"
    },
    "reviewer": {
        # Reviewer può gestire review
        "revert_to_assigned", "close", "send_to_review"
    },
    "analyst": {
        # Analyst può solo inviare in review i propri progetti
        "send_to_review"
    },
    "viewer": {
        # Viewer solo lettura - nessuna azione
    }
}


# ============================================================================
# FUNZIONI DI VALIDAZIONE
# ============================================================================

def get_allowed_actions(project: Project, user: User) -> List[str]:
    """
    Ritorna lista azioni consentite per il progetto dato e l'utente corrente

    Combina:
    1. Azioni consentite per lo stato del progetto
    2. Permessi del ruolo utente
    3. Regole business specifiche (es: analyst può modificare solo progetti assegnati a lui)

    Args:
        project: Progetto da verificare
        user: Utente che vuole eseguire l'azione

    Returns:
        Lista di azioni consentite (stringhe)

    Examples:
        >>> project = Project(state='assigned', assigned_to=user.id)
        >>> get_allowed_actions(project, user)
        ['reassign', 'send_to_review', 'cancel']
    """
    # 1. Azioni consentite per lo stato
    state_actions = set(ALLOWED_ACTIONS.get(project.state, []))

    # 2. Permessi del ruolo
    role_actions = ROLE_PERMISSIONS.get(user.role, set())

    # 3. Intersezione: azioni sia permesse per stato che per ruolo
    allowed = state_actions & role_actions

    # 4. Regole business specifiche
    if user.role == 'analyst':
        # Analyst può modificare solo progetti assegnati a lui
        if project.assigned_to != user.id:
            allowed.clear()  # Nessuna azione permessa

    if user.role in ['admin', 'reviewer']:
        # Admin e Reviewer possono agire solo su progetti della loro associazione
        if project.association_id != user.association_id and user.role != 'superuser':
            allowed.clear()

    return sorted(list(allowed))


def validate_action(project: Project, action: str, user: User) -> tuple[bool, Optional[str]]:
    """
    Valida se un'azione è consentita per il progetto e l'utente

    Args:
        project: Progetto su cui si vuole agire
        action: Azione da eseguire (es: 'assign', 'cancel')
        user: Utente che vuole eseguire l'azione

    Returns:
        Tuple (is_valid, error_message)
        - is_valid: True se azione consentita, False altrimenti
        - error_message: Messaggio di errore se is_valid=False, None altrimenti

    Examples:
        >>> is_valid, error = validate_action(project, 'assign', user)
        >>> if not is_valid:
        >>>     raise PermissionError(error)
    """
    # 1. Verifica azione consentita per lo stato
    if action not in ALLOWED_ACTIONS.get(project.state, []):
        return False, (f"Azione '{action}' non consentita per progetto in stato '{project.state}'. "
                      f"Azioni valide: {', '.join(ALLOWED_ACTIONS.get(project.state, []))}")

    # 2. Verifica permessi ruolo
    if action not in ROLE_PERMISSIONS.get(user.role, set()):
        return False, f"Ruolo '{user.role}' non autorizzato per azione '{action}'"

    # 3. Regole business specifiche
    if user.role == 'analyst':
        # Analyst può modificare solo progetti assegnati a lui
        if project.assigned_to != user.id:
            return False, "Analyst può modificare solo progetti assegnati a sé stesso"

    if user.role in ['admin', 'reviewer'] and user.role != 'superuser':
        # Admin/Reviewer possono agire solo nella loro associazione
        if project.association_id != user.association_id:
            return False, "Non hai permessi per modificare progetti di altre associazioni"

    # 4. Validazioni specifiche per azione
    if action == 'assign' and project.state != 'available':
        return False, f"Può assegnare solo progetti in stato 'available', stato attuale: '{project.state}'"

    if action == 'send_to_review' and not project.assigned_to:
        return False, "Progetto non assegnato - impossibile inviare in review"

    # Tutto OK
    return True, None


def can_promote_to_channel(project: Project, user: User) -> tuple[bool, Optional[str]]:
    """
    Valida se è possibile promuovere il thread Slack a canale dedicato

    Condizioni:
    - Stato progetto: assigned o in_review
    - Contesto attuale: thread (non già canale)
    - Ruolo utente: admin o superuser

    Args:
        project: Progetto da verificare
        user: Utente richiedente

    Returns:
        Tuple (can_promote, error_message)
    """
    # 1. Verifica permessi utente
    if user.role not in ['admin', 'superuser']:
        return False, "Solo admin e superuser possono promuovere thread a canale"

    # 2. Verifica associazione (admin possono solo nella loro associazione)
    if user.role == 'admin' and project.association_id != user.association_id:
        return False, "Admin può promuovere solo progetti della propria associazione"

    # 3. Verifica stato progetto
    if project.state not in ['assigned', 'in_review']:
        return False, f"Può promuovere solo progetti in stato assigned/in_review, stato attuale: '{project.state}'"

    # 4. Verifica contesto Slack (richiederebbe query al DB)
    # Questa verifica va fatta nel command che ha accesso al ProjectSlackThread
    # from agata.auth_models import ProjectSlackThread
    # slack_thread = db.query(ProjectSlackThread).filter_by(project_id=project.id, is_active=True).first()
    # if slack_thread and slack_thread.slack_type == 'channel':
    #     return False, "Progetto già associato a canale dedicato"

    return True, None


def get_next_state(current_state: str, action: str) -> Optional[str]:
    """
    Ritorna il prossimo stato dopo un'azione valida

    Args:
        current_state: Stato attuale progetto
        action: Azione da eseguire

    Returns:
        Nuovo stato, o None se transizione non valida

    Examples:
        >>> get_next_state('available', 'assign')
        'assigned'
        >>> get_next_state('assigned', 'send_to_review')
        'in_review'
    """
    # Mappa azioni → nuovo stato
    transitions = {
        ('available', 'assign'): 'assigned',
        ('assigned', 'reassign'): 'assigned',  # Rimane assigned con nuovo utente
        ('assigned', 'send_to_review'): 'in_review',
        ('assigned', 'cancel'): 'cancelled',
        ('in_review', 'revert_to_assigned'): 'assigned',
        ('in_review', 'close'): 'accepted_aavso',  # Assumiamo chiusura = successo
        ('accepted_aavso', 'close'): 'accepted_aavso',  # Già chiuso
        ('rejected_aavso', 'reassign'): 'assigned',
        ('rejected_aavso', 'cancel'): 'cancelled',
        ('incoming', 'cancel'): 'cancelled',
    }

    return transitions.get((current_state, action))


def get_state_badge_color(state: str) -> str:
    """
    Ritorna il colore del badge per lo stato (per UI)

    Args:
        state: Stato progetto

    Returns:
        Nome classe CSS o colore hex

    Examples:
        >>> get_state_badge_color('assigned')
        'primary'
        >>> get_state_badge_color('cancelled')
        'danger'
    """
    colors = {
        'incoming': 'secondary',
        'available': 'info',
        'assigned': 'primary',
        'in_review': 'warning',
        'submitted_aavso': 'light',
        'accepted_aavso': 'success',
        'rejected_aavso': 'danger',
        'cancelled': 'dark'
    }
    return colors.get(state, 'secondary')


# ============================================================================
# COSTANTI EVENT TYPES per Audit Log
# ============================================================================

class AuditEventType:
    """Tipi di eventi standard per audit log"""

    # Lifecycle progetto
    PROJECT_CREATED = "project_created"
    PROJECT_ASSIGNED = "project_assigned"
    PROJECT_REASSIGNED = "project_reassigned"
    PROJECT_SENT_TO_REVIEW = "project_sent_to_review"
    PROJECT_REVIEW_COMPLETED = "project_review_completed"
    PROJECT_REVERTED_TO_ASSIGNED = "project_reverted_to_assigned"
    PROJECT_CANCELLED = "project_cancelled"
    PROJECT_CLOSED = "project_closed"

    # Invio AAVSO
    PROJECT_SUBMITTED_AAVSO = "project_submitted_aavso"
    PROJECT_ACCEPTED_AAVSO = "project_accepted_aavso"
    PROJECT_REJECTED_AAVSO = "project_rejected_aavso"

    # Slack
    SLACK_THREAD_CREATED = "slack_thread_created"
    SLACK_THREAD_PROMOTED_TO_CHANNEL = "slack_thread_promoted_to_channel"
    SLACK_MESSAGE_SENT = "slack_message_sent"
    SLACK_ERROR = "slack_error"

    # Dati scientifici
    SCIENCE_DATA_UPDATED = "science_data_updated"
    OUTPUT_UPLOADED = "output_uploaded"
    DATASET_UPLOADED = "dataset_uploaded"

# AGATA Admin Blueprint

Interfaccia di amministrazione autoritativa per il sistema AGATA.

## Principi fondamentali

1. **AGATA è autoritativo** - Tutti i cambi stato avvengono qui, Slack è riflesso
2. **Multi-associazione nativa** - Ogni associazione ha scope isolato
3. **Audit completo** - Ogni azione amministrativa è tracciata
4. **RBAC per associazione** - Permessi context-aware
5. **Nessuna azione distruttiva irreversibile**

## Ruoli supportati

| Ruolo | Scope | Permessi |
|-------|-------|----------|
| `superuser` | Globale | Governance completa, tutte le associazioni |
| `admin` | Associazione singola | Gestione operativa associazione |
| `reviewer` | Associazione singola | Review scientifica progetti |
| `analyst` | Associazione singola | Analisi stelle, accesso limitato |
| `viewer` | Audit | Sola lettura per audit esterni |

## Struttura

```
agata/admin/
├── __init__.py              # Blueprint principale
├── decorators.py            # RBAC decorators
├── README.md               # Questa documentazione
├── routes/                 # Routes per funzionalità
│   ├── overview.py         # Dashboard principale
│   ├── associations.py     # Gestione associazioni
│   ├── users.py           # Gestione utenti
│   ├── projects.py        # Catalogo progetti (cuore)
│   ├── workflow.py        # Vista workflow globale
│   ├── slack_integration.py # Monitoring Slack
│   ├── audit.py           # Audit log viewer
│   └── config.py          # Policy e configurazioni
├── services/              # Business logic
│   ├── audit_service.py   # Gestione audit log
│   ├── project_service.py # Operazioni progetti
│   └── stats_service.py   # Statistiche dashboard
└── templates/             # Templates HTML
```

## URL Routes

### Dashboard e Overview
- `GET /agata/admin/` - Dashboard principale
- `GET /agata/admin/dashboard` - Alias dashboard
- `GET /agata/admin/api/stats` - Statistiche JSON

### Gestione Progetti (core)
- `GET /agata/admin/projects` - Catalogo progetti
- `GET /agata/admin/projects/<id>` - Dettaglio progetto
- `POST /agata/admin/api/projects/<id>/assign` - Assegna analyst
- `POST /agata/admin/api/projects/<id>/reassign` - Riassegna analyst
- `POST /agata/admin/api/projects/<id>/send-to-review` - Invia in review
- `POST /agata/admin/api/projects/<id>/cancel` - Cancella progetto
- `POST /agata/admin/api/projects/<id>/change-state` - Cambio stato manuale
- `GET /agata/admin/api/projects/<id>/audit-trail` - Timeline audit completo

### Gestione Associazioni
- `GET /agata/admin/associations` - Lista associazioni
- `GET /agata/admin/associations/<id>` - Dettaglio associazione
- `GET /agata/admin/api/associations` - JSON lista
- `POST /agata/admin/api/associations` - Crea (superuser)
- `PATCH /agata/admin/api/associations/<id>` - Aggiorna

### Gestione Utenti
- `GET /agata/admin/users` - Lista utenti
- `GET /agata/admin/users/<id>` - Dettaglio utente
- `GET /agata/admin/api/users` - JSON lista
- `POST /agata/admin/api/users/<id>/update-role` - Cambio ruolo
- `POST /agata/admin/api/users/<id>/toggle-active` - Attiva/sospendi

### Workflow
- `GET /agata/admin/workflow` - Vista matrice workflow
- `GET /agata/admin/api/workflow/stats` - Statistiche JSON

### Slack
- `GET /agata/admin/slack` - Overview integrazione
- `GET /agata/admin/api/slack/channels` - Canali JSON
- `POST /agata/admin/api/slack/test-connection` - Test (superuser)

### Audit Log
- `GET /agata/admin/audit` - Visualizzatore audit log
- `GET /agata/admin/api/audit` - Query audit JSON

### Configurazioni
- `GET /agata/admin/config` - Configurazioni sistema (superuser)
- `GET /agata/admin/api/config` - Config JSON
- `PUT /agata/admin/api/config/<key>` - Aggiorna config

## Workflow Stati Progetti

Stati validi:
```
incoming → available → assigned → in_review → submitted_aavso
                                               ↓
                                    accepted_aavso / rejected_aavso
                     ↓
                 cancelled (da qualsiasi stato)
```

### Transizioni permesse

```python
STATE_TRANSITIONS = {
    'incoming': ['available', 'cancelled'],
    'available': ['assigned', 'cancelled'],
    'assigned': ['available', 'in_review', 'cancelled'],
    'in_review': ['assigned', 'submitted_aavso', 'cancelled'],
    'submitted_aavso': ['accepted_aavso', 'rejected_aavso', 'cancelled'],
    'accepted_aavso': [],  # finale
    'rejected_aavso': ['assigned'],
    'cancelled': []  # finale
}
```

## Utilizzo Decorators

### `@admin_required(min_role)`
Richiede ruolo minimo:
```python
@admin_bp.route('/projects')
@admin_required('analyst')  # analyst o superiore
def list_projects():
    ...
```

### `@superuser_required`
Solo superuser:
```python
@admin_bp.route('/config')
@superuser_required
def system_config():
    ...
```

### `@association_scope_required`
Valida accesso associazione da URL/body:
```python
@admin_bp.route('/associations/<int:association_id>/users')
@association_scope_required
def list_association_users(association_id):
    # association_id già validato
    ...
```

### `@audit_action(action, entity_type)`
Registra automaticamente in audit log:
```python
@admin_bp.route('/projects/<int:id>/assign', methods=['POST'])
@audit_action('project_assigned', 'project')
def assign_project(id):
    ...
```

## Permission Checking Functions

```python
from agata.admin.decorators import can_manage_association, can_view_association

# Check se utente può gestire associazione
if can_manage_association(association_id):
    # permetti modifica
    ...

# Check se utente può vedere dati associazione
if can_view_association(association_id):
    # permetti lettura
    ...
```

## Services

### Audit Service
```python
from agata.admin.services.audit_service import log_audit, query_audit_log

# Registra evento
log_audit(
    user_id=current_user.id,
    user_email=current_user.email,
    association_id=association_id,
    action='project_state_changed',
    entity_type='project',
    entity_id=str(project_id),
    old_value='assigned',
    new_value='in_review',
    description='Project sent to review'
)

# Query audit log
entries = query_audit_log(
    association_id=1,
    action='project_assigned',
    from_date=datetime.now() - timedelta(days=7),
    limit=100
)
```

### Project Service
```python
from agata.admin.services.project_service import (
    assign_project,
    reassign_project,
    send_to_review,
    cancel_project,
    change_project_state
)

# Assegna progetto
success, error, project = assign_project(
    project_id=123,
    analyst_user_id='user-uuid',
    assigned_by_user_id=current_user.id
)

if success:
    # OK
else:
    # Gestisci errore
```

### Stats Service
```python
from agata.admin.services.stats_service import (
    get_dashboard_stats,
    get_blocked_projects,
    get_review_backlog
)

# Statistiche dashboard
stats = get_dashboard_stats(association_id=1)  # o None per globale

# Progetti bloccati
blocked = get_blocked_projects(days_threshold=7, association_id=1)

# Backlog review
backlog = get_review_backlog(association_id=1)
```

## Templates

Layout base: `admin/base.html`
- Sidebar con navigazione
- Header con user info
- Content area

Pagine implementate:
- `admin/dashboard.html` - Dashboard principale
- `admin/projects/list.html` - Catalogo progetti
- `admin/projects/detail.html` - Dettaglio progetto (TODO completare)
- Altri template placeholder da completare

## TODO / Next Steps

1. **Completare templates HTML** per:
   - Dettaglio progetto (con azioni context-aware)
   - Lista/dettaglio associazioni
   - Lista/dettaglio utenti
   - Workflow matrix view
   - Slack monitoring dashboard
   - Audit log viewer avanzato

2. **Implementare tabella `slack_errors`** per log errori Slack

3. **Aggiungere frontend JavaScript** per:
   - Azioni AJAX sui progetti (assign, cancel, etc.)
   - Filtri dinamici tabelle
   - Grafici statistiche

4. **Integrare con Slack API** reale:
   - Test connessione bot
   - Invio messaggi da admin
   - Retry queue errori

5. **Export audit log** per compliance (CSV, JSON)

6. **Notifiche email** per eventi critici

## Testing

```bash
# Verifica import blueprint
python -c "from agata.admin import admin_bp; print(admin_bp.name)"

# Run app
python app.py

# Accedi a: https://your-domain/agata/admin/
```

## Security Notes

- **RBAC enforced** - Tutti i routes protetti da decorators
- **Association scope** - Non-superuser vedono solo propria associazione
- **Audit immutabile** - Log non modificabili
- **No destructive actions** - Cancellazioni sono soft (stato 'cancelled')
- **Session protection** - Flask-Login strong mode

## Support

Per problemi o domande:
- Controlla i log audit: `/agata/admin/audit`
- Verifica permessi utente nel DB: tabella `agata_users`
- Controlla stato progetti: `/agata/admin/workflow`

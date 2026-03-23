# Field Star Map (AGATA module)

Modulo FE in stile AGATA 2026 (template + static JS/CSS), funzionalmente equivalente a `fe-demo`.

## Endpoint UI

- `/agata/field-star-map/`

## API backend usata

Il frontend chiama direttamente:

- `GET {FIELD_STAR_MAP_API_BASE_URL}/health`
- `GET {FIELD_STAR_MAP_API_BASE_URL}/field-star-map`

Variabile ambiente:

- `FIELD_STAR_MAP_API_BASE_URL` (default: `http://localhost:8000`)

## Registrazione blueprint (app Flask principale)

Esempio:

```python
from agata.field_star_map import field_star_map_bp
app.register_blueprint(field_star_map_bp)
```


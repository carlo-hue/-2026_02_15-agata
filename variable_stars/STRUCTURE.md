# Variable Stars Module - Struttura Refactorizzata

## Panoramica

Il modulo `variable_stars` è stato refactorizzato per migliorare:
- ✅ **Manutenibilità**: Ogni file ha responsabilità chiare e dimensioni gestibili
- ✅ **Testabilità**: Servizi isolati facilmente testabili
- ✅ **Leggibilità**: Codice organizzato per funzionalità
- ✅ **Scalabilità**: Facile aggiungere nuove features senza toccare file esistenti

## Struttura Directory

```
agata/variable_stars/
├── __init__.py                    # Blueprint registration + import routes
├── constants.py                   # Costanti globali (65 righe)
├── STRUCTURE.md                   # Questa documentazione
├── routes/
│   ├── __init__.py                # Package marker
│   ├── views.py                   # Rendering template (23 righe)
│   ├── data_routes.py             # Caricamento dati (181 righe)
│   ├── periodigramma.py           # Periodogramma + multi-periodo (318 righe)
│   ├── phase_routes.py            # Phase folding (148 righe)
│   ├── sigma_clipping.py          # Sigma clipping outlier (224 righe)
│   ├── extrema.py                 # Calcolo estremi (161 righe)
│   ├── zero_point_align.py        # Zero-point alignment (279 righe)
│   ├── ai_routes.py               # LLM Advisor (474 righe)
│   └── state_routes.py            # Persistenza stato (130 righe)
├── services/
│   ├── __init__.py                # Package marker
│   ├── arrow_parser.py            # Utility Arrow IPC (51 righe)
│   ├── statistics.py              # MAD, sigma-clipping helpers (109 righe)
│   ├── peak_detection.py          # find_peaks wrapper (131 righe)
│   └── llm_client.py              # AI provider abstraction (151 righe)
└── routes.py                      # ⚠️ FILE LEGACY (2210 righe) - DA DEPRECARE
```

## Routes Mapping

### Homepage
- **GET** `/` → `views.py::index()`

### Data Loading
- **GET** `/api/lightcurve.arrow` → `data_routes.py::api_lightcurve_arrow()`

### Periodogram Analysis
- **POST** `/api/periodogram.arrow` → `periodigramma.py::api_periodogram_arrow()`
- **POST** `/api/multiperiod.arrow` → `periodigramma.py::api_multiperiod_arrow()`

### Phase Folding
- **POST** `/api/phase` → `phase_routes.py::api_phase_json()`
- **POST** `/api/phase.arrow` → `phase_routes.py::api_phase_arrow()`

### Quality Analysis
- **POST** `/api/sigma_clip.arrow` → `sigma_clipping.py::api_sigma_clip_arrow()`
- **POST** `/api/extrema.arrow` → `extrema.py::api_compute_extrema_per_session()`

### Calibration
- **POST** `/api/align_zeropoint.arrow` → `zero_point_align.py::api_align_zeropoint()`

### AI Advisor
- **POST** `/api/analyze_with_llm.arrow` → `ai_routes.py::api_analyze_with_llm()`

### State Persistence
- **POST** `/api/state/save` → `state_routes.py::api_state_save()`
- **GET** `/api/state/load` → `state_routes.py::api_state_load()`

## Services Layer

### arrow_parser.py
Utility per parsing Apache Arrow IPC stream:
- `read_arrow_table_from_request()`: Deserializza Arrow da Flask request
- `create_arrow_response()`: Serializza PyArrow table a bytes per Response

### statistics.py
Statistiche robuste per fotometria:
- `calculate_mad()`: Median Absolute Deviation
- `mad_to_sigma()`: Conversione MAD → σ equivalente
- `weighted_median()`: Mediana pesata
- `sigma_clip_mask()`: Maschera booleana per sigma clipping

### peak_detection.py
Identificazione picchi in curve di luce:
- `find_maxima()`: Trova massimi locali (stella debole)
- `find_minima()`: Trova minimi locali (stella luminosa)
- `compute_extrema_binned()`: Calcola estremi con binning mediano

### llm_client.py
Client astratto per provider AI:
- `LLMClient`: Classe che supporta Cerebras, Claude, OpenAI
- `generate()`: Genera completamento da prompt

## Constants

File `constants.py` centralizza tutte le costanti:
- Limiti validazione (MAX_SESSIONS, MIN/MAX_PERIOD, etc.)
- Soglie default (DEFAULT_SIGMA_THRESHOLD, etc.)
- Tipi stelle sintetiche supportati (ALLOWED_SYNTHETIC_KINDS)

## Migrazione da routes.py Legacy

Il vecchio file `routes.py` (2210 righe) è stato suddiviso come segue:

| Righe Originali | Nuovo File | Funzionalità |
|-----------------|------------|--------------|
| 65-74 | views.py | Homepage |
| 81-235 | data_routes.py | Caricamento lightcurve |
| 268-399 | periodigramma.py | Periodogramma singolo |
| 402-590 | periodigramma.py | Multi-periodo pre-whitening |
| 597-729 | phase_routes.py | Phase folding |
| 736-975 | sigma_clipping.py | Sigma clipping MAD |
| 1126-1337 | extrema.py | Calcolo estremi per sessione |
| 1344-1612 | zero_point_align.py | Zero-point alignment |
| 1619-2205 | ai_routes.py | AI Advisor LLM |
| 1000-1119 | state_routes.py | Persistenza stato DB |
| 49-59 | constants.py | Costanti configurazione |
| 242-261 | services/arrow_parser.py | Utility Arrow |

## Testing

Per testare il modulo refactorizzato:

```bash
# Avvia il server Flask
python run.py

# Test manuale endpoints (esempio)
curl http://localhost:5000/agata/variable-stars/

# Test con dati sintetici
curl "http://localhost:5000/agata/variable-stars/api/lightcurve.arrow?kind=rrlyrae&sessions=6"
```

## Prossimi Passi

1. ✅ Refactoring completato
2. ⏳ Testing funzionale su tutti gli endpoint
3. ⏳ Rimuovere `routes.py` legacy dopo verifica
4. ⏳ Aggiungere unit test per services layer
5. ⏳ Documentazione API completa (OpenAPI/Swagger)

## Note Importanti

- **NON modificare** `routes.py` legacy - è mantenuto solo per riferimento
- **Tutte le nuove modifiche** vanno fatte sui file refactorizzati
- I nomi dei file routes riflettono la loro funzionalità specifica:
  - `periodigramma.py` (non `analysis_routes.py`) per essere più descrittivo
  - `sigma_clipping.py` ed `extrema.py` (separati da `quality_routes.py`)
  - `zero_point_align.py` (non `calibration_routes.py`) più specifico

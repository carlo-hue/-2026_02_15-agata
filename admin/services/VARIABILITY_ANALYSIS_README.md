# Analisi Comparativa Stelle Variabili - API Documentation

## Overview

Questo modulo implementa un sistema completo di analisi comparativa per stelle variabili, integrando:

- **Query multi-catalogo**: Gaia DR3 Variability, VSX (AAVSO), ASAS-SN
- **Phased light curves**: Phase folding con periodi multipli
- **χ² fit**: Modello Fourier 2nd order per quantificare similarità
- **Caching Redis**: Performance ottimizzate con TTL 1h
- **Visualizzazione**: Plot PNG multi-panel (base64)

---

## Architettura

```
agata/admin/
├── services/
│   └── variability_analysis.py    # Core: query, LC, χ² fit
├── routes/
│   └── project_detail.py          # API endpoints
└── cache.py                        # Flask-Caching instance
```

### Dipendenze Aggiunte

```txt
astroquery==0.4.8      # Gaia TAP queries
redis==5.0.1           # Cache backend
Flask-Caching==2.3.0   # Flask cache wrapper
lightkurve==2.5.0      # Light curve handling
matplotlib==3.9.4      # Plot generation
```

---

## API Endpoints

### 1. Ricerca Stelle Analoghe

**Endpoint**: `POST /api/projects/<project_id>/variability/search-analogues`

**Permessi**: `analyst`, `admin`, `superuser`

**Body JSON**:
```json
{
  "periods": [0.345, 0.690],          // Lista periodi candidati (giorni)
  "bp_rp": 1.23,                      // Colore BP-RP (opzionale, auto-fetch da Gaia)
  "mag": 12.5,                        // Magnitudine G (opzionale, da project)
  "teff": 5800,                       // Temperatura efficace K (opzionale)
  "top_n": 10                         // Numero risultati (default 10)
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "project_id": 123,
  "gaia_id": "Gaia DR3 1234567890",
  "search_params": {
    "bp_rp": 1.23,
    "mag": 12.5,
    "teff": 5800,
    "periods": [0.345, 0.690]
  },
  "analogues_count": 10,
  "analogues": [
    {
      "source_id": "1234567891",
      "catalog": "Gaia DR3",
      "bp_rp": 1.25,
      "mag": 12.48,
      "teff": 5830,
      "var_type": "DSCT",
      "class_score": 0.95,
      "period": null,
      "similarity_score": 0.92
    },
    {
      "source_id": "VSX_J123456",
      "catalog": "VSX",
      "name": "V1234 And",
      "var_type": "DSCT",
      "mag": 12.6,
      "period": 0.348,
      "ra": 123.456,
      "dec": 45.678,
      "similarity_score": 0.88
    }
  ],
  "cached": false
}
```

**Tolleranze Scientifiche** (configurabili in `DEFAULT_TOLERANCES`):
- BP-RP: ±0.15 mag
- Magnitudine: ±0.5 mag
- Teff: ±300 K
- Periodo: ±0.5% del periodo

**Caching**:
- Cache key: `analogues:<gaia_id>:<periodo1,periodo2,...>`
- TTL: 3600s (1h)
- Backend: Redis (fallback: SimpleCache)

---

### 2. Phased Light Curve Comparison

**Endpoint**: `POST /api/projects/<project_id>/variability/phased-comparison`

**Permessi**: `analyst`, `admin`, `superuser`

**Body JSON**:
```json
{
  "periodo": 0.345,                           // Periodo per folding (giorni)
  "analogue_gaia_ids": [                      // IDs stelle analoghe (max 3)
    "1234567891",
    "1234567892"
  ],
  "catalog": "ASAS-SN"                        // Catalogo dati (opzionale: tutti)
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "project_id": 123,
  "periodo": 0.345,
  "lc_count": 3,
  "plot": "data:image/png;base64,iVBORw0KGgoAAAANS...",  // PNG base64
  "message": "Generated phased comparison for 3 light curves"
}
```

**Plot Output**:
- Multi-panel: 1 panel per LC (target + analoghe)
- Asse X: Phase (0-1)
- Asse Y: Normalized Flux (invertito per magnitudini)
- Overlay: Fourier fit (2nd order) in rosso
- Titolo panel: `Label | χ²=X.XX`

**χ² Fit**:
- Modello: `flux(φ) = 1 + a₁·sin(2πφ + φ₁) + a₂·sin(4πφ + φ₂)`
- Parametri output: `{a1, phi1, a2, phi2, chi2_reduced, residuals_std}`

---

### 3. Clear Cache

**Endpoint**: `POST /api/projects/<project_id>/variability/clear-cache`

**Permessi**: `admin`, `superuser`

**Body**: Nessuno

**Response** (200 OK):
```json
{
  "success": true,
  "project_id": 123,
  "gaia_id": "Gaia DR3 1234567890",
  "cache_cleared": true,
  "message": "Cache cleared successfully"
}
```

**Behavior**:
- Redis: Delete keys matching `analogues:<gaia_id>:*`
- SimpleCache: Nessuna action (no pattern delete)

---

## Workflow Esempio (Frontend Integration)

### Step 1: Ottieni Periodi da Periodogramma
(Assumi frontend ha già calcolato periodi con Lomb-Scargle)

```javascript
const periodi = [0.345, 0.690, 1.035]; // Top 3 periodi
```

### Step 2: Cerca Stelle Analoghe

```javascript
const response = await fetch(`/api/projects/${projectId}/variability/search-analogues`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    periods: periodi,
    top_n: 10
  })
});

const data = await response.json();
console.log(`Trovate ${data.analogues_count} stelle analoghe`);

// Mostra tabella analoghe ordinate per similarity_score
data.analogues.forEach(a => {
  console.log(`${a.source_id} (${a.catalog}): score=${a.similarity_score}, tipo=${a.var_type}`);
});
```

### Step 3: Confronta Phased Light Curves

```javascript
// Selezione top 3 analoghe più simili
const topAnalogues = data.analogues.slice(0, 3).map(a => a.source_id);

const plotResponse = await fetch(`/api/projects/${projectId}/variability/phased-comparison`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    periodo: periodi[0],  // Periodo primario
    analogue_gaia_ids: topAnalogues,
    catalog: 'ASAS-SN'
  })
});

const plotData = await plotResponse.json();

// Mostra plot PNG base64 in <img>
document.getElementById('phased-plot').src = plotData.plot;
```

### Step 4: Clear Cache (Admin Panel)

```javascript
// Admin panel: button "Clear Cache"
await fetch(`/api/projects/${projectId}/variability/clear-cache`, {
  method: 'POST'
});
```

---

## Cataloghi Interrogati

### Gaia DR3 Variability

**Tabella**: `gaiadr3.vari_classifier_result` JOIN `gaiadr3.gaia_source`

**Parametri**:
- `bp_rp`, `phot_g_mean_mag`, `teff_gspphot`: Filtri primari
- `best_class_name`, `best_class_score`: Classificazione variabile (ML)

**Limiti**:
- Periodo non direttamente disponibile in `vari_classifier_result`
- Per periodi precisi serve `vari_time_series_statistics` (pesante, non implementato)

### VSX (AAVSO Variable Star Index)

**API**: `https://www.aavso.org/vsx/index.php?view=api.delim`

**Parametri**:
- `coords`, `size`: Cone search (raggio default 5°)
- `max_mag`, `min_mag`: Range magnitudine
- `period_min`, `period_max`: Range periodo

**Output**:
- Nome, tipo variabile, coordinate, periodo, magnitudine max/min

### ASAS-SN

**Implementazione**: Usa module `asassn.py` esistente

**Note**:
- Per query analoghe serve cross-reference Gaia ID
- API pubblica ha rate limiting (timeout 300s)

---

## Configurazione Redis (Production)

### Setup Redis

```bash
# Install Redis
sudo apt install redis-server

# Start Redis
sudo systemctl start redis
sudo systemctl enable redis

# Test
redis-cli ping  # → PONG
```

### Environment Variables

Aggiungi in `.env`:

```bash
# Redis URL (default: localhost:6379 database 0)
REDIS_URL=redis://localhost:6379/0

# Opzionale: Redis password/SSL
# REDIS_URL=redis://:password@host:6379/0
# REDIS_URL=rediss://host:6380/0  # SSL
```

### Verifica Cache in Logs

```python
# Flask logs mostreranno:
# INFO: Cached 10 analogues for analogues:1234567890:0.345,0.690
# INFO: Retrieved 10 analogues from cache
```

---

## Testing API (cURL Examples)

### Search Analogues

```bash
curl -X POST https://astrogen.it/api/projects/123/variability/search-analogues \
  -H "Content-Type: application/json" \
  -H "Cookie: session=..." \
  -d '{
    "periods": [0.345, 0.690],
    "top_n": 5
  }'
```

### Generate Phased Comparison

```bash
curl -X POST https://astrogen.it/api/projects/123/variability/phased-comparison \
  -H "Content-Type: application/json" \
  -H "Cookie: session=..." \
  -d '{
    "periodo": 0.345,
    "analogue_gaia_ids": ["1234567891", "1234567892"],
    "catalog": "ASAS-SN"
  }' \
  | jq -r '.plot' | sed 's/data:image\/png;base64,//' | base64 -d > plot.png
```

---

## Estensioni Future

### 1. Query ASAS-SN Variability Catalog

Implementare query diretta al database ASAS-SN per periodi precisi:

```python
# Usa pyasassn client
from pyasassn import SkyPatrolClient
client = SkyPatrolClient()
results = client.adql_query(f"""
  SELECT * FROM stellar_main
  WHERE ABS(gaia_bp_rp - {bp_rp}) < 0.15
  AND period BETWEEN {periodo - delta_p} AND {periodo + delta_p}
""")
```

### 2. Cross-Match Multiplo

Aggiungi cross-match tra Gaia, VSX, ASAS-SN per validazione incrociata:

```python
# Merge candidati per source_id
merged = gaia_df.merge(vsx_df, on='source_id', how='outer')
```

### 3. Machine Learning Classification

Usa χ² scores per training ML classifier:

```python
from sklearn.ensemble import RandomForestClassifier

# Features: chi2, similarity, period_match, color_diff
X = [[chi2, sim, p_diff, bp_rp_diff], ...]
y = ['DSCT', 'RR', 'MIRA', ...]

clf = RandomForestClassifier()
clf.fit(X, y)
```

### 4. Interactive Plot (Plotly)

Sostituisci Matplotlib con Plotly per plot interattivi:

```python
import plotly.graph_objects as go

fig = go.Figure()
fig.add_trace(go.Scatter(x=phase, y=flux, mode='markers'))
fig.update_layout(title='Phased LC')
return fig.to_html()
```

---

## Troubleshooting

### Error: `No lightcurve data for Gaia XXX`

**Causa**: Nessun dato in `Cataloghi_esterni` per il progetto

**Soluzione**:
1. Verifica import da ASAS-SN/TESS: `/api/catalogs/asassn/auto/download-data`
2. Controlla `catalog_name` match (case-sensitive)

### Error: `Redis connection refused`

**Causa**: Redis non attivo o URL errato

**Soluzione**:
1. Verifica Redis: `redis-cli ping`
2. Check `.env`: `REDIS_URL=redis://localhost:6379/0`
3. Fallback: app usa `SimpleCache` (in-memory)

### Error: `Fit failed` nei plot

**Causa**: Dati insufficienti o LC troppo noise

**Soluzione**:
1. Minimo 50 punti LC per fit robusto
2. Check `flux_err`: se troppo grandi, fit diverge
3. Normalizza LC prima del fit (già implementato)

---

## Credits & References

- **Gaia DR3 Variability**: [ESA Gaia Archive](https://gea.esac.esa.int/archive/)
- **VSX**: [AAVSO Variable Star Index](https://www.aavso.org/vsx/)
- **ASAS-SN**: [All-Sky Automated Survey](https://asas-sn.osu.edu/)
- **Lomb-Scargle**: Astropy TimeSeries
- **χ² fit**: Scipy curve_fit

---

**Maintainer**: AstroGen APS
**Version**: 1.0.0
**Last Update**: 2026-01-30

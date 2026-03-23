# Test Locale TPF

## Prerequisiti

- Python disponibile da terminale
- Flask installato nell'ambiente usato per il test
- Dipendenze gia' presenti per il modulo TPF, in particolare `astroquery` e `astropy`
- Connessione di rete disponibile verso Gaia DR3 per il ramo reale di `/tpf/api/run`

## Avvio rapido

Apri PowerShell, posizionati nella root del repo AGATA e avvia il modulo locale:

```powershell
cd "C:\Users\CarloMarino\OneDrive - camarino59\OneDrive\CODICE\2026_02_15-agata"
python -m moduli.tpf.run
```

In alternativa:

```powershell
cd "C:\Users\CarloMarino\OneDrive - camarino59\OneDrive\CODICE\2026_02_15-agata"
py -m moduli.tpf.run
```

All'avvio il server stampa in console gli URL principali del modulo.

## URL utili

- UI autonoma: `http://127.0.0.1:5010/tpf/`
- UI con gaia_source_id da URL: `http://127.0.0.1:5010/tpf/?gaia_source_id=5853498713190525696`
- UI con contesto applicativo: `http://127.0.0.1:5010/tpf/?gaia_source_id=5853498713190525696&source_context=tce`
- Health: `http://127.0.0.1:5010/tpf/health`
- API run: `http://127.0.0.1:5010/tpf/api/run`
- API save: `http://127.0.0.1:5010/tpf/api/save`

## Esempio di Gaia source_id

Per una prova iniziale usa un Gaia DR3 source_id numerico, ad esempio:

- `5853498713190525696`

## Cosa aspettarsi nella UI

### `/tpf/`

La pagina mostra:

- form con campo `gaia_source_id`
- bottone `Run`
- bottone `Salva sessione`, disabilitato finche' non c'e' un risultato valido
- sezione stato
- sezione target
- preview TPF come heatmap Plotly
- sezione light curve
- output JSON formattato
- preview separata del payload di ritorno AGATA

### Apertura con query parameter

Se apri:

```text
/tpf/?gaia_source_id=5853498713190525696&source_context=tce
```

la UI:

- precompila il campo `gaia_source_id`
- mostra il `source_context`
- indica che il modulo e' stato aperto con parametri in ingresso
- non lancia automaticamente la pipeline

### `/tpf/health`

Risposta attesa:

```json
{
  "status": "ok",
  "message": "TPF component healthy",
  "component": "tpf"
}
```

## Esempio chiamata API `/tpf/api/run`

```powershell
$body = @{ gaia_source_id = '5853498713190525696'; source_context = 'tce' } | ConvertTo-Json
Invoke-RestMethod -Uri 'http://127.0.0.1:5010/tpf/api/run' -Method Post -ContentType 'application/json' -Body $body
```

## Esempio risposta `/tpf/api/run`

```json
{
  "status": "ok",
  "message": "Pipeline TPF completata correttamente.",
  "mode": "preview",
  "input": {
    "gaia_source_id": "5853498713190525696"
  },
  "target": {
    "gaia_source_id": "5853498713190525696",
    "ra_deg": 0.0,
    "dec_deg": 0.0,
    "gmag": 12.3,
    "catalog": "Gaia DR3"
  },
  "tpf": {
    "status": "ok",
    "available": true,
    "mode": "preview",
    "message": "Preview TPF derivata da Gaia DR3: heatmap sintetica basata su target e stelle vicine.",
    "flux_grid": [[0.0]]
  },
  "lightcurve": {
    "status": "ok",
    "available": false,
    "mode": "placeholder",
    "message": "Light curve non ancora disponibile in questa fase.",
    "time": [],
    "flux": []
  }
}
```

## Esempio chiamata API `/tpf/api/save`

```powershell
$payload = @{
  input = @{ gaia_source_id = '5853498713190525696' }
  target = @{ gaia_source_id = '5853498713190525696'; label = 'demo' }
  tpf = @{ available = $true }
  lightcurve = @{ available = $false }
  agata_context = @{ entry_mode = 'incoming-params'; source_context = 'tce' }
} | ConvertTo-Json -Depth 6
Invoke-RestMethod -Uri 'http://127.0.0.1:5010/tpf/api/save' -Method Post -ContentType 'application/json' -Body $payload
```

## Integrazione con altri moduli AGATA

Il meccanismo standard di ingresso ora e':

- query parameter `gaia_source_id`
- query parameter opzionale `source_context`

Il frontend prepara anche un payload di ritorno applicativo, mostrato in pagina come anteprima, pensato come punto di estensione per futuri richiami da altri moduli AGATA.

## Troubleshooting base

- Se `/tpf/health` non risponde, controlla che il server sia partito sulla porta `5010`.
- Se `/tpf/api/run` ritorna `gaia_source_id mancante`, verifica che il campo non sia vuoto.
- Se `/tpf/api/run` ritorna `gaia_source_id non valido`, verifica che il valore sia numerico.
- Se `/tpf/api/run` fallisce con errore remoto, controlla la raggiungibilita' del servizio Gaia DR3.
- Se la UI sembra vecchia dopo una modifica, fai un refresh forzato con `Ctrl+F5`.
- Se `Salva sessione` resta disabilitato, significa che l'ultimo `Run` non ha prodotto un risultato valido.

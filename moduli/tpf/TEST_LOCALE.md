# Test Locale TPF

## Input standard del modulo

Il contratto applicativo minimo del modulo `tpf` prevede:

- `gaia_source_id`: input principale
- `source_context`: input opzionale di integrazione applicativa

## Modalita' supportate

### standalone

Il modulo e' aperto direttamente, senza contesto chiamante.

Esempio:

```text
/tpf/
/tpf/?gaia_source_id=5853498713190525696
```

### integrated

Il modulo e' aperto da un altro componente AGATA e riceve un `source_context` esplicito.

Esempio:

```text
/tpf/?gaia_source_id=5853498713190525696&source_context=tce
```

## Prerequisiti

- Python disponibile da terminale
- Flask installato nell'ambiente usato per il test
- Dipendenze gia' presenti per il modulo TPF, in particolare `astroquery` e `astropy`
- Connessione di rete disponibile verso Gaia DR3 per il ramo reale di `/tpf/api/run`

## Avvio rapido

```powershell
cd "C:\Users\CarloMarino\OneDrive - camarino59\OneDrive\CODICE\2026_02_15-agata"
python -m moduli.tpf.run
```

In alternativa:

```powershell
cd "C:\Users\CarloMarino\OneDrive - camarino59\OneDrive\CODICE\2026_02_15-agata"
py -m moduli.tpf.run
```

## URL utili

- UI standalone: `http://127.0.0.1:5010/tpf/`
- UI standalone con input precompilato: `http://127.0.0.1:5010/tpf/?gaia_source_id=5853498713190525696`
- UI integrated: `http://127.0.0.1:5010/tpf/?gaia_source_id=5853498713190525696&source_context=tce`
- Health: `http://127.0.0.1:5010/tpf/health`
- API run: `http://127.0.0.1:5010/tpf/api/run`
- API save: `http://127.0.0.1:5010/tpf/api/save`

## Cosa aspettarsi nella UI

La pagina mostra:

- input `gaia_source_id`
- modalita' corrente: `standalone` oppure `integrated`
- `source_context`, se presente
- preview TPF
- stato salvataggio
- output JSON tecnico completo
- sezione separata `AGATA Return Payload`

La pipeline non parte automaticamente anche quando `gaia_source_id` arriva via query parameter.

## Esempio chiamata API `/tpf/api/run`

```powershell
$body = @{ gaia_source_id = '5853498713190525696'; source_context = 'tce' } | ConvertTo-Json
Invoke-RestMethod -Uri 'http://127.0.0.1:5010/tpf/api/run' -Method Post -ContentType 'application/json' -Body $body
```

## Payload di ritorno applicativo

Il frontend costruisce un payload sintetico e stabile tramite:

```javascript
buildAgataReturnPayload(lastRunResult, pageContext)
```

Struttura:

```json
{
  "component": "tpf",
  "mode": "standalone",
  "source_context": null,
  "input": {
    "gaia_source_id": "5853498713190525696"
  },
  "result": {
    "status": "ok",
    "target": {
      "gaia_source_id": "5853498713190525696",
      "catalog": "Gaia DR3",
      "ra_deg": 0.0,
      "dec_deg": 0.0,
      "gmag": 12.3
    },
    "tpf": {
      "available": true,
      "mode": "preview"
    },
    "lightcurve": {
      "available": false,
      "mode": "placeholder"
    },
    "save": {
      "mode": "stub",
      "saved": true
    }
  }
}
```

Questo payload:

- e' distinto dal JSON tecnico completo della pipeline
- e' mostrato in pagina
- non viene ancora inviato automaticamente ad altri moduli

## Troubleshooting base

- Se `/tpf/health` non risponde, controlla che il server sia partito sulla porta `5010`.
- Se `/tpf/api/run` ritorna `gaia_source_id mancante`, verifica che il campo non sia vuoto.
- Se `/tpf/api/run` ritorna `gaia_source_id non valido`, verifica che il valore sia numerico.
- Se `/tpf/api/run` fallisce con errore remoto, controlla la raggiungibilita' del servizio Gaia DR3.
- Se la UI sembra vecchia dopo una modifica, fai un refresh forzato con `Ctrl+F5`.
- Se `Salva sessione` resta disabilitato, significa che l'ultimo `Run` non ha prodotto un risultato valido.

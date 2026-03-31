# Test Locale TPF

## Input standard dell'editor TPF

Il contratto applicativo minimo dell'editor TPF prevede:

- `gaia_source_id`: obbligatorio
- `sector`: obbligatorio per il recupero del TPF reale locale
- `source_context`: opzionale

## Modalita' supportate

### standalone

Il modulo e' aperto direttamente, senza contesto chiamante.

Esempio:

```text
/tpf/
/tpf/?gaia_source_id=1996211639964641280&sector=57
```

### integrated

Il modulo e' aperto da un altro componente AGATA e riceve un `source_context` esplicito.

Esempio:

```text
/tpf/?gaia_source_id=1996211639964641280&sector=57&source_context=test
```

## Configurazione sorgente TPF reale

Il modulo tenta di leggere un TPF reale dalla cartella locale di test configurata in:

- `moduli/tpf/config.py`
- `settings.local_tpf_data_dir`
- `settings.mast_tpf_download_dir`
- `settings.legacy_tpf_util_path`

Path attuale:

- `C:\Users\CarloMarino\OneDrive - camarino59\OneDrive\CODICE\2026_02_15-agata\moduli\tpf\Dati_di_Prova`

Convenzione corrente:

- i file storici di test possono stare direttamente in `Dati_di_Prova`
- i TPF scaricati e i nuovi file locali vanno in `Dati_di_Prova/<gaia_source_id>/`

La lettura e' incapsulata in:

- `moduli/tpf/services/tpf_data_service.py`

## Lookup deterministico del file

Il TPF reale locale viene cercato in modo deterministico usando:

- `gaia_source_id`
- `sector`

Pattern atteso:

```text
{gaia_source_id}_num_sett_TESS_{sector}.fit
```

Per i TPF scaricati da MAST/TESS il naming locale usato dal nuovo workflow e':

```text
tpf_gaia_<gaia_id>_s<sector>_cut<cutout_size>.fits
```

Posizione attesa:

```text
moduli/tpf/Dati_di_Prova/<gaia_id>/tpf_gaia_<gaia_id>_s<sector>_cut<cutout_size>.fits
```

Se il file non viene trovato o non e' leggibile:

- la pipeline non fallisce
- viene usata la preview sintetica di fallback
- la light curve resta non disponibile con messaggio esplicito
- l'editing pixel viene disabilitato

## Maschere iniziali automatiche, editing manuale e light curve reale

Quando il TPF reale e' disponibile, il modulo:

- propone una maschera iniziale `foreground/target`
- propone una maschera iniziale `background`
- costruisce una light curve reale corretta

Ora l'utente puo' anche:

- scegliere la modalita' `Target` o `Background`
- cliccare sui pixel del TPF
- modificare manualmente le maschere
- premere `Ricalcola light curve`
- usare lo slider frame per navigare il TPF reale cadence per cadence
- cliccare un punto della light curve per vedere il frame corrispondente

Regole di editing:

- in modalita' `Target`, il click fa toggle del pixel target e rimuove lo stesso pixel dal background
- in modalita' `Background`, il click fa toggle del pixel background e rimuove lo stesso pixel dal target
- le due maschere restano mutuamente esclusive

Il backend valida le maschere ricevute e ricalcola la light curve usando quelle nuove.

## Conversione flux -> magnitudine

Per i TPF reali il backend salva ora, oltre alla curva in flusso:

- `flux_corrected`
- `mag_instr`
- `mag_tess_anchored`

Regole adottate:

- `mag_instr = -2.5 * log10(flux_corrected)` solo per i punti con `flux_corrected > 0`
- i punti con flusso non positivo non mandano in errore la pipeline
- i punti esclusi dalla conversione vengono contati e registrati nei metadata
- non viene usato alcuno zeropoint fotometrico fisso

Se nel TPF reale e' disponibile una magnitudine TESS del target:

- viene letta da `TESSMAG` o keyword equivalente nel FITS
- la curva viene ancorata con:
  - `delta = tessmag_ref - median(mag_instr)`
  - `mag_tess_anchored = mag_instr + delta`
- viene salvata anche la keyword FITS effettivamente usata come riferimento

Se la magnitudine TESS non e' disponibile:

- `mag_instr` resta disponibile
- `mag_tess_anchored` resta non ancorata e viene serializzata come `null`
- il metadata di ancoraggio resta vuoto

## Riferimento temporale e riproducibilita'

Per ogni light curve reale il modulo salva anche:

- `time_btjd`
- `time_bjd`
- `time_format`
- `time_system`
- `bjd_ref`

Scelta adottata:

- `time_btjd` usa i valori `TIME` originali del TPF reale
- `time_bjd` viene derivato come `TIME + BJDREFI + BJDREFF`
- il riferimento temporale viene letto dai metadata FITS del TPF reale, non hardcodato

Nel payload della light curve vengono inoltre salvati i dati necessari a riprodurre la curva a partire dal solo TPF:

- filename e path del TPF sorgente
- `gaia_id`, `sector`, `camera`, `ccd`, `cutout_size`
- maschere come lista di coordinate pixel:
  - `target_pixels`
  - `background_pixels`
- parametri di estrazione:
  - origine maschera `auto` / `manual`
  - threshold target/background se disponibili
  - metodo di stima del background
- parametri di ancoraggio magnitudine:
  - `reference_mag_value`
  - `reference_mag_band = "TESS"`
  - `reference_mag_key`
  - `anchoring_method = "median_shift"`

## Navigazione temporale del TPF

Quando il TPF reale e' disponibile:

- il `Run` non trasferisce piu' subito tutto il cubo `FLUX`
- il backend espone solo i metadati dei frame e la mappa `frame_indices` della light curve reale
- i frame reali vengono caricati a richiesta tramite endpoint dedicato

In UI:

- compare il pulsante `Carica frame visibili`
- l'utente puo' fare zoom sulla light curve
- il pulsante carica solo i cadence visibili nella finestra attuale
- dopo il caricamento, compare lo slider `Frame`
- viene mostrato `Frame: i / N`
- viene mostrato `Time: ...`
- il TPF visualizza il frame corrente invece della sola mediana riassuntiva
- cliccando un punto della light curve si seleziona il frame corrispondente se quel frame appartiene alla finestra caricata

Le maschere foreground/background, il target e l'overlay Gaia restano visibili su ogni frame caricato.

## Overlay target e sorgenti Gaia

Quando il TPF reale e' disponibile, il modulo prova anche a mostrare:

- la posizione del target sul TPF
- le sorgenti Gaia vicine che ricadono nel campo del cutout

Logica adottata:

- il target viene convertito da `RA/DEC` a coordinate pixel usando il WCS del TPF reale
- se il WCS non e' disponibile o non e' utilizzabile, il target viene posizionato al centro del TPF come fallback
- le sorgenti Gaia vicine vengono recuperate con una query leggera centrata sul target
- ogni sorgente viene convertita da `RA/DEC` a coordinate pixel tramite WCS
- vengono mantenute solo le sorgenti che ricadono dentro il campo del TPF

In UI:

- target = marker giallo
- sorgenti Gaia = marker blu
- pulsante `Gaia overlay ON/OFF` per mostrare o nascondere le sorgenti Gaia durante l'editing
- foreground/background restano distinti come overlay separato

## Workflow MAST / TESS

Il modulo espone ora anche un workflow separato, non distruttivo rispetto al viewer esistente, per:

- cercare i settori TESS disponibili a partire da un `gaia_id`
- verificare se il TPF di un settore e' gia' presente localmente
- scaricare il TPF scelto da MAST/TESS
- aprire poi il viewer TPF gia' esistente sul file appena scaricato

Questo workflow riusa in backend la logica legacy di `util.py`, ma salva i FITS in una cartella locale del modulo:

- `moduli/tpf/Dati_di_Prova/<gaia_id>/`

Se la cartella non esiste, viene creata automaticamente.

### Endpoint nuovi

- `POST /tpf/api/mast/sectors`
- `POST /tpf/api/mast/download`

### UI minima

Nel pannello `MAST / TESS` puoi:

- impostare `cutout_size` (default `10`)
- premere `Cerca settori TESS`
- vedere l'elenco dei settori disponibili
- distinguere quelli gia' scaricati localmente
- premere `Scarica TPF` oppure `Riusa / scarica`
- confermare se vuoi aprire subito il TPF nel viewer esistente

### Assunzione sul viewer esistente

Non viene creato un nuovo viewer.

Dopo il download, se confermi l'apertura, la UI richiama il normale flusso gia' esistente del modulo:

- `POST /tpf/api/run`

Il loader locale del modulo riconosce anche i TPF salvati in `moduli/tpf/Dati_di_Prova/<gaia_id>/`, quindi il viewer esistente li apre senza cambiare contratto.

## Prerequisiti

- Python disponibile da terminale
- Flask installato nell'ambiente usato per il test
- Dipendenze gia' presenti per il modulo TPF, in particolare `astroquery`, `astropy` e `numpy`
- Connessione di rete disponibile verso Gaia DR3 per il ramo reale di `/tpf/api/run`

## Avvio rapido

```powershell
cd "C:\Users\CarloMarino\OneDrive - camarino59\OneDrive\CODICE\2026_02_15-agata"
python -m moduli.tpf.run
```

## URL utili

- UI standalone: `http://127.0.0.1:5010/tpf/`
- UI standalone con input precompilato: `http://127.0.0.1:5010/tpf/?gaia_source_id=1996211639964641280&sector=57`
- UI integrated: `http://127.0.0.1:5010/tpf/?gaia_source_id=1996211639964641280&sector=57&source_context=tce`
- Health: `http://127.0.0.1:5010/tpf/health`
- API run: `http://127.0.0.1:5010/tpf/api/run`
- API frames: `http://127.0.0.1:5010/tpf/api/frames`
- API MAST sectors: `http://127.0.0.1:5010/tpf/api/mast/sectors`
- API MAST download: `http://127.0.0.1:5010/tpf/api/mast/download`
- API save: `http://127.0.0.1:5010/tpf/api/save`

## Cosa aspettarsi nella UI

La pagina mostra:

- input `gaia_source_id`
- input `sector`
- modalita' corrente: `standalone` oppure `integrated`
- TPF reale locale quando disponibile
- marker del target sul TPF
- marker delle sorgenti Gaia nel campo TPF
- pulsante `Carica frame visibili` sotto la light curve
- slider frame attivo solo dopo il caricamento esplicito dei frame visibili
- etichetta con indice frame e tempo corrente
- click sulla light curve che sincronizza il frame mostrato nel TPF quando il frame e' dentro la finestra caricata
- pulsante `Gaia overlay ON/OFF` utile quando le stelle Gaia rendono difficile il click sui pixel
- overlay foreground in rosso sul TPF
- overlay background in bianco sul TPF
- pulsanti `Target` e `Background` per la modalita' di editing
- pulsante `Ricalcola light curve`
- riepilogo del numero di pixel target/background
- light curve reale corretta aggiornata dopo il ricalcolo
- dati backend della light curve con:
  - `time_btjd`
  - `time_bjd`
  - `mag_instr`
  - `mag_tess_anchored`
- fallback a preview sintetica quando il TPF reale non e' disponibile
- pannello `MAST / TESS` per cercare e scaricare TPF reali da MAST/TESS
- evidenza dei settori gia' presenti localmente nella cartella download del modulo

## Come testare il caso TPF reale con editing manuale

Usa per esempio:

- `gaia_source_id = 1996211639964641280`
- `sector = 84`

Flusso suggerito:

1. Esegui `Run`
2. Verifica che il TPF sia `mode = real`
3. Verifica che compaiano foreground/background automatici
4. Fai zoom su una porzione della light curve, oppure lascia la vista completa
5. Premi `Carica frame visibili` e conferma l'avviso
6. Muovi lo slider `Frame` e verifica che il TPF cambi cadence
7. Clicca un punto della light curve nella finestra caricata e verifica che il TPF salti al frame corretto
8. Scegli `Target` oppure `Background`
9. Clicca alcuni pixel sulla heatmap
10. Premi `Ricalcola light curve`
7. Verifica:
   - aggiornamento del riepilogo pixel
   - aggiornamento del grafico light curve
   - messaggio `Light curve aggiornata`
   - slider frame coerente con la finestra caricata

## Come testare il caso preview sintetica

Usa una combinazione valida lato Gaia ma senza file locale corrispondente, ad esempio:

- `gaia_source_id = 1996211639964641280`
- `sector = 99`

Esito atteso:

- `tpf.mode = "preview"`
- pulsante `Carica frame visibili` disabilitato
- slider frame disabilitato
- editing pixel disabilitato
- `Ricalcola light curve` disabilitato
- light curve non disponibile con messaggio esplicito
- overlay Gaia non disponibile oppure limitato al solo fallback target

## Come testare il workflow MAST / TESS

1. Avvia il modulo `tpf` in locale.
2. Apri `http://127.0.0.1:5010/tpf/`.
3. Inserisci un `gaia_source_id` valido nel campo principale.
4. Nel pannello `MAST / TESS`, lascia `cutout_size = 10`.
5. Premi `Cerca settori TESS`.
6. Verifica che il backend risponda con:
   - coordinate risolte
   - elenco dei settori
   - flag `downloaded` per ogni settore
7. Premi `Scarica TPF` su un settore disponibile.
8. Verifica che il file venga creato in:
   - `moduli/tpf/Dati_di_Prova/<gaia_id>/`
9. Alla conferma UI scegli se aprire subito il TPF nel viewer esistente.

Esito atteso:

- il download endpoint restituisce `ok = true`
- il filename segue il pattern `tpf_gaia_<gaia_id>_s<sector>_cut10.fits`
- il pannello MAST evidenzia il settore come gia' scaricato
- il viewer TPF esistente riesce ad aprire il FITS scaricato senza modifiche al suo contratto

## Esempi curl

### Lista settori disponibili

```powershell
curl.exe -X POST "http://127.0.0.1:5010/tpf/api/mast/sectors" `
  -H "Content-Type: application/json" `
  -d "{\"gaia_id\":\"1996211639964641280\"}"
```

### Download TPF da MAST/TESS

```powershell
curl.exe -X POST "http://127.0.0.1:5010/tpf/api/mast/download" `
  -H "Content-Type: application/json" `
  -d "{\"gaia_id\":\"1996211639964641280\",\"sector\":57,\"cutout_size\":10}"
```

## Troubleshooting base

- Se `/tpf/api/run` ritorna `sector mancante`, verifica che il campo `sector` non sia vuoto.
- Se `/tpf/api/run` ritorna `sector non valido`, verifica che il valore sia numerico.
- Se `/tpf/api/mast/sectors` ritorna `gaia_source_id non valido`, verifica che il campo `gaia_id` sia numerico e non vuoto.
- Se `/tpf/api/mast/sectors` ritorna `gaia_id non risolto`, controlla il resolver Gaia legacy in `util.py`.
- Se `/tpf/api/mast/download` fallisce, verifica la connettivita' verso MAST/TESS e la presenza delle dipendenze legacy (`lightkurve`, `astroquery`).
- Se il file non viene scritto, controlla i permessi della cartella `moduli/tpf/Dati_di_Prova/<gaia_id>/`.
- Se il backend ritorna errore sulle maschere, controlla che target/background abbiano shape corretta e almeno un pixel ciascuno.
- Se il TPF reale non viene trovato, controlla che esista un file con naming coerente `gaia_source_id + sector` nella cartella di prova.
- Se la UI sembra vecchia dopo una modifica, fai un refresh forzato con `Ctrl+F5`.

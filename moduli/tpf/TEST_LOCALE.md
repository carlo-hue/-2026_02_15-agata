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

Path attuale:

- `C:\Users\CarloMarino\OneDrive - camarino59\OneDrive\CODICE\2026_02_15-agata\moduli\tpf\Dati_di_Prova`

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

Regole di editing:

- in modalita' `Target`, il click fa toggle del pixel target e rimuove lo stesso pixel dal background
- in modalita' `Background`, il click fa toggle del pixel background e rimuove lo stesso pixel dal target
- le due maschere restano mutuamente esclusive

Il backend valida le maschere ricevute e ricalcola la light curve usando quelle nuove.

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
- API save: `http://127.0.0.1:5010/tpf/api/save`

## Cosa aspettarsi nella UI

La pagina mostra:

- input `gaia_source_id`
- input `sector`
- modalita' corrente: `standalone` oppure `integrated`
- TPF reale locale quando disponibile
- marker del target sul TPF
- marker delle sorgenti Gaia nel campo TPF
- pulsante `Gaia overlay ON/OFF` utile quando le stelle Gaia rendono difficile il click sui pixel
- overlay foreground in rosso sul TPF
- overlay background in bianco sul TPF
- pulsanti `Target` e `Background` per la modalita' di editing
- pulsante `Ricalcola light curve`
- riepilogo del numero di pixel target/background
- light curve reale corretta aggiornata dopo il ricalcolo
- fallback a preview sintetica quando il TPF reale non e' disponibile

## Come testare il caso TPF reale con editing manuale

Usa per esempio:

- `gaia_source_id = 1996211639964641280`
- `sector = 84`

Flusso suggerito:

1. Esegui `Run`
2. Verifica che il TPF sia `mode = real`
3. Verifica che compaiano foreground/background automatici
4. Scegli `Target` oppure `Background`
5. Clicca alcuni pixel sulla heatmap
6. Premi `Ricalcola light curve`
7. Verifica:
   - aggiornamento del riepilogo pixel
   - aggiornamento del grafico light curve
   - messaggio `Light curve aggiornata`

## Come testare il caso preview sintetica

Usa una combinazione valida lato Gaia ma senza file locale corrispondente, ad esempio:

- `gaia_source_id = 1996211639964641280`
- `sector = 99`

Esito atteso:

- `tpf.mode = "preview"`
- editing pixel disabilitato
- `Ricalcola light curve` disabilitato
- light curve non disponibile con messaggio esplicito
- overlay Gaia non disponibile oppure limitato al solo fallback target

## Troubleshooting base

- Se `/tpf/api/run` ritorna `sector mancante`, verifica che il campo `sector` non sia vuoto.
- Se `/tpf/api/run` ritorna `sector non valido`, verifica che il valore sia numerico.
- Se il backend ritorna errore sulle maschere, controlla che target/background abbiano shape corretta e almeno un pixel ciascuno.
- Se il TPF reale non viene trovato, controlla che esista un file con naming coerente `gaia_source_id + sector` nella cartella di prova.
- Se la UI sembra vecchia dopo una modifica, fai un refresh forzato con `Ctrl+F5`.

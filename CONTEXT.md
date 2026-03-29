# AGATA Context

## Descrizione progetto

AGATA e' un insieme di moduli Flask e servizi Python per strumenti astronomici e componenti operativi. Nel repository sono presenti moduli storici e moduli piu' recenti sotto `moduli/`, tra cui `tpf` e `tess_tce`.

Il repository non espone una app factory Flask unica chiaramente definita a livello root. Il runner locale esplicito presente nel codice e' [moduli/tpf/run.py](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/moduli/tpf/run.py).

## Struttura reale del codice

- [__init__.py](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/__init__.py): metadata package
- [admin/](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/admin): route e servizi amministrativi
- [auth/](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/auth): autenticazione e decorator
- [auth_models/](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/auth_models): modelli applicativi
- [catalog/](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/catalog): blueprint/API cataloghi
- [exoplanets/](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/exoplanets): modulo analisi transiti
- [field_star_map/](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/field_star_map): UI AGATA per mappa Gaia
- [kb/](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/kb): servizi e CLI knowledge base
- [moduli/tess_tce/](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/moduli/tess_tce): modulo TESS TCE con blueprint
- [moduli/tpf/](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/moduli/tpf): editor TPF standalone e blueprint riusabile
- [services/](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/services): servizi condivisi
- [static/](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/static): asset condivisi
- [templates/](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/templates): template condivisi
- [variable_stars/](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/variable_stars): modulo storico piu' esteso

## Funzionalita' implementate visibili nel codice

- `variable_stars`
  - blueprint con controllo ruoli
  - endpoint per light curve, periodogramma, phase, clipping, save/load stato e advisor
- `exoplanets`
  - homepage
  - upload dati osservativi
  - caricamento/sintesi curve di luce
  - analisi BLS e validazione fisica
- `field_star_map`
  - UI AGATA per mappa stelle Gaia con protezione ruoli
- `catalog`
  - endpoint POST `/api/query`
  - cache in-memory e cache DB
- `moduli/tess_tce`
  - blueprint `/agata/tess-tce`
  - health endpoint
  - API e UI Jinja
- `moduli/tpf`
  - endpoint `/tpf/`, `/tpf/health`, `/tpf/api/run`, `/tpf/api/frames`, `/tpf/api/save`
  - runner locale Flask dedicato
  - lookup TPF reale da file FITS locale di test
  - fallback sintetico
  - overlay target/Gaia
  - maschere automatiche e manuali
  - light curve reale con sottrazione background
  - slider frame e sincronizzazione minima light curve -> frame TPF
  - caricamento ottimizzato dei frame visibili tramite route dedicata `/tpf/api/frames`
  - toggle UI per Gaia on/off, scala colore fissa on/off, linea/punti sulla light curve
  - save stub

## Stato attuale

### Cosa funziona

- Il modulo `moduli/tpf` e' avviabile localmente in modo autonomo.
- I blueprint `moduli/tpf` e `moduli/tess_tce` usano pattern `create_blueprint()`.
- `moduli/tpf` ha una pipeline locale reale basata su FITS di test, con editing pixel e ricalcolo light curve.
- `moduli/tpf` non invia piu' l'intero cubo TPF al frontend in `run`: espone metadati frame e carica finestre di frame on demand.
- `variable_stars`, `field_star_map`, `catalog` ed `exoplanets` hanno codice applicativo reale e route concrete.

### Cosa manca o non e' esplicito in questo repo

- Non c'e' una app Flask root unica chiaramente definita nel repository.
- Non e' presente un bootstrap centrale che registri tutti i blueprint in un solo punto.
- Alcuni moduli usano import relativi, altri import assoluti `agata.*`: il packaging complessivo non e' uniforme.
- `moduli/tpf` usa ancora dati FITS locali di prova e salvataggio stub; non c'e' persistenza reale.
- `moduli/tpf` non implementa ancora workflow multi-settore, detrend, binning, flatten o magnitudini finali.

## Prossimi step realistici

- Rendere esplicita una app factory AGATA centrale, se esiste fuori repo o va definita qui.
- Uniformare registrazione blueprint e packaging/import.
- Per `moduli/tpf`:
  - decidere la sorgente dati oltre ai FITS locali di prova
  - definire un contratto di persistenza reale
  - valutare un'opzione robusta per la stima del background se richiesta
- Aggiornare la documentazione root quando cambia il comportamento pubblico del modulo `tpf`.

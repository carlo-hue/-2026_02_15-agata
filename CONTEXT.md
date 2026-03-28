# AGATA Context

## Descrizione progetto

AGATA e' un insieme di moduli Flask e servizi Python per analisi astronomiche e strumenti operativi collegati. Nel codice attuale sono presenti aree per:

- stelle variabili
- esopianeti
- mappe di campo stellare
- cataloghi esterni
- knowledge base
- amministrazione/autenticazione
- moduli sperimentali o piu' recenti sotto `moduli/`, tra cui `tpf` e `tess_tce`

Il repository non espone una factory Flask unica a livello root. L'unico runner locale esplicito presente nel codice e' [moduli/tpf/run.py](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/moduli/tpf/run.py).

## Struttura reale del codice

- [__init__.py](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/__init__.py): metadata package (`AGATA`, versione `2.0.0`)
- [admin/](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/admin): route e servizi amministrativi
- [auth/](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/auth): autenticazione, OAuth, magic link, decorator
- [auth_models/](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/auth_models): modelli applicativi
- [catalog/](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/catalog): blueprint/API cataloghi, servizi, repository
- [exoplanets/](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/exoplanets): modulo analisi transiti esopianeti
- [field_star_map/](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/field_star_map): blueprint protetto per mappa stelle Gaia
- [kb/](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/kb): CLI e servizi knowledge base
- [moduli/tpf/](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/moduli/tpf): editor TPF standalone e blueprint riusabile
- [moduli/tess_tce/](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/moduli/tess_tce): modulo TESS TCE con blueprint
- [services/](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/services): servizi condivisi
- [static/](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/static): JS/CSS condivisi
- [templates/](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/templates): template Jinja condivisi
- [variable_stars/](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/variable_stars): modulo piu' esteso, con route separate e servizi dedicati

## Funzionalita' implementate visibili nel codice

- `variable_stars`
  - blueprint con controllo ruoli
  - endpoint API per lightcurve, periodogramma, phase, sigma clipping, estremi, zero-point, AI advisor, save/load stato
- `exoplanets`
  - homepage
  - upload file osservativi
  - caricamento/sintesi curve di luce
  - analisi BLS e validazione fisica
- `field_star_map`
  - UI AGATA per mappa stelle Gaia con protezione ruoli
- `catalog`
  - endpoint POST `/api/query`
  - query cataloghi con cache in-memory e cache DB
- `moduli/tess_tce`
  - blueprint `/agata/tess-tce`
  - health endpoint
  - API TCE e UI Jinja
- `moduli/tpf`
  - endpoint `/tpf/`, `/tpf/health`, `/tpf/api/run`, `/tpf/api/save`
  - runner locale Flask dedicato
  - lookup TPF reale da file locale di test
  - fallback sintetico
  - overlay target/Gaia
  - maschere automatiche e manuali
  - light curve reale con sottrazione background
  - save stub

## Stato attuale

### Cosa funziona

- Il modulo `moduli/tpf` e' avviabile localmente in modo autonomo.
- Il blueprint `moduli/tpf` e il blueprint `moduli/tess_tce` sono costruiti con `create_blueprint()`.
- `variable_stars`, `field_star_map`, `catalog`, `exoplanets` hanno codice applicativo reale e route concrete.
- Esistono servizi catalogo, KB e admin non banali, non solo placeholder.

### Cosa manca o non e' esplicito in questo repo

- Non c'e' una app Flask root unica chiaramente definita nel repository.
- Non e' presente un bootstrap centrale che registri tutti i blueprint in un solo punto.
- Alcuni moduli usano import relativi, altri usano import assoluti `agata.*`: il packaging complessivo non e' uniforme.
- `moduli/tpf` usa dati FITS locali di prova; non c'e' ancora persistenza reale.
- `moduli/tpf` non implementa ancora workflow multi-settore, detrend, binning o salvataggio DB.

## Prossimi step realistici

- Definire o rendere esplicita una app factory AGATA centrale, se esiste fuori repo o va creata qui.
- Uniformare la registrazione dei blueprint `moduli/*` rispetto ai moduli storici.
- Stabilizzare il packaging/import (`relative imports` vs `agata.*`).
- Per `moduli/tpf`: decidere la futura sorgente dati oltre ai FITS locali di prova e il contratto di persistenza reale.
- Aggiungere documentazione sintetica per i moduli principali oltre a `moduli/tpf`.

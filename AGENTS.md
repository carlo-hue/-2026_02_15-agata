# AGATA Working Notes

## Obiettivo

Lavorare sul repository AGATA senza assumere architetture o feature non presenti nel codice.

## Architettura reale

- Il repository contiene piu' blueprints/moduli Flask, non una singola app factory chiaramente centralizzata.
- Il runner locale esplicito presente nel codice e' [moduli/tpf/run.py](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/moduli/tpf/run.py).
- I moduli sotto [moduli/](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/moduli) usano pattern `create_blueprint()`.
- Moduli storici come [variable_stars/](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/variable_stars), [field_star_map/](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/field_star_map) e [catalog/](C:/Users/CarloMarino/OneDrive%20-%20camarino59/OneDrive/CODICE/2026_02_15-agata/catalog) hanno integrazioni proprie.

## Regole pratiche

- Usa solo funzionalita' osservabili nel codice.
- Non assumere l'esistenza di un bootstrap AGATA centrale se non e' nel repo.
- Prima di integrare un modulo nuovo, verifica se esiste gia' un blueprint o un runner locale.
- Non spostare logica scientifica nelle route: preferisci `services/`.
- Per UI dei moduli, mantieni il pattern:
  - `templates/...`
  - `static/js/...`
  - `static/css/...`

## Convenzioni di codice osservate

- Flask + Jinja lato server
- JS vanilla lato frontend
- Plotly gia' presente per i grafici
- servizi Python separati da route nei moduli piu' recenti
- logging semplice con `logging.getLogger(__name__)`
- JSON API abbastanza esplicite nei moduli recenti

## Vincoli per modifiche future

- Evita refactor globali se stai lavorando su un solo modulo.
- Se tocchi `moduli/tpf`, preserva:
  - endpoint esistenti
  - fallback sintetico
  - assenza di DB reale finche' non richiesto
- Se tocchi `moduli/tess_tce`, preserva il blueprint `/agata/tess-tce` e le API gia' esposte.
- Se tocchi moduli protetti (`variable_stars`, `field_star_map`, `catalog`), controlla sempre `before_request`, `login_required` o decorator ruoli.
- Non introdurre nuove dipendenze senza bisogno esplicito.

## Attenzioni specifiche

- Il repository non e' ancora uniformato sugli import:
  - alcuni file usano import relativi
  - altri usano `agata.*`
- Documenta sempre se una modifica vale:
  - solo in locale
  - solo per un modulo
  - oppure per tutta AGATA
- Quando aggiungi documentazione, scrivila vicino al modulo se e' locale al modulo; usa root solo per contesto trasversale.

## Priorita' consigliata

1. Capire se la modifica e' locale a un modulo o trasversale.
2. Verificare runner, blueprint e route reali del modulo coinvolto.
3. Mantenere compatibilita' con i servizi gia' presenti.
4. Aggiornare una documentazione minima se il comportamento pubblico cambia.

# TPF - Pacchetto per AGATA Produzione

Contenuto:
- codice del modulo `moduli/tpf`
- `db.py` per il binding SQLAlchemy usato dal save TPF

Esclusi volutamente:
- `.venv`
- `.env`
- `moduli/tpf/Dati_di_Prova`
- cache locali e file temporanei

Invocazioni UI:
- `/tpf/`
- `/tpf/?gaia_source_id=<GAIA_SOURCE_ID>&sector=<SECTOR>`
- `/tpf/?gaia_source_id=<GAIA_SOURCE_ID>&sector=<SECTOR>&source_context=<SOURCE_CONTEXT>`

Note:
- il modulo TPF ora include persistenza locale su MySQL tramite `DATABASE_URL`
- il file `.env` non e' incluso e va configurato nell'ambiente target
- il package non contiene dati locali di prova

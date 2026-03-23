# agata/cache.py
"""
Flask-Caching instance per AGATA.

Questo modulo esporta l'istanza cache che può essere importata
da qualsiasi modulo dell'applicazione.

Inizializzato in app.py dopo creazione Flask app.
"""
from flask_caching import Cache

# Cache instance (inizializzata in app.py)
cache = Cache()

__all__ = ['cache']

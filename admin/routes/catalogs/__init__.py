# agata/admin/routes/catalogs/__init__.py
"""
Blueprint per endpoint cataloghi esterni.

Ogni catalogo ha il suo file con endpoint dedicati:
- tess.py: TESS via MAST Portal
- ztf.py: ZTF via IRSA
- asassn.py: ASAS-SN via Sky Patrol
- ogle.py: OGLE via OCVS
- file_upload.py: Upload file fotometrici
- file_upload_qlp.py: Upload file TESS QLP (flusso)
"""
from flask import Blueprint

catalogs_bp = Blueprint('catalogs', __name__)

# Import route dopo la creazione del blueprint per evitare circular imports
from . import tess
from . import ztf
from . import asassn
from . import ogle
from . import file_upload
from . import file_upload_qlp

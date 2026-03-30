from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
LOCAL_TPF_DATA_DIR = MODULE_DIR / "Dati_di_Prova"
LEGACY_TPF_UTIL_PATH = Path(
    os.getenv(
        "TPF_LEGACY_UTIL_PATH",
        r"C:\Users\CarloMarino\OneDrive - camarino59\OneDrive\CODICE\gvt\python flask logica\util.py",
    )
)


@dataclass(frozen=True)
class TpfSettings:
    module_title: str = "AGATA - TPF"
    local_debug: bool = True
    placeholder_message: str = "Editor TPF pronto."
    local_tpf_data_dir: str = str(LOCAL_TPF_DATA_DIR)
    mast_tpf_download_dir: str = str(LOCAL_TPF_DATA_DIR)
    legacy_tpf_util_path: str = str(LEGACY_TPF_UTIL_PATH)
    default_cutout_size: int = 10


settings = TpfSettings()

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
LOCAL_TPF_DATA_DIR = MODULE_DIR / "Dati_di_Prova"


@dataclass(frozen=True)
class TpfSettings:
    module_title: str = "AGATA - TPF"
    local_debug: bool = True
    placeholder_message: str = "Editor TPF pronto."
    local_tpf_data_dir: str = str(LOCAL_TPF_DATA_DIR)


settings = TpfSettings()

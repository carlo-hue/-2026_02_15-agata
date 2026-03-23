from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TpfSettings:
    module_title: str = "AGATA - TPF"
    local_debug: bool = True
    placeholder_message: str = "Scaffold iniziale TPF attivo."


settings = TpfSettings()
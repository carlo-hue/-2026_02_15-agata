#service.py
import numpy as np
from agata.services.synthetic import generate_synthetic_lightcurve
from agata.services.db_loader import load_lightcurve_from_db


def get_lightcurve(
    source="synthetic",
    **kwargs
):
    """
    source:
      - synthetic
      - db
    """

    if source == "db":
        gaia_id = kwargs.get("gaia_id")
        if not gaia_id:
            raise ValueError("GAIAID richiesto per source=db")
        return load_lightcurve_from_db(gaia_id)

    kind = kwargs.get("kind", "rrlyrae")
    n_sessions = kwargs.get("n_sessions", 6)
    seed = kwargs.get("seed", 1)
    realism = kwargs.get("realism", 4)

    # Default: usa generatore standard (include "multiperiod")
    return generate_synthetic_lightcurve(
        kind=kind,
        n_sessions=n_sessions,
        seed=seed,
        realism=realism,
    )

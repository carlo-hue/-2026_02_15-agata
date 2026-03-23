#service_db.py
import numpy as np
from sqlalchemy import text
from agata.db import engine


def load_lightcurve_from_db(gaia_id: str):
    """
    Restituisce lo stesso formato di generate_synthetic_lightcurve()
    """

    sql = text("""
        SELECT
            JDT,
            mag as magCalibrataMedia,
            sessione
        FROM dati_stelle
        WHERE GAIAID = :gaia_id
        union all
 		SELECT
            hjd as JDT,
            Vmag as magCalibrataMedia,
            catalogo as sessione
        FROM Cataloghi_esterni
        WHERE Source = :gaia_id 
        AND Vmag is not null
    """)

    with engine.connect() as conn:
        rows = conn.execute(sql, {"gaia_id": gaia_id}).fetchall()

    if not rows:
        return []

    # -------------------------------
    # Raggruppa per sessione
    # -------------------------------
    sessions = {}
    for jd, mag, sessione in rows:
        sessions.setdefault(sessione, {"jd": [], "mag": []})
        sessions[sessione]["jd"].append(jd)
        sessions[sessione]["mag"].append(mag)

    # -------------------------------
    # Normalizzazione + output finale
    # -------------------------------
    out = []
    for idx, (session_name, data) in enumerate(sessions.items()):
        jd = np.asarray(data["jd"], dtype=np.float64)
        mag = np.asarray(data["mag"], dtype=np.float64)

        out.append({
            "session_id": idx,
            "session_name": str(session_name),  # Nome sessione dal DB
            "jd": jd,
            "mag": mag
        })

    return out

"""
services/synthetic_exoplanets.py - Generatore Transiti Esopianeti

Genera curve di luce sintetiche con transiti esopianeti fisicamente accurati.
Usa il modello Mandel & Agol 2002 per transiti realistici.

Riferimenti:
- Mandel & Agol 2002, ApJ 580, L171
- Seager & Mallén-Ornelas 2003, ApJ 585, 1038
- Winn 2010, arXiv:1001.2010 (exoplanet transits review)

Autore: AGATA Project Team
Data: 2026-01-03
"""

import numpy as np
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# COSTANTI FISICHE
# =============================================================================

G_SI = 6.67430e-11          # Gravitazione universale [m³ kg⁻¹ s⁻²]
M_SUN = 1.98847e30          # Massa solare [kg]
R_SUN = 6.95700e8           # Raggio solare [m]
R_JUP = 6.9911e7            # Raggio Giove [m]
R_EARTH = 6.371e6           # Raggio Terra [m]
AU = 1.495978707e11         # Unità astronomica [m]


# =============================================================================
# UTILITY: PARAMETRI ORBITALI
# =============================================================================

def calc_semimajor_axis(period_days, stellar_mass_msun):
    """
    Calcola semiasse orbitale dalla Terza Legge di Keplero.
    
    P² = (4π²/GM★) × a³
    → a = [(GM★ × P²) / (4π²)]^(1/3)
    
    Args:
        period_days: Periodo orbitale [giorni]
        stellar_mass_msun: Massa stella [M☉]
    
    Returns:
        Semiasse orbitale [AU]
    """
    period_sec = period_days * 86400  # giorni → secondi
    mass_kg = stellar_mass_msun * M_SUN
    
    a_meters = ((G_SI * mass_kg * period_sec**2) / (4 * np.pi**2)) ** (1/3)
    a_au = a_meters / AU
    
    return a_au


def calc_transit_duration(period_days, rp_over_rs, a_over_rs, impact_param):
    """
    Calcola durata transito totale.
    
    Formula approssimata (circolare, piccolo pianeta):
    T = (P/π) × arcsin(√[(1+k)² - b²] / (a/R★))
    
    dove k = Rp/R★
    
    Args:
        period_days: Periodo orbitale [giorni]
        rp_over_rs: Raggio pianeta / raggio stella
        a_over_rs: Semiasse / raggio stella
        impact_param: Parametro d'impatto b
    
    Returns:
        Durata transito [giorni]
    """
    k = rp_over_rs
    b = impact_param
    
    # Verifica fisica
    if b >= 1 + k:
        # Nessun transito
        return 0.0
    
    # Formula approssimata
    numerator = np.sqrt((1 + k)**2 - b**2)
    duration_frac = np.arcsin(numerator / a_over_rs) / np.pi
    duration_days = period_days * duration_frac
    
    return duration_days


def calc_impact_parameter(inclination_deg, a_over_rs):
    """
    Calcola parametro d'impatto dall'inclinazione.
    
    b = (a/R★) × cos(i)
    
    Args:
        inclination_deg: Inclinazione orbitale [gradi]
        a_over_rs: Semiasse / raggio stella
    
    Returns:
        Parametro d'impatto b (0 = centrale, 1 = rasante)
    """
    inclination_rad = np.radians(inclination_deg)
    b = a_over_rs * np.cos(inclination_rad)
    return b


# =============================================================================
# GENERATORE TRANSITO - MODELLO SEMPLIFICATO
# =============================================================================

def simple_transit_model(time, t0, period, duration, depth):
    """
    Modello transito semplificato (box-shaped).
    
    Per test veloci. Per fisica accurata, usa batman.
    
    Args:
        time: Array tempi [giorni]
        t0: Epoca centro primo transito [giorni]
        period: Periodo orbitale [giorni]
        duration: Durata transito [giorni]
        depth: Profondità transito (ΔF/F)
    
    Returns:
        Flux relativo (1 = nessun transito)
    """
    flux = np.ones_like(time)
    
    # Fase orbitale
    phase = ((time - t0) % period) / period
    
    # Transito quando fase è vicina a 0
    # Convertiamo durata in frazione di periodo
    duration_frac = duration / period
    
    # Maschera punti in transito
    in_transit = (phase < duration_frac / 2) | (phase > 1 - duration_frac / 2)
    
    # Applica profondità
    flux[in_transit] = 1.0 - depth
    
    return flux


# =============================================================================
# GENERATORE PRINCIPALE
# =============================================================================

def generate_exoplanet_lightcurve(
    planet_type="hot_jupiter",
    n_transits=10,
    cadence_minutes=30,
    noise_ppm=1000,
    seed=42,
    custom_params=None
):
    """
    Genera curva di luce sintetica con transiti esopianeti.
    
    Args:
        planet_type: Tipo pianeta predefinito
            "hot_jupiter": Giove caldo, P~3d, Rp~1.2 Rjup
            "neptune": Nettuno caldo, P~5d, Rp~4 Rearth
            "super_earth": Super-Terra, P~10d, Rp~2 Rearth
            "earth": Analogo Terra, P~365d, Rp~1 Rearth
        
        n_transits: Numero transiti da osservare
        cadence_minutes: Cadenza osservativa [minuti]
        noise_ppm: Rumore fotometrico [ppm = parti per milione]
        seed: Seed RNG per riproducibilità
        custom_params: Dict parametri custom (sovrascrive preset)
    
    Returns:
        Dict con:
            "jd": array Julian Dates
            "flux": array flussi relativi (normalizzati a 1)
            "params": dict parametri fisici usati
    """
    
    rng = np.random.default_rng(seed)
    
    # =========================================================================
    # PARAMETRI PIANETA PRESET
    # =========================================================================
    
    presets = {
        "hot_jupiter": {
            "period": 3.5,              # [giorni]
            "rp_rjup": 1.2,             # [R_jup]
            "stellar_mass": 1.0,        # [M☉]
            "stellar_radius": 1.0,      # [R☉]
            "inclination": 89.0,        # [gradi] - quasi edge-on
            "limb_u1": 0.3,             # Limb darkening quadratico
            "limb_u2": 0.2,
        },
        "neptune": {
            "period": 5.0,
            "rp_rearth": 4.0,
            "stellar_mass": 1.0,
            "stellar_radius": 1.0,
            "inclination": 88.5,
            "limb_u1": 0.3,
            "limb_u2": 0.2,
        },
        "super_earth": {
            "period": 10.0,
            "rp_rearth": 2.0,
            "stellar_mass": 1.0,
            "stellar_radius": 1.0,
            "inclination": 89.5,
            "limb_u1": 0.3,
            "limb_u2": 0.2,
        },
        "earth": {
            "period": 365.0,
            "rp_rearth": 1.0,
            "stellar_mass": 1.0,
            "stellar_radius": 1.0,
            "inclination": 89.8,  # Più edge-on per vedere transito
            "limb_u1": 0.3,
            "limb_u2": 0.2,
        }
    }
    
    # Carica preset
    if planet_type not in presets:
        logger.warning(f"Tipo pianeta sconosciuto: {planet_type}, uso hot_jupiter")
        planet_type = "hot_jupiter"
    
    params = presets[planet_type].copy()
    
    # Sovrascrivi con custom params
    if custom_params:
        params.update(custom_params)
    
    # =========================================================================
    # CALCOLO PARAMETRI DERIVATI
    # =========================================================================
    
    period = params["period"]
    stellar_mass = params["stellar_mass"]
    stellar_radius = params["stellar_radius"]
    inclination = params["inclination"]
    
    # Converti raggio pianeta in R☉
    if "rp_rjup" in params:
        rp_rsun = params["rp_rjup"] * (R_JUP / R_SUN)
    elif "rp_rearth" in params:
        rp_rsun = params["rp_rearth"] * (R_EARTH / R_SUN)
    else:
        raise ValueError("Specificare rp_rjup o rp_rearth")
    
    # Rp/R★
    rp_over_rs = rp_rsun / stellar_radius
    
    # Semiasse orbitale
    a_au = calc_semimajor_axis(period, stellar_mass)
    a_meters = a_au * AU
    a_rsun = a_meters / R_SUN
    a_over_rs = a_rsun / stellar_radius
    
    # Parametro d'impatto
    impact_param = calc_impact_parameter(inclination, a_over_rs)
    
    # Durata transito
    duration = calc_transit_duration(period, rp_over_rs, a_over_rs, impact_param)
    
    # Profondità transito
    depth = rp_over_rs**2
    
    logger.info(
        f"Parametri pianeta:\n"
        f"  Tipo: {planet_type}\n"
        f"  Periodo: {period:.2f} giorni\n"
        f"  Rp/R★: {rp_over_rs:.4f}\n"
        f"  a/R★: {a_over_rs:.2f}\n"
        f"  Inclinazione: {inclination:.2f}°\n"
        f"  Parametro impatto: {impact_param:.3f}\n"
        f"  Durata transito: {duration*24:.2f} ore\n"
        f"  Profondità: {depth*100:.3f}% = {depth*1e6:.0f} ppm"
    )
    
    # =========================================================================
    # GENERAZIONE TEMPI OSSERVAZIONE
    # =========================================================================
    
    # Baseline totale per contenere n_transits
    baseline_days = n_transits * period
    
    # Numero punti totali
    cadence_days = cadence_minutes / (24 * 60)
    n_points = int(baseline_days / cadence_days)
    
    logger.info(
        f"Osservazioni:\n"
        f"  Transiti: {n_transits}\n"
        f"  Baseline: {baseline_days:.1f} giorni\n"
        f"  Cadenza: {cadence_minutes} min\n"
        f"  Punti totali: {n_points}"
    )
    
    # Genera tempi uniformi
    t0 = 2460000.0  # Epoca base (JD)
    time = np.linspace(t0, t0 + baseline_days, n_points)
    
    # =========================================================================
    # MODELLO TRANSITO
    # =========================================================================
    
    # Usa modello semplificato
    flux = simple_transit_model(time, t0 + period/2, period, duration, depth)
    
    # =========================================================================
    # AGGIUNGI RUMORE
    # =========================================================================
    
    # Rumore fotometrico Gaussiano
    noise_frac = noise_ppm / 1e6  # ppm → frazione
    noise = rng.normal(0, noise_frac, size=len(flux))
    flux += noise
    
    # =========================================================================
    # AGGIUNGI OUTLIER (opzionale, 0.1%)
    # =========================================================================
    
    outlier_prob = 0.001
    outlier_mask = rng.random(len(flux)) < outlier_prob
    n_outliers = outlier_mask.sum()
    
    if n_outliers > 0:
        # Outlier positivi e negativi
        outlier_values = rng.normal(0, 5 * noise_frac, size=n_outliers)
        flux[outlier_mask] += outlier_values
        logger.info(f"Aggiunti {n_outliers} outlier")
    
    # =========================================================================
    # RETURN
    # =========================================================================
    
    # Salva parametri usati
    params_output = {
        "planet_type": planet_type,
        "period": period,
        "t0": t0 + period/2,
        "duration": duration,
        "depth": depth,
        "rp_over_rs": rp_over_rs,
        "a_over_rs": a_over_rs,
        "inclination": inclination,
        "impact_param": impact_param,
        "stellar_mass": stellar_mass,
        "stellar_radius": stellar_radius,
        "noise_ppm": noise_ppm,
        "n_transits": n_transits,
        "cadence_minutes": cadence_minutes,
    }
    
    return {
        "jd": time,
        "flux": flux,
        "params": params_output
    }


# =============================================================================
# WRAPPER PER COMPATIBILITÀ CON INFRASTRUCTURE ESISTENTE
# =============================================================================

def generate_exoplanet_lightcurve_sessions(
    planet_type="hot_jupiter",
    n_transits=10,
    seed=42
):
    """
    Wrapper per compatibilità con get_lightcurve().
    
    Returns:
        Lista di dict sessioni (formato compatibile con variable_stars)
    """
    data = generate_exoplanet_lightcurve(
        planet_type=planet_type,
        n_transits=n_transits,
        seed=seed
    )
    
    # Converti flux → magnitudini (per compatibilità)
    # mag = -2.5 × log10(flux)
    mag = -2.5 * np.log10(data["flux"])
    
    # Formato sessione singola
    session = {
        "session_id": 0,
        "session_name": f"Exoplanet_{planet_type}",
        "jd": data["jd"],
        "mag": mag,
        "flux": data["flux"],  # Mantieni anche flux
        "params": data["params"]
    }
    
    return [session]


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    """
    Test generatore.
    """
    logging.basicConfig(level=logging.INFO)
    
    print("="*60)
    print("TEST GENERATORE TRANSITI ESOPIANETI")
    print("="*60)
    print()
    
    # Test 1: Hot Jupiter
    print("Test 1: Hot Jupiter")
    print("-"*60)
    data = generate_exoplanet_lightcurve(
        planet_type="hot_jupiter",
        n_transits=5,
        noise_ppm=500
    )
    
    print(f"\nGenerati {len(data['jd'])} punti")
    print(f"Flusso medio: {np.mean(data['flux']):.6f}")
    print(f"Flusso std: {np.std(data['flux'])*1e6:.0f} ppm")
    print(f"Min flux: {np.min(data['flux']):.6f} (profondità transito)")
    print()
    
    # Test 2: Super-Earth
    print("Test 2: Super-Earth")
    print("-"*60)
    data2 = generate_exoplanet_lightcurve(
        planet_type="super_earth",
        n_transits=3,
        noise_ppm=200
    )
    
    print(f"\nGenerati {len(data2['jd'])} punti")
    print(f"Profondità attesa: {data2['params']['depth']*1e6:.0f} ppm")
    print()
    
    print("="*60)
    print("✓ Test completato")
    print("="*60)
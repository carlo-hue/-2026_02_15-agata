"""
service_synthetic.py - Generatore di Curve di Luce Sintetiche

Questo modulo genera curve di luce artificiali per stelle variabili,
utilizzato per testing, demo e validazione algoritmi.

Riferimenti Scientifici:
- Smith, H. A. 1995, "RR Lyrae Stars", Cambridge Astrophysics Series
- Percy, J. R. 2007, "Understanding Variable Stars", Cambridge University Press
- Soszyński et al. 2016, "The OGLE Collection of Variable Stars"
"""

import logging

import numpy as np


# Setup logger
logger = logging.getLogger(__name__)

# ==========================================================
# UTILITIES PER GENERAZIONE RUMORE REALISTICO
# ==========================================================

def red_noise(rng, n, sigma=0.02, tau=50):
    """
    Genera rumore correlato (red noise) usando processo autoregressivo AR(1).
    
    Il rumore fotometrico reale non è puramente bianco (Gaussiano indipendente),
    ma mostra correlazioni temporali dovute a:
    - Variazioni atmosferiche (seeing, trasparenza)
    - Derive strumentali
    - Effetti sistematici di calibrazione
    
    Formula AR(1): r[i] = α * r[i-1] + w[i]
    dove:
    - α = exp(-1/τ) = fattore di correlazione temporale
    - w[i] = rumore bianco Gaussiano
    - τ = scala temporale di correlazione (in unità di campioni)
    
    Args:
        rng: numpy.random.Generator - generatore numeri casuali
        n: int - numero di punti da generare
        sigma: float - deviazione standard del rumore bianco [mag]
        tau: float - scala temporale correlazione [punti]
                     tau grande = correlazione lunga (drift lento)
                     tau piccolo → rumore quasi bianco
    
    Returns:
        numpy.ndarray - serie temporale di rumore correlato
        
    Note:
        Per tau=50 e campionamento ogni ~1h, la correlazione persiste
        per ~2 giorni, tipico per effetti atmosferici stagionali.
    """
    # Genera rumore bianco Gaussiano di base
    white = rng.normal(0, sigma, size=n)
    
    # Array per rumore rosso (correlato)
    red = np.zeros(n)
    
    # Calcola coefficiente autoregressivo
    # α vicino a 1 = correlazione forte
    # α vicino a 0 = decorrelazione rapida
    alpha = np.exp(-1.0 / tau)
    
    # Genera processo AR(1) iterativamente
    # Ogni punto dipende dal precedente più rumore nuovo
    for i in range(1, n):
        red[i] = alpha * red[i-1] + white[i]
    
    return red


def add_outliers(rng, mag, prob=0.003, strength=(0.2, 0.4)):
    """
    Aggiunge outlier casuali per simulare eventi fotometrici reali.
    
    Outlier possono essere causati da:
    - Raggi cosmici sul CCD
    - Satelliti/aerei nel campo
    - Errori di flat-fielding
    - Problemi di centraggio stellare
    - Nuvole sottili transitorie
    
    Args:
        rng: numpy.random.Generator
        mag: numpy.ndarray - magnitudini da contaminare (modificato in-place!)
        prob: float - probabilità outlier per punto (default 0.3% = ~3 ogni 1000)
        strength: tuple(float, float) - range deviazione outlier [mag]
                  (0.2, 0.4) significa outlier tra +0.2 e +0.4 mag
    
    Returns:
        numpy.ndarray - array magnitudini modificato (stesso oggetto di input!)
        
    Note:
        Modifica array in-place per efficienza. Se serve preservare originale,
        passare una copia: add_outliers(rng, mag.copy())
    """
    # Crea maschera booleana: True = punto diventa outlier
    mask = rng.random(mag.size) < prob
    
    # Per i punti marcati come outlier, aggiungi deviazione
    # Strength casuale nell'intervallo + rumore Gaussiano
    mag[mask] += rng.normal(
        rng.uniform(*strength),  # Media casuale in range strength
        0.1,                      # Dispersione Gaussiana aggiuntiva
        size=mask.sum()          # Numero di outlier da generare
    )
    
    return mag


# ==========================================================
# GENERATORE PRINCIPALE
# ==========================================================

def generate_synthetic_lightcurve(
    kind="rrlyrae",
    n_sessions=6,
    seed=1,
    realism=4
):
    """
    Genera curva di luce sintetica per stella variabile.
    
    Simula campagne osservative multi-sessione con caratteristiche realistiche:
    - Periodicità intrinseca (base fisica)
    - Offset zero-point tra sessioni (calibrazione)
    - Rumore fotometrico (atmosfera + detector)
    - Modulazioni fisiche (Blazhko, eclissi parziali)
    - Outlier occasionali (raggi cosmici, etc.)
    
    Args:
        kind: str - tipo stella variabile
            "rrlyrae": RR Lyrae tipo ab (pulsatore radiale)
            "delta_scuti": Delta Scuti (multiperiodica)
            "eclipsing": Binaria eclissante (EA type)
            "cepheid": Cepheide classica
            "irregular": Variabile semi-regolare/irregolare
            
        n_sessions: int - numero sessioni osservative (default 6)
            Simula campagne multi-anno con ~1 sessione/anno
            
        seed: int - seed per riproducibilità (default 1)
        
        realism: int - livello complessità (0=ideale, 5=realistico massimo)
            0 = curva teorica perfetta
            1 = + offset calibrazione per sessione
            2 = + rumore correlato (red noise)
            3 = + jitter in fase (Blazhko-like)
            4 = + modulazioni ampiezza
            5 = + outlier fotometrici
    
    Returns:
        list[dict] - lista di sessioni, ciascuna con:
            {
                "session_id": int,
                "jd": numpy.ndarray (float64) - Julian Date
                "mag": numpy.ndarray (float64) - magnitudini
            }
    
    Note Scientifiche:
        Il realismo aumenta gradualmente per permettere test controllati:
        - realism=0 → test fit periodogramma puro
        - realism=2 → test algoritmi robusti (MAD sigma clip)
        - realism=5 → simula dati survey reali (GAIA, ZTF, ASAS-SN)
    
    Esempio:
        >>> data = generate_synthetic_lightcurve(
        ...     kind="rrlyrae",
        ...     n_sessions=8,
        ...     realism=4,
        ...     seed=42
        ... )
        >>> print(f"Generato {len(data)} sessioni")
        >>> print(f"Punti totali: {sum(len(s['jd']) for s in data)}")
    """
    
    # Inizializza generatore numeri casuali con seed fisso
    # Permette riproducibilità: stesso seed → stessi dati
    rng = np.random.default_rng(seed)
    
    # Container per tutte le sessioni
    sessions = []
    
    # Epoca base (Julian Date)
    # 2460000.0 ≈ 2023-02-25 (epoca moderna per GAIA DR3)
    base_jd = 2460000.0

    # Genera ogni sessione osservativa
    for s in range(n_sessions):

        # ---------------------------
        # CAMPIONAMENTO TEMPORALE REALISTICO
        # ---------------------------
        
        # Numero punti variabile per sessione
        # Range 8000-120000 simula:
        # - Survey shallow: ~8k punti/stella (ASAS-SN)
        # - Survey deep: ~120k punti/stella (GAIA, ZTF)
        n = int(rng.integers(8000, 120000))
        
        # Inizio sessione: sparso nel tempo (simulazione multi-anno)
        # Offset 0-20 giorni simula finestra osservativa preferenziale
        start = base_jd + rng.uniform(0, 20)
        
        # Durata sessione: 0.5-5 giorni
        # 0.5d = singola notte
        # 5d = campagna intensiva
        span = rng.uniform(0.5, 5.0)
        
        # Tempi osservazione: distribuiti casualmente in finestra
        # Sort garantisce ordine cronologico
        t = start + np.sort(rng.uniform(0, span, size=n))

        # ---------------------------
        # REALISM LEVEL 1: OFFSET ZERO-POINT
        # ---------------------------
        # Ogni sessione ha calibrazione fotometrica leggermente diversa
        # Offset tipico: σ=0.05 mag (realistico per fotometria ground-based)
        zp_offset = rng.normal(0, 0.05) if realism >= 1 else 0.0

        # ==================================================
        # MODELLI FISICI STELLE VARIABILI
        # ==================================================
        
        # --------------------------------------------------
        # RR LYRAE TIPO ab
        # --------------------------------------------------
        # Pulsatori radiali vecchi (Pop II), markers distanza
        # Riferimento: Smith 1995, "RR Lyrae Stars"
        if kind == "rrlyrae":
            # Parametri fisici tipici
            P = 0.57      # Periodo [giorni] - range tipico: 0.3-0.8d
            m0 = 13.8     # Magnitudine media (stella a ~8 kpc)
            amp = 0.6     # Ampiezza pulsazione [mag] - range: 0.5-1.5
            
            # Calcola fase: (tempo / periodo) mod 1
            # Fase 0.0 = massimo, 0.5 = minimo
            phase = (t / P) % 1.0

            # ---------------------------
            # REALISM LEVEL 3: JITTER IN FASE (EFFETTO BLAZHKO)
            # ---------------------------
            # Alcune RR Lyrae mostrano modulazione Blazhko:
            # - Variazione periodo con scala ~30-50 giorni
            # - Causa: risonanza modi pulsazione non-radiali
            # Riferimento: Szabó et al. 2010, MNRAS 409, 1244
            if realism >= 3:
                # Modulazione sinusoidale del periodo con P_Blazhko ~ 30*P
                phase += 0.002 * np.sin(2*np.pi*t/(P*30))
                phase %= 1.0  # Riporta in range [0,1]

            # ---------------------------
            # REALISM LEVEL 4: MODULAZIONE AMPIEZZA
            # ---------------------------
            # Blazhko modula anche ampiezza pulsazione
            amp_mod = 1.0
            if realism >= 4:
                # Modulazione ±15% con P_mod ~ 40*P
                amp_mod += 0.15 * np.sin(2*np.pi*t/(P*40))

            # ---------------------------
            # CURVA DI LUCE: SERIE DI FOURIER
            # ---------------------------
            # Formula empirica standard per RRab:
            # m(φ) = m₀ + A × [a₁sin(2πφ) + a₂sin(4πφ)]
            #
            # Coefficienti tipici RRab:
            # - a₁ = 0.7 (componente fondamentale dominante)
            # - a₂ = 0.3 (prima armonica per asimmetria)
            #
            # Questo produce:
            # - Rise veloce (φ=0.9→0.1): ~20% periodo
            # - Decay lento (φ=0.1→0.9): ~80% periodo
            # Caratteristica distintiva RRab!
            mag = m0 + amp * amp_mod * (
                0.7*np.sin(2*np.pi*phase) +      # Componente fondamentale
                0.3*np.sin(4*np.pi*phase)        # Armonica (asimmetria)
            )

        # --------------------------------------------------
        # DELTA SCUTI
        # --------------------------------------------------
        # Pulsatori multiperiodici (Pop I), sequenza principale
        # Tipicamente 2-10 modi simultanei
        # Riferimento: Breger 2000, ASPC 210, 3
        elif kind == "delta_scuti":
            # Periodi principali (ore)
            P1 = 0.08        # Periodo fondamentale [giorni] ~ 1.9h
            P2 = 0.08 * 0.77 # Secondo modo (ratio non risonante)
            m0 = 11.2        # Magnitudine media
            
            # Curva = somma sinusoidi (multiperiodica)
            # Ampiezza decrescente per modi superiori
            mag = (
                m0 +
                0.08 * np.sin(2*np.pi*t/P1) +  # Modo fondamentale
                0.03 * np.sin(2*np.pi*t/P2)    # Primo overtone
            )

            # ---------------------------
            # REALISM LEVEL 4: MODULAZIONE LENTA
            # ---------------------------
            # Alcune Delta Scuti mostrano variazioni decennali
            # (probabilmente precessione rotazionale)
            if realism >= 4:
                mag += 0.02 * np.sin(2*np.pi*t/(P1*15))

        # --------------------------------------------------
        # MULTIPERIODICA (BINARIA + PULSAZIONI)
        # --------------------------------------------------
        # Sistema binario eclissante con componente pulsante
        # Caso tipico: Algol + δ Scuti companion
        # Riferimento: Mkrtichian et al. 2004, A&A 419, 1015
        elif kind == "multiperiod":
            # Usa seed per generare periodi diversi ma riproducibili
            rng_local = np.random.default_rng(seed)

            # Genera 3 periodi ben separati e non armonici
            # P1: periodo corto (tipo RR Lyrae/delta Scuti) - range 0.3-0.8 giorni
            P1 = rng_local.uniform(0.3, 0.8)

            # P2: periodo medio (tipo binaria) - range 1.0-3.0 giorni
            # Assicurati che NON sia multiplo di P1
            P2 = rng_local.uniform(1.0, 3.0)
            while abs(P2 / P1 - round(P2 / P1)) < 0.2:  # Evita ratio interi
                P2 = rng_local.uniform(1.0, 3.0)

            # P3: periodo lungo (tipo Cepheide/modulazione) - range 5-15 giorni
            # Assicurati che NON sia multiplo di P1 o P2
            P3 = rng_local.uniform(5.0, 15.0)
            while (abs(P3 / P1 - round(P3 / P1)) < 0.2 or
                   abs(P3 / P2 - round(P3 / P2)) < 0.2):
                P3 = rng_local.uniform(5.0, 15.0)

            m0 = 12.5        # Magnitudine media

            # Inizializza magnitudine base
            mag = np.full_like(t, m0)

            # ==================================================
            # COMPONENTE 1: PULSAZIONE RAPIDA (P1 ~ 0.3-0.8d)
            # ==================================================
            # Simula RR Lyrae o δ Scuti
            phase1 = (t / P1) % 1.0
            # Ampiezza dominante
            mag += 0.15 * (
                0.7 * np.sin(2*np.pi*phase1) +      # Fondamentale
                0.3 * np.sin(4*np.pi*phase1)        # Armonica
            )

            # ==================================================
            # COMPONENTE 2: PERIODO MEDIO (P2 ~ 1-3d)
            # ==================================================
            # Simula binaria eclissante o variazione ellipsoidale
            phase2 = (t / P2) % 1.0

            # Eclissi/dip caratteristico
            mag += 0.10 * np.exp(-0.5 * ((phase2 - 0.0) / 0.03)**2)  # Eclisse primaria
            mag += 0.05 * np.exp(-0.5 * ((phase2 - 0.5) / 0.04)**2)  # Eclisse secondaria
            mag += 0.03 * np.sin(2*np.pi*phase2)                      # Variazione ellipsoidale

            # ==================================================
            # COMPONENTE 3: MODULAZIONE LENTA (P3 ~ 5-15d)
            # ==================================================
            # Simula Cepheide o modulazione Blazhko
            phase3 = (t / P3) % 1.0
            mag += 0.08 * (
                np.sin(2*np.pi*phase3) +                  # Fondamentale
                0.2 * np.sin(4*np.pi*phase3 + 0.5)       # Armonica con fase
            )

            # ==================================================
            # INTERAZIONI (opzionale per realism >= 4)
            # ==================================================
            if realism >= 4:
                # Battimenti tra P1 e P2 (debole)
                mag += 0.015 * np.sin(2*np.pi*t * abs(1/P1 - 1/P2))

        # --------------------------------------------------
        # BINARIA ECLISSANTE (ALGOL TYPE - EA)
        # --------------------------------------------------
        # Sistema detached: due stelle che si eclissano mutuamente
        # Riferimento: Kallrath & Milone 2009, "Eclipsing Binary Stars"
        elif kind == "eclipsing":
            P = 1.23  # Periodo orbitale [giorni]
            m0 = 12.4 # Magnitudine fuori eclisse
            phase = (t / P) % 1.0
            
            # Inizializza a magnitudine costante
            mag = np.full_like(t, m0)

            # ---------------------------
            # ECLISSE PRIMARIA (fase 0.0)
            # ---------------------------
            # Stella più calda passa davanti a stella più fredda
            # Gaussiana stretta simula:
            # - Durata eclisse ~ 2.5% periodo (tipico sistemi detached)
            # - Profondità 0.9 mag (dipende da ratio raggi e temperature)
            mag += 0.9 * np.exp(-0.5 * ((phase - 0.0) / 0.025)**2)
            
            # ---------------------------
            # ECLISSE SECONDARIA (fase 0.5)
            # ---------------------------
            # Stella più fredda passa davanti a stella più calda
            # Profondità minore (0.5 mag) perché stella eclissata meno luminosa
            mag += 0.5 * np.exp(-0.5 * ((phase - 0.5) / 0.035)**2)

            # ---------------------------
            # REALISM LEVEL 4: ELLIPSOIDAL VARIATION
            # ---------------------------
            # Fuori eclisse, distorsione mareale produce variazione sinusoidale
            # P_ell = P_orb/2 (2 massimi per orbita)
            if realism >= 4:
                mag += 0.05 * np.sin(2*np.pi*phase)

        # --------------------------------------------------
        # CEPHEIDE CLASSICA
        # --------------------------------------------------
        # Supergianti gialle pulsanti (Pop I)
        # Candele standard per scala distanze cosmiche
        # Riferimento: Madore & Freedman 1991, PASP 103, 933
        elif kind == "cepheid":
            P = 5.4   # Periodo [giorni] - range: 1-100d
            m0 = 10.8 # Magnitudine media (stella luminosa)
            amp = 0.8 # Ampiezza [mag]
            
            phase = (t / P) % 1.0
            
            # Serie di Fourier con forte seconda armonica
            # Produce asimmetria caratteristica:
            # - Rise rapido (~30% periodo)
            # - Decay lento (~70% periodo)
            mag = m0 + amp * (
                np.sin(2*np.pi*phase) +               # Fondamentale
                0.3*np.sin(4*np.pi*phase + 0.6)       # Armonica con fase
            )

            # ---------------------------
            # REALISM LEVEL 4: MODULAZIONE HERTZSPRUNG
            # ---------------------------
            # Alcune Cefeidi mostrano modulazioni P~50P_puls
            if realism >= 4:
                mag += 0.1 * np.sin(2*np.pi*t/(P*50))

        # --------------------------------------------------
        # VARIABILE IRREGOLARE / SEMI-REGOLARE
        # --------------------------------------------------
        # Giganti/supergiganti rosse con pulsazioni caotiche
        # Es: Mira variables in fase non-periodica
        elif kind == "irregular":
            P = rng.uniform(1.5, 4.0)  # Periodo "dominante" approssimativo
            m0 = 14.2
            
            # Componente pseudo-periodica debole
            mag = m0 + 0.2 * np.sin(2*np.pi*t/P + rng.uniform(0, 2*np.pi))

            # ---------------------------
            # REALISM LEVEL 4: DOMINATO DA RED NOISE
            # ---------------------------
            # Variabilità caotica dominante
            if realism >= 4:
                mag += red_noise(rng, t.size, sigma=0.05, tau=200)

        else:
            raise ValueError(f"Tipo non supportato: {kind}")

        # ==================================================
        # RUMORI OSSERVATIVI
        # ==================================================
        
        # Applica offset zero-point (calibrazione sessione)
        mag += zp_offset

        # ---------------------------
        # REALISM LEVEL 2: RED NOISE
        # ---------------------------
        # Rumore correlato (atmosfera, strumentazione)
        if realism >= 2:
            mag += red_noise(rng, t.size, sigma=0.02, tau=50)

        # ---------------------------
        # RUMORE BIANCO (SEMPRE PRESENTE)
        # ---------------------------
        # Rumore fotometrico shot noise + detector
        # σ=0.015 mag tipico per:
        # - CCD moderni in banda V
        # - Stelle V~12-14
        # - Seeing 1-2 arcsec
        mag += rng.normal(0, 0.015, size=t.size)

        # ---------------------------
        # REALISM LEVEL 5: OUTLIER
        # ---------------------------
        # Eventi sporadici (raggi cosmici, satelliti, etc.)
        if realism >= 5:
            mag = add_outliers(rng, mag)

        # ---------------------------
        # SALVA SESSIONE
        # ---------------------------
        sessions.append({
            "session_id": int(s),
            "jd": t.astype(np.float64),   # Julian Date
            "mag": mag.astype(np.float64)  # Magnitudini
        })

    return sessions


# ==========================================================
# ESEMPIO USO (test standalone)
# ==========================================================
if __name__ == "__main__":
    """
    Test rapido del generatore.
    
    Uso:
        python service_synthetic.py
        
    Output:
        Stampa numero sessioni e punti totali generati.
    """
    data = generate_synthetic_lightcurve(
        kind="rrlyrae",
        n_sessions=6,
        realism=4,
        seed=42
    )

    print(f"Generato {len(data)} sessioni")
    print(f"Punti totali: {sum(len(s['jd']) for s in data)}")
    print(f"Range JD: {min(s['jd'][0] for s in data):.2f} - {max(s['jd'][-1] for s in data):.2f}")
🚀 WORKFLOW COMPLETO
Step 1-3: Come prima

Genera dati (Hot Jupiter, 10 transiti)
Esegui BLS → Trova periodo
Valida fisica → Parametri pianeta

Step 4: Effemeridi (NUOVO!)

Click "📊 Calcola Effemeridi"

Sistema rileva 10 transiti individuali
Calcola fit lineare: T(E) = T₀ + E × P
Mostra:

T₀ = 2460001.75 ± 0.72 min
P = 3.500000 ± 0.15 sec
RMS O-C = 1.2 min
χ²_red = 0.98


Plot O-C diagram
Tabella con 10 transiti (epoca, T_mid, O-C, SNR)



Step 5: Export (NUOVO!)

Click "📥 Export ExoClock"

Download test_hot_jupiter_exoclock.csv
Formato compatibile ExoClock
Pronto per upload su exoclock.space




📊 FORMATO EXOCLOCK
Il file CSV esportato ha questo formato:
csv# ExoClock Transit Times Export
# Planet: Test Hot Jupiter
# Observer: AGATA
# Filter: Clear
# Ephemeris: T0=2460001.750000, P=3.500000
#
Epoch,BJD_TDB,Error_days,O-C_min,Filter,Observer,Valid
0,2460001.750000,0.000700,0.123,Clear,AGATA,True
1,2460005.250000,0.000700,-0.087,Clear,AGATA,True
2,2460008.750000,0.000700,0.045,Clear,AGATA,True
...
Campi:

Epoch: Numero transito (0, 1, 2, ...)
BJD_TDB: Barycentric Julian Date (tempo centro transito)
Error_days: Errore in giorni
O-C_min: Residuo Observed - Calculated [minuti]
Filter: Banda filtro (Clear, V, R, etc.)
Observer: Nome osservatore/telescopio
Valid: Flag validità transito


🧪 TEST FUNZIONALITÀ
Test Standalone
bashcd /var/www/astrogen/agata/services
python ephemeris_exoplanets.py

# Output atteso:
# TEST MODULO EFFEMERIDI ESOPIANETI
# Test 1: Calcolo Effemeridi
#   Input: T0=2460000.500000, P=3.500000
#   Fit:   T0=2460000.500000 ± 1.00 min
#          P =3.500000 ± 0.10 sec
#   RMS O-C: 1.44 min
# Test 2: Calcolo O-C
#   Epoca 0: O-C = +0.72 ± 1.00 min
#   Epoca 1: O-C = -0.43 ± 1.00 min
#   ...
# ✓ Test completato

📐 FORMULE USATE
Effemeridi Lineari
T(E) = T₀ + E × P

dove:
- T(E) = tempo centro transito all'epoca E
- T₀ = epoca zero (primo transito)
- E = numero epoca (0, 1, 2, ...)
- P = periodo orbitale
Fit Pesato (Weighted Least Squares)
Pesi: w_i = 1 / σ_i²

T₀ = (Σw·x² · Σw·y - Σw·x · Σw·xy) / Δ
P  = (Σw · Σw·xy - Σw·x · Σw·y) / Δ

Δ = Σw · Σw·x² - (Σw·x)²
Errori
σ(T₀) = √(Σw·x² / Δ)
σ(P)  = √(Σw / Δ)
RMS O-C
RMS = √(Σ(O-C)² / N)

dove O-C = T_observed - T_calculated

🎓 RIFERIMENTI SCIENTIFICI

Effemeridi Transiti:

Winn, J. N. 2010, "Transits and Occultations", arXiv:1001.2010


ExoClock Project:

https://www.exoclock.space/
Citizen science per timing transiti esopianeti
Rilevamento variazioni TTV (Transit Timing Variations)


Analisi O-C:

Sterken, C. 2005, "The O-C Diagram: Basic Concepts", ASP Conf. Series
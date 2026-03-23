# 🤖 AI Advisor - Guida Setup

## Panoramica

L'AI Advisor è un sistema di analisi intelligente integrato in AGATA che usa Claude AI (Anthropic) per fornire suggerimenti esperti su:

- 🎯 **Qualità sessioni osservative**: Valutazione automatica della qualità di ogni sessione
- 🔧 **Suggerimenti pre-processing**: Raccomandazioni su zero-align, detrending, sigma-clipping
- 📈 **Range periodigramma ottimale**: Suggerimenti basati sui dati per il calcolo del periodigramma
- ⭐ **Classificazione stelle variabili**: Identificazione del tipo di stella (RR Lyrae, Delta Scuti, etc.)

## Setup

### 1. Installa dipendenze

La dipendenza `anthropic` è già inclusa in `requirements.txt`. Se non è già installata:

```bash
# Attiva virtual environment
source flask/bin/activate

# Installa
pip install anthropic==0.42.0
```

### 2. Configura API Key

Hai bisogno di una chiave API di Anthropic:

1. Vai su https://console.anthropic.com/
2. Crea un account (se non ce l'hai)
3. Genera una API key nella sezione "API Keys"
4. Copia la chiave

### 3. Imposta la variabile d'ambiente

#### Opzione A: File `.env` (raccomandato per sviluppo)

```bash
# Copia il template
cp .env.example .env

# Modifica .env e aggiungi la tua chiave
ANTHROPIC_API_KEY=sk-ant-api03-...
```

Poi assicurati che Flask carichi le variabili d'ambiente (ad esempio con `python-dotenv`).

#### Opzione B: Export diretto (per testing)

```bash
export ANTHROPIC_API_KEY="sk-ant-api03-..."
```

#### Opzione C: Systemd service (per produzione)

Aggiungi al file service:

```ini
[Service]
Environment="ANTHROPIC_API_KEY=sk-ant-api03-..."
```

### 4. Riavvia l'applicazione

```bash
# Se usi systemd
sudo systemctl restart astrogen

# Se run manuale
# Ctrl+C e riavvia flask
```

## Utilizzo

1. Carica una curva di luce (dati reali o sintetici)
2. Vai al tab **"🤖 AI Advisor"**
3. Premi **"✨ Analizza Ora"**
4. Attendi 5-15 secondi per l'analisi
5. Ricevi suggerimenti strutturati!

### Con Periodigramma

Per ottenere anche la classificazione della stella variabile:

1. Calcola prima il periodigramma nel tab "Periodogramma"
2. Vai al tab AI Advisor
3. L'analisi includerà automaticamente la classificazione

## Costi

Claude API ha un costo per token:

- **Claude Sonnet 4.5**: ~$3 per 1M token input, ~$15 per 1M token output
- Una singola analisi costa circa **$0.01-0.02** (molto economico!)
- Budget suggerito: $10/mese copre centinaia di analisi

## Modelli Supportati

Il sistema usa **Claude Sonnet 4.5** (`claude-sonnet-4-20250514`) per:
- Velocità elevata (3-5 secondi)
- Costo contenuto
- Qualità eccellente per analisi scientifica

## Troubleshooting

### Errore: "ANTHROPIC_API_KEY non configurata"

La variabile d'ambiente non è impostata. Verifica:

```bash
echo $ANTHROPIC_API_KEY
```

Se vuoto, segui i passaggi di setup sopra.

### Errore: "Authentication error"

La chiave API non è valida o è scaduta. Verifica su https://console.anthropic.com/

### Errore: "Rate limit exceeded"

Hai superato il limite di richieste. Attendi qualche secondo e riprova.

### Timeout

L'analisi impiega più di 30 secondi (raro). Verifica la connessione internet.

## Architettura

### Backend (`routes.py`)

```python
@variable_stars_bp.post("/api/analyze_with_llm.arrow")
```

- Riceve dati in formato Arrow
- Calcola statistiche robuste per sessione (MAD, gaps, amplitude)
- Costruisce prompt strutturato per Claude
- Chiama API con timeout 30s
- Restituisce JSON con suggerimenti

### Frontend (`ai-advisor.js`)

- Gestisce UI (loading, empty state, results)
- Formatta e visualizza suggerimenti
- Integrazione con altri moduli (periodigramma, etc.)

### Stili (`variable_stars.css`)

Classi custom:
- `.ai-card`: Card per sezioni risultati
- `.ai-suggestion`: Box suggerimento con priorità
- `.ai-score-badge`: Badge punteggio qualità

## Esempi di Output

### Suggerimento Pre-processing

```
🎯 Allineamento Zero-Point [HIGH]
Le sessioni 2 e 3 mostrano offset fotometrici significativi
(0.15 e 0.22 mag rispetto alla mediana globale).
Si raccomanda allineamento zero-point prima dell'analisi periodigramma.

Parametri suggeriti:
- sigma: 3.0
- max_iters: 5
```

### Classificazione Stella

```
⭐ RR Lyrae tipo ab
Confidenza: 85%

Periodo di 0.567d e ampiezza 0.8 mag sono coerenti con RR Lyrae ab.
La forma asimmetrica della curva di fase (salita rapida, discesa lenta)
è caratteristica di questo tipo di variabile pulsante.

Tipi alternativi: RR Lyrae tipo c, Delta Scuti multiperiodica
```

## Estensioni Future

Possibili miglioramenti:

- [ ] Analisi automatica al caricamento dati
- [ ] Suggerimenti interattivi (click per applicare)
- [ ] Export report PDF con analisi AI
- [ ] Cache risultati per evitare rianalisi
- [ ] Supporto per modelli custom/local (Ollama)

## Contatti

Per problemi o suggerimenti sull'AI Advisor, apri una issue su GitHub.

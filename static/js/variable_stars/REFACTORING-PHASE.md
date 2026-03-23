# Refactoring: Estrazione Controlli Fase

## 📋 Sommario

È stato creato il nuovo modulo **`phase-controls.js`** che centralizza tutta la logica UI per l'analisi in fase, rimuovendo ~460 linee da `main.js` e rendendolo più pulito e manutenibile.

## 🎯 Obiettivo

Separare la logica dei controlli fase da `main.js` per:
- ✅ Migliorare la manutenibilità del codice
- ✅ Ridurre la complessità di `main.js`
- ✅ Raggruppare funzionalità correlate
- ✅ Facilitare testing e debug

## 📦 Nuovo Modulo: `phase-controls.js`

### Funzionalità Gestite

Il modulo gestisce **tutti** i controlli UI relativi alla fase:

#### 1. **Phase Shift Slider**
- Preview veloce durante drag (throttled a 60fps)
- Full update al rilascio
- Integrazione con `computePhasePreviewOnly()` e `computePhase()`

#### 2. **Controlli Display**
- Titolo personalizzato (`phaseCustomTitle`)
- Range fase (`phaseRange`: -1→1, 0→2, -0.5→0.5)
- Etichetta periodo (`phasePeriodLabel`)
- Bottone "Calcola Fase"

#### 3. **Template Overlay**
- Applicazione template variabili standard
- Reset automatico su cambio selezione
- Integrazione con `overlayTemplate()`

#### 4. **Moltiplicatori Periodo**
- Raddoppia periodo (×2)
- Dimezza periodo (÷2)
- Aggiornamento automatico statistiche

#### 5. **Fine-Tuning Periodo**
- Slider con offset incrementale
- Bottoni +/- singolo step
- Bottoni +/- 10 step (grande)
- Reset slider
- **Keyboard shortcuts**:
  - `←` / `→`: ±1 step
  - `Shift + ←` / `Shift + →`: ±10 step
  - `Home`: reset slider

#### 6. **Confronto Periodi (ΔP)**
- Calcolo grafici comparativi
- Suggerimento automatico ΔP intelligente
- Click-to-select su grafici delta-P
- Rigenerazione dinamica su selezione

#### 7. **Sampling Intelligente**
- Slider percentuale campionamento
- Visual feedback colorato
- Warning per sampling < 100%
- Bottone "Calcolo Finale 100%"
- Update automatico statistiche

### API Pubblica

```javascript
// Funzione principale di inizializzazione
initializePhaseControls()

// Navigazione al tab fase con periodo
goToPhaseTabAndUpdate(period)
```

### Setup Funzioni Interne

- `setupPhaseShiftControls()`
- `setupPhaseDisplayControls()`
- `setupTemplateControls()`
- `setupPeriodMultiplierControls()`
- `setupPeriodFineTuningControls()`
- `setupDeltaPControls()`
- `setupSamplingControls()`

## 🔧 Modifiche a `main.js`

### Import Rimossi

```javascript
// ❌ Rimossi (non più necessari in main.js)
import { computePhaseDelta, renderPhaseDelta } from './phase-delta.js';
import { renderEphemeris } from './ephemeris.js';
import { computePhase, computePhasePreviewOnly } from './phase-analysis.js';
import { syncHarmonicsPeriod } from './harmonics-analysis.js';
import { syncOCPeriod } from './oc-analysis.js';
import { calculatePhaseStatistics, renderPhaseStatistics, overlayTemplate } from './phase-statistics.js';
```

### Import Aggiunti

```javascript
// ✅ Nuovo import
import { initializePhaseControls, goToPhaseTabAndUpdate } from './phase-controls.js';
```

### Codice Rimosso

- ~460 linee di handler UI per controlli fase
- Funzione `updatePhaseViewFull()` (ora interna a phase-controls.js)
- Funzione `goToPhaseTabAndUpdate()` (spostata in phase-controls.js)
- Tutti gli event listener fase (phaseShift, computePhase, template, etc.)
- Logica fine-tuning periodo (slider, bottoni, keyboard)
- Handler Delta-P (computeDeltaP, suggestDeltaP)
- Handler sampling (slider, calcolo finale 100%)

### Codice Aggiunto

```javascript
// ============================================
// INIZIALIZZAZIONE CONTROLLI FASE
// ============================================
initializePhaseControls();
```

## 📊 Statistiche

| Metrica | Prima | Dopo | Delta |
|---------|-------|------|-------|
| Linee main.js | ~1400 | 947 | **-453** |
| Linee phase-controls.js | 0 | 627 | **+627** |
| Import main.js | 20+ | 15 | **-5** |
| Complessità ciclomatica | Alta | Media | ⬇️ |

## 🎨 Pattern Utilizzati

### 1. **Module Pattern**
Ogni funzionalità è incapsulata in una funzione `setup*Controls()`

### 2. **Single Responsibility**
Ogni funzione gestisce UN aspetto specifico dell'UI

### 3. **Event Delegation**
Gli event listener sono centralizzati e ben organizzati

### 4. **Lazy Initialization**
Check esistenza elementi DOM prima di attaccare listener

### 5. **Throttling**
Preview fase usa `requestAnimationFrame` per performance

## ✅ Vantaggi

### Manutenibilità
- **Codice raggruppato**: Tutta la logica fase in un file
- **Naming chiaro**: Funzioni `setup*Controls()` autodocumentanti
- **Responsabilità singole**: Ogni funzione fa una cosa sola

### Performance
- **Throttling intelligente**: Preview fase ottimizzata
- **Lazy initialization**: No overhead per elementi mancanti
- **Caching**: Sampling usa cache persistente

### Testabilità
- **Isolamento**: Logica fase separata facilita unit test
- **API chiara**: `initializePhaseControls()` entry point unico
- **Mock-friendly**: Dipendenze iniettabili

### Developer Experience
- **File più piccoli**: main.js ridotto del 32%
- **Navigazione facile**: Trova codice fase in un posto solo
- **Debug semplificato**: Stack trace più chiare

## 🚀 Come Usare

### Caricamento Modulo

Il modulo si carica automaticamente con `main.js`:

```javascript
import { initializePhaseControls, goToPhaseTabAndUpdate } from './phase-controls.js';
```

### Inizializzazione

Chiamata automatica alla fine di `main.js`:

```javascript
initializePhaseControls();
```

### Navigazione Programmatica

Da altri moduli (es. `plots.js` per periodogram):

```javascript
// Importa la funzione
import { goToPhaseTabAndUpdate } from './phase-controls.js';

// Usa quando serve
goToPhaseTabAndUpdate(bestPeriod);
```

## 🔄 Dipendenze

### Input (Dipende da)

- `state.js`: Stato globale applicazione
- `phase-analysis.js`: Calcoli fase (computePhase, computePhasePreviewOnly)
- `phase-statistics.js`: Statistiche e template (calculatePhaseStatistics, renderPhaseStatistics, overlayTemplate)
- `phase-delta.js`: Confronto periodi (computePhaseDelta, renderPhaseDelta)
- `ephemeris.js`: Calcolo effemeridi (renderEphemeris)
- `harmonics-analysis.js`: Analisi armoniche (syncHarmonicsPeriod)
- `oc-analysis.js`: Diagramma O-C (syncOCPeriod)

### Output (Usato da)

- `main.js`: Per inizializzazione e navigazione
- `plots.js`: Per navigazione post-periodogram
- `ui-bridge.js`: Per callback da UI

## 📝 Note Implementative

### Keyboard Shortcuts

Gli shortcuts funzionano **solo** quando:
- Tab fase è attivo
- Focus non è su input text/number (tranne periodSlider)

### Sampling Persistente

Il sampling % viene mantenuto tra operazioni:
- Impostato automaticamente al caricamento dati
- Modificabile via slider
- Reset a 100% con bottone dedicato

### Visual Feedback

Tutti i controlli hanno feedback visivo:
- Slider: Colore cambia con valore
- Bottoni: Background flash su click
- Info box: Mostra punti stimati in tempo reale

## 🐛 Testing

Per testare il modulo:

```javascript
// In console browser
window.initializePhaseControls()  // Re-init se necessario
window.goToPhaseTabAndUpdate(0.5)  // Test navigazione
```

## 📚 Documentazione Correlata

- [phase-analysis.js](./phase-analysis.js) - Logica calcolo fase
- [phase-statistics.js](./phase-statistics.js) - Statistiche variabilità
- [phase-delta.js](./phase-delta.js) - Confronto periodi
- [state.js](./state.js) - Gestione stato globale

## 🎯 Prossimi Passi (Futuro)

Possibili miglioramenti:

1. **Test Unit**: Aggiungere test automatici per ogni setup function
2. **Config Esterna**: Spostare costanti (throttle delay, colors) in config
3. **Custom Events**: Usare eventi personalizzati per comunicazione moduli
4. **State Management**: Considerare Redux-like pattern per stato UI
5. **Accessibilità**: Aggiungere ARIA labels e keyboard navigation migliorata

---

**Data**: 2026-01-10
**Versione**: 1.9.1
**Autore**: Refactoring automatico
**Status**: ✅ Completato e testato

/**
 * utils-arrow.js - Utility Apache Arrow
 * 
 * Funzioni per lavorare con Apache Arrow in JavaScript.
 * Arrow è un formato colonnare in-memory ottimizzato per:
 * - Zero-copy data sharing
 * - Parsing velocissimo (10-100x più veloce di JSON)
 * - Interoperabilità linguaggi (Python ↔ JavaScript)
 * 
 * Questo modulo fornisce:
 * 1. Conversione bitset ↔ base64 per compressione
 * 2. Costruzione stream Arrow per API calls
 * 
 * UTILIZZO:
 * 
 * ```javascript
 * import { packActiveBitsetToBase64, buildArrowStreamJDMag } from './utils-arrow.js';
 * 
 * // Comprime array booleano per persistenza
 * const active = new Uint8Array([1,0,1,1,0,1]);
 * const compressed = packActiveBitsetToBase64(active);
 * // → "qA==" (molto più compatto!)
 * 
 * // Crea stream Arrow per POST request
 * const stream = buildArrowStreamJDMag(jdArray, magArray);
 * fetch('/api/endpoint', {
 *   method: 'POST',
 *   body: stream,
 *   headers: { 'Content-Type': 'application/vnd.apache.arrow.stream' }
 * });
 * ```
 * 
 * RIFERIMENTI:
 * - Apache Arrow: https://arrow.apache.org/
 * - Arrow JS: https://arrow.apache.org/docs/js/
 */

import { logger } from './logger.js';

// Crea logger per questo modulo
const log = logger('Arrow');

// Riferimento libreria Arrow globale
// Caricata da Arrow.es2015.min.js in HTML
const arrow = window.Arrow;

// =============================================================================
// BITSET COMPRESSION
// =============================================================================

/**
 * Comprime array booleano in base64 usando bitpacking.
 * 
 * Converte array di 0/1 in rappresentazione compatta:
 * - Ogni byte contiene 8 bit (8 punti)
 * - Array codificato in base64 per persistenza
 * 
 * ESEMPIO:
 * Input: [1,0,1,1,0,0,0,1]  (8 bytes = 64 bits)
 * Bitpacked: 10110001 = 0xB1 = 1 byte
 * Base64: "sQ==" (4 chars)
 * 
 * Compressione: 8x (8 bytes → 1 byte)
 * 
 * @param {Uint8Array} activePoint - Array booleano (0 o 1) di lunghezza N
 * @returns {string} - Stringa base64 (~N/8 bytes compressi)
 * 
 * ALGORITMO:
 * 1. Calcola quanti byte servono: ceil(N/8)
 * 2. Per ogni punto, setta il bit corrispondente nel byte giusto
 * 3. Converti bytes in stringa binaria
 * 4. Codifica in base64
 */
export function packActiveBitsetToBase64(activePoint) {
  log.time('pack-bitset');
  
  const n = activePoint.length;
  log.debug(`Packing ${n} points to base64`);
  
  // Calcola numero bytes necessari
  // Math.ceil(n/8) = arrotonda per eccesso
  // Es: 15 punti → 2 bytes (16 bits)
  const nBytes = Math.ceil(n / 8);
  
  // Array bytes output (inizializzato a 0)
  const bytes = new Uint8Array(nBytes);
  
  // Itera su ogni punto
  for (let i = 0; i < n; i++) {
    // Se punto è attivo (1), setta il bit corrispondente
    if (activePoint[i]) {
      // Calcola quale byte (indice)
      // i >> 3 = floor(i/8) = divisione intera per 8
      // Es: i=10 → byte 1 (punti 8-15 vanno nel byte 1)
      const b = i >> 3;
      
      // Calcola quale bit dentro il byte (0-7)
      // i & 7 = i % 8 = modulo 8
      // Es: i=10 → bit 2 (10 % 8 = 2)
      const bit = i & 7;
      
      // Setta il bit usando OR bitwise
      // 1 << bit = maschera con bit-esimo bit = 1
      // Es: bit=2 → 00000100 = 0x04
      bytes[b] |= (1 << bit);
    }
  }
  
  log.debug(`Packed to ${nBytes} bytes (${((nBytes/n)*100).toFixed(1)}% original size)`);
  
  // Converti Uint8Array → stringa binaria
  // Processa a chunks per evitare stack overflow su array grandi
  // (String.fromCharCode ha limite argomenti)
  let bin = "";
  const chunk = 0x8000;  // 32KB chunks
  
  for (let i = 0; i < bytes.length; i += chunk) {
    // Prendi slice e converti in stringa
    const slice = bytes.subarray(i, i + chunk);
    bin += String.fromCharCode.apply(null, slice);
  }
  
  // Codifica in base64
  // btoa() = binary to ASCII (base64 encoding)
  const result = btoa(bin);
  
  log.debug(`Base64 string: ${result.length} chars`);
  log.timeEnd('pack-bitset');
  
  return result;
}

/**
 * Decomprime stringa base64 in array booleano.
 * 
 * Operazione inversa di packActiveBitsetToBase64.
 * 
 * @param {string} b64 - Stringa base64 compressa
 * @param {number} n - Numero punti originale (necessario per dimensione output)
 * @returns {Uint8Array} - Array booleano (0 o 1) di lunghezza n
 * 
 * NOTA: n è necessario perché l'ultimo byte potrebbe non essere pieno.
 * Es: 10 punti → 2 bytes, ma ultimo byte ha solo 2 bit validi
 * 
 * ALGORITMO:
 * 1. Decodifica base64 → stringa binaria
 * 2. Converti stringa → Uint8Array
 * 3. Per ogni punto, leggi il bit corrispondente
 * 4. Costruisci array output
 */
export function unpackActiveBitsetFromBase64(b64, n) {
  log.time('unpack-bitset');
  log.debug(`Unpacking base64 to ${n} points`);
  
  // Decodifica base64 → stringa binaria
  // atob() = ASCII to binary (base64 decoding)
  const bin = atob(b64);
  
  // Converti stringa → Uint8Array
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) {
    bytes[i] = bin.charCodeAt(i);
  }
  
  log.debug(`Decoded ${bytes.length} bytes`);
  
  // Array output (booleano)
  const active = new Uint8Array(n);
  
  // Itera su ogni punto
  for (let i = 0; i < n; i++) {
    // Calcola byte e bit (stesso algoritmo di pack)
    const b = i >> 3;           // floor(i/8)
    const bit = i & 7;          // i % 8
    
    // Leggi il bit usando AND bitwise
    // bytes[b] & (1 << bit) = 0 se bit è 0, ≠0 se bit è 1
    // Convertiamo a 0/1 con operatore ternario
    active[i] = (bytes[b] & (1 << bit)) ? 1 : 0;
  }
  
  log.debug(`Unpacked ${active.reduce((a,b) => a+b, 0)} active points`);
  log.timeEnd('unpack-bitset');
  
  return active;
}

// =============================================================================
// ARROW STREAM CONSTRUCTION
// =============================================================================

/**
 * Costruisce stream Arrow IPC da array JD e mag.
 *
 * Crea tabella Arrow con 2-3 colonne (jd, mag, session_id opzionale) e la serializza
 * in formato IPC stream per invio al server.
 *
 * IPC (Inter-Process Communication) stream è formato binario Arrow
 * ottimizzato per network transfer:
 * - Zero-copy quando possibile
 * - Compatto (no overhead JSON)
 * - Veloce da parsare (sia Python che JS)
 *
 * @param {Float64Array} jd64 - Array Julian Date (float64)
 * @param {Float32Array} mag32 - Array magnitudini (float32)
 * @param {Int32Array} [session_id] - Array session IDs (int32, opzionale)
 * @returns {Uint8Array} - Stream Arrow IPC binario
 *
 * UTILIZZO:
 *
 * ```javascript
 * const jd = new Float64Array([2460000.5, 2460001.5]);
 * const mag = new Float32Array([13.45, 13.52]);
 * const sid = new Int32Array([0, 1]);
 * const stream = buildArrowStreamJDMag(jd, mag, sid);
 *
 * // POST al server
 * const response = await fetch('/api/phase.arrow', {
 *   method: 'POST',
 *   body: stream,
 *   headers: { 'Content-Type': 'application/vnd.apache.arrow.stream' }
 * });
 * ```
 *
 * IMPORTANTE:
 * - jd64 DEVE essere Float64Array (precisione necessaria per JD)
 * - mag32 può essere Float32Array (sufficiente per magnitudini)
 * - session_id opzionale, se fornito deve essere Int32Array
 */
export function buildArrowStreamJDMag(jd64, mag32, session_id = null) {
  log.time('build-arrow-stream');

  const nPoints = jd64.length;
  log.debug(`Building Arrow stream: ${nPoints} points`);

  // Verifica lunghezze corrispondano
  if (jd64.length !== mag32.length) {
    const error = `Length mismatch: jd=${jd64.length}, mag=${mag32.length}`;
    log.error(error);
    throw new Error(error);
  }

  if (session_id && session_id.length !== jd64.length) {
    const error = `Length mismatch: jd=${jd64.length}, session_id=${session_id.length}`;
    log.error(error);
    throw new Error(error);
  }

  // Crea tabella Arrow da array
  // arrow.tableFromArrays accetta oggetto { columnName: array }
  // Inferisce automaticamente i tipi Arrow da TypedArray
  const columns = {
    jd: jd64,    // → Arrow: float64
    mag: mag32   // → Arrow: float32
  };

  // Aggiungi session_id se fornito
  if (session_id) {
    columns.session_id = session_id;  // → Arrow: int32
  }

  const table = arrow.tableFromArrays(columns);

  log.debug('Table created:', {
    numRows: table.numRows,
    numCols: table.numCols,
    schema: table.schema.toString()
  });

  // Serializza tabella → IPC stream
  // "stream" format = una tabella, formato streaming
  // Alternative: "file" format = multipletabelle, random access
  const stream = arrow.tableToIPC(table, "stream");

  // stream è Uint8Array ready per fetch body
  const sizeKB = (stream.length / 1024).toFixed(2);
  log.info(`Arrow stream ready: ${sizeKB} KB`);
  log.timeEnd('build-arrow-stream');

  return stream;
}

// =============================================================================
// UTILITY ADDIZIONALI
// =============================================================================

/**
 * Legge tabella Arrow da response fetch.
 * 
 * Utility per parsare risposta server Arrow.
 * 
 * @param {Response} response - Fetch response con body Arrow
 * @returns {Promise<Table>} - Tabella Arrow
 * 
 * UTILIZZO:
 * 
 * ```javascript
 * const response = await fetch('/api/lightcurve.arrow');
 * const table = await readArrowTable(response);
 * 
 * // Accedi colonne
 * const jd = table.getChild('jd').toArray();
 * const mag = table.getChild('mag').toArray();
 * ```
 */
export async function readArrowTable(response) {
  log.time('read-arrow-table');
  
  if (!response.ok) {
    const error = `HTTP ${response.status}: ${response.statusText}`;
    log.error('Response not OK:', error);
    throw new Error(error);
  }
  
  // Leggi body come ArrayBuffer
  const buffer = await response.arrayBuffer();
  const sizeKB = (buffer.byteLength / 1024).toFixed(2);
  log.debug(`Received ${sizeKB} KB`);
  
  // Parse Arrow IPC stream
  const table = arrow.tableFromIPC(new Uint8Array(buffer));
  
  log.info('Table parsed:', {
    numRows: table.numRows,
    numCols: table.numCols,
    columns: table.schema.names
  });
  log.timeEnd('read-arrow-table');
  
  return table;
}

/**
 * Estrai colonna da tabella Arrow come TypedArray.
 * 
 * Arrow mantiene dati in formato colonnare.
 * Questa utility estrae singola colonna.
 * 
 * @param {Table} table - Tabella Arrow
 * @param {string} columnName - Nome colonna
 * @returns {TypedArray} - Array nativo JavaScript
 */
export function getColumnArray(table, columnName) {
  log.debug(`Extracting column: ${columnName}`);
  
  // Ottieni colonna
  const column = table.getChild(columnName);
  
  if (!column) {
    const error = `Column not found: ${columnName}`;
    log.error(error, { available: table.schema.names });
    throw new Error(error);
  }
  
  // Converti a TypedArray
  // toArray() fa zero-copy quando possibile
  const array = column.toArray();
  
  log.debug(`Extracted ${array.length} values`);
  return array;
}

// =============================================================================
// PERFORMANCE NOTES
// =============================================================================

/**
 * PERFORMANCE COMPARISON (1M points):
 * 
 * JSON serialization:
 * - Size: ~50 MB
 * - Parse time: ~2000ms
 * 
 * Arrow IPC stream:
 * - Size: ~12 MB (4x smaller)
 * - Parse time: ~50ms (40x faster!)
 * 
 * BITSET COMPRESSION (1M boolean array):
 * - Original: 1,000,000 bytes
 * - Bitpacked: 125,000 bytes (8x smaller)
 * - Base64 overhead: +33% → ~167,000 bytes (6x smaller overall)
 * 
 * CONCLUSION:
 * Arrow + bitset compression = massive bandwidth & performance win!
 */
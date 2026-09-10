# SPECIFICA TECNICA DI SISTEMA: chunk-compress

**Architettura Software, Contratti di Interfaccia, Modello di I/O e Pipeline di Esecuzione**  
*Progetto: Compressore locale reversible text/code LLM-ready ottimizzato per file di grandi dimensioni*

---

### Componenti del progetto:

1. **`core.py`**: Motore algoritmico con P0 (roundtrip esatto `recon == target`, chunking atomico), P1 (espansione sincronizzata, filtro per singola occorrenza), P2 (memoizzazione O(1) offset, indice compatto a 64 bit) e P3 (metriche reali di risparmio netto e token).
2. **`cli.py`**: Orchestratore CLI con `--keep-empty-lines`, gestione errori atomica ed exit codes dedicati (`0`, `1`, `2`).
3. **`io_utils.py`**: I/O atomico memory-bounded su file grandi (streaming senza duplicazioni heap, buffer SHA256 a 64 KB).
4. **`test_suite.py`**: Suite di test unitari automatizzati.
5. **`test.sh`**: Test di integrazione end-to-end e infrastruttura di smoke test per chunk-compress.
6. **`SPEC.md`**: Specifica Tecnica di Sistema: Riferimento architetturale completo per sviluppatori ed auditor.
7. **`README.md`**: Guida operativa e documentazione utente.
8. **`PROMPT MASTER`**: Guida ai prompt per LLM con verifica di integrità a due stadi.

---

## 1. Visione d'Insieme e Separazione delle Responsabilità

Il sistema è strutturato su tre livelli modulari disaccoppiati:

```text
+-----------------------------------------------------------------------+
|                               cli.py                                  |
|   Orchestrazione pipeline, contratti CLI, gestione ciclo di vita      |
|   degli errori, exit codes (0, 1, 2) e reportistica token LLM         |
+-----------------------------------+-----------------------------------+
                                    |
                                    v
+-----------------------------------------------------------------------+
|                               core.py                                 |
|   Motore algoritmico in memoria (UTF-8 str): rolling hash 61-bit,     |
|   memoizzazione O(1) blocchi, selezione greedy boundary-safe (P1.5),  |
|   chunking atomico protetto (P0.2), verifica roundtrip esatta (P0.1)  |
+-----------------------------------+-----------------------------------+
                                    |
                                    v
+-----------------------------------------------------------------------+
|                              io_utils.py                              |
|   Persistenza atomica transazionale (mkstemp + os.replace),           |
|   streaming memory-bounded su file grandi, hashing SHA-256 a 64 KB    |
+-----------------------------------------------------------------------+
```

---

## 2. Modulo `io_utils.py`: Persistenza Atomica e Gestione I/O

Il modulo incapsula tutte le interazioni con il sistema operativo e il file system, garantendo la coerenza dei dati e l'assenza di duplicazioni in memoria heap durante l'elaborazione di file di grandi dimensioni.

### 2.1 Contratti delle Funzioni

#### `ensure_dir(path: PathLike) -> None`
* **Comportamento**: Crea ricorsivamente la directory genitore o di destinazione se non esiste (`mkdir(parents=True, exist_ok=True)`). Operazione idempotente.

#### `read_text(path: PathLike, encoding: str = "utf-8", errors: str = "strict") -> str`
* **Comportamento**: Apre e decodifica il file come testo in modalità standard `r`.

#### `read_bytes(path: PathLike) -> bytes`
* **Comportamento**: Restituisce il contenuto binario grezzo del file.

#### `write_atomic(path: PathLike, data: Union[str, bytes], encoding: str = "utf-8") -> None`
* **Architettura di Atomicità**:
  1. Identifica la directory genitore `p.parent` e genera un file temporaneo univoco tramite `tempfile.mkstemp(prefix=p.name + ".", dir=str(p.parent))`. La creazione nella stessa cartella garantisce che il file temporaneo e il file di destinazione risiedano sullo **stesso filesystem/punto di montaggio**, prerequisito per l'atomicità POSIX di `os.replace`.
  2. **Memory-Bounding per File Grandi**:
     * Se `data` è `str`: apre il descrittore in modalità testo `with os.fdopen(fd, "w", encoding=encoding, errors="strict")` e scrive in streaming. **Non effettua `data.encode(...)` preventivo**, evitando di duplicare centinaia di megabyte come oggetto `bytes` in memoria heap.
     * Se `data` è `bytes`: apre in modalità binaria `with os.fdopen(fd, "wb")`.
  3. **Flush su Disco**: Esegue `f.flush()` e tenta `os.fsync(f.fileno())` (ignorando eventuali eccezioni su filesystem privi di supporto fsync, come tmpfs in memoria).
  4. **Sostituzione Atomica**: Esegue `os.replace(tmp_path, str(p))`. Se il processo fallisce prima della sostituzione, il blocco `finally` rimuove il file temporaneo residuo.

#### `sha256_file(path: PathLike, buffer_size: int = 65536) -> str`
* **Comportamento**: Calcola l'hash SHA256 leggendo a blocchi di **64 KB** (`65536` byte), riducendo di un fattore 8 le chiamate di sistema rispetto a buffer convenzionali da 8 KB.

#### `sha256_text(s: str, encoding: str = "utf-8") -> str`
* **Comportamento**: Calcola l'hash SHA256 della stringa decodificata in UTF-8.

#### `write_json_atomic(path: PathLike, obj: Any, **json_kwargs: Any) -> None`
* **Comportamento**: Serializza `obj` in formato JSON (default: `indent=2`, `ensure_ascii=False`) e delega la persistenza atomica a `write_atomic`.

---

## 3. Modulo `core.py`: Motore Algoritmico e Regole di Trasformazione

Il modulo opera interamente sul testo in formato stringa UTF-8 (`str`), assumendo coordinate a caratteri semichiuse `[start, end)`.

### 3.1 Scansione e Caricamento

* **`scan_files(input_path: str, exclude_pointless: bool = True) -> List[Dict[str, Any]]`**:
  * Scansiona file singoli, directory ricorsive o liste testuali.
  * Esclude file nascosti (`.name.startswith(".")`).
  * Se `exclude_pointless=True`, scarta per default 36 estensioni binarie/non testuali (`.png`, `.jpg`, `.pdf`, `.zip`, `.exe`, `.so`, `.db`, `.pyc`, ecc.).
  * Restituisce record `FileMeta`: `{"path": str (risolto assoluto), "size": int (byte), "sha256": str (hex)}`.
  * Se nessun file valido è reperibile, solleva `RuntimeError("No valid files found in input")`.
* **`load_contents(file_metas: List[Dict[str, Any]]) -> Dict[str, str]`**:
  * Carica i file in un dizionario in-memory `Dict[path_assoluto, testo_utf8]`.

### 3.2 Preprocessing: Compressione Righe Vuote (P0.3)

* **`strip_empty_lines_by_extension(contents: Dict[str, str], preserve_exts: Optional[Set[str]] = None) -> Dict[str, str]`**:
  * Whitelist predefinita: `{".md", ".txt", ".rst", ".html", ".tex", ".adoc", ".org"}`.
  * Per tutti i formati non in whitelist (codice sorgente `.py`, `.c`, `.java`, dati `.json`, ecc.), scarta ogni riga in cui `line.strip() == ""`.
  * Preserva invariata l'indentazione e il contenuto di tutte le righe non vuote.

### 3.3 Ricerca Ripetizioni (P1.4, P2.6, P2.7)

* **`_find_substring_candidates(...)`**:
  * **Rolling Hash Rabin-Karp**: Opera su finestre di lunghezza fissa `L_min` con aritmetica a 61 bit (`base = 257`, `mod = 2**61 - 1`).
  * **Indice Compatto a 64 Bit (P2.7)**: L'indice mappa `hash -> List[int]`. Ciascuna occorrenza è codificata come intero scalare:
    `packed = (file_id << 32) | offset`
    dove `file_id < 2**32` e `offset < 2**32`. Riduce di oltre il 60% il consumo di RAM eliminando tuple e puntatori a stringa.
  * **Anti-Collisione Preliminare (P1.4)**: Per ciascun bucket con cardinalità `>= N_min`, le occorrenze vengono raggruppate per stringa esatta della finestra iniziale:
    `contents[path][start : start + L_min]`
    garantendo che solo finestre con testo identico al 100% vengano espanse.
  * **Invariante di Espansione Sincronizzata (P1.4)**:
    Dato il seed a coordinate `(seed_path, seed_start)` ed ogni occorrenza `(path, start)`:
    * Sinistra: `t[start - 1 - k] == seed_text[seed_start - 1 - k]` per `k >= 0`.
    * Destra: `t[start + L_min + m] == seed_text[seed_start + L_min + m]` per `m >= 0`.
    L'estensione viene vincolata alla minima comune denominatrice:
    `common_left = min(k_left_i)`
    `common_right = min(k_right_i)`
    con limite `L_min + common_left + common_right <= L_max`.
    Ogni occorrenza registrata ha lunghezza e contenuto identici a `seed_text[content_start:content_end]`.

* **`_find_block_candidates(...)`**:
  * **Memoizzazione O(1) degli Offset (P2.6)**: Esegue `splitlines(keepends=True)` una sola volta per file e genera l'array cumulativo:
    `file_offsets[file_id] = [0, len(l0), len(l0)+len(l1), ...]`
  * Analizza finestre fisse di righe `{B_min_lines, (B_min_lines + B_max_lines) // 2, B_max_lines}`.
  * Ricava `start = file_offsets[file_id][li]` ed `end = file_offsets[file_id][li + size]` in tempo costante **O(1)**.
  * Memorizza nell'indice solo tuple leggere `(file_id, li, size)` senza duplicare le stringhe dei blocchi.

### 3.4 Selezione Sostituzioni con Filtro Singola Occorrenza (P1.5)

* **`select_replacements(...)`**:
  * **Formula di Valutazione**:
    `saving_per_occ = max(0, len(content) - ph_len)`
    `total_saving = saving_per_occ * (len(occs) - 1)`
  * **Tie-Breaker Deterministico**: Ordina decrescente per `(-total_saving, -len(content), id_hash)`.
  * **Filtro Greedy a Singola Occorrenza**:
    Se un'occorrenza di un candidato si sovrappone a un intervallo già approvato, **viene scartata solo quella singola occorrenza**, mantenendo tutte le altre valide.
  * **Ricalcolo Dinamico**:
    `recomputed_saving = saving_per_occ * (len(valid_occs) - 1)`
    Il candidato è ammesso solo se `len(valid_occs) >= 2` e `recomputed_saving >= min_total_saving`.
  * **Ricerca Binaria O(log K)**: La verifica di overlap `_has_interval_overlap` usa `bisect.bisect_right` con chiave `x[1]` (coordinate di fine intervallo) su liste ordinate, garantendo tempi logaritmici anche su decine di migliaia di sostituzioni.

### 3.5 Applicazione Placeholder e Reverse Map

* **`apply_placeholders(...)`**:
  * Ordina per ciascun file le sostituzioni per indice `start` crescente.
  * Ricostruisce il testo compresso concatenando le porzioni originali invariate e i token (`§§s001§§`, `§§b001§§`).
  * Popola `reverse_map["placeholders"][token]`. Calcola SHA256 e metadati **una sola volta per token univoco** tramite guardia `if token not in reverse_map["placeholders"]:`.

### 3.6 Verifica di Integrità: Exact Roundtrip (P0.1)

* **`roundtrip_check(target_contents: Dict[str, str], llm_ready: Dict[str, str], reverse_map: Dict[str, Any]) -> Tuple[bool, List[str]]`**:
  * **Verifica Matematica di Reversibilità**:
    Per ogni file compresso, riapplica la sostituzione inversa ordinando i token per lunghezza decrescente (`_reconstruct_using_tokens`).
  * **Criteri di Conformità**:
    1. Nessun token residuo non risolto nel testo ricostruito.
    2. Nessun token usato nei file ma assente nella mappa.
    3. **Uguaglianza esatta carattere per carattere**:
       `recon == target_contents[path]`
  * **Diagnostica di Errore**: In caso di mancata uguaglianza, calcola l'indice esatto `mismatch_idx` del primo carattere difforme ed estrae le porzioni di contesto circostante (`Expected` vs `Recon`) delimitate con `repr()` per visualizzare caratteri invisibili o spazi difformi.

### 3.7 Chunking Atomico Boundary-Aware (P0.2)

* **`chunk_outputs(...)`**:
  * **Mappa degli Intervalli Protetti**: Traccia tutti gli intervalli `[ph_start, ph_end)` occupati dai placeholder nel testo compresso.
  * **Vincolo Atomico**: Se il limite `curr + chunk_size` cade internamente a un placeholder (`ph_start < target_cut < ph_end`), il punto di taglio indietreggia forzatamente a `cut = ph_start`.
  * **Backtracking su Newline**: Cerca a ritroso l'ultimo delimitatore `\n` in `(curr, cut]`. Se presente (e non interno a un token), sposta il taglio a `cut = nl_pos + 1`.
  * **Prevenzione Stallo**: Se un singolo blocco indivisibile o una riga eccede `chunk_size`, forza l'avanzamento minimo senza entrare in loop infinito.
  * **Albero Directory**: I chunk vengono scritti in `OUT_DIR/chunks/<rel_path>/0001.txt`, `0002.txt`.

### 3.8 Metriche di Risparmio Reale e Stima Token LLM (P3.8)

* **`estimate_savings(...)`**:
  * Formule esatte:
    * `gross_saved_chars = orig_total - new_total`
    * `gross_saved_pct = (gross_saved_chars / orig_total) * 100.0`
    * `net_saved_chars = orig_total - (new_total + mapping_size)`
    * `net_saved_pct = (net_saved_chars / orig_total) * 100.0`
    * `orig_tokens_est = int(round(orig_total / chars_per_token))`
    * `new_tokens_est = int(round(new_total / chars_per_token))`
    * `mapping_tokens_est = int(round(mapping_size / chars_per_token))`
    * `net_saved_tokens = orig_tokens_est - (new_tokens_est + mapping_tokens_est)`
  * Il parametro `chars_per_token` ha valore predefinito pari a `4.0` (standard de-facto empirico per codice e testo).

---

## 4. Modulo `cli.py`: Flusso di Esecuzione, Contratti e Ciclo di Vita

Il file `cli.py` funge da punto d'ingresso principale e controlla le transizioni di stato della pipeline.

### 4.1 Tabella Parametri CLI

| Flag | Tipo | Default | Descrizione Tecnica |
| :--- | :--- | :--- | :--- |
| `--input, -i` | String | *Obbligatorio* | Percorso directory radice o file-lista contenente i target. |
| `--output, -o` | String | `compressed_output` | Percorso directory di destinazione dell'output. |
| `--L_min` | Integer | `64` | Lunghezza minima della finestra di rolling hash substring. |
| `--N_min` | Integer | `2` | Frequenza minima di occorrenza per i candidati substring. |
| `--B_min_lines`| Integer | `5` | Numero minimo di righe per candidati blocco. |
| `--B_max_lines`| Integer | `20` | Numero massimo di righe per candidati blocco. |
| `--min_total_saving` | Integer | `100` | Soglia minima di caratteri risparmiati per ammettere un placeholder. |
| `--placeholder-sub` | String | `§§s{:03d}§§` | Maschera di formattazione per placeholder substring. |
| `--placeholder-blk` | String | `§§b{:03d}§§` | Maschera di formattazione per placeholder blocco. |
| `--keep-empty-lines` | Flag | `False` | Preserva le righe vuote in tutti i file (disattiva il preprocessing lossy P0.3). |
| `--verify-roundtrip` | Flag | `False` | Attiva la verifica esatta di uguaglianza stringa post-compressione (P0.1). |
| `--no-export-mapping` | String opz. | `None` | Gestisce l'esportazione di `mapping_subset.json` (vedi sez. 4.2). |
| `--export-manifest` | Flag | `False` | Genera `manifest.json` compatto della struttura file e placeholder. |
| `--chunk-output` | Flag | `False` | Attiva la generazione dei chunk boundary-aware in `OUT_DIR/chunks/`. |
| `--chunk-size` | Integer | `16000` | Dimensione nominale massima di ciascun chunk in caratteri. |
| `--include-pointless`| Flag | `False` | Disabilita il filtro di scansione sulle estensioni binarie. |

### 4.2 Regola di Esclusione `--no-export-mapping`

La gestione del flag segue una logica a tre stati:
1. **Flag assente (`None`)**: Include tutti i file processati in `mapping_subset.json`.
2. **Flag presente senza valore (`""`)**: Disabilita totalmente l'esportazione (nessun `mapping_subset.json` scritto).
3. **Flag presente con valore stringa (es. `"f1.py,dir/f2.py"`)**: Parsa una lista separata da virgole di percorsi relativi da escludere, esportando il mapping per tutti i file rimanenti.

### 4.3 Macchina a Stati della Pipeline CLI

```text
[1. Scan Files] ---> [2. Load Contents] ---> [2b. Strip Empty Lines (Default)]
                                                             |
+------------------------------------------------------------+
|
v
[3. Find Repetitions] ---> [4. Select Replacements] ---> [5. Apply Placeholders]
                                                                   |
+------------------------------------------------------------------+
|
v
[6. Atomic Write Outputs] ---> Scrittura file compressi e reverse_map.json
[6b. Export Mapping Subset] -> Scrittura mapping_subset.json
[6c. Export Manifest] -------> Scrittura manifest.json (opzionale)
[6d. Chunk Outputs] ---------> Scrittura chunks/ e chunks/manifest.json (opzionale)
                                 |
+--------------------------------+
|
v
[7. Verify Roundtrip (Opzionale)]
   |---> OK: continua
   |---> FAIL: scrive roundtrip_failures.json ed esce con EXIT CODE 2
|
v
[8. Report Savings] ---------> Calcolo metriche reali e stampa a terminale
|
v
EXIT CODE 0
```

### 4.4 Codici di Uscita (Exit Codes)

* **`0` (SUCCESS)**: Esecuzione completata correttamente. Tutti gli output richiesti sono stati scritti e l'eventuale verifica di roundtrip è passata al 100%.
* **`1` (FATAL / I/O ERROR)**: 
  * Percorso di input non esistente.
  * Nessun file valido rilevato dallo scanner.
  * Eccezione non gestita o fallimento di scrittura atomica in `_write_outputs`.
* **`2` (ROUNDTRIP INTEGRITY FAILURE)**:
  * Il controllo `--verify-roundtrip` ha rilevato una discrepanza tra il testo ricostruito e il target pre-compressione.
  * Salva il report analitico in `OUT_DIR/roundtrip_failures.json` prima di terminare.

---

## 5. Schemi Formali degli Output JSON

### 5.1 `reverse_map.json` (Registro di Ripristino Completo)
Percorso: `OUT_DIR/reverse_map.json`
```json
{
  "placeholders": {
    "§§s001§§": {
      "type": "substring",
      "content": "def calculate_loss(y_true, y_pred):\n    return np.mean((y_true - y_pred) ** 2)\n",
      "sha256": "8f3b...12c4",
      "length": 75,
      "occurrences": [
        {"path": "/abs/project/models/dense.py", "start": 340, "end": 415},
        {"path": "/abs/project/models/conv.py", "start": 890, "end": 965}
      ],
      "token": "§§s001§§",
      "id": "S:001"
    }
  },
  "metadata": {
    "tool": "chunk_compress"
  }
}
```

### 5.2 `mapping_subset.json` (Payload di Contesto per LLM)
Percorso: `OUT_DIR/mapping_subset.json`
```json
{
  "§§s001§§": {
    "content": "def calculate_loss(y_true, y_pred):\n    return np.mean((y_true - y_pred) ** 2)\n",
    "sha256": "8f3b...12c4",
    "length": 75
  }
}
```

### 5.3 `manifest.json` (Struttura di Progetto)
Percorso: `OUT_DIR/manifest.json`
```json
{
  "paths": [
    "models/dense.py",
    "models/conv.py"
  ],
  "files": [
    {"i": 0, "sha": "3a7b...4c2d", "ph": ["§§s001§§"]},
    {"i": 1, "sha": "5e8d...9f1a", "ph": ["§§s001§§"]}
  ],
  "ph": {
    "§§s001§§": {"sha": "8f3b...12c4", "len": 75}
  },
  "v": 1
}
```

### 5.4 `chunks/manifest.json` (Manifest Riassemblaggio Chunk)
Percorso: `OUT_DIR/chunks/manifest.json`
```json
{
  "files": {
    "models/dense.py": {
      "chunks": [
        "models/dense.py/0001.txt",
        "models/dense.py/0002.txt"
      ],
      "sha256_full": "c71a...44e2",
      "chunk_size": 16000,
      "total_len": 24500
    }
  },
  "chunks_dir": "chunks",
  "v": 1
}
```
*Nota*: `sha256_full` certifica l'integrità del testo compresso dopo la concatenazione sequenziale dei chunk, prima che il modello o l'interprete esegua la sostituzione inversa dei placeholder.

---

## 6. Invarianti Formali di Sistema

1. **Invariante di Disgiunzione degli Intervalli (Non-Overlap)**:
   Dati due intervalli di sostituzione $I_1 = [s_1, e_1)$ e $I_2 = [s_2, e_2)$ appartenenti allo stesso percorso di file:
   `e_1 <= s_2` oppure `e_2 <= s_1`
2. **Invariante di Uguaglianza Sostitutiva**:
   Data una sostituzione $r$ ed ogni sua occorrenza registrata $o = (path, s, e)$:
   `target_contents[path][s : e] == r.content`
3. **Invariante di Atomicità del Taglio (Boundary Safety)**:
   Dato un punto di taglio chunk $C_{cut}$ e un token protetto $P = [ph_{start}, ph_{end})$:
   Non può esistere alcuna suddivisione tale per cui:
   `ph_{start} < C_{cut} < ph_{end}`
4. **Invariante di Reversibilità Perfetta**:
   Sia $T$ il testo target derivato (con o senza rimozione righe vuote). Applicando la trasformazione $\text{apply}$ e successivamente la ricostruzione inversa $\text{reconstruct}$ con `reverse_map`:
   `reconstruct(apply(T)) == T`
   garantito per qualsiasi combinazione valida di parametri CLI.


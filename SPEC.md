# SPECIFICA TECNICA DI SISTEMA: chompress 

***version 1.0.0***  

**Architettura Software, Contratti di Interfaccia, Modello di Token Economics P0-P4 e Pipeline di Esecuzione**  
*Progetto: Local LLM-ready Context Compressor (Token-First Architecture)*  
*Autore: Cristian Evangelisti*  
*Licenza: GNU General Public License v3.0 (GPL-3.0-or-later)*  
*Codice sorgente: https://github.com/kamaludu/chompress*  

```text
chompress/             # Project Structure
├── LICENSE            # GNU General Public License v3.0
├── PROMPT.md          # AI Prompt Master
├── README.md          # User Guide & Documentation
├── SPEC.md            # System Technical Specification
├── benchmark.py       # P0 & Alphabet Optimizer Evaluation Harness
├── chompress.py       # Token-Aware CLI Orchestrator
├── core.py            # Token-Aware Core Pipeline
├── io_utils.py        # Atomic I/O utilities
├── mapping.py         # Protocol Header Multi-Range Support
├── minifiers.py       # Semantic Canonicalization & Aggressive Compactor
├── placeholders.py    # Alphabet Optimizer & Multi-Range Generator
├── test.sh            # End-to-end integration and smoke-test harness
├── test_suite.py      # Comprehensive Test Suite for chompress
└── tokenizer.py       # Tokenizer Heuristic Calibration & BPE Alignment
```

---

## 1. Visione d'Insieme e Gerarchia degli Obiettivi

`chompress` è un motore deterministico di compressione e canonicalizzazione del contesto progettato per massimizzare la capienza utile e l'efficienza di ragionamento dei Large Language Models (LLM).

### 1.1 Gerarchia dei Vincoli di Progetto
1. **Zero Dipendenze Esterne**: Il motore, l'interfaccia CLI e la suite di test operano al 100% mediante la sola Standard Library di Python, senza dipendenze terze (`pip`).
2. **Isolamento e Confinamento Locale (No System `/tmp/`)**: Divieto tassativo di utilizzare la directory `/tmp/` globale del sistema operativo. Qualsiasi operazione temporanea (scrittura atomica, chunking, esecuzione test) avviene esclusivamente all'interno di percorsi relativi locali dedicati nella cartella di lavoro del progetto.
3. **Sicurezza e Integrità di Esecuzione (No `eval` / `exec`)**: Divieto tassativo di usare `eval` negli script Bash e di invocare funzioni di esecuzione dinamica di codice in Python (`eval()`, `exec()`, `os.system()`, chiamate `subprocess` con shell). Tutte le analisi e verifiche sul codice avvengono in modo statico (AST o `compile(..., "exec")` a sola validazione sintattica).
4. **Massimo risparmio netto di token (Metrica Sovrana)**: L'architettura ottimizza l'occupazione nello spazio dei token del modello di destinazione (BPE cl100k_base, o200k_base, tokenizzatori LLaMA 3/Qwen), non la mera dimensione in byte o caratteri su disco.
5. **Minima perdita informativa sostanziale**: Le trasformazioni preservano l'intero grafo causale, la logica di esecuzione e le relazioni semantiche del codice e dei dati.
6. **Assenza del vincolo di leggibilità umana**: La leggibilità umana non costituisce un requisito. Sono ammesse e incentivate minificazioni lossy e compattazioni sintetiche, purché il modello linguistico sia in grado di comprendere, elaborare e ricostruire fedelmente il contesto.
7. **Architettura Single-File First**: Il sistema opera in modo diretto, atomico e privo di sovrastrutture di directory quando riceve singoli script, documenti o flussi pipe Unix (`stdin` / `stdout`), scalando in modo trasparente su repository multi-file tramite dizionari ammortizzati a livello globale.

### 1.2 Mappa dei Componenti di Sistema (8 Moduli)

```text
+---------------------------------------------------------------------------------+
|                                  chompress.py                                   |
|  Orchestrazione CLI, profili (aggressive/semantic/lossless), routing streaming  |
|  (stdout vs stderr), gestione envelope P4.3, exit codes dedicati (0, 1, 2)      |
+--------+------------------+-------------------+-------------------+-------------+
         |                  |                   |                   |
         v                  v                   v                   v
+----------------+  +---------------+  +-----------------+  +---------------------+
|  minifiers.py  |  |  mapping.py   |  | placeholders.py |  |    tokenizer.py     |
| Pipeline AST   |  | Serializzatori|  | Alphabet        |  | Backend Tiktoken /  |
| P1, P3, P4     |  | Positional,   |  | Optimizer, BPE  |  | HuggingFace /       |
| (Licenze, Log, |  | Delimited, KV,|  | Tier 1 (CJK) e  |  | Heuristic Regex     |
| Argparse, Ren) |  | JSON          |  | Tier 2 (Prefix) |  | BPE a 0 dipendenze  |
+--------+-------+  +-------+-------+  +--------+--------+  +----------+----------+
         |                  |                   |                      |
         +------------------+---------+---------+----------------------+
                                      |
                                      v
+---------------------------------------------------------------------------------+
|                                    core.py                                      |
|  Rabin-Karp 64-bit substring rolling hash, Sliding Block Discovery 60-bit O(1), |
|  selezione greedy boundary-safe O(log K), applicazione token, verifica esatta   |
|  roundtrip (P0.1) e chunking atomico boundary-aware (P0.2)                      |
+-------------------------------------+-------------------------------------------+
                                      |
                                      v
+---------------------------------------------------------------------------------+
|                                  io_utils.py                                    |
|  Persistenza atomica transazionale (mkstemp + os.replace), streaming su heap    |
|  senza duplicazione (os.fdopen), hashing SHA-256 bufferizzato a 64 KB           |
+-------------------------------------+-------------------------------------------+
                                      |
       +------------------------------+------------------------------+
       v                                                             v
+-----------------------------+              +------------------------------------+
|        benchmark.py         |              |           test_suite.py            |
| Suite di ablazione P0-P2    |              | 30 test unitari automatizzati      |
| scoring token cl100k/o200k  |              | validazione di integrità P0,P1,P2, |
| su corpus reali             |              | P3, P4 e regressione               |
+-----------------------------+              +------------------------------------+
```

---

## 2. Modello Matematico dei Token (Notazione ASCII Pura)

L'intero sistema valuta le trasformazioni e le sostituzioni confrontando i token effettivi misurati o stimati. Nessuna formula adotta notazioni LaTeX o simboli non presenti sulla tastiera ASCII standard.

### 2.1 Bilancio Sovrano di Risparmio di Contesto
Dati il testo originale T_orig e il payload compresso T_comp:

```text
tokens_payload = count_tokens(T_comp)
tokens_mapping = count_tokens(mapping_payload)
tokens_protocol = count_tokens(protocol_header) + count_tokens(envelope_text)

net_tokens_saved = tokens(T_orig) - (tokens_payload + tokens_mapping + tokens_protocol)
net_compression_ratio = ((net_tokens_saved) * 100.0) / (tokens(T_orig))
```

Se `net_tokens_saved <= 0`, la sostituzione o la voce viene rigettata per evitare token penalty nel context window dell'LLM.

### 2.2 Equazioni di Risparmio Specifiche per Canonicalizzazione (Stage 1)

```text
tokens_license_saved = sum(i=1 to n_files, tokens(license_header_i) - tokens(lic_marker))
tokens_err_saved = sum(j=1 to m_exceptions, tokens(verbose_str_j) - tokens(short_id_j))
tokens_import_saved = sum(k=1 to p_imports, tokens(unused_import_k))
tokens_assert_saved = sum(q=1 to r_asserts, tokens(assert_stmt_q))
tokens_cli_saved = sum(u=1 to v_cli, tokens(narrative_kwarg_u))
tokens_rename_saved = sum(m=1 to s_locals, freq_m * (tokens(orig_name_m) - 1))
tokens_priv_saved = sum(p=1 to t_privates, freq_p * (tokens(orig_priv_p) - tokens(new_priv_p)))
```

### 2.3 Guadagno Marginale per Singolo Candidato di Deduplicazione (Stage 2)
Dato un pattern candidato con N occorrenze nel corpus, contenuto C, placeholder assegnato P, costo marginale di rappresentazione nel dizionario M_cost e delta di overhead del protocollo D_proto:

```text
candidate_net_gain = N * (tokens(C) - tokens(P)) - M_cost - D_proto
```

Nelle architetture con dizionario globale ammortizzato (P1.3):
- M_cost viene addebitato una sola volta per l'intero repository, ammortizzandosi su tutte le N occorrenze complessive distribuite tra i vari file.
- Nel formato `PositionalMappingSerializer`, tokens(P) == 0 all'interno del mapping poiché le chiavi sono omesse e dedotte per indice ordinale.

### 2.4 Modello di Allineamento Euristico del Tokenizzatore
Dati n campioni di calibrazione tra tokenizzatore euristico a zero dipendenze e tokenizzatore reale di riferimento:

```text
error_pct_i = ((abs(tokens_heuristic_i - tokens_real_i)) * 100.0) / (tokens_real_i)
mean_error_pct = (sum(i=1 to n, error_pct_i)) / (n)

diff_i = tokens_heuristic_i - tokens_real_i
bar_D = (sum(i=1 to n, diff_i)) / (float(n))
variance_D = (sum(i=1 to n, (diff_i - bar_D) * (diff_i - bar_D))) / (float(n - 1))
s_D = sqrt(variance_D)
margin_95 = (1.96 * s_D) / (sqrt(float(n)))
CI_95%(bar_D) = [bar_D - margin_95, bar_D + margin_95]
```

---

## 3. Specifiche di Modulo e Contratti di Interfaccia

### 3.1 `minifiers.py`: Pipeline di Canonicalizzazione e Compattazione (P1, P3, P4)

Il modulo implementa trasformazioni del codice a livello AST (Abstract Syntax Tree) e pattern matching per eliminare testo superfluo prima dell'indicizzazione delle ripetizioni.

#### Contratti Principali
- **`strip_license_header(code: str, ext: str) -> str` (P3.1)**:
  - Scansiona le prime 40 righe di codice sorgente (.py, .sh, .js, .ts, .c, .cpp, .go, .rs).
  - Preserva intatto lo shebang iniziale (`#!/...`) se presente alla riga 0.
  - Rimuove blocchi C-style (`/* ... */`) o sequenze di commenti mono-riga (`#`, `//`) contenenti match case-insensitive con l'espressione:
    `LICENSE_KEYWORDS_RE = re.compile(r"(?:copyright\s+(?:\(c\)|©|\d{4})|license|spdx-license-identifier|all rights reserved)", re.IGNORECASE)`
  - Se non viene rilevato alcun pattern di licenza, restituisce il codice originale invariato.

- **`minify_bash(code: str, remove_comments: bool = True, remove_ansi: bool = True) -> str` (P1.1)**:
  - Preserva tassativamente lo shebang alla prima riga.
  - Rimuove sequenze di escape ANSI tramite:
    `ANSI_ESCAPE_RE = re.compile(r"(?:\x1b|\033|\\e|\\033|\\x1b)\[[0-9;]*[a-zA-Z]")`
  - Rimuove commenti a riga intera (`stripped.startswith("#")`), lasciando inalterati i commenti inline e le stringhe virgolettate per non alterare l'espansione shell.
  - Collassa sequenze di righe vuote multiple in una singola riga vuota.

- **`minify_markdown(doc: str, compact_tables: bool = True, remove_badges: bool = True) -> str` (P1.2)**:
  - Riconosce i code fence Markdown (` ``` `) e ne sospende qualsiasi manipolazione interna per non corrompere blocchi di codice incapsulati.
  - Elimina link e immagini di badge grafici (shields.io, badgen.net, codecov, workflow GitHub Actions) sia in formato Markdown che HTML.
  - Compatta le tabelle Markdown eliminando gli spazi di allineamento visivo interni alle celle (`| col1 | col2 |` anziché `|   col1        |   col2   |`), preservando i delimitatori di allineamento (`:---:`).

- **`minify_python(...) -> str` (P1.1, P3.2, P4.1, P4.2, Vettori A e B)**:
  - Riceve il codice Python e ne genera l'AST (`ast.parse(code)`). In caso di errore sintattico di parsing, restituisce il codice originale intatto.
  - **`_DocstringStripper`**: Rimuove module, class e function docstrings. Sostituisce il corpo con `pass` qualora la docstring fosse l'unica istruzione del blocco.
  - **`_TypeAnnotationStripper`**: Rimuove le type annotations PEP 484/526 dagli argomenti delle funzioni, dal tipo di ritorno e trasforma `AnnAssign` (`x: int = 5`) in assegnazioni standard (`x = 5`), cancellando le annotazioni prive di valore (`x: int`).
  - **`_ErrorAndLogStringCompactor` (P3.2)**: Trasforma messaggi di eccezione verbose (`raise ValueError("very long explanatory string...")`) in token compatti (`raise ValueError("ERR")`) e compila le chiamate di log verbose (`logger.info("...")`) in `logger.info("LOG")` se il testo supera gli 8 caratteri.
  - **`_AssertPruner` (P4.2)**: Rimuove totalmente i nodi `ast.Assert` in modalità aggressiva.
  - **`_ArgparseNarrativeStripper` (Vettore A)**: Strippa con whitelist rigorosa i soli argomenti narrativi di documentazione CLI (`help`, `description`, `epilog`) da `ArgumentParser`, `add_argument`, `add_parser` e `add_argument_group`. Preserva tassativamente tutti i parametri funzionali di configurazione (`type`, `default`, `choices`, `action`, `required`, `formatter_class`, `parents`, `conflict_handler`, `add_help`, `allow_abbrev`, ecc.).
  - **`_UsedNamesCollector` & `_UnusedImportPruner` (P4.1)**:
    - Raccoglie tutti i nomi con contesto `Load` nell'AST (compresi decoratori, classi base e tuple `__all__`).
    - Pota da `ast.Import` e `ast.ImportFrom` gli alias e i moduli non referenziati nel codice a runtime.
    - Preserva tassativamente gli import `__future__` e i wildcard import (`*`).
    - Rimuove integralmente le classi del modulo `typing` (`List`, `Dict`, `Optional`, `Union`) non più referenziate dopo lo stripping delle annotazioni di tipo.
  - **`_ModuleScopeAnalyzer` & `_ModulePrivateRenamer` (Vettore B)**:
    - Rinomina simboli privati top-level (`_foo` -> `_a`, `_b`...).
    - Guardrail anti-riflessione: bails out se il modulo include chiamate o accessi a `eval`, `exec`, `locals`, `globals`, `getattr`, `setattr`, `hasattr`, `vars`, `dir`, `__dict__`.
    - Esclude tassativamente nomi dunder (`__init__`), nomi esportati in `__all__`, import e simboli con ombreggiamento interno.
    - Condizione di efficienza: ridenomina solo se `tok.count(old_name) > tok.count(new_name)`.
  - **`_LocalScopeAnalyzer` & `_LocalRenamer`**:
    - Rinomina variabili locali su funzioni esenti da riflessione.
    - Assegna identificatori BPE a 1 token (`a`, `b`, `c`... Tier 1, `aa`, `ab`... Tier 2).
    - **Filtro preventivo di efficienza**: esclude tassativamente le variabili che occupano già 1 solo token (`tok.count(name) <= 1`), azzerando l'inflazione sintattica e preservando simboli brevi naturali.
    - Ordina i candidati per guadagno decrescente: `freq * (tok.count(name) - 1)`.
    - Isola le funzioni nidificate proteggendo le closure.
  - **`_EmptyBodyFixer`**: Visita tutti i blocchi sintattici (`body`, `orelse`, `finalbody`) e inietta `pass` se lo svuotamento da asserzioni o import ha reso vuoto il blocco.
  - Rigenera il sorgente con `ast.unparse(tree)` e valida l'integrità sintattica del codice risultante tramite `compile(code, "<minified>", "exec")`.

- **`minify_json(code: str) -> str` & `minify_yaml(code: str) -> str` (P3.4)**:
  - JSON: deserializzazione e ricompattazione priva di spazi (`separators=(",", ":")`).
  - YAML: eliminazione commenti mono-riga (`#`) e collasso righe vuote nel rispetto dell'indentazione.

---

### 3.2 `placeholders.py`: Alphabet Optimizer & Protocol Metadata (P2.3)

Gestisce la generazione e calibrazione dinamica dell'alfabeto dei token di sostituzione, garantendo l'assenza di collisioni e il minor costo in token BPE.

#### Stili di Placeholder Disponibili
1. **`single_token` (Tier 1 Default)**: Caratteri ideografici CJK Unificati (range `\u4e00-\u9fff`, base `0x4E00` = `一`). Ciascun carattere occupa **esattamente 1 token** nei modelli BPE cl100k, o200k e LLaMA. Dimensione pool: 2.500 simboli.
2. **`prefix_compact` (Tier 2 Spillover)**: Prefisso asimmetrico seguito da intero (`^1`, `^2` o `~1`, `~2`). Occupa **esattamente 2 token**.
3. **`guillemet`**: Virgolette caporali francesi (`«1»`, `«2»`). Occupa 3 token.
4. **`classic`**: Delimitatori baseline legacy a 4 token (`__s1__`, `__b1__`).
5. **`section` (`§1§`)**, **`bracket` (`⟦1⟧`)**, **`ascii_compact` (`~1~`)**: Formati ausiliari a 3 token.

#### Algoritmo di Allocazione e Spillover
1. **Calibrazione Automatica (`auto_calibrate`)**: Ispeziona il corpus di input `raw_corpus`. Se almeno 90 dei primi 100 caratteri CJK di Tier 1 sono totalmente assenti dal testo originale, elegge `single_token`. Altrimenti seleziona lo stile a minor costo medio tra `prefix_compact` e `guillemet`.
2. **Costruzione dell'Alfabeto (`build_alphabet`)**:
   - Esclude ogni singolo carattere presente nel corpus.
   - Alloca per primi i simboli CJK atomici a 1 token (Tier 1).
   - Se il fabbisogno di sostituzioni eccede la capienza di Tier 1, attiva lo spillover ibrido in Tier 2 (`^1`, `^2`, ...).
   - Raggruppa i codepoint in intervalli contigui:
     `ranges = [(start_1, end_1), (start_2, end_2), ...]`
3. **Finalizzazione (`finalize_used_alphabet`)**: Al termine della fase greedy, riduce l'alfabeto attivo strettamente ai token effettivamente impiegati nei file compressi e genera il descrittore di protocollo `get_protocol_meta()`.

---

### 3.3 `mapping.py`: Serializzatori di Mappatura e Protocollo (P2.3)

Serializza il dizionario delle sostituzioni per la trasmissione all'LLM.

#### 1. `PositionalMappingSerializer` (Default Zero-Key Mapping)
- **Principio**: Nel corpo del payload memorizza **esclusivamente i contenuti originali** separati da un delimitatore compatto a 1 token (sentinel predefinita `'§'`), omettendo totalmente le chiavi placeholder nel corpo.
- **Header di Protocollo a Bassissimo Overhead (~8 - ~28 token)**:
  - **CJK Contiguo**:  
    `[MAP:INDEXED sentinel='§' cjk_start=19968 count=N]`
  - **CJK Multi-Range (P2.3)**:  
    `[MAP:INDEXED sentinel='§' cjk_ranges='19968-20050,20060-20500' count=N]`
  - **Ibrido CJK + Prefix (P2.3)**:  
    `[MAP:INDEXED sentinel='§' cjk_ranges='...' prefix='^' p_start=1 p_count=M]`
  - **Sequenza Prefisso**:  
    `[MAP:INDEXED sentinel='§' prefix='^' start=1 count=N]`
  - **Sequenza Template**:  
    `[MAP:INDEXED sentinel='§' seq='«{:d}»' start=1 count=N]`
- **Ordinamento di Serializzazione**: Definito da `positional_sort_key`:
  - Tier 0: Caratteri CJK (ordinati per codepoint).
  - Tier 1: Prefissi numerici (`^1`, `^2`, ordinati per valore intero).
  - Tier 2: Simboli singoli generali.
  - Tier 3: Stringhe e template complessi in ordinamento naturale numerico.
- **Invariante di Ricostruzione**:  
  `deserialize(serialize(M, ph_meta)) == M` per qualsiasi dizionario M.

#### 2. `DelimitedMappingSerializer`
Memorizza blocchi `TOKEN\nCONTENUTO` separati da sentinel dinamica priva di collisioni. Preserva ritorni a capo e virgolette grezze senza l'overhead di escaping JSON.

#### 3. `KVMappingSerializer`
Memorizza `TOKEN=CONTENUTO` riga per riga, compattando i ritorni a capo interni con il marcatore `␤`.

#### 4. `JSONMappingSerializer`
Serializzazione standard `json.dumps(mapping, ensure_ascii=False, separators=(",", ":"))`. Utilizzato come riferimento baseline di confronto nei benchmark.

---

### 3.4 `core.py`: Motore Algoritmico e Pipeline di Deduplicazione

#### 3.4.1 Rilevamento Ripetizioni Multi-Granularità
1. **Identificatori e Parole (`_find_word_candidates`)**: Regex `\b[A-Za-z_][A-Za-z0-9_]{3,}\b`. Rileva parole con lunghezza `>= 4` e frequenza `>= 3`, escludendo a monte i candidati che non generano un guadagno netto rispetto al placeholder.
2. **Rabin-Karp Substring Rolling Hash (`_find_substring_candidates`)**:
   - Finestra di scansione `L_min` caratteri.
   - Parametri rolling hash: `base = 257`, `mod = 2**61 - 1`.
   - Indice compatto a 64 bit:
     `packed_coordinate = (file_id << 32) | start_offset`
   - Bucket raggruppati per stringa esatta della finestra iniziale.
   - **Espansione Sincronizzata Birezionale**: Calcola `common_left` e `common_right` estendendo contemporaneamente tutte le occorrenze rispetto alla stringa seed finché tutti i caratteri coincidono, entro il tetto `L_max`.
3. **Dynamic Sliding Block Discovery (`_find_block_candidates` - P2.2)**:
   - Scansiona finestre parametriche di righe intere da `B_max_lines` a `B_min_lines`.
   - Pre-computa gli offset di riga cumulativi `file_offsets[file_id]` per ricavare coordinate in tempo **O(1)**.
   - State machine rolling hash su righe con base a 60 bit:
     `base = 1000003`, `mod = 2**61 - 1`
   - Calcolo rolling window per riga in tempo O(1):
     `h = ((h - hash_prev * power) * base + hash_next) % mod`
   - Verifica stringa esatta del blocco prima di confermare il candidato.
 
#### 3.4.2 Selezione Greedy con Risoluzione Overlap O(log K) (`select_replacements`)
- I candidati vengono pre-valutati:
  `tok_gain = N * (tok_content - tok_ph) - tok_map`
  dove `tok_map` è conteggiato una sola volta a livello di repository.
- Ordinamento deterministico: per `tok_gain` decrescente, poi per frequenza N decrescente, poi per lunghezza contenuto decrescente, infine per hash SHA-256.
- Controllo collisioni: durante l'allocazione, se un placeholder è già presente nel testo originale, l'Alphabet Optimizer avanza al simbolo successivo.
- Risoluzione sovrapposizioni (`_has_interval_overlap`):
  Utilizza `bisect.bisect_right` con chiave di ricerca sulla coordinata di fine intervallo `end` su liste mantenute ordinate tramite `bisect.insort`. Complessità temporale: **O(log K)** per verifica, con K intervalli occupati nel file.
- Se un'occorrenza si sovrappone a un blocco prioritario precedentemente assegnato, **viene scartata solo la singola occorrenza sovrapposta**. Il pattern viene mantenuto se il numero residuo di occorrenze valide `N_valid >= 2` continua a generare un guadagno netto positivo superiore a `min_total_saving`.

#### 3.4.3 Applicazione Placeholder e Protezione dei Confini (`apply_placeholders`)
- Sostituisce le occorrenze valide nel testo da sinistra verso destra.
- **Digit Boundary Guard**: Per i prefissi asimmetrici che terminano con cifra (es. `^1`, `^2`), impedisce la sostituzione se il carattere successivo nel testo originale è una cifra numerica (`text[e].isdigit()`), evitando la fusione ambigua del token (es. `^1` seguito da `5` che verrebbe letto come `^15`).
- Genera il dizionario strutturato `reverse_map`.

#### 3.4.4 Verifica Roundtrip Reversibile Esatta (`roundtrip_check` - P0.1)
- Verifica che per ogni file valga rigorosamente:
  `reconstruct(llm_ready[path]) == target_contents[path]`
- I token vengono ordinati per lunghezza decrescente (`tokens_sorted = sorted(keys, key=len, reverse=True)`).
- Applica una regex a lookahead negativo `(?!\d)` per i prefissi aperti a cifra, garantendo che prefissi più brevi non consumino parzialmente prefissi più lunghi.
- Se viene rilevata anche una sola discordanza di un carattere, calcola l'offset `mismatch_idx`, genera il dump del contesto atteso rispetto al ricostruito, crea `roundtrip_failures.json` e forza l'interruzione con codice di uscita `2`.

#### 3.4.5 Chunking Atomico Boundary-Aware (`chunk_outputs` - P0.2)
- Se `--chunk-output` è attivo, suddivide i file compressi in frammenti con dimensione nominale massima `--chunk-size` (default 16.000 caratteri).
- **Protezione Boundary-Aware**: Mappa tutti i token di placeholder presenti nel testo. Se il target cut cade all'interno di un token (`s_start < target_cut < s_end`), arretra istantaneamente l'indice di taglio a `s_start`.
- **Backtracking su Newline**: All'interno dello span consentito, arretra all'ultimo ritorno a capo `\n` che non intersechi un token protetto.
- Scrive i chunk in `chunks/<rel_path>/0001.txt`, `0002.txt` e genera `chunks/manifest.json`.

---

### 3.5 `tokenizer.py`: Backend di Tokenizzazione e Calibrazione BPE

#### Backend Supportati
1. **`TiktokenBackend`**: Supporto diretto a `cl100k_base` (GPT-4), `o200k_base` (GPT-4o), `p50k_base`.
2. **`HuggingFaceBackend`**: Supporto per tokenizzatori LLaMA 3, Qwen, Mistral tramite pacchetto `transformers`.
3. **`HeuristicBackend` (Zero Dipendenze)**:
   Implementa un pattern regex che riproduce con fedeltà `>= 95%` le regole di pre-tokenizzazione BPE standard:
   - Contrazioni inglesi (`'s`, `'t`, `'re`, `'ve`, `'m`, `'ll`, `'d`).
   - Caratteri CJK Unificati atomici: `[\u4e00-\u9fff]` contati rigorosamente come **1 token ciascuno**.
   - Ritorni a capo con indentazione associata: `\r?\n[ \t]*`.
   - Parole alfabetiche con eventuale spazio iniziale (CamelCase, lowercase runs fino a 12 caratteri contate come 1 token).
   - Raggruppamenti numerici fino a 3 cifre: ` ?[0-9]{1,3}`.
   - Run di spazi fino a 4: `[ ]{1,4}`.
   - Token alfanumerici lunghi o hash spezzati su blocchi di 4 caratteri.

---

### 3.6 `chompress.py`: Orchestratore e Contratti di Esecuzione

#### 3.6.1 Modalità Operative Primarie (`--mode`)
- **`--mode aggressive` (Default)**:
  Attiva l'intero spettro di canonicalizzatori e compattatori:
  - Rimozione licenze (P3.1)
  - Compattazione errori e log (P3.2)
  - Stripping descrizioni narrative CLI Argparse (Vettore A)
  - Ridenominazione simboli privati top-level (Vettore B)
  - Ridenominazione identificatori locali a 1 token BPE (`a`, `b`, `c`...)
  - Pruning import inutilizzati e typing (P4.1)
  - Pruning asserzioni (P4.2)
  - Stripping commenti, docstring e tipi PEP 484/526
  - Minificazione Bash, Markdown, JSON e YAML
  - Normalizzazione indentazione (4 spazi -> tab)
  - Eliminazione righe vuote nel codice
  - Inoltro del tokenizer attivo `tok` alla pipeline di canonicalizzazione AST
  - Preset tuning consolidato: `aggressive` (`L_min=7`, `min_total_saving=3`, `B_min_lines=2`, `B_max_lines=6`)
- **`--mode semantic`**:
  Preserva la semantica funzionale runtime:
  - Attiva stripping commenti, docstring, annotazioni di tipo, tabelle, badge e potatura import inutilizzati.
  - **Disattiva** la compattazione stringhe di errore, il pruning delle asserzioni diagnostiche e lo stripping CLI.
  - Preset tuning: `code-max` (`L_min=14`, `min_total_saving=2`).
- **`--mode lossless`**:
  Decompressione identica al byte su tutti i file:
  - Disattiva tutti i minificatori e le trasformazioni AST.
  - Preserva ogni singolo spazio e riga vuota (`keep_empty_lines = True`).
  - Esegue esclusivamente deduplicazione reversibile con mapping posizionale o specificato.

#### 3.6.2 Streaming e LLM Prompt Envelope (P3.3, P4.3)
- **`-i -`**: Lettura del codice sorgente da standard input pipe Unix.
- **`--stdout`**: Emissione dell'output compresso direttamente su `sys.stdout`. I messaggi diagnostici, log e report sui token vengono automaticamente reindirizzati su `sys.stderr`.
- **`--envelope, -e`**: Incapsula lo stream di output all'interno di un envelope ottimizzato per LLM:
  ```text
  <context>
  [LLM-READY COMPRESSED CONTEXT - chompress v3.5.0]
  [INSTRUCTION: Expand placeholders using mapping dictionary before execution or analysis.]
  (protocol header)
  (mapping payload)
  (file compresso o stream multi-file)
  </context>
  ```

#### 3.6.3 Codici di Uscita (Exit Codes)
- **`0`**: Esecuzione completata con successo. Output scritti e roundtrip verificato.
- **`1`**: Errore fatale di input/output (file non trovato, permessi negati, eccezione irreversibile).
- **`2`**: Violazione di integrità roundtrip (`roundtrip_check` fallito).

---

## 4. Schemi Formali di Persistenza e Output

### 4.1 `mapping_subset.txt` & `protocol_header.txt` (Default Positional)
- **`protocol_header.txt`**:
  ```text
  [MAP:INDEXED sentinel='§' cjk_start=19968 count=3]
  ```
- **`mapping_subset.txt`**:
  ```text
  def calculate_hash(data):
  return hashlib.sha256(data).hexdigest()
  §validate_session(token)§https://api.internal/v1/stream
  ```

### 4.2 `reverse_map.json` (Registro di Ripristino Globale)
```json
{
  "placeholders": {
    "一": {
      "type": "block",
      "content": "def calculate_hash(data):\n    return hashlib.sha256(data).hexdigest()\n",
      "sha256": "8f3b...12c4",
      "length": 75,
      "occurrences": [
        {"path": "/abs/project/src/auth.py", "start": 340, "end": 415},
        {"path": "/abs/project/src/api.py", "start": 890, "end": 965}
      ],
      "token": "一",
      "id": "B:1"
    }
  },
  "ph_meta": {
    "type": "cjk_contiguous",
    "start_cp": 19968,
    "start_char": "一",
    "count": 1
  },
  "metadata": {
    "tool": "chompress",
    "version": "3.5.0"
  }
}
```

### 4.3 `manifest.json` (Indice Strutturale del Repository)
```json
{
  "paths": [
    "src/auth.py",
    "src/api.py"
  ],
  "files": [
    {"i": 0, "sha": "3a7b...4c2d", "ph": ["一"]},
    {"i": 1, "sha": "5e8d...9f1a", "ph": ["一"]}
  ],
  "ph": {
    "一": {"sha": "8f3b...12c4", "len": 75}
  },
  "v": 1
}
```

### 4.4 `chunks/manifest.json` (Manifest Riassemblaggio Chunk)
```json
{
  "files": {
    "src/auth.py": {
      "chunks": [
        "src/auth.py/0001.txt",
        "src/auth.py/0002.txt"
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

---

## 5. Invarianti Formali di Sistema

1. **Invariante di Disgiunzione degli Intervalli (Non-Overlap)**:  
   Per qualsiasi coppia di sostituzioni approvate nello stesso file I_1 = [s_1, e_1) e I_2 = [s_2, e_2):  
   `e_1 <= s_2` oppure `e_2 <= s_1`.
2. **Invariante di Uguaglianza Sostitutiva**:  
   Per ogni sostituzione r ed ogni sua occorrenza valida o = (path, s, e):  
   `target_contents[path][s : e] == r["content"]`.
3. **Invariante di Atomicità del Chunking (Boundary Safety)**:  
   Dato qualsiasi punto di taglio del chunk C_cut e un token protetto P = [ph_start, ph_end):  
   Non può esistere alcuna condizione per cui:  
   `ph_start < C_cut < ph_end`.
4. **Invariante di Reversibilità Perfetta**:  
   Sia T il testo target post-canonicalizzazione. Applicando la trasformazione di sostituzione `apply` e successivamente la decodifica `reconstruct` tramite `reverse_map`:  
   `reconstruct(apply(T)) == T`.
5. **Invariante di Ammortamento del Dizionario**:  
   La quota di token del dizionario associata a una voce di mappatura viene addebitata una sola volta a livello di repository, consentendo a pattern multi-file di ottenere un guadagno netto positivo anche con frequenze individuali basse per singolo file.
6. **Invariante di Confinamento Locale**: 
   Nessuna operazione di I/O può creare file al di fuori della cartella del file di destinazione o dell'albero di lavoro del progetto.
7. **Invariante di Determinismo Statico**: 
   Nessuna porzione di codice utente o trasformato viene eseguita a runtime dal programma durante le fasi di scansione, deduplicazione o test.


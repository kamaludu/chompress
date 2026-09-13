# SYSTEM TECHNICAL SPECIFICATION: chompress 

***version 1.0.0***  

**Software Architecture, Interface Contracts, P0-P4 Token Economics Model, and Execution Pipeline**  
*Project: Local LLM-ready Context Compressor (Token-First Architecture)*  
*Author: Cristian Evangelisti*  
*License: GNU General Public License v3.0 (GPL-3.0-or-later)*  
*Source code: https://github.com/kamaludu/chompress*  

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

## 1. Overview and Goal Hierarchy

`chompress` is a deterministic context compression and canonicalization engine designed to maximize the usable capacity and reasoning efficiency of Large Language Models (LLMs).

### 1.1 Hierarchy of Project Constraints
1. **Zero External Dependencies**: The engine, CLI interface, and test suite operate 100% using only Python's Standard Library, without third-party dependencies (`pip`).
2. **Isolation and Local Confinement (No System `/tmp/`)**: Strict prohibition against using the operating system's global `/tmp/` directory. Any temporary operations (atomic writes, chunking, test execution) occur exclusively within dedicated local relative paths inside the project workspace folder.
3. **Execution Safety and Integrity (No `eval` / `exec`)**: Strict prohibition against using `eval` in Bash scripts and invoking dynamic code execution functions in Python (`eval()`, `exec()`, `os.system()`, `subprocess` calls with shell). All analysis and verification on code occur statically (AST or `compile(..., "exec")` for syntactic validation only).
4. **Maximum Net Token Savings (Sovereign Metric)**: The architecture optimizes space occupancy within the target model's token space (BPE cl100k_base, o200k_base, LLaMA 3/Qwen tokenizers), not mere byte or character size on disk.
5. **Minimal Substantive Information Loss**: Transformations preserve the entire causal graph, execution logic, and semantic relationships of code and data.
6. **Absence of Human Readability Constraint**: Human readability is not a requirement. Lossy minifications and synthetic compactions are permitted and encouraged, provided the language model is able to faithfully understand, process, and reconstruct the context.
7. **Single-File First Architecture**: The system operates directly, atomically, and without directory overhead when processing individual scripts, documents, or Unix pipe streams (`stdin` / `stdout`), scaling seamlessly to multi-file repositories via globally amortized dictionaries.

### 1.2 System Component Map (8 Modules)

```text
+---------------------------------------------------------------------------------+
|                                  chompress.py                                   |
|  CLI orchestration, profiles (aggressive/semantic/lossless), streaming routing  |
|  (stdout vs stderr), P4.3 envelope management, dedicated exit codes (0, 1, 2)   |
+--------+------------------+-------------------+-------------------+-------------+
         |                  |                   |                   |
         v                  v                   v                   v
+----------------+  +---------------+  +-----------------+  +---------------------+
|  minifiers.py  |  |  mapping.py   |  | placeholders.py |  |    tokenizer.py     |
| AST Pipeline   |  | Serializers   |  | Alphabet        |  | Tiktoken Backend /  |
| P1, P3, P4     |  | Positional,   |  | Optimizer, BPE  |  | HuggingFace /       |
| (Licenses, Log,|  | Delimited, KV,|  | Tier 1 (CJK) &  |  | Heuristic Regex     |
| Argparse, Ren) |  | JSON          |  | Tier 2 (Prefix) |  | 0-dependency BPE    |
+--------+-------+  +-------+-------+  +--------+--------+  +----------+----------+
         |                  |                   |                      |
         +------------------+---------+---------+----------------------+
                                      |
                                      v
+---------------------------------------------------------------------------------+
|                                    core.py                                      |
|  Rabin-Karp 64-bit substring rolling hash, Sliding Block Discovery 60-bit O(1), |
|  boundary-safe greedy selection O(log K), token application, exact roundtrip    |
|  verification (P0.1), and boundary-aware atomic chunking (P0.2)                 |
+-------------------------------------+-------------------------------------------+
                                      |
                                      v
+---------------------------------------------------------------------------------+
|                                  io_utils.py                                    |
|  Transactional atomic persistence (mkstemp + os.replace), heap streaming        |
|  without duplication (os.fdopen), 64 KB buffered SHA-256 hashing                |
+-------------------------------------+-------------------------------------------+
                                      |
       +------------------------------+------------------------------+
       v                                                             v
+-----------------------------+              +------------------------------------+
|        benchmark.py         |              |           test_suite.py            |
| P0-P2 ablation suite        |              | 30 automated unit tests            |
| cl100k/o200k token scoring  |              | P0, P1, P2, P3, P4 integrity       |
| on real corpora             |              | validation and regression          |
+-----------------------------+              +------------------------------------+
```

---

## 2. Token Mathematical Model (Pure ASCII Notation)

The entire system evaluates transformations and replacements by comparing actual measured or estimated tokens. No formula adopts LaTeX notation or symbols not present on a standard ASCII keyboard.

### 2.1 Sovereign Context Saving Balance
Given original text T_orig and compressed payload T_comp:

```text
tokens_payload = count_tokens(T_comp)
tokens_mapping = count_tokens(mapping_payload)
tokens_protocol = count_tokens(protocol_header) + count_tokens(envelope_text)

net_tokens_saved = tokens(T_orig) - (tokens_payload + tokens_mapping + tokens_protocol)
net_compression_ratio = ((net_tokens_saved) * 100.0) / (tokens(T_orig))
```

If `net_tokens_saved <= 0`, the replacement or entry is rejected to avoid token penalties in the LLM's context window.

### 2.2 Specific Savings Equations for Canonicalization (Stage 1)

```text
tokens_license_saved = sum(i=1 to n_files, tokens(license_header_i) - tokens(lic_marker))
tokens_err_saved = sum(j=1 to m_exceptions, tokens(verbose_str_j) - tokens(short_id_j))
tokens_import_saved = sum(k=1 to p_imports, tokens(unused_import_k))
tokens_assert_saved = sum(q=1 to r_asserts, tokens(assert_stmt_q))
tokens_cli_saved = sum(u=1 to v_cli, tokens(narrative_kwarg_u))
tokens_rename_saved = sum(m=1 to s_locals, freq_m * (tokens(orig_name_m) - 1))
tokens_priv_saved = sum(p=1 to t_privates, freq_p * (tokens(orig_priv_p) - tokens(new_priv_p)))
```

### 2.3 Marginal Gain for Single Deduplication Candidate (Stage 2)
Given a candidate pattern with N occurrences in the corpus, content C, assigned placeholder P, marginal dictionary representation cost M_cost, and protocol overhead delta D_proto:

```text
candidate_net_gain = N * (tokens(C) - tokens(P)) - M_cost - D_proto
```

In architectures with a globally amortized dictionary (P1.3):
- M_cost is charged only once for the entire repository, amortizing across all N total occurrences distributed across the various files.
- In the `PositionalMappingSerializer` format, tokens(P) == 0 within the mapping since keys are omitted and inferred by ordinal index.

### 2.4 Tokenizer Heuristic Alignment Model
Given n calibration samples between the zero-dependency heuristic tokenizer and the real reference tokenizer:

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

## 3. Module Specifications and Interface Contracts

### 3.1 `minifiers.py`: Canonicalization and Compaction Pipeline (P1, P3, P4)

The module implements code transformations at the AST (Abstract Syntax Tree) and pattern-matching levels to eliminate superfluous text before indexing repetitions.

#### Main Contracts
- **`strip_license_header(code: str, ext: str) -> str` (P3.1)**:
  - Scans the first 40 lines of source code (.py, .sh, .js, .ts, .c, .cpp, .go, .rs).
  - Preserves the initial shebang (`#!/...`) intact if present on line 0.
  - Removes C-style blocks (`/* ... */`) or single-line comment sequences (`#`, `//`) containing case-insensitive matches for the expression:
    `LICENSE_KEYWORDS_RE = re.compile(r"(?:copyright\s+(?:\(c\)|©|\d{4})|license|spdx-license-identifier|all rights reserved)", re.IGNORECASE)`
  - If no license pattern is detected, returns the original code unchanged.

- **`minify_bash(code: str, remove_comments: bool = True, remove_ansi: bool = True) -> str` (P1.1)**:
  - Strictly preserves the shebang on the first line.
  - Removes ANSI escape sequences via:
    `ANSI_ESCAPE_RE = re.compile(r"(?:\x1b|\033|\\e|\\033|\\x1b)\[[0-9;]*[a-zA-Z]")`
  - Removes full-line comments (`stripped.startswith("#")`), leaving inline comments and quoted strings untouched so as not to alter shell expansion.
  - Collapses multiple empty lines into a single empty line.

- **`minify_markdown(doc: str, compact_tables: bool = True, remove_badges: bool = True) -> str` (P1.2)**:
  - Recognizes Markdown code fences (` ``` `) and suspends any internal manipulation to avoid corrupting encapsulated code blocks.
  - Removes links and images for graphical badges (shields.io, badgen.net, codecov, GitHub Actions workflows) in both Markdown and HTML formats.
  - Compacts Markdown tables by eliminating visual alignment spaces inside cells (`| col1 | col2 |` instead of `|   col1        |   col2   |`), preserving alignment delimiters (`:---:`).

- **`minify_python(...) -> str` (P1.1, P3.2, P4.1, P4.2, Vectors A and B)**:
  - Receives Python code and generates its AST (`ast.parse(code)`). In case of a syntax parsing error, returns the original code intact.
  - **`_DocstringStripper`**: Removes module, class, and function docstrings. Replaces the body with `pass` if the docstring was the only statement in the block.
  - **`_TypeAnnotationStripper`**: Removes PEP 484/526 type annotations from function arguments and return types, and transforms `AnnAssign` (`x: int = 5`) into standard assignments (`x = 5`), removing annotations without values (`x: int`).
  - **`_ErrorAndLogStringCompactor` (P3.2)**: Transforms verbose exception messages (`raise ValueError("very long explanatory string...")`) into compact tokens (`raise ValueError("ERR")`) and compiles verbose log calls (`logger.info("...")`) into `logger.info("LOG")` if the text exceeds 8 characters.
  - **`_AssertPruner` (P4.2)**: Completely removes `ast.Assert` nodes in aggressive mode.
  - **`_ArgparseNarrativeStripper` (Vector A)**: Strips via strict whitelist only narrative CLI documentation arguments (`help`, `description`, `epilog`) from `ArgumentParser`, `add_argument`, `add_parser`, and `add_argument_group`. Strictly preserves all functional configuration parameters (`type`, `default`, `choices`, `action`, `required`, `formatter_class`, `parents`, `conflict_handler`, `add_help`, `allow_abbrev`, etc.).
  - **`_UsedNamesCollector` & **`_UnusedImportPruner` (P4.1)**:
    - Collects all names with `Load` context in the AST (including decorators, base classes, and `__all__` tuples).
    - Prunes from `ast.Import` and `ast.ImportFrom` aliases and modules not referenced in runtime code.
    - Strictly preserves `__future__` imports and wildcard imports (`*`).
    - Completely removes `typing` module classes (`List`, `Dict`, `Optional`, `Union`) no longer referenced after stripping type annotations.
  - **`_ModuleScopeAnalyzer` & **`_ModulePrivateRenamer` (Vector B)**:
    - Renames top-level private symbols (`_foo` -> `_a`, `_b`...).
    - Anti-reflection guardrail: bails out if the module includes calls to or accesses of `eval`, `exec`, `locals`, `globals`, `getattr`, `setattr`, `hasattr`, `vars`, `dir`, `__dict__`.
    - Strictly excludes dunder names (`__init__`), names exported in `__all__`, imports, and symbols with internal shadowing.
    - Efficiency condition: renames only if `tok.count(old_name) > tok.count(new_name)`.
  - **`_LocalScopeAnalyzer` & **`_LocalRenamer`**:
    - Renames local variables in reflection-free functions.
    - Assigns 1-token BPE identifiers (`a`, `b`, `c`... Tier 1, `aa`, `ab`... Tier 2).
    - **Preventive efficiency filter**: strictly excludes variables that already occupy only 1 token (`tok.count(name) <= 1`), eliminating syntactic inflation and preserving natural short symbols.
    - Sorts candidates by descending gain: `freq * (tok.count(name) - 1)`.
    - Isolates nested functions, protecting closures.
  - **`_EmptyBodyFixer`**: Visits all syntactic blocks (`body`, `orelse`, `finalbody`) and injects `pass` if clearing assertions or imports made the block empty.
  - Regenerates the source with `ast.unparse(tree)` and validates the resulting code's syntactic integrity via `compile(code, "<minified>", "exec")`.

- **`minify_json(code: str) -> str` & `minify_yaml(code: str) -> str` (P3.4)**:
  - JSON: deserialization and whitespace-free re-compaction (`separators=(",", ":")`).
  - YAML: single-line comment removal (`#`) and empty line collapsing while respecting indentation.

---

### 3.2 `placeholders.py`: Alphabet Optimizer & Protocol Metadata (P2.3)

Manages dynamic generation and calibration of replacement token alphabets, ensuring absence of collisions and the lowest BPE token cost.

#### Available Placeholder Styles
1. **`single_token` (Tier 1 Default)**: Unified CJK ideographs (range `\u4e00-\u9fff`, base `0x4E00` = `一`). Each character occupies **exactly 1 token** in BPE models cl100k, o200k, and LLaMA. Pool size: 2,500 symbols.
2. **`prefix_compact` (Tier 2 Spillover)**: Asymmetric prefix followed by an integer (`^1`, `^2` or `~1`, `~2`). Occupies **exactly 2 tokens**.
3. **`guillemet`**: French guillemets (`«1»`, `«2»`). Occupies 3 tokens.
4. **`classic`**: Legacy baseline 4-token delimiters (`__s1__`, `__b1__`).
5. **`section` (`§1§`)**, **`bracket` (`⟦1⟧`)**, **`ascii_compact` (`~1~`)**: Auxiliary 3-token formats.

#### Allocation and Spillover Algorithm
1. **Automatic Calibration (`auto_calibrate`)**: Inspects input corpus `raw_corpus`. If at least 90 of the first 100 Tier 1 CJK characters are completely absent from the original text, selects `single_token`. Otherwise, selects the style with the lowest average cost between `prefix_compact` and `guillemet`.
2. **Alphabet Construction (`build_alphabet`)**:
   - Excludes every single character present in the corpus.
   - Allocates atomic 1-token CJK symbols first (Tier 1).
   - If replacement demand exceeds Tier 1 capacity, triggers hybrid spillover into Tier 2 (`^1`, `^2`, ...).
   - Groups codepoints into contiguous ranges:
     `ranges = [(start_1, end_1), (start_2, end_2), ...]`
3. **Finalization (`finalize_used_alphabet`)**: At the end of the greedy phase, trims the active alphabet strictly to tokens actually used in the compressed files and generates the protocol descriptor `get_protocol_meta()`.

---

### 3.3 `mapping.py`: Mapping and Protocol Serializers (P2.3)

Serializes the replacement dictionary for transmission to the LLM.

#### 1. `PositionalMappingSerializer` (Default Zero-Key Mapping)
- **Principle**: In the payload body, stores **exclusively original contents** separated by a compact 1-token delimiter (default sentinel `'§'`), completely omitting placeholder keys in the body.
- **Ultra-Low Overhead Protocol Header (~8 - ~28 tokens)**:
  - **Contiguous CJK**:  
    `[MAP:INDEXED sentinel='§' cjk_start=19968 count=N]`
  - **Multi-Range CJK (P2.3)**:  
    `[MAP:INDEXED sentinel='§' cjk_ranges='19968-20050,20060-20500' count=N]`
  - **Hybrid CJK + Prefix (P2.3)**:  
    `[MAP:INDEXED sentinel='§' cjk_ranges='...' prefix='^' p_start=1 p_count=M]`
  - **Prefix Sequence**:  
    `[MAP:INDEXED sentinel='§' prefix='^' start=1 count=N]`
  - **Template Sequence**:  
    `[MAP:INDEXED sentinel='§' seq='«{:d}»' start=1 count=N]`
- **Serialization Order**: Defined by `positional_sort_key`:
  - Tier 0: CJK characters (sorted by codepoint).
  - Tier 1: Numeric prefixes (`^1`, `^2`, sorted by integer value).
  - Tier 2: General single symbols.
  - Tier 3: Complex strings and templates in natural numeric order.
- **Reconstruction Invariant**:  
  `deserialize(serialize(M, ph_meta)) == M` for any dictionary M.

#### 2. `DelimitedMappingSerializer`
Stores `TOKEN\nCONTENT` blocks separated by a dynamic collision-free sentinel. Preserves raw line breaks and quotes without JSON escaping overhead.

#### 3. `KVMappingSerializer`
Stores `TOKEN=CONTENT` line by line, compacting internal line breaks with the `␤` marker.

#### 4. `JSONMappingSerializer`
Standard serialization `json.dumps(mapping, ensure_ascii=False, separators=(",", ":"))`. Used as a baseline reference for comparison in benchmarks.

---

### 3.4 `core.py`: Algorithmic Engine and Deduplication Pipeline

#### 3.4.1 Multi-Granularity Repetition Detection
1. **Identifiers and Words (`_find_word_candidates`)**: Regex `\b[A-Za-z_][A-Za-z0-9_]{3,}\b`. Detects words with length `>= 4` and frequency `>= 3`, preemptively excluding candidates that do not generate net gain compared to the placeholder.
2. **Rabin-Karp Substring Rolling Hash (`_find_substring_candidates`)**:
   - Scan window `L_min` characters.
   - Rolling hash parameters: `base = 257`, `mod = 2**61 - 1`.
   - 64-bit compact index:
     `packed_coordinate = (file_id << 32) | start_offset`
   - Buckets grouped by exact string of initial window.
   - **Synchronized Bidirectional Expansion**: Computes `common_left` and `common_right` by simultaneously extending all occurrences relative to the seed string as long as all characters match, up to the `L_max` ceiling.
3. **Dynamic Sliding Block Discovery (`_find_block_candidates` - P2.2)**:
   - Scans parametric windows of full lines from `B_max_lines` down to `B_min_lines`.
   - Precomputes cumulative line offsets `file_offsets[file_id]` to retrieve coordinates in **O(1)** time.
   - Rolling hash state machine across lines with 60-bit base:
     `base = 1000003`, `mod = 2**61 - 1`
   - Rolling window computation per line in O(1) time:
     `h = ((h - hash_prev * power) * base + hash_next) % mod`
   - Exact block string verification before confirming candidate.
 
#### 3.4.2 Greedy Selection with O(log K) Overlap Resolution (`select_replacements`)
- Candidates are pre-scored:
  `tok_gain = N * (tok_content - tok_ph) - tok_map`
  where `tok_map` is counted once at repository level.
- Deterministic sorting: by descending `tok_gain`, then descending frequency N, then descending content length, and finally SHA-256 hash.
- Collision checking: during allocation, if a placeholder is already present in the original text, Alphabet Optimizer advances to the next symbol.
- Overlap resolution (`_has_interval_overlap`):
  Uses `bisect.bisect_right` with search key on the `end` interval coordinate on lists maintained sorted via `bisect.insort`. Time complexity: **O(log K)** per check, with K occupied intervals in the file.
- If an occurrence overlaps with a previously assigned priority block, **only the single overlapping occurrence is discarded**. The pattern is retained if the remaining count of valid occurrences `N_valid >= 2` continues to generate a positive net gain exceeding `min_total_saving`.

#### 3.4.3 Placeholder Application and Boundary Protection (`apply_placeholders`)
- Substitutes valid occurrences in text from left to right.
- **Digit Boundary Guard**: For asymmetric prefixes ending with a digit (e.g. `^1`, `^2`), prevents substitution if the next character in original text is a digit (`text[e].isdigit()`), avoiding ambiguous token merging (e.g. `^1` followed by `5` being read as `^15`).
- Generates structured dictionary `reverse_map`.

#### 3.4.4 Exact Reversible Roundtrip Verification (`roundtrip_check` - P0.1)
- Verifies that for every file, strictly:
  `reconstruct(llm_ready[path]) == target_contents[path]`
- Tokens are sorted by descending length (`tokens_sorted = sorted(keys, key=len, reverse=True)`).
- Applies negative lookahead regex `(?!\d)` for open digit prefixes, ensuring shorter prefixes do not partially consume longer prefixes.
- If even a single-character discrepancy is detected, computes offset `mismatch_idx`, generates expected vs reconstructed context dump, creates `roundtrip_failures.json`, and forces termination with exit code `2`.

#### 3.4.5 Boundary-Aware Atomic Chunking (`chunk_outputs` - P0.2)
- If `--chunk-output` is active, partitions compressed files into fragments with nominal maximum size `--chunk-size` (default 16,000 characters).
- **Boundary-Aware Protection**: Maps all placeholder tokens present in the text. If the target cut falls inside a token (`s_start < target_cut < s_end`), immediately backtracks the cut index to `s_start`.
- **Newline Backtracking**: Within the allowed span, backtracks to the last newline `\n` that does not intersect a protected token.
- Writes chunks to `chunks/<rel_path>/0001.txt`, `0002.txt` and generates `chunks/manifest.json`.

---

### 3.5 `tokenizer.py`: Tokenizer Backends and BPE Calibration

#### Supported Backends
1. **`TiktokenBackend`**: Direct support for `cl100k_base` (GPT-4), `o200k_base` (GPT-4o), `p50k_base`.
2. **`HuggingFaceBackend`**: Support for LLaMA 3, Qwen, Mistral tokenizers via `transformers` package.
3. **`HeuristicBackend` (Zero Dependencies)**:
   Implements a regex pattern reproducing standard BPE pre-tokenization rules with `>= 95%` fidelity:
   - English contractions (`'s`, `'t`, `'re`, `'ve`, `'m`, `'ll`, `'d`).
   - Atomic Unified CJK characters: `[\u4e00-\u9fff]` counted strictly as **1 token each**.
   - Line breaks with associated indentation: `\r?\n[ \t]*`.
   - Alphabetic words with optional leading space (CamelCase, lowercase runs up to 12 characters counted as 1 token).
   - Numeric groupings up to 3 digits: ` ?[0-9]{1,3}`.
   - Space runs up to 4: `[ ]{1,4}`.
   - Long alphanumeric tokens or hashes split across 4-character blocks.

---

### 3.6 `chompress.py`: Orchestrator and Execution Contracts

#### 3.6.1 Primary Operating Modes (`--mode`)
- **`--mode aggressive` (Default)**:
  Enables the full spectrum of canonicalizers and compactors:
  - License removal (P3.1)
  - Error and log compaction (P3.2)
  - Argparse CLI narrative description stripping (Vector A)
  - Top-level private symbol renaming (Vector B)
  - 1-token BPE local identifier renaming (`a`, `b`, `c`...)
  - Unused import and typing pruning (P4.1)
  - Assertion pruning (P4.2)
  - Stripping of comments, docstrings, and PEP 484/526 types
  - Bash, Markdown, JSON, and YAML minification
  - Indentation normalization (4 spaces -> tab)
  - Empty line elimination in code
  - Forwarding active tokenizer `tok` to the AST canonicalization pipeline
  - Consolidated preset tuning: `aggressive` (`L_min=7`, `min_total_saving=3`, `B_min_lines=2`, `B_max_lines=6`)
- **`--mode semantic`**:
  Preserves runtime functional semantics:
  - Enables comment stripping, docstring stripping, type annotations stripping, tables, badges, and pruning of unused imports.
  - **Disables** error string compaction, diagnostic assertion pruning, and CLI stripping.
  - Preset tuning: `code-max` (`L_min=14`, `min_total_saving=2`).
- **`--mode lossless`**:
  Byte-identical decompression across all files:
  - Disables all minifiers and AST transformations.
  - Preserves every single space and empty line (`keep_empty_lines = True`).
  - Performs exclusively reversible deduplication with positional or specified mapping.

#### 3.6.2 Streaming and LLM Prompt Envelope (P3.3, P4.3)
- **`-i -`**: Reads source code from Unix stdin pipe.
- **`--stdout`**: Emits compressed output directly to `sys.stdout`. Diagnostic messages, logs, and token reports are automatically redirected to `sys.stderr`.
- **`--envelope, -e`**: Encapsulates output stream inside an LLM-optimized envelope:
  ```text
  <context>
  [LLM-READY COMPRESSED CONTEXT - chompress v1.0.0]
  [INSTRUCTION: Expand placeholders using mapping dictionary before execution or analysis.]
  (protocol header)
  (mapping payload)
  (file compresso o stream multi-file)
  </context>
  ```

#### 3.6.3 Exit Codes
- **`0`**: Execution completed successfully. Outputs written and roundtrip verified.
- **`1`**: Fatal input/output error (file not found, permission denied, unrecoverable exception).
- **`2`**: Roundtrip integrity violation (`roundtrip_check` failed).

---

## 4. Formal Persistence and Output Schemas

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

### 4.2 `reverse_map.json` (Global Restoration Registry)
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
    "version": "1.0.0"
  }
}
```

### 4.3 `manifest.json` (Repository Structural Index)
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

### 4.4 `chunks/manifest.json` (Chunk Reassembly Manifest)
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

## 5. Formal System Invariants

1. **Interval Disjointness Invariant (Non-Overlap)**:  
   For any pair of approved replacements in the same file I_1 = [s_1, e_1) and I_2 = [s_2, e_2):  
   `e_1 <= s_2` or `e_2 <= s_1`.
2. **Substitution Equality Invariant**:  
   For every replacement r and each of its valid occurrences o = (path, s, e):  
   `target_contents[path][s : e] == r["content"]`.
3. **Chunking Atomicity Invariant (Boundary Safety)**:  
   Given any chunk cut point C_cut and a protected token P = [ph_start, ph_end):  
   Under no circumstances can there exist:  
   `ph_start < C_cut < ph_end`.
4. **Perfect Reversibility Invariant**:  
   Let T be target post-canonicalization text. Applying replacement transformation `apply` and subsequently decoding `reconstruct` via `reverse_map`:  
   `reconstruct(apply(T)) == T`.
5. **Dictionary Amortization Invariant**:  
   The dictionary token cost associated with a mapping entry is charged only once at repository level, enabling multi-file patterns to achieve a positive net gain even with low individual frequencies per single file.
6. **Local Confinement Invariant**:  
   No I/O operation may create files outside the destination file's folder or the project workspace tree.
7. **Static Determinism Invariant**:  
   No portion of user or transformed code is executed at runtime by the program during scanning, deduplication, or testing phases.

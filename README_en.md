[![Chompress](https://img.shields.io/badge/Chompress-00aa55?style=for-the-badge&label=><&labelColor=004d00)](README.md)  
[![License: GPLv3](https://img.shields.io/badge/License-GPLv3-green.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](#)
[![GitHub Release](https://img.shields.io/github/v/release/kamaludu/chompress?label=Latest%20Release)](https://github.com/kamaludu/chompress/releases/latest)

# Chompress: AI Context Compressor [🇮🇹](README.md) 🇬🇧  
***version 1.0.0***

**chompress** is a lightweight, transparent tool that drastically reduces the size of source files, scripts, and entire software projects **before pasting them into an artificial intelligence chat** (such as ChatGPT, Claude, Copilot, DeepSeek, or local models).

By replacing duplicated portions with ultra-high-efficiency abbreviations (atomic 1-token CJK ideographic symbols), renaming internal variables to minimal identifiers, and eliminating superfluous text, **it allows you to save from 40% to over 75% of tokens** (the space available in the context window), enabling you to send much more code in a single prompt without losing substantive information.

---

## 1. Quick Guide in 30 Seconds

**Installation and Requirements:**
- **Python 3.8+**
- **Zero dependencies or external libraries** (works entirely with Python's standard library alone).
- **No access to global system directories**: the program operates only locally and leaves no residue in `/tmp`.

**To clone the repository:**
```sh
git clone --depth 1 --branch main https://github.com/kamaludu/chompress.git chompress
cd chompress
```

### Case 1: Compress a single file ready for the prompt (Recommended!)
If you have a single code or text file and want to immediately create a single prompt to paste into the AI:

```sh
python3 chompress.py -i mio_script.py -e > prompt_pronto.txt
```

The file `prompt_pronto.txt` will contain instructions for the AI, the compact vocabulary of abbreviations, and your compressed code inside the `<context>` tag. Open the file, select all, and paste it to the AI!

You can also view it on the fly in the terminal via pipe:
```sh
cat mio_script.py | python3 chompress.py -i - -e
```

### Case 2: Compress an entire folder or project
If you have a folder with multiple files and subfolders:

```sh
python3 chompress.py -i ./cartella_progetto -o out --verify-roundtrip
```
The compressed files will be saved inside the `out/` folder, maintaining the exact same original directory tree.

---

## 2. Practical Ready-to-Use Examples

Here are the most common commands explained step by step:

### Example 1: "I just want to prepare a single file to paste immediately into the AI"
It is the quintessential everyday use case: you have a `.py` file, a `.sh` script, or a `.md` document and want to create a single prompt with everything ready to go.

```sh
python3 chompress.py -i mio_script.py -e > prompt.txt
```
* **What it does**: Compresses `mio_script.py`, adds AI instructions and the compact vocabulary at the top, and saves everything into a single `prompt.txt` file.
* **What you need to do**: Open `prompt.txt`, select all (Ctrl+A or Cmd+A), copy it, and paste it into the chat of ChatGPT, Claude, or Copilot, appending your question at the bottom.

---

### Example 2: "I don't want to create files on my computer, show it directly in the terminal"
If you want to view the compressed prompt on screen on the fly or send it via Unix pipe:

```sh
cat mio_script.py | python3 chompress.py -i - -e
```
* **What it does**: Reads the file from standard input (`-i -`) and prints the ready prompt directly to the terminal, without writing anything to disk.

---

### Example 3: "I have a folder with an entire project and want to compress it all together"
When you want to compress an entire application while maintaining the folder tree:

```sh
python3 chompress.py -i ./cartella_progetto -o out --verify-roundtrip
```
* **What it does**: Scans all text files inside `./cartella_progetto` (automatically excluding binary files, images, and folders like `.git` or `.venv`), creates a shared dictionary, and saves compressed files inside the `out/` folder.
* **Why `--verify-roundtrip`**: Performs an automatic mathematical verification to ascertain 100% that compressed text can be reconstructed without losing a single character.

---

### Example 4: "The file is too long for the chat: I want the maximum savings possible"
If the AI chat gets blocked because code exceeds the allowed token limit:

```sh
python3 chompress.py -i codice_lungo.py --mode aggressive -e > prompt_minimo.txt
```
* **What it does**: Activates all optimizations of v1.0.0:
  - Removal of legal licenses and repetitive boilerplate.
  - Stripping of comments, docstrings, and PEP 484/526 type annotations.
  - AST renaming of local variables to 1-token identifiers (`a`, `b`, `c`...).
  - Safe renaming of internal private functions (`_foo` -> `_a`).
  - Stripping of CLI narrative descriptions in `argparse` (`help`, `description`, `epilog`), leaving parameter logic intact.
  - Compaction of long error and log messages (`ERR`, `LOG`).
  - Pruning of debug assertions (`assert`) and unused imports.
  - Replacement of repetitions with atomic 1-token symbols (up to **41%+ on dense single scripts** and over **76% on repositories**).

---

### Example 5: "I want the text to remain identical to the original byte, without removing spaces or lines"
If you need to send code to a colleague or a system requiring 100% bit-by-bit restoration (including all empty lines and original spacing):

```sh
python3 chompress.py -i ./mio_progetto -o out_lossless --mode lossless --verify-roundtrip
```
* **What it does**: Does not alter even a single space or blank line of the original text. It performs only reversible deduplication of duplicated sequences.

---

### Example 6: "I have a gigantic 200,000-character file that exceeds the chat limit"
If a single file is so long that the web interface refuses to accept it in a single message:

```sh
python3 chompress.py -i file_gigante.py -o out_spezzato --chunk-output --chunk-size 12000
```
* **What it does**: Splits the compressed file into numbered fragments (`0001.txt`, `0002.txt`, etc.) inside the `out_spezzato/chunks/` folder.
* **Advantage**: Never cuts a word or function in half; each piece always ends cleanly by backtracking to the end of a line, allowing controlled sequential sending.

---

## 3. In-Depth Guide to Using CHUNKS

### 3.1 What is a Chunk and Why is it Needed?
Artificial intelligence web interfaces often have a **maximum character limit per single message** (usually between 15,000 and 30,000 characters). If you try to paste a huge file of 100,000 or 300,000 characters, the chat will display an error or brutally truncate the text.

The **Chunking** feature of `chompress` solves this problem: it takes the compressed file and cuts it into ordered fragments (`0001.txt`, `0002.txt`, etc.), allowing you to transmit them to the AI in a controlled sequence.

---

### 3.2 The 3 Security Protections of Chunks
Unlike a generic command like Linux's `split`, `chompress` applies three safety algorithms:

1. **Atomic Protection (Boundary-Aware)**: The compressor **NEVER** cuts an abbreviation or dictionary token (such as `^1` or `一`) in half. If the character limit falls in the middle of a token, the program instantly backtracks to the beginning of the protected token.
2. **Clean Cut at Line End (Newline Backtracking)**: Each fragment does not break in the middle of a code instruction, but always backtracks to the last valid line break (`\n`). Each chunk contains syntactically coherent blocks.
3. **The Guarantee Seal (`sha256_full`)**: When you paste text into a chat, the browser might alter lines. In the `chunks/manifest.json` file, the compressor records the exact fingerprint (`sha256_full`) of the entire reassembled compressed file. The AI verifies the fingerprint after concatenating chunks: if it matches 100%, you are certain that not a single character was lost during copy-pasting.

---

### 3.3 How to Generate Chunks
To activate chunking on a single file or on a project, add `--chunk-output`:

```sh
python3 chompress.py -i codice_lungo.py -o out_chunks --chunk-output --chunk-size 14000
```

* **`--chunk-output`**: instructs the program to create the `chunks/` folder.
* **`--chunk-size 14000`**: sets the approximate maximum size of each piece (14,000 characters is ideal for AI chats, leaving room for your questions).

Inside the folder you will find:
```text
out_chunks/
  mapping_subset.txt              <- The token vocabulary
  protocol_header.txt             <- The protocol header for the AI
  chunks/
    codice_lungo.py/
      0001.txt                    <- First fragment
      0002.txt                    <- Second fragment
      0003.txt                    <- Third fragment
    manifest.json                 <- Chunk map with sha256_full seals
```

---

### 3.4 How to Use Chunks in Chat with AI (Step by Step)

#### Step 1: Send instructions and the chunk manifest
Open the chat with the AI and paste the `chunks/manifest.json` file, saying:
```text
I am about to send you a file partitioned into ordered fragments (chunks).
This is the chunks/manifest.json file describing the pieces and the expected checksum (sha256_full).
Store it and confirm when you are ready to receive the dictionary.

(paste chunks/manifest.json content here)
```

#### Step 2: Send the dictionary
Paste the `protocol_header.txt` file followed by `mapping_subset.txt`, saying:
```text
This is the vocabulary of abbreviations.
Store it without applying substitutions yet.

(paste protocol_header.txt and mapping_subset.txt here)
```

#### Step 3: Send chunk fragments one at a time
Send each fragment in exact order:
```text
Here is chunk 0001.txt of file codice_lungo.py:
(paste 0001.txt)
```
then:
```text
Here is chunk 0002.txt of file codice_lungo.py:
(paste 0002.txt)
```
(and so on until the last chunk).

#### Step 4: Order reassembly and verification
When you have sent all pieces, send this command to the AI:
```text
All chunks have been transmitted.
Strictly execute the procedure:
1. Concatenate the chunks in exact order (0001.txt + 0002.txt + ...).
2. Compute the SHA-256 hash of the resulting text and compare it with sha256_full specified in the manifest.
3. If the hash matches, confirm integrity, expand placeholders using the dictionary, and explain what this module does.
```

*(Note: you can find complete pre-formulated prompts for the AI in the* ***[PROMPT MASTER](docs/PROMPT_en.md)*** *file).*

---

## 4. The 3 Compression Modes

| Mode | Command | When to use it | What it does |
| :--- | :--- | :--- | :--- |
| **Maximum Savings** *(Default)* | `--mode aggressive` | When you have a lot of code and limited space in the AI chat. | Removes licenses, comments, docstrings, type annotations, assertions, verbose logs, CLI help texts (`argparse`), renames variables and internal private symbols to 1 token, and compresses repetitions. **Guarantees up to 75%+ savings.** |
| **Conservative** | `--mode semantic` | When you want to clean code while preserving error messages and test assertions. | Removes comments, docstrings, and unnecessary whitespace, but leaves all error messages, assert checks, and CLI descriptions untouched. |
| **Pure Lossless** | `--mode lossless` | When you need to be able to reconstruct the file 100% identically, bit by bit. | Does not alter even a single empty line or space in your text. Replaces only duplicate phrases with 100% reversible abbreviations. |

---

## 5. What Does the Program Do? (In Simple Terms)

When you send code or documents to an artificial intelligence, you consume context memory based on the number of **tokens** (word fragments according to BPE vocabularies). Code files often contain:
1. **Repetitive headers**: copyright notices, identical legal licenses across dozens of files.
2. **Duplicate phrases or functions**: code blocks, authorization checks, or web paths repeated everywhere.
3. **Long identifiers and internal documentation**: verbose variable names and CLI explanations that take up dozens of tokens.
4. **Visual spacing**: empty spaces and tabs that serve the human eye but waste precious AI context.

**chompress** analyzes text, compiles a small vocabulary of abbreviations (using CJK ideographic symbols that the AI instantly understands as exact single tokens), and replaces all repetitions.

### Real Net Savings (ASCII Formula)
The program calculates real savings by also subtracting the space occupied by the vocabulary and protocol instructions:
```text
tokens_saved = original_tokens - (compressed_text_tokens + vocabulary_tokens + instruction_tokens)
savings_percentage = ((tokens_saved) * 100.0) / (original_tokens)
```
If the result is positive, it means you are saving real, effective space in the chat window!

---

## 6. Table of Useful Commands

| Option | Simple Description | Usage Example |
| :--- | :--- | :--- |
| **-i, --input** | The file, folder, or hyphen `-` to read from standard input pipe. | `-i script.py` or `-i ./src` |
| **-o, --output** | Folder where results are saved (default: `compressed_output`). | `-o results` |
| **-e, --envelope** | Encapsulates the result with the instruction prompt for the AI, ready for copy-pasting. | `python3 chompress.py -i app.py -e` |
| **--stdout** | Displays output on screen instead of creating folders on disk. | `python3 chompress.py -i app.py --stdout` |
| **--mode** | Chooses between `aggressive` (maximum savings), `semantic`, or `lossless`. | `--mode aggressive` |
| **--verify-roundtrip** | Mathematically checks that compressed text can be reconstructed without errors. | `--verify-roundtrip` |
| **--chunk-output** | Splits long files into small pieces ready for chat. | `--chunk-output --chunk-size 12000` |
| **--chunk-size** | Nominal maximum size (in characters) of each chunk (default: 16000). | `--chunk-size 14000` |
| **--keep-empty-lines** | Keeps every empty line of source code (pure lossless). | `--keep-empty-lines` |

---

## 7. Frequently Asked Questions (FAQ)

### Will the AI understand compressed code even if there are ideographic symbols or renamed variables?
**Yes.** Advanced language models (such as GPT-4o, Claude 3.5/3.7 Sonnet, OpenAI o1/o3, DeepSeek, and LLaMA 3) interpret compact symbols and the associated vocabulary as an exact deterministic dictionary. They are able to understand code topology, perform logical analysis, and mentally reconstruct instructions without difficulty.

### Can I trust that the code will not be corrupted?
**Absolutely yes.** Simply add the `--verify-roundtrip` flag. Before completing the operation, the program runs a test decompression and verifies, character by character, that the result matches the pre-substitution original perfectly. If it finds even a single discordant character, it immediately aborts the process with an error.

### Why do CJK characters or symbols like `^1` appear in compressed code?
Because in the tokenization systems of modern models (BPE), these symbols occupy **exactly 1 or 2 tokens**, compared to the 4 or 6 tokens traditional abbreviations like `__s1__` would occupy. It is precisely this atomic allocation that guarantees maximum context savings.

### Do I need to install external libraries?
**No.** `chompress` works with the base installation of Python 3.8+ alone (zero required external packages).

### Is the program safe? Does it modify system files or execute code?  
**No.** `chompress` does not use the system's global `/tmp` folder, does not execute dynamic commands (`eval` or `exec`), does not require administrator privileges, and operates exclusively via static AST analysis and buffered hashing algorithms.

For more information, see: [SYSTEM TECHNICAL SPECIFICATION](docs/SPEC_en.md)

---

## 8. Files Included in the Project

To function properly, the folder includes the following standard modules:
- `chompress.py`: command-line orchestrator for compression and streaming modes.
- `core.py`: rolling hash deduplication engine, greedy selection, chunking, and roundtrip verification.
- `minifiers.py`: AST canonicalization pipeline for Python (1-token renamer, import/assert pruning, license/log/CLI help stripping), Bash, Markdown, JSON, and YAML.
- `placeholders.py`: BPE alphabet manager and multi-range protocol metadata.
- `mapping.py`: mapping serializers (compact positional, delimited, KV, JSON).
- `tokenizer.py`: BPE token counter (tiktoken, HuggingFace, or zero-dependency heuristic).
- `io_utils.py`: atomic transactional write utilities and 64 KB SHA-256 hashing.

---

## License and Contacts

* **License:** GNU General Public License v3.0 ([LICENSE](LICENSE))
* **Author:** Cristian Evangelisti  
* **Email:** `opensource@cevangel.anonaddy.me`  
* **Repository:** [GitHub kamaludu/chompress](https://github.com/kamaludu/chompress)

### Use of Artificial Intelligence Tools in Development

**chompress** is a work developed by the author with extensive use of generative Artificial Intelligence (LLM) tools for design, implementation, analysis, debugging, review, and documentation.

LLMs were utilized as development tools, not as autonomous generators of the project. The author defined the architecture, requirements, and design decisions, orchestrating work across different models and sessions, and employing those same LLMs to examine, challenge, and critique output produced by other models.

Code and documentation are therefore the result of an iterative, supervised process in which proposals generated by LLMs were evaluated, compared, modified, or rejected by the author. Final decisions and the overall project result rest with the author.

The use of LLMs offers significant benefits in terms of productivity, analysis, and review, but also introduces risks: no verification process can guarantee that every error or omission is caught. This notice is intended to make transparent both the extent of LLM usage and their actual role in the development process.


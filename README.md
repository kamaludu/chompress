[![Compressore locale LLM‑ready](https://img.shields.io/badge/Compressore_locale_LLM‑ready-00aa55?style=for-the-badge&label=>&labelColor=004d00)](README.md)
[![License: GPLv3](https://img.shields.io/badge/License-GPLv3-green.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](#)

# Compressore locale LLM‑ready  
Compressione reversibile di testo e codice sorgente, ottimizzata per l'invio a Large Language Models (placeholder semantici + mapping compatto + chunking boundary-aware + verifica roundtrip esatta).

> [!IMPORTANT]  
> **Comportamento predefinito sul testo:**  
> Per massimizzare il risparmio di token, il programma rimuove per impostazione predefinita le righe vuote nei file di codice sorgente e dati (mantenendole intatte per la documentazione `.md`, `.txt`, `.rst`, `.html`).  
> Se hai bisogno di una compressione al 100% identica al byte su tutti i file (modalità lossless pura), aggiungi semplicemente il flag `--keep-empty-lines`.

---

## 1. Installazione e Requisiti

- **Python 3.8+**
- **Nessuna dipendenza o libreria esterna da installare** (funziona con la sola libreria standard di Python).

Per clonare il repository:
```sh
git clone --depth 1 --branch main https://github.com/kamaludu/chunk-compress.git chunk-compress
cd chunk-compress
```

Assicurati che i seguenti file siano presenti nella cartella di lavoro:
```text
core.py
cli.py
io_utils.py
```

---

## 2. Preparazione dell'Input

Il programma accetta due tipi di sorgente tramite il parametro `--input` (o `-i`):

**A) Una directory di progetto**  
Elabora ricorsivamente tutti i file testuali contenuti nella cartella:
```sh
--input /percorso/del/tuo/progetto/
```

**B) Un file-lista**  
Un semplice file di testo che elenca un percorso per riga:
```text
src/database.py
src/api/routes.py
docs/architecture.md
```

I file binari (immagini, archivi compressi, eseguibili, database SQLite) vengono esclusi automaticamente dalla scansione per sicurezza e rapidità.

---

## 3. Esecuzione Rapida

### Compressione base con salvataggio in `out/`:
```sh
python3 cli.py --input ./mio_progetto --output out
```

Se non specifichi `--output`, i file verranno salvati automaticamente in `./compressed_output/`.

### Compressione consigliata con verifica di integrità e stima token:
```sh
python3 cli.py -i ./mio_progetto -o out --verify-roundtrip
```

---

## 4. File e Directory di Output

All'interno della cartella di output specificata troverai:

```text
out/
  mio_progetto/
    src/
      database.py         <- File compresso (con placeholder)
      api/routes.py       <- File compresso (con placeholder)
    docs/
      architecture.md     <- File documentazione preservato
  mapping_subset.json     <- Vocabolario ridotto da incollare nella chat LLM
  reverse_map.json        <- Registro completo per ripristino o verifiche locali
  manifest.json           <- (Opzionale) Mappa globale delle firme e dei file
  chunks/                 <- (Opzionale) Cartella con file suddivisi in porzioni
    mio_progetto/
      src/
        database.py/
          0001.txt        <- Primo chunk del file
          0002.txt        <- Secondo chunk del file
    manifest.json         <- Manifest per riassemblare i chunk
```

### Dettaglio dei file generati:

1. **File compressi LLM-ready**:  
   Mantengono l'esatta struttura ad albero del tuo progetto. Le porzioni ripetute sono sostituite da placeholder leggibili:
   - `§§s001§§` per sequenze e sottostringhe ripetute.
   - `§§b001§§` per interi blocchi multi-riga (funzioni, intestazioni, classi).

2. **`mapping_subset.json`**:  
   È il file fondamentale per il tuo prompt. Contiene **esclusivamente i placeholder effettivamente usati**, associati al loro testo originale. È studiato per occupare il minor numero possibile di token quando viene incollato nel prompt.

3. **`reverse_map.json`**:  
   Contiene il database completo di tutti i placeholder, comprensivo di offset originali, tipi e frequenze. È utile per ispezione locale, ma solitamente troppo esteso da incollare direttamente in chat.

4. **`chunks/`** (se attivo `--chunk-output`):  
   Se hai file di decine di migliaia di righe che superano la finestra di contesto del tuo LLM, questo flag li suddivide in porzioni sicure (`0001.txt`, `0002.txt`).  
   **Protezione boundary-aware:** Il sistema garantisce che nessun placeholder (es. `§§s001§§`) venga mai tagliato a metà e arretra preferenzialmente sui ritorni a capo (`\n`) per mantenere integro il codice.

---

## 5. Report a Terminale e Calcolo Risparmio

Al termine dell'esecuzione, il programma stampa a terminale il consuntivo del risparmio:

```text
=== SAVINGS AND TOKEN REPORT ===
Original characters:               125040
Compressed characters:              78210
Mapping subset overhead (chars):     6120
Gross character savings:            46830 (37.45%)
Net character savings:              40710 (32.56%)
Estimated original tokens (LLM):    31260
Estimated compressed text tokens:   19553
Estimated mapping prompt tokens:     1530
Estimated net token savings (LLM):  10177
Active replacements:                   18
================================
```

* **Risparmio Lordo (Gross):** Caratteri risparmiati all'interno dei soli file sorgente.
* **Risparmio Netto Reale (Net):** Risparmio effettivo calcolato sottraendo la dimensione di `mapping_subset.json`. Se questo valore è positivo, stai inviando meno token all'LLM a parità di informazione trasmessa.
* **Stima Token:** Calcolata sul rapporto empirico medio di 4 caratteri per token `(caratteri / 4.0)`.

---

## 6. Come Utilizzare gli Output con un LLM

### Scenario A — File di dimensioni standard (Senza Chunking)
1. Esegui la compressione standard:
   ```sh
   python3 cli.py -i ./progetto -o out --verify-roundtrip
   ```
2. Nella chat del modello linguistico, incolla:
   - I file compressi contenuti in `out/`.
   - Il contenuto di `out/mapping_subset.json`.
3. Chiedi al modello di analizzare o modificare il codice. Il modello userà `mapping_subset.json` come vocabolario per comprendere i token `§§...§§`.

### Scenario B — File molto grandi (Con Chunking)
1. Esegui la compressione con chunking:
   ```sh
   python3 cli.py -i ./progetto -o out --chunk-output --chunk-size 16000
   ```
2. Invia al modello:
   - `out/chunks/manifest.json` (per definire l'ordine dei pezzi).
   - `out/mapping_subset.json` (vocabolario dei token).
   - I file `0001.txt`, `0002.txt` nell'ordine indicato.

---

## 7. Parametri da Linea di Comando (CLI)

| Flag | Tipo | Default | Descrizione | Esempio |
| :--- | :--- | :--- | :--- | :--- |
| **--input, -i** | Stringa | *Obbligatorio* | Cartella radice o file-lista da elaborare. | `-i ./src` |
| **--output, -o** | Stringa | `compressed_output` | Cartella in cui salvare i risultati. | `-o ./out` |
| **--keep-empty-lines**| Flag | `False` | Preserva tutte le righe vuote (modalità lossless pura). | `--keep-empty-lines` |
| **--verify-roundtrip** | Flag | `False` | Ricostruisce il testo e verifica matematicamente l'esatta uguaglianza con l'originale. | `--verify-roundtrip` |
| **--chunk-output** | Flag | `False` | Suddivide i file compressi in porzioni dentro `OUT_DIR/chunks/`. | `--chunk-output` |
| **--chunk-size** | Intero | `16000` | Dimensione massima (in caratteri) di ciascun chunk. | `--chunk-size 8000` |
| **--export-manifest** | Flag | `False` | Genera `manifest.json` con la struttura dei file e le firme SHA256. | `--export-manifest` |
| **--L_min** | Intero | `64` | Lunghezza minima di una sequenza ripetuta per essere compressa. | `--L_min 32` |
| **--N_min** | Intero | `2` | Numero minimo di ripetizioni richieste per sostituire una sequenza. | `--N_min 2` |
| **--B_min_lines** | Intero | `5` | Numero minimo di righe per un blocco ripetuto. | `--B_min_lines 3` |
| **--B_max_lines** | Intero | `20` | Numero massimo di righe per un blocco ripetuto. | `--B_max_lines 10` |
| **--min_total_saving**| Intero | `100` | Risparmio minimo di caratteri richiesto per ammettere un placeholder. | `--min_total_saving 30` |
| **--no-export-mapping**| Stringa | `None` | Ometti per esportare tutto; passa senza valore per non esportare; passa lista separata da virgole per escludere file. | `--no-export-mapping a.py,b.py` |
| **--include-pointless**| Flag | `False` | Include anche estensioni binarie o non testuali nella scansione. | `--include-pointless` |
| **--placeholder-sub** | Stringa | `§§s{:03d}§§` | Modello di formattazione per token di sottostringa. | `--placeholder-sub "§s{:02d}§"` |
| **--placeholder-blk** | Stringa | `§§b{:03d}§§` | Modello di formattazione per token di blocco. | `--placeholder-blk "§b{:02d}§"` |

---

## 8. Preset Pronti all'Uso

### A) Massimo Risparmio Token (Consigliato per repository di codice)
Rileva ripetizioni anche brevi e compatta le righe vuote del codice sorgente:
```sh
python3 cli.py \
  --input ./mio_progetto \
  --output ./out_ottimizzato \
  --L_min 32 \
  --N_min 2 \
  --B_min_lines 3 \
  --B_max_lines 12 \
  --min_total_saving 25 \
  --verify-roundtrip
```

### B) Modalità Lossless Pura (Preservazione totale al byte)
Mantiene ogni singolo spazio o riga vuota originale:
```sh
python3 cli.py \
  --input ./mio_progetto \
  --output ./out_lossless \
  --keep-empty-lines \
  --verify-roundtrip
```

### C) Modalità File Grandi con Chunking
Ottimale quando i sorgenti superano i 100-200 KB per singolo file:
```sh
python3 cli.py \
  --input ./mio_progetto \
  --output ./out_chunks \
  --chunk-output \
  --chunk-size 12000 \
  --verify-roundtrip
```

---

## 9. Risoluzione dei Problemi e Verifica

* **Il controllo `--verify-roundtrip` fallisce**:  
  Se durante la verifica viene rilevata una discrepanza tra il testo target e quello ricostruito, il programma termina con codice di uscita `2` e scrive il file `roundtrip_failures.json` contenente l'offset del primo carattere difforme e la porzione di testo non coincidente.
* **I chunk tagliano il codice a metà?**:  
  No: l'algoritmo di chunking atomico boundary-aware impedisce tassativamente tagli all'interno dei placeholder e arretra all'ultimo ritorno a capo `\n` valido prima del limite di caratteri.
* **Risparmio netto negativo?**:  
  Se `Net saved chars` risulta negativo o vicino allo zero, il codice di partenza contiene pochissime porzioni duplicate rispetto all'overhead del dizionario. In tal caso, puoi alzare `--min_total_saving` (es. a `150` o `200`) per selezionare solo le ripetizioni ad alto rendimento.

---

## Licenza

Questo progetto è distribuito sotto licenza **GNU General Public License v3.0 (GPL-3.0-or-later)**. Consulta il file `LICENSE` per il testo completo.

---

## Note

Parte del codice e della documentazione è stata redatta con l’assistenza di strumenti di IA.  
L’architettura e le decisioni tecniche restano curate manualmente.

---

## Contatti

- Autore: Cristian Evangelisti  
- Email: opensource​@​cevangel.​anonaddy.​me  
- Repository: https://github.com/kamaludu/chunk-compress


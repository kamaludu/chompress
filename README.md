[![Chompress](https://img.shields.io/badge/Chompress-00aa55?style=for-the-badge&label=><&labelColor=004d00)](README.md)  
[![License: GPLv3](https://img.shields.io/badge/License-GPLv3-green.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](#)
[![GitHub Release](https://img.shields.io/github/v/release/kamaludu/chompress?label=Latest%20Release)](https://github.com/kamaludu/chompress/releases/latest)

# Chompress: Compressore di Contesto per AI  🇮🇹 [🇬🇧](README-en.md)
***version 1.0.0***

**chompress** è uno strumento leggero e trasparente che riduce drasticamente le dimensioni di file sorgente, script e interi progetti software **prima di incollarli nella chat di un'intelligenza artificiale** (come ChatGPT, Claude, Copilot, DeepSeek o modelli locali).

Sostituendo le porzioni duplicate con abbreviazioni ad altissima efficienza (simboli ideografici CJK a 1 token esatto), rinominando le variabili interne in identificatori minimi ed eliminando il testo superfluo, **ti permette di risparmiare dal 40% a oltre il 75% dei token** (lo spazio disponibile nella finestra di contesto), consentendoti di inviare molto più codice in un singolo prompt senza perdere informazioni sostanziali.

---

## 1. Guida Rapida in 30 Secondi

**Installazione e Requisiti:**
- **Python 3.8+**
- **Zero dipendenze o librerie esterne** (funziona interamente con la sola libreria standard di Python).
- **Nessun accesso a cartelle globali di sistema**: il programma lavora solo localmente e non lascia residui in `/tmp`.

**Per clonare il repository:**
```sh
git clone --depth 1 --branch main https://github.com/kamaludu/chompress.git chompress
cd chompress
```

### Caso 1: Comprimere un singolo file pronto per il prompt (Consigliato!)
Se hai un singolo file di codice o testo e vuoi creare subito un unico prompt da incollare nell'AI:

```sh
python3 chompress.py -i mio_script.py -e > prompt_pronto.txt
```

Il file `prompt_pronto.txt` conterrà le istruzioni per l'AI, il vocabolario compatto delle abbreviazioni e il tuo codice compresso all'interno del tag `<context>`. Apri il file, seleziona tutto e incollalo all'AI!

Puoi anche visualizzarlo al volo a terminale via pipe:
```sh
cat mio_script.py | python3 chompress.py -i - -e
```

### Caso 2: Comprimere un'intera cartella o progetto
Se hai una cartella con diversi file e sottocartelle:

```sh
python3 chompress.py -i ./cartella_progetto -o out --verify-roundtrip
```
I file compressi verranno salvati dentro la cartella `out/`, mantenendo la stessa identica alberatura originale.

---

## 2. Esempi Pratici Pronti all'Uso

Ecco i comandi più comuni spiegati passo dopo passo:

### Esempio 1: "Voglio solo preparare un singolo file da incollare subito nell'AI"
È il caso d'uso quotidiano per eccellenza: hai un file `.py`, uno script `.sh` o un documento `.md` e vuoi creare un prompt unico con tutto già pronto.

```sh
python3 chompress.py -i mio_script.py -e > prompt.txt
```
* **Cosa fa**: Comprime `mio_script.py`, aggiunge in cima le istruzioni per l'AI e il vocabolario compatto, e salva tutto in un unico file `prompt.txt`.
* **Cosa devi fare tu**: Apri `prompt.txt`, seleziona tutto (Ctrl+A o Cmd+A), copialo e incollalo nella chat di ChatGPT, Claude o Copilot aggiungendo la tua domanda in fondo.

---

### Esempio 2: "Non voglio creare file sul computer, mostramelo direttamente a terminale"
Se vuoi visualizzare al volo il prompt compresso a schermo o inviarlo in pipe Unix:

```sh
cat mio_script.py | python3 chompress.py -i - -e
```
* **Cosa fa**: Legge il file dallo standard input (`-i -`) e stampa il prompt pronto direttamente a terminale, senza scrivere nulla sul disco.

---

### Esempio 3: "Ho una cartella con un intero progetto e voglio comprimerlo tutto insieme"
Quando vuoi comprimere un'intera applicazione mantenendo l'albero delle cartelle:

```sh
python3 chompress.py -i ./cartella_progetto -o out --verify-roundtrip
```
* **Cosa fa**: Scansiona tutti i file di testo dentro `./cartella_progetto` (escludendo in automatico file binari, immagini e cartelle come `.git` o `.venv`), crea un dizionario condiviso e salva i file compressi dentro la cartella `out/`.
* **Perché `--verify-roundtrip`**: Esegue una verifica matematica automatica per accertare al 100% che il testo compresso possa essere ricostruito senza perdere nemmeno un carattere.

---

### Esempio 4: "Il file è troppo lungo per la chat: voglio il massimo risparmio possibile"
Se la chat dell'AI si blocca perché il codice supera il limite di token consentito:

```sh
python3 chompress.py -i codice_lungo.py --mode aggressive -e > prompt_minimo.txt
```
* **Cosa fa**: Attiva tutte le ottimizzazioni di v1.0.0:
  - Rimozione licenze legali e boilerplate ripetitivi.
  - Stripping di commenti, docstring e annotazioni di tipo PEP 484/526.
  - Ridenominazione AST delle variabili locali in identificatori a 1 token (`a`, `b`, `c`...).
  - Ridenominazione sicura delle funzioni private interne (`_foo` -> `_a`).
  - Stripping delle descrizioni narrative CLI di `argparse` (`help`, `description`, `epilog`), lasciando intatta la logica dei parametri.
  - Compattazione dei messaggi di errore e log lunghi (`ERR`, `LOG`).
  - Pruning delle asserzioni di debug (`assert`) e degli import inutilizzati.
  - Sostituzione delle ripetizioni con simboli atomici a 1 token (fino al **41%+ su singoli script densi** e oltre il **76% su repository**).

---

### Esempio 5: "Voglio che il testo rimanga identico al byte originale, senza togliere spazi o righe"
Se devi inviare codice a un collega o a un sistema che richiede il ripristino al 100% bit per bit (comprese tutte le righe vuote e le spaziature originali):

```sh
python3 chompress.py -i ./mio_progetto -o out_lossless --mode lossless --verify-roundtrip
```
* **Cosa fa**: Non altera neanche uno spazio né una riga vuota del testo originale. Esegue solo la deduplicazione reversibile delle sequenze duplicate.

---

### Esempio 6: "Ho un file gigantesco da 200.000 caratteri che supera il limite della chat"
Se un singolo file è così lungo che l'interfaccia web rifiuta di riceverlo in un unico messaggio:

```sh
python3 chompress.py -i file_gigante.py -o out_spezzato --chunk-output --chunk-size 12000
```
* **Cosa fa**: Suddivide il file compresso in frammenti numerati (`0001.txt`, `0002.txt`, ecc.) dentro la cartella `out_spezzato/chunks/`.
* **Vantaggio**: Non taglia mai una parola o una funzione a metà; ogni pezzo termina sempre arretrando a fine riga in modo pulito, consentendo l'invio sequenziale controllato.

---

## 3. Guida Approfondita all'Uso dei CHUNKS

### 3.1 Cos'è un Chunk e Perché Serve?
Le interfacce web delle intelligenze artificiali hanno spesso un **limite massimo di caratteri per singolo messaggio** (solitamente tra i 15.000 e i 30.000 caratteri). Se tenti di incollare un file enorme da 100.000 o 300.000 caratteri, la chat mostrerà un errore o troncherà brutalmente il testo.

La funzione **Chunking** di `chompress` risolve questo problema: prende il file compresso e lo taglia in frammenti ordinati (`0001.txt`, `0002.txt`, ecc.), permettendoti di trasmetterli all'AI in sequenza controllata.

---

### 3.2 Le 3 Protezioni di Sicurezza dei Chunk
A differenza di un comando generico come `split` di Linux, `chompress` applica tre algoritmi di sicurezza:

1. **Protezione Atomica (Boundary-Aware)**: Il compressore non taglia **MAI** a metà un'abbreviazione o un token di dizionario (come `^1` o `一`). Se il limite di caratteri cade nel mezzo di un token, il programma arretra istantaneamente all'inizio del token protetto.
2. **Taglio Pulito a Fine Riga (Newline Backtracking)**: Ogni frammento non si interrompe nel mezzo di un'istruzione di codice, ma arretra sempre all'ultimo ritorno a capo valido (`\n`). Ogni chunk contiene blocchi sintatticamente coerenti.
3. **Il Sigillo di Garanzia (`sha256_full`)**: Quando incolli del testo in una chat, il browser potrebbe alterare delle righe. Nel file `chunks/manifest.json`, il compressore registra l'impronta digitale esatta (`sha256_full`) dell'intero file compresso riassemblato. L'AI verifica l'impronta dopo aver concatenato i chunk: se coincide al 100%, sei certo che non è andato perso nemmeno un carattere durante il copia-incolla.

---

### 3.3 Come Generare i Chunk
Per attivare il chunking su un singolo file o su un progetto, aggiungi `--chunk-output`:

```sh
python3 chompress.py -i codice_lungo.py -o out_chunks --chunk-output --chunk-size 14000
```

* **`--chunk-output`**: indica al programma di creare la cartella `chunks/`.
* **`--chunk-size 14000`**: imposta la dimensione indicativa massima di ciascun pezzo (14.000 caratteri è l'ideale per le chat AI, lasciando spazio per le tue domande).

Dentro la cartella troverai:
```text
out_chunks/
  mapping_subset.txt              <- Il vocabolario dei token
  protocol_header.txt             <- L'intestazione del protocollo per l'AI
  chunks/
    codice_lungo.py/
      0001.txt                    <- Primo frammento
      0002.txt                    <- Secondo frammento
      0003.txt                    <- Terzo frammento
    manifest.json                 <- Mappa dei pezzi con i sigilli sha256_full
```

---

### 3.4 Come Usare i Chunk nella Chat con l'AI (Passo dopo Passo)

#### Passo 1: Invia le istruzioni e il manifest dei chunk
Apri la chat con l'AI e incolla il file `chunks/manifest.json` dicendo:
```text
Sto per inviarti un file suddiviso in frammenti ordinati (chunk).
Questo è il file chunks/manifest.json che descrive i pezzi e il checksum atteso (sha256_full).
Memorizzalo e conferma quando sei pronto a ricevere il dizionario.

(incolla qui il contenuto di chunks/manifest.json)
```

#### Passo 2: Invia il dizionario
Incolla il file `protocol_header.txt` seguito da `mapping_subset.txt` dicendo:
```text
Questo è il vocabolario delle abbreviazioni.
Memorizzalo senza applicare ancora le sostituzioni.

(incolla qui protocol_header.txt e mapping_subset.txt)
```

#### Passo 3: Invia i frammenti chunk uno per volta
Invia ciascun frammento nell'ordine esatto:
```text
Ecco il chunk 0001.txt del file codice_lungo.py:
(incolla 0001.txt)
```
poi:
```text
Ecco il chunk 0002.txt del file codice_lungo.py:
(incolla 0002.txt)
```
(e così via fino all'ultimo chunk).

#### Passo 4: Ordina il riassemblaggio e la verifica
Quando hai inviato tutti i pezzi, invia all'AI questo comando:
```text
Tutti i chunk sono stati trasmessi.
Esegui tassativamente la procedura:
1. Concatena i chunk nell'ordine esatto (0001.txt + 0002.txt + ...).
2. Calcola l'hash SHA-256 del testo ottenuto e confrontalo con sha256_full indicato nel manifest.
3. Se l'hash coincide, conferma l'integrità, espandi i placeholder usando il dizionario e spiegami cosa fa questo modulo.
```

*(Nota: puoi trovare i prompt completi già formulati per l'AI nel file* ***[PROMPT MASTER](docs/PROMPT.md)*** *).*

---

## 4. Le 3 Modalità di Compressione

| Modalità | Comando | Quando usarla | Cosa fa |
| :--- | :--- | :--- | :--- |
| **Massimo Risparmio** *(Predefinita)* | `--mode aggressive` | Quando hai tanto codice e poco spazio nella chat dell'AI. | Rimuove licenze, commenti, docstring, annotazioni di tipo, asserzioni, log verbosi, testi di help CLI (`argparse`), rinomina le variabili e i simboli privati interni a 1 token, e comprime le ripetizioni. **Garantisce fino al 75%+ di risparmio.** |
| **Conservativa** | `--mode semantic` | Quando vuoi pulire il codice preservando messaggi di errore e asserzioni di test. | Rimuove commenti, docstring e spaziature inutili, ma lascia inalterati tutti i messaggi di errore, i controlli di assert e le descrizioni CLI. |
| **Lossless Pura** | `--mode lossless` | Quando devi poter ricostruire il file identico al 100%, bit per bit. | Non altera nemmeno una riga vuota o uno spazio del tuo testo. Sostituisce solo le frasi duplicate con abbreviazioni reversibili al 100%. |

---

## 5. Cosa Fa il Programma? (In Parole Semplici)

Quando invii codice o documenti a un'intelligenza artificiale, consumi memoria di contesto in base al numero di **token** (frammenti di parole secondo i vocabolari BPE). I file di codice contengono spesso:
1. **Intestazioni ripetitive**: note di copyright, licenze legali uguali su decine di file.
2. **Frasi o funzioni duplicate**: blocchi di codice, controlli di autorizzazione o percorsi web ripetuti ovunque.
3. **Identificatori lunghi e documentazione interna**: nomi di variabili verbosi e spiegazioni CLI che occupano decine di token.
4. **Spaziature visive**: spazi e tabulazioni vuote che servono all'occhio umano ma sprecano prezioso contesto dell'AI.

**chompress** analizza il testo, compila un piccolo vocabolario di abbreviazioni (usando simboli ideografici CJK che l'AI comprende al volo come singoli token esatti) e sostituisce tutte le ripetizioni.

### Il Risparmio Netto Reale (Formula ASCII)
Il programma calcola il risparmio reale sottraendo anche lo spazio occupato dal vocabolario e dalle istruzioni di protocollo:
```text
token_risparmiati = token_originali - (token_testo_compresso + token_vocabolario + token_istruzioni)
percentuale_risparmio = ((token_risparmiati) * 100.0) / (token_originali)
```
Se il risultato è positivo, significa che stai risparmiando spazio reale ed effettivo nella finestra della chat!

---

## 6. Tabella dei Comandi Utili

| Opzione | Descrizione Semplice | Esempio d'uso |
| :--- | :--- | :--- |
| **-i, --input** | Il file, la cartella o il trattino `-` per leggere da pipe standard input. | `-i script.py` oppure `-i ./src` |
| **-o, --output** | Cartella dove salvare i risultati (default: `compressed_output`). | `-o risultati` |
| **-e, --envelope** | Incapsula il risultato con il prompt di istruzioni per l'AI, pronto per il copia-incolla. | `python3 chompress.py -i app.py -e` |
| **--stdout** | Mostra l'output a schermo anziché creare cartelle su disco. | `python3 chompress.py -i app.py --stdout` |
| **--mode** | Sceglie tra `aggressive` (massimo risparmio), `semantic` o `lossless`. | `--mode aggressive` |
| **--verify-roundtrip** | Controlla matematicamente che il testo compresso possa essere ricostruito senza errori. | `--verify-roundtrip` |
| **--chunk-output** | Suddivide i file lunghi in piccoli pezzi pronti per la chat. | `--chunk-output --chunk-size 12000` |
| **--chunk-size** | Dimensione nominale massima (in caratteri) di ciascun chunk (default: 16000). | `--chunk-size 14000` |
| **--keep-empty-lines** | Mantiene ogni riga vuota del codice sorgente (lossless pura). | `--keep-empty-lines` |

---

## 7. Domande Frequenti (FAQ)

### L'AI capirà il codice compresso anche se ci sono simboli ideografici o variabili rinominate?
**Sì.** I modelli linguistici avanzati (come GPT-4o, Claude 3.5/3.7 Sonnet, OpenAI o1/o3, DeepSeek e LLaMA 3) interpretano i simboli compatti e il vocabolario associato come un dizionario deterministico esatto. Riescono a comprendere la topologia del codice, a eseguire analisi logiche e a ricostruire mentalmente le istruzioni senza difficoltà.

### Posso fidarmi che il codice non venga corrotto?
**Assolutamente sì.** Ti basta aggiungere il flag `--verify-roundtrip`. Prima di completare l'operazione, il programma esegue una decompressione di prova e controlla, carattere per carattere, che il risultato coincida perfettamente con l'originale pre-sostituzione. Se trova anche un solo carattere discordante, blocca immediatamente il processo con errore.

### Perché compaiono caratteri CJK o simboli come `^1` nel codice compresso?
Perché nei sistemi di tokenizzazione dei modelli moderni (BPE), questi simboli occupano **esattamente 1 o 2 token**, contro i 4 o 6 token che occuperebbero abbreviazioni tradizionali come `__s1__`. È proprio questa allocazione atomica che garantisce il massimo risparmio di contesto.

### Serve installare librerie esterne?
**No.** `chompress` funziona con la sola installazione base di Python 3.8+ (zero pacchetti esterni obbligatori).

### Il programma è sicuro? Modifica file di sistema o esegue il codice?  
**No.** `chompress` non usa la cartella globale `/tmp` di sistema, non esegue comandi dinamici (`eval` o `exec`), non richiede privilegi di amministratore e opera esclusivamente tramite analisi statica AST e algoritmi di hashing bufferizzati.

Maggiori informazioni consulta: [SPECIFICA TECNICA DI SISTEMA](docs/SPEC.md)

---

## 8. File Inclusi nel Progetto

Per funzionare correttamente, la cartella include i seguenti moduli standard:
- `chompress.py`: orchestratore da riga di comando per le modalità di compressione e streaming.
- `core.py`: motore di deduplicazione a rolling hash, selezione greedy, chunking e verifica roundtrip.
- `minifiers.py`: pipeline di canonicalizzazione AST per Python (renamer 1-token, pruning import/assert, stripping licenze, log e help CLI), Bash, Markdown, JSON e YAML.
- `placeholders.py`: gestore dell'alfabeto BPE e dei metadati di protocollo multi-range.
- `mapping.py`: serializzatori di mappatura (posizionale compatto, delimitato, KV, JSON).
- `tokenizer.py`: misuratore dei token BPE (tiktoken, HuggingFace o euristico a zero dipendenze).
- `io_utils.py`: utilità atomiche di scrittura transazionale e hashing SHA-256 a 64 KB.

---

## Licenza e Contatti

* **Licenza:** GNU General Public License v3.0 ([LICENSE](LICENSE))
* **Autore:** Cristian Evangelisti  
* **Email:** `opensource@cevangel.anonaddy.me`  
* **Repository:** [GitHub kamaludu/chompress](https://github.com/kamaludu/chompress)

### Uso di strumenti di Intelligenza Artificiale nello sviluppo

**chompress** è un'opera sviluppata dall'autore con un uso esteso di strumenti di Intelligenza Artificiale generativa (LLM) per progettazione, implementazione, analisi, debugging, revisione e documentazione.

Gli LLM sono stati utilizzati come strumenti di sviluppo, non come generatori autonomi del progetto. L'autore ha definito l'architettura, i requisiti e le scelte progettuali, orchestrando il lavoro attraverso modelli e sessioni differenti e utilizzando gli stessi LLM anche per esaminare, mettere in discussione e criticare il lavoro prodotto da altri modelli.

Il codice e la documentazione sono quindi il risultato di un processo iterativo e supervisionato, nel quale le proposte generate dagli LLM sono state valutate, confrontate, modificate o scartate dall'autore. Le decisioni finali e il risultato complessivo del progetto sono dell'autore.

L'uso degli LLM offre significativi vantaggi in termini di produttività, analisi e revisione, ma introduce anche rischi: nessun processo di verifica può garantire che ogni errore o omissione venga individuato. Questa informativa intende rendere trasparente sia l'ampiezza dell'utilizzo degli LLM sia il loro ruolo effettivo nel processo di sviluppo.

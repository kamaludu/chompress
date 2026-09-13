[![Compressore locale LLM‑ready](https://img.shields.io/badge/Compressore_locale_LLM‑ready-00aa55?style=for-the-badge&label=>&labelColor=004d00)](README.md)
[![License: GPLv3](https://img.shields.io/badge/License-GPLv3-green.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](#)

# Compressore di Contesto per AI (chunk-compress v3.4.1)

**chunk-compress** è uno strumento leggero e trasparente che riduce le dimensioni di file sorgente, script e interi progetti software **prima di incollarli nella chat di un'intelligenza artificiale** (come ChatGPT, Claude, Copilot, DeepSeek o modelli locali).

Sostituendo le porzioni duplicate con abbreviazioni ad altissima efficienza ed eliminando il testo superfluo, **ti permette di risparmiare dal 30% al 60% dei token** (lo spazio disponibile nella finestra della chat), consentendoti di inviare molto più codice in un singolo prompt senza perdere informazioni importanti.

---

## 1. Guida Rapida in 30 Secondi

Non serve configurare nulla. Assicurati solo di avere **Python 3.8 o successivo** installato sul computer.

### Caso 1: Comprimere un singolo file pronto per il prompt (Consigliato!)
Se hai un singolo file di codice o testo e vuoi creare subito un unico prompt da incollare nell'AI:

```sh
python3 cli.py -i mio_script.py -e > prompt_pronto.txt
```

Il file `prompt_pronto.txt` conterrà le istruzioni per l'AI, il piccolo vocabolario delle abbreviazioni e il tuo codice compresso. Apri il file, seleziona tutto e incollalo all'AI!

Puoi anche visualizzarlo al volo a terminale via pipe:
```sh
cat mio_script.py | python3 cli.py -i - -e
```

### Caso 2: Comprimere un'intera cartella o progetto
Se hai una cartella con diversi file e sottocartelle:

```sh
python3 cli.py -i ./cartella_progetto -o out --verify-roundtrip
```
I file compressi verranno salvati dentro la cartella `out/`, mantenendo la stessa identica alberatura originale.

---

## 2. Esempi Pratici Pronti all'Uso

Ecco i comandi più comuni spiegati passo dopo passo, a seconda di cosa vuoi ottenere:

### Esempio 1: "Voglio solo preparare un singolo file da incollare subito nell'AI"
È il caso d'uso quotidiano per eccellenza: hai un file `.py`, uno script `.sh` o un documento `.md` e vuoi creare un prompt unico con tutto già dentro.

```sh
python3 cli.py -i mio_script.py -e > prompt.txt
```
* **Cosa fa**: Comprime `mio_script.py`, aggiunge in cima le istruzioni per l'AI e il vocabolario compatto, e salva tutto in un unico file `prompt.txt`.
* **Cosa devi fare tu**: Apri `prompt.txt`, seleziona tutto (Ctrl+A o Cmd+A), copialo e incollalo nella chat di ChatGPT, Claude o Copilot aggiungendo la tua domanda in fondo.

---

### Esempio 2: "Non voglio creare file sul computer, mostramelo direttamente a terminale"
Se vuoi visualizzare al volo il prompt compresso a schermo o copiarlo al volo:

```sh
cat mio_script.py | python3 cli.py -i - -e
```
* **Cosa fa**: Legge il file dallo standard input (`-i -`) e stampa il prompt pronto direttamente a terminale, senza scrivere nulla sul disco.

---

### Esempio 3: "Ho una cartella con un intero progetto e voglio comprimerlo tutto insieme"
Quando vuoi comprimere un'intera applicazione mantenendo l'albero delle cartelle:

```sh
python3 cli.py -i ./cartella_progetto -o out --verify-roundtrip
```
* **Cosa fa**: Scansiona tutti i file di testo dentro `./cartella_progetto` (escludendo in automatico file binari, immagini e cartelle di sistema come `.git`), crea un dizionario condiviso e salva i file compressi dentro la cartella `out/`.
* **Perché `--verify-roundtrip`**: Fa un controllo matematico automatico per essere certi al 100% che il testo compresso possa essere ricostruito senza perdere nemmeno una virgola.

---

### Esempio 4: "Il file è troppo lungo per la chat e non entra: voglio il massimo risparmio possibile"
Se la chat dell'AI si blocca perché il codice supera il limite di token consentito:

```sh
python3 cli.py -i codice_lungo.py --mode aggressive -e > prompt_minimo.txt
```
* **Cosa fa**: Attiva tutte le ottimizzazioni disponibili (rimozione licenze legali noiose, stripping di commenti, asserzioni di debug e messaggi di log lunghi, sostituzione delle parole ripetute con simboli compatti a 1 token). È la modalità che garantisce il massimo risparmio di spazio (fino al 60%).

---

### Esempio 5: "Voglio che il testo rimanga identico al byte originale, senza togliere righe vuote"
Se devi inviare codice a un collega o a un sistema che richiede il ripristino al 100% bit per bit (comprese tutte le righe vuote e le spaziature originali):

```sh
python3 cli.py -i ./mio_progetto -o out_lossless --mode lossless --verify-roundtrip
```
* **Cosa fa**: Non altera neanche uno spazio né una riga vuota del tuo testo originale. Esegue solo la deduplicazione reversibile delle frasi duplicate.

---

### Esempio 6: "Ho un file gigantesco da 200.000 caratteri che supera il limite di testo della chat"
Se un singolo file è così lungo che la chat dell'AI rifiuta di riceverlo in un unico messaggio:

```sh
python3 cli.py -i file_gigante.py -o out_spezzato --chunk-output --chunk-size 12000
```
* **Cosa fa**: Suddivide il file compresso in piccoli pezzi numerati (`0001.txt`, `0002.txt`, ecc.) dentro la cartella `out_spezzato/chunks/`.
* **Vantaggio**: Non taglia mai una parola o una funzione a metà; ogni pezzo termina sempre andando a capo in modo pulito, così puoi incollarli uno alla volta nella chat.

---

## 3. Guida Approfondita all'Uso dei CHUNKS

### 3.1 Cos'è un Chunk e Perché Serve?
Le interfacce web delle intelligenze artificiali (come ChatGPT, Claude o Copilot) hanno spesso un **limite massimo di caratteri per singolo messaggio** (solitamente tra i 15.000 e i 30.000 caratteri). Se tenti di incollare un file enorme da 100.000 o 300.000 caratteri, la chat mostrerà un errore di testo troppo lungo oppure troncherà brutalmente il testo a metà.

La funzione **Chunking** di `chunk-compress` risolve questo problema: prende il file compresso e lo taglia in frammenti ordinati e autosufficienti (`0001.txt`, `0002.txt`, ecc.), permettendoti di trasmetterli all'AI in sequenza controllata.

---

### 3.2 Le 3 Protezioni di Sicurezza dei Chunk
A differenza di un comando generico come `split` di Linux, `chunk-compress` applica tre algoritmi di sicurezza:

1. **Protezione Atomica (Boundary-Aware)**: Il compressore non taglia **MAI** a metà un'abbreviazione o un token di dizionario (come `^1` o `一`). Se il limite di caratteri cade nel mezzo di un token, il programma arretra istantaneamente all'inizio del token.
2. **Taglio Pulito a Fine Riga (Newline Backtracking)**: Ogni frammento non si interrompe nel mezzo di un'istruzione di codice, ma arretra sempre all'ultimo ritorno a capo valido (`\n`). Ogni chunk contiene blocchi di codice completi.
3. **Il Sigillo di Garanzia (`sha256_full`)**: Quando incolli del testo in una chat, il browser potrebbe troncare accidentalmente delle righe. Nel file `chunks/manifest.json`, il compressore calcola l'impronta digitale esatta (`sha256_full`) dell'intero file riassemblato. L'AI calcolerà l'impronta dopo aver concatenato i chunk: se coincide al 100%, sei certo che non è andato perso nemmeno un carattere durante il copia-incolla!

---

### 3.3 Come Generare i Chunk
Per attivare il chunking su un singolo file o su un progetto, aggiungi `--chunk-output`:

```sh
python3 cli.py -i codice_lungo.py -o out_chunks --chunk-output --chunk-size 14000
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

Segui questa procedura in 4 semplici passaggi:

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

*(Nota: puoi trovare i prompt completi già formulati per l'AI nel file `PROMPT_MASTER.md`).*

---

## 4. Le 3 Modalità di Compressione

| Modalità | Comando | Quando usarla | Cosa fa |
| :--- | :--- | :--- | :--- |
| **Massimo Risparmio** *(Predefinita)* | `--mode aggressive` | Quando hai tanto codice e poco spazio nella chat dell'AI. | Rimuove intestazioni di licenza noiose, commenti, spiegazioni di log chilometriche, annotazioni di tipo, asserzioni e abbrevia le ripetizioni. **È la modalità più potente.** |
| **Conservativa** | `--mode semantic` | Quando vuoi pulire il codice preservando messaggi di errore e asserzioni di test. | Rimuove commenti e spaziature inutili, ma lascia inalterati tutti i messaggi di errore e i controlli interni del codice. |
| **Lossless Pura** | `--mode lossless` | Quando devi poter ricostruire il file identico al 100%, bit per bit. | Non altera nemmeno una riga vuota o uno spazio del tuo testo. Sostituisce solo le frasi duplicate con abbreviazioni reversibili al 100%. |

---

## 5. Cosa Fa il Programma? (In Parole Semplici)

Quando invii codice o documenti a un'intelligenza artificiale, paghi (o consumi memoria di contesto) in base al numero di **token** (frammenti di parole). I file di codice contengono spesso:
1. **Intestazioni ripetitive**: note di copyright, licenze legali uguali su decine di file.
2. **Frasi o funzioni duplicate**: blocchi di codice, controlli di autorizzazione o percorsi web ripetuti ovunque.
3. **Spaziature visive**: spazi e tabulazioni vuote che servono all'occhio umano ma sprecano memoria dell'AI.

**chunk-compress** analizza il testo, compila un piccolo vocabolario di abbreviazioni (usando simboli speciali che l'AI comprende al volo come singoli caratteri) e sostituisce tutte le ripetizioni. 

### Il Risparmio Netto Reale
Il programma calcola il risparmio reale sottraendo anche lo spazio occupato dal vocabolario stesso:
```text
token_risparmiati = token_originali - (token_testo_compresso + token_vocabolario + token_istruzioni)
percentuale_risparmio = ((token_risparmiati) * 100.0) / (token_originali)
```
Se il risultato è positivo, significa che stai risparmiando spazio reale ed effettivo nella finestra della chat!

---

## 6. Tabella dei Comandi Utili

| Opzione | Descrizione Semplice | Esempio d'uso |
| :--- | :--- | :--- |
| **-i, --input** | Il file, la cartella o il trattino `-` per leggere da pipe. | `-i script.py` oppure `-i ./src` |
| **-o, --output** | Cartella dove salvare i risultati (default: `compressed_output`). | `-o risultati` |
| **-e, --envelope** | Incapsula il risultato con le istruzioni per l'AI, pronto per il copia-incolla. | `python3 cli.py -i app.py -e` |
| **--stdout** | Mostra l'output a schermo anziché creare cartelle su disco. | `python3 cli.py -i app.py --stdout` |
| **--mode** | Sceglie tra `aggressive` (massimo risparmio), `semantic` o `lossless`. | `--mode aggressive` |
| **--verify-roundtrip** | Controlla matematicamente che il testo compresso possa essere ricostruito senza errori. | `--verify-roundtrip` |
| **--chunk-output** | Suddivide i file lunghi in piccoli pezzi pronti per la chat. | `--chunk-output --chunk-size 12000` |
| **--chunk-size** | Dimensione nominale massima (in caratteri) di ciascun chunk (default: 16000). | `--chunk-size 14000` |
| **--keep-empty-lines** | Mantiene ogni riga vuota del codice sorgente (lossless pura). | `--keep-empty-lines` |

---

## 7. Domande Frequenti (FAQ)

### L'AI capirà il codice compresso anche se ci sono simboli speciali o ideogrammi?
**Sì.** I modelli linguistici avanzati (come GPT-4o, Claude 3.5/3.7, OpenAI o1/o3, DeepSeek e LLaMA 3) interpretano i simboli compatti e il vocabolario associato come chiavi esatte di un dizionario. Riescono a ragionare sul codice e a ricostruirlo mentalmente senza difficoltà.

### Posso fidarmi che il codice non venga corrotto?
**Assolutamente sì.** Ti basta aggiungere il flag `--verify-roundtrip`. Prima di completare l'operazione, il programma esegue una decompressione di prova e controlla, carattere per carattere, che il risultato coincida perfettamente con l'originale. Se trova anche un solo spazio fuori posto, ti avvisa e blocca il processo.

### Perché compaiono caratteri orientali o simboli come `^1` nel codice compresso?
Perché nei sistemi dei modelli AI (chiamati BPE tokenizers), questi simboli occupano **esattamente 1 o 2 token**, contro i 5 o 10 token che occuperebbero abbreviazioni come `__token_001__`. È proprio questo trucco che garantisce fino al 60% di risparmio reale!

### Serve installare librerie esterne?
**No.** `chunk-compress` funziona immediatamente con la sola installazione base di Python (zero pacchetti esterni obbligatori).

---

## 8. File Inclusi nel Progetto

Per funzionare correttamente, la cartella deve contenere i seguenti file di programma:
- `cli.py`: il comando principale da lanciare da terminale.
- `core.py`: il motore che trova le ripetizioni, gestisce il chunking e le sostituzioni.
- `minifiers.py`: il modulo che pulisce il codice superfluo, le licenze e i commenti.
- `placeholders.py`: il gestore dei simboli e delle abbreviazioni compatti.
- `mapping.py`: il formattatore del dizionario (posizionale o JSON).
- `tokenizer.py`: il misuratore dei token per stimare i risparmi.
- `io_utils.py`: il gestore dei file e del salvataggio sicuro su disco.

---

## Licenza e Contatti

* **Licenza:** GNU General Public License v3.0 ([LICENSE](LICENSE))
* **Autore:** Cristian Evangelisti  
* **Email:** `opensource@cevangel.anonaddy.me`  
* **Repository:** [GitHub kamaludu/chunk-compress](https://github.com/kamaludu/chunk-compress)

### Uso di strumenti di Intelligenza Artificiale nello sviluppo

**chunk-compress** è un'opera sviluppata dall'autore con un uso esteso di strumenti di Intelligenza Artificiale generativa (LLM) per progettazione, implementazione, analisi, debugging, revisione e documentazione.

Gli LLM sono stati utilizzati come strumenti di sviluppo, non come generatori autonomi del progetto. L'autore ha definito l'architettura, i requisiti e le scelte progettuali, orchestrando il lavoro attraverso modelli e sessioni differenti e utilizzando gli stessi LLM anche per esaminare, mettere in discussione e criticare il lavoro prodotto da altri modelli.

Il codice e la documentazione sono quindi il risultato di un processo iterativo e supervisionato, nel quale le proposte generate dagli LLM sono state valutate, confrontate, modificate o scartate dall'autore. Le decisioni finali e il risultato complessivo del progetto sono dell'autore.

L'uso degli LLM offre significativi vantaggi in termini di produttività, analisi e revisione, ma introduce anche rischi: nessun processo di verifica può garantire che ogni errore o omissione venga individuato. Questa informativa intende rendere trasparente sia l'ampiezza dell'utilizzo degli LLM sia il loro ruolo effettivo nel processo di sviluppo.


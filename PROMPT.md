[![Compressore locale LLM‑ready](https://img.shields.io/badge/Compressore_locale_LLM‑ready-00aa55?style=for-the-badge&label=>&labelColor=004d00)](README.md)

# GUIDA AI PROMPT MASTER (v3.4.0)
*(Ottimizzato per modelli di ragionamento avanzato: OpenAI o1/o3/GPT-4o, Anthropic Claude 3.5/3.7 Sonnet, Copilot Think Deeper, DeepSeek R1)*

Questa guida definisce i protocolli di comunicazione tra l'utente e il Large Language Model per l'ingestione, la decompressione in memoria e l'analisi del contesto compresso generato da **chompress**.

---

## Indice dei Flussi Operativi
- **FLUSSO 0: Ingestione Diretta con Prompt Envelope (P4.3 - Consigliato a Singolo Step)**
  *Adatto per:* Singoli file, pipe Unix e contesti che rientrano nella finestra di contesto senza frammentazione su disco.
- **FLUSSO 1: Workflow Controllato Multi-Turn (Senza Chunking)**
  *Adatto per:* Repository multi-file o sessioni in cui si desidera verificare la ricostruzione prima di procedere con refactoring o analisi.
- **FLUSSO 2: Workflow per File Grandi (Con Chunking Atomico)**
  *Adatto per:* File enormi (oltre 50.000-100.000 caratteri) suddivisi in porzioni con verifica di integrità `sha256_full`.

---
---

# FLUSSO 0: Ingestione Diretta con Prompt Envelope (P4.3)
*(Pipeline a singolo passaggio: zero file intermedi, prompt pronto per il copia-incolla immediato)*

Quando si esegue il compressore con l'opzione `--envelope` (o `-e`), l'output è già auto-consistente e racchiuso nei tag `<context>`.

### Prompt da inviare all'AI:

```text
(Incolla qui l'intero output generato con il comando: python3 cli.py -i <file> -e)

--- RICHIESTA OPERATIVA ---
Ho fornito il contesto del codice compresso racchiuso nel tag <context>.
Segui le istruzioni del protocollo [MAP:...] specificato nell'intestazione per interpretare ed espandere mentalmente i placeholder prima di analizzare il sorgente.

Esegui la seguente richiesta:
[INSERISCI QUI LA TUA RICHIESTA, es.:
- "Spiega l'architettura logica e il flusso dei dati del file."
- "Individua potenziali vulnerabilità o race conditions nel modulo."
- "Proponi un refactoring mirato per ottimizzare le prestazioni mantenendo invariate le firme."]
```

---
---

# FLUSSO 1: Workflow Controllato Multi-Turn (Senza Chunking)
*(Pipeline: manifest -> protocollo e vocabolario -> file compressi -> ricostruzione esatta -> analisi)*

Da utilizzare quando si gestiscono repository completi e si vuole validare passo-passo la decompressione del modello prima di richiedere modifiche al codice.

---

### Stadio 1.1: Apertura Sessione e Vincoli di Esecuzione
*(Impedisce al modello di anticipare azioni o inventare porzioni mancanti)*

```text
Sto per fornirti in sequenza controllata:
1) Il manifest opzionale della struttura del progetto (manifest.json)
2) Il protocollo e il vocabolario di mappatura dei placeholder (protocol_header.txt e mapping_subset.txt oppure mapping_subset.json)
3) Uno o più file compressi contenenti i placeholder

Il tuo compito operativo sarà:
- Registrare la struttura dei percorsi e l'alfabeto dei token.
- Trattare il mapping come dizionario deterministico esatto: token -> contenuto originale.
- Attendere le mie istruzioni prima di applicare le sostituzioni.
- Ricostruire i file in modo rigoroso, carattere per carattere, senza invenzioni, correzioni di stile o riformattazioni di spaziature.
- Procedere con analisi o modifiche solo dopo aver confermato l'avvenuta ricostruzione.

Regole vincolanti:
- NON iniziare la ricostruzione fino al comando esplicito: "Procedi con la ricostruzione".
- Conferma la ricezione di ciascun elemento prima di passare alla fase successiva.

Conferma di aver compreso e dichiara quando sei pronto a ricevere il manifest o il dizionario.
```

---

### Stadio 1.2: Inserimento Manifest di Progetto (Opzionale)
```text
Questo è il file manifest.json del progetto.

Contiene:
- paths: elenco ordinato dei percorsi relativi dei file
- files: indice del file, hash SHA256 target e lista dei placeholder presenti
- ph: indice analitico dei placeholder
- v: versione dello schema

Istruzioni:
- Non applicare alcuna trasformazione.
- Non ricostruire nulla.
- Conferma solo la corretta ricezione indicando il numero totale di file censiti nel manifest.

(Incolla qui il contenuto di manifest.json)
```

---

### Stadio 1.3: Inserimento Protocollo e Dizionario di Mappatura
*(Supporta sia il nuovo Positional Mapping a zero chiavi sia il formato JSON legacy)*

```text
Questo è il dizionario di mappatura dei placeholder generato da chompress.

Se l'intestazione inizia con [MAP:INDEXED...], interpretalo come mapping posizionale ordinale:
- L'header indica la regola di generazione dei token (es. caratteri CJK contigui cjk_start=19968 count=N, prefissi numerici prefix='^', o intervalli multipli cjk_ranges).
- Le voci nel payload sono separate dal marcatore sentinella (es. ---§---).
- Ciascuna voce corrisponde esattamente all'n-esimo token generato dalla sequenza del protocollo.

Se l'intestazione è [MAP:JSON], usalo come dizionario JSON standard {token: contenuto}.

Istruzioni:
- Registra la corrispondenza esatta token -> contenuto.
- NON applicare ancora le sostituzioni al codice.
- Conferma la ricezione riepilogando quanti token univoci risultano registrati e la famiglia dell'alfabeto (es. CJK atomico, prefisso '^', virgolette o JSON).

(Incolla qui protocol_header.txt seguito da mapping_subset.txt, oppure mapping_subset.json)
```

---

### Stadio 1.4: Inserimento dei File Compressi
```text
Di seguito ti trasmetto uno o più file compressi contenenti i placeholder registrati.

Istruzioni:
- Registra il testo di ciascun file associandolo al rispettivo percorso.
- NON applicare ancora il dizionario.
- Conferma la ricezione elencando i file ricevuti e il numero approssimativo di caratteri per ciascuno.

(Incolla qui i file compressi preceduti dal relativo percorso, es: --- FILE: src/main.py ---)
```

---

### Stadio 1.5: Esecuzione della Ricostruzione Esatta
```text
Procedi con la ricostruzione.

Applica le sostituzioni inverse su ciascun file compresso, sostituendo ogni placeholder con il rispettivo contenuto originale del vocabolario.

Regole tassative di decodifica:
1. Nessuna invenzione o inferenza di codice non presente.
2. Nessuna correzione automatica di sintassi, bug preesistenti o nomi di variabile.
3. Risoluzione dei prefissi in ordine di lunghezza decrescente: i token più lunghi hanno precedenza per evitare collisioni di prefisso (es. ^10 non deve essere confuso con ^1 seguito da 0).
4. Nessuna alterazione di indentazione o righe. Ricostruzione esatta carattere per carattere.
5. Se un token incontrato nel testo non esiste nel vocabolario, interrompi immediatamente ed esponi il token mancante.
6. Se è stato fornito manifest.json, verifica la corrispondenza con l'hash sha indicato per il file.

Restituisci lo stato finale: "RICOSTRUZIONE COMPLETATA CON SUCCESSO" e mostra il codice ricostruito (o attendi la richiesta successiva).
```

---

### Stadio 1.6: Analisi, Refactoring o Modifiche
```text
Ora che il contesto è interamente decodificato e allineato in memoria, esegui la seguente richiesta:

(Inserisci qui l'obiettivo, es.:
- "Spiega come interagiscono i moduli ricostruiti."
- "Applica una patch per gestire l'errore di timeout sulla funzione connect_db()."
- "Genera una suite di unit test per la classe handler.")

Regole:
- Mantieni rigorosamente l'architettura originale.
- Modifica solo le porzioni direttamente interessate dalla richiesta.
```

---
---

# FLUSSO 2: Workflow per File Grandi (Con Chunking Atomico)
*(Pipeline: chunks/manifest.json -> mapping -> frammenti chunk -> riassemblaggio -> verifica sha256_full -> decodifica -> analisi)*

Da utilizzare quando i file sorgente superano la dimensione del prompt o il limite di output della sessione e sono stati suddivisi tramite `--chunk-output`.

---

### Stadio 2.1: Apertura Sessione Chunking
```text
Sto per fornirti un file di grandi dimensioni suddiviso in frammenti ordinati (chunk) tramite chompress.

Riceverai in sequenza:
1) Il file descrittore: chunks/manifest.json
2) Il dizionario dei token: protocol_header.txt + mapping_subset.txt (o mapping_subset.json)
3) I singoli file chunk sequenziali (0001.txt, 0002.txt, ...)

Il tuo compito sarà:
- Registrare ciascun chunk senza eseguire azioni premature.
- Riassemblare il testo concatenando i chunk nell'ordine sequenziale esatto indicato nel manifest.
- Verificare l'integrità del testo compresso calcolando e confrontando l'hash SHA-256 con il campo sha256_full.
- Solo a verifica confermata, applicare il dizionario per espandere i placeholder.
- Non alterare alcuna porzione del testo.

Conferma quando sei pronto a ricevere chunks/manifest.json.
```

---

### Stadio 2.2: Inserimento chunks/manifest.json
```text
Questo è chunks/manifest.json.

Definisce per ciascun file:
- percorso di destinazione
- elenco ordinato dei chunk (es. 0001.txt, 0002.txt, ...)
- sha256_full: hash SHA-256 atteso del file compresso concatenato (prima dell'espansione dei placeholder)
- chunk_size e total_len

Istruzioni:
- NON iniziare il riassemblaggio.
- NON applicare alcuna sostituzione.
- Conferma la ricezione indicando i percorsi dei file e il numero totale di chunk attesi per ciascuno.

(Incolla qui il contenuto di chunks/manifest.json)
```

---

### Stadio 2.3: Inserimento del Vocabolario di Mappatura
```text
Questo è il vocabolario dei placeholder associato ai chunk.

Istruzioni:
- Registralo come vocabolario esatto.
- NON applicare ancora le sostituzioni.
- Conferma la ricezione indicando il formato del protocollo e il numero di voci censite.

(Incolla qui protocol_header.txt + mapping_subset.txt oppure mapping_subset.json)
```

---

### Stadio 2.4: Inserimento dei Frammenti Chunk
```text
Ti invio di seguito i frammenti numerati progressivamente.

Istruzioni:
- Memorizza ciascun blocco associandolo al file e al progressivo numerico indicato (es. chunk 0001.txt, chunk 0002.txt).
- NON ricostruire ancora.
- Conferma la ricezione specificando i progressivi ricevuti. Se riscontri buchi nella numerazione, segnalalo immediatamente.

(Incolla qui i singoli chunk contrassegnati dal loro nome, es. === CHUNK: src/service.py/0001.txt ===)
```

---

### Stadio 2.5: Riassemblaggio a Due Stadi e Verifica di Integrità
*(Comando da inviare solo dopo aver trasmesso tutti i chunk previsti dal manifest)*

```text
Procedi con il riassemblaggio e la ricostruzione.

Esegui tassativamente la procedura nei seguenti due stadi consecutivi:

STADIO 1: CONCATENAZIONE E VERIFICA INTEGRITA (sha256_full)
1. Per ciascun file, concatena i blocchi nell'ordine esatto specificato nell'array chunks di chunks/manifest.json (0001.txt + 0002.txt + ...).
2. Calcola l'hash SHA-256 del testo compresso risultante dalla concatenazione.
3. Confronta l'hash calcolato con il valore atteso presente nel campo sha256_full di chunks/manifest.json:
   - Se COINCIDE: segnala "STADIO 1 SUPERATO: Integrità sha256_full verificata con successo" e passa allo Stadio 2.
   - Se NON COINCIDE: BLOCCA tassativamente la procedura e restituisci: "ERRORE CRITICO: Discrepanza sha256_full sul testo compresso riassemblato. Rilevata possibile perdita o corruzione nel copia-incolla dei chunk."

STADIO 2: ESPANSIONE PLACEHOLDER E DECOMPRESSIONE
4. Sul testo compresso verificato allo Stadio 1, espandi ciascun placeholder sostituendolo con il testo corrispondente registrato nel mapping.
5. Rispetta la precedenza longest-first sui token e non effettuare alcuna variazione a spazi o codice.

Restituisci:
- Resoconto esplicito della verifica di Stadio 1 (hash calcolato vs sha256_full atteso).
- Stato di completamento: "RICOSTRUZIONE INTEGRALE COMPLETATA".
- Il codice decodificato pronto per l'analisi.
```

---

### Stadio 2.6: Sessione Operativa sul Codice Ricostruito
```text
Ora che i file sono stati verificati e decompressi con successo, procedi con l'elaborazione del seguente task:

(Inserisci qui il task da eseguire sul codice ricomposto)
```

---

## Note Tecniche per l'Utente Operatore

1. **Garanzia Boundary-Aware a Monte**:  
   I chunk creati da `chompress` non tagliano mai a metà i simboli di placeholder (`一`, `^1`, `«1»`, ecc.) e arretrano sempre al delimitatore di riga `\n` più vicino. Ciascun chunk termina sempre con istruzioni sintatticamente integre.
2. **Ruolo Chiave di `sha256_full`**:  
   Verificare `sha256_full` prima di decodificare i placeholder permette di isolare immediatamente eventuali troncamenti o alterazioni introdotte dall'interfaccia di chat durante il copia-incolla, evitando di sprecare token in analisi su codice parziale.
3. **Formule di Risparmio di Riferimento (ASCII Pura)**:
   ```text
   net_tokens_saved = original_tokens - (compressed_payload_tokens + mapping_tokens + protocol_tokens)
   net_compression_ratio = ((net_tokens_saved) * 100.0) / (original_tokens)
   ```


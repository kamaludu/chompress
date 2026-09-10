[![Compressore locale LLM‑ready](https://img.shields.io/badge/Compressore_locale_LLM‑ready-00aa55?style=for-the-badge&label=>&labelColor=004d00)](README.md)

# PROMPT MASTER - senza uso di CHUNKS
(Ottimizzato per modelli di ragionamento avanzato: Copilot Think Deeper, Claude 3.7 Sonnet, OpenAI o1/o3)

Pipeline ottimale:  
**manifest -> mapping -> file compressi -> ricostruzione -> analisi**

---

## 1) Inizio sessione
*(Stabilisce il contesto operativo, definisce i ruoli e impedisce al modello di anticipare azioni non richieste)*

```text
Sto per fornirti in sequenza controllata:
1) un manifest dei file (struttura, percorsi, placeholder usati)
2) un mapping dei placeholder -> contenuto originale (mapping_subset.json)
3) uno o più file compressi contenenti i placeholder

Il tuo compito sarà:
- leggere il manifest come mappa della struttura del progetto
- leggere il mapping come vocabolario esatto dei placeholder
- attendere le mie istruzioni prima di applicare il mapping ai file compressi
- ricostruire i file originali in modo esatto, carattere per carattere, senza invenzioni o correzioni implicite
- procedere con l'analisi o le modifiche solo su mia richiesta esplicita

Nota vincolante:
- Non ricostruire nulla finché non ricevi il comando esplicito "Procedi con la ricostruzione".
- Ogni fase deve essere confermata prima di passare alla successiva.

Conferma quando sei pronto a ricevere il manifest.
```

---

## 2) Incolla manifest.json
*(Il modello carica la struttura senza interpretarla)*

```text
Questo è il manifest dei file (manifest.json).

Contiene:
- paths: elenco ordinato dei file del progetto
- files: per ogni file, indice -> sha256 del target -> placeholder usati
- ph: metadati dei placeholder (sha256, lunghezza)
- v: versione dello schema

Istruzioni:
- Non usarlo ancora.
- Non tentare di ricostruire nulla.
- Conferma solo che il manifest è stato caricato correttamente indicando quanti file sono elencati.

(incolla qui il contenuto di manifest.json)
```

---

## 3) Incolla mapping_subset.json
*(Il modello carica il dizionario dei placeholder)*

```text
Questo è il mapping dei placeholder (mapping_subset.json).
Usalo come dizionario deterministico placeholder -> contenuto.

Istruzioni:
- Non applicare ancora il mapping.
- Non tentare di ricostruire i file.
- Conferma solo che il mapping è stato caricato indicando il numero totale di placeholder registrati.

(incolla qui il contenuto di mapping_subset.json)
```

---

## 4) Incolla file compressi
*(Il modello riceve il testo compresso)*

```text
Ora ti fornisco uno o più file compressi che contengono i placeholder definiti nel mapping.

Istruzioni:
- Non ricostruire ancora.
- Non applicare il mapping.
- Conferma solo la ricezione indicando i percorsi dei file ricevuti.

(incolla qui il contenuto del file o dei file compressi)
```

---

## 5) Ricostruzione esatta
*(Esecuzione vincolata della de-sostituzione)*

```text
Procedi con la ricostruzione.

Sostituisci ogni placeholder presente nei file con il rispettivo contenuto presente in mapping_subset.json.

Regole tassative:
1. Nessuna invenzione di codice o testo.
2. Nessuna correzione automatica di sintassi o refusi preesistenti.
3. Nessuna riformattazione di spazi o rientri.
4. Ricostruzione esatta, carattere per carattere.
5. Se un token (es. §§s001§§ o §§b001§§) non esiste nel mapping, interrompi immediatamente e segnalalo.
6. Se è presente lo sha nel manifest.json, verifica la corrispondenza con il testo ricostruito.

Restituisci il file ricostruito.
```

---

## 6) Analisi o modifiche
*(Fase eseguibile solo a ricostruzione confermata)*

```text
Ora analizza il file ricostruito ed esegui la seguente richiesta:

(inserisci qui la tua richiesta, es.:
- "Trova potenziali bug di concurrency nella funzione X"
- "Proponi un refactoring mirato mantenendo le firme invariate"
- "Spiega il flusso logico del modulo")

Regole:
- Mantieni rigorosamente la struttura del progetto.
- Non alterare porzioni di codice non richieste.
```

---

## Sequenza finale consigliata (Workflow standard)

```text
Passo 1: Inizio sessione
Passo 2: Incolla manifest.json (opzionale)
Passo 3: Incolla mapping_subset.json
Passo 4: Incolla file compressi
Passo 5: Comando "Procedi con la ricostruzione"
Passo 6: Analisi o modifiche sul codice ricostruito
```

---
---

# PROMPT MASTER — con uso di CHUNKS

Pipeline ottimale:  
**chunks/manifest.json -> mapping_subset.json -> chunk files -> riassemblaggio -> verifica integrità chunk (sha256_full) -> ricostruzione -> analisi**

---

## 1) Inizio sessione
```text
Sto per fornirti, in sequenza controllata:

1) il file chunks/manifest.json  
   (specifica l'elenco ordinato dei chunk per ciascun file e il checksum sha256_full del file compresso)

2) il file mapping_subset.json  
   (dizionario token placeholder -> contenuto originale)

3) uno o più file chunk (es. 0001.txt, 0002.txt)  
   (sezioni di testo compresso pronte per il riassemblaggio)

Il tuo compito sarà:
- caricare ogni elemento confermandone la ricezione senza eseguire azioni premature
- riassemblare i file concatenando i chunk nell'ordine esatto indicato nel manifest
- verificare l'integrità del testo compresso riassemblato confrontandone l'hash con sha256_full
- sostituire i placeholder con i rispettivi contenuti del mapping
- segnalare immediatamente chunk mancanti, token non risolti o disallineamenti di checksum
- non inventare, non correggere e non riformattare nulla

Conferma quando sei pronto a ricevere chunks/manifest.json.
```

---

## 2) Incolla chunks/manifest.json
```text
Questo è chunks/manifest.json.

Contiene per ciascun file:
- percorso relativo di appartenenza
- lista ordinata dei chunk che compongono il file (es. 0001.txt, 0002.txt)
- sha256_full: hash SHA256 atteso del file compresso intero (prima della de-sostituzione)
- dimensione totale del file compresso

Istruzioni:
- NON iniziare il riassemblaggio.
- NON applicare il mapping.
- Conferma solo la corretta ricezione riepilogando i file elencati e il numero di chunk per ciascuno.

(incolla qui chunks/manifest.json)
```

---

## 3) Incolla mapping_subset.json
```text
Questo è il file mapping_subset.json.

Istruzioni:
- Registralo come vocabolario placeholder -> contenuto originale.
- NON applicare ancora le sostituzioni.
- Conferma solo la ricezione indicando quanti token sono registrati.

(incolla qui mapping_subset.json)
```

---

## 4) Incolla i chunk files
```text
Ora ti invio i chunk generati dal compressore.

Ogni chunk appartiene a un file specifico ed è numerato progressivamente (0001.txt, 0002.txt, ...).

Istruzioni:
- Memorizza ciascun chunk mantenendo traccia del file di appartenenza e del numero progressivo.
- NON ricostruire ancora.
- Conferma la ricezione di ciascun blocco.
- Se mancano chunk rispetto a quanto specificato nel manifest, segnalalo immediatamente.

(incolla qui uno o più chunk)
```

---

## 5) Riassemblaggio e Ricostruzione (Due Stadi)
*(Comando da inviare solo dopo aver trasmesso tutti i chunk)*

```text
Procedi con il riassemblaggio e la ricostruzione.

Esegui tassativamente la procedura nei seguenti due stadi consecutivi:

STADIO 1: RIASSEMBLAGGIO E VERIFICA INTEGRITA CHUNK
1. Per ciascun file, concatena i chunk nell'ordine sequenziale esatto specificato in chunks/manifest.json (0001.txt + 0002.txt + ...).
2. Calcola l'hash SHA256 del testo compresso ottenuto.
3. Confronta l'hash calcolato con sha256_full presente in chunks/manifest.json:
   - Se coincide: segnala "INTEGRITA CHUNK VERIFICATA (sha256_full OK)" e procedi allo Stadio 2.
   - Se non coincide: BLOCCA il processo e segnala "ERRORE: mismatch sha256_full sul testo compresso riassemblato".

STADIO 2: ESPANSIONE PLACEHOLDER E RICOSTRUZIONE
4. Sul testo compresso verificato, applica le sostituzioni usando mapping_subset.json:
   - Sostituisci ogni occorrenza di token con il relativo contenuto.
   - Se un token non è presente nel mapping, interrompi e segnala il token mancante.
5. Se ho fornito anche il manifest.json globale del progetto, confronta lo SHA256 del testo finale decodificato con il campo sha del file.

Restituisci:
- Esito della verifica di Stadio 1 (sha256_full calcolato vs atteso)
- Stato finale: RICOSTRUITO CON SUCCESSO / FALLITO
- Il testo del file ricostruito (se richiesto).

Regole di esecuzione:
- Nessuna alterazione o correzione implicita.
- Ricostruzione esatta carattere per carattere.
```

---

## 6) Analisi o modifiche (solo dopo ricostruzione confermata)
```text
Ora che i file sono stati riassemblati e ricostruiti con successo, esegui la seguente operazione:

(inserisci qui l'obiettivo, es.:
- "Spiega come interagiscono i moduli ricostruiti"
- "Individua vulnerabilità o race conditions nel file X"
- "Applica la seguente modifica al file ricostruito: ...")

Regole:
1. Mantieni intatta la struttura del progetto.
2. Non inventare parti non presenti.
3. Se una modifica richiesta impatta parti esterne, avvisami prima.
```

---

## 7) Sequenza consigliata (Workflow con Chunking)

```text
1. Inizio sessione
2. Incolla chunks/manifest.json
3. Incolla mapping_subset.json
4. Incolla tutti i file chunk (suddivisi per cartella e numerazione)
5. Comando: "Procedi con il riassemblaggio e la ricostruzione"
6. Validazione sha256_full -> Espansione mapping -> Output
7. Sessione di analisi, refactoring o coding sul codice ricostruito
```

---

## 8) Note Tecniche per l'Utente

1. **Integrità dei Token garantita a monte**: I chunk generati da `chunk-compress` non tagliano mai a metà un placeholder (`§§s...§§` o `§§b...§§`) e arretrano sempre al newline precedente, garantendo che ciascun frammento sia sintatticamente coerente.
2. **Ruolo di `sha256_full`**: Questo valore presente in `chunks/manifest.json` convalida il testo compresso riassemblato (concatenazione dei chunk). Serve a isolare immediatamente eventuali corruzioni o omissioni introdotte durante il copia-incolla nella chat.
3. **Ordine dei Chunk**: L'ordine di concatenazione è stabilito rigorosamente dall'array `chunks` associato al file in `chunks/manifest.json`. Non concatenare i chunk in ordine sparso.


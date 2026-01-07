# OEIS-probe
Tool CLI Python per riconoscere sequenze di interi archiviate su OEIS, con ricerca offline su stripped/names e cache SQLite. Ideale come “oracolo esterno” da laboratorio per validare le sequenze generate da algoritmi, regressioni, e riconoscimento rapido di pattern noti.

**Sequence fingerprinting** contro OEIS:
- online via `&fmt=json` (JSON API)
- offline via file `stripped(.gz)` + opzionale `names(.gz)`
- cache SQLite per non martellare OEIS (e per non far bannare la scimmia 🐒)

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

# Quick start

## probe online
oeis-probe "1,2,3,6,11,23,47,106"

## salva JSON
oeis-probe "1,2,3,6,11,23,47,106" --json-out oeis_hits.json

## fetch completo per A-number
oeis-probe fetch A000045

## Offline mode (stripped/names)
Scarica i dump (aggiornati quotidianamente):

```bash
wget -O stripped.gz https://oeis.org/stripped.gz
wget -O names.gz    https://oeis.org/names.gz

Poi:

oeis-probe "1,2,3,6,11,23,47,106" \
  --offline-stripped ./stripped.gz \
  --offline-names ./names.gz
```

Nota: questo repo NON include i dump OEIS. Se li usi/distribuisci, devi rispettare
CC BY-SA 4.0 + EULA OEIS (attribution e condizioni).

Ecco un **capitolo “Esempi”** pronto da incollare nel tuo `README.md` (in Italiano, stile laboratorio).

---

## 🧪 Esempi d’uso (laboratorio)
`oeis-probe` cerca corrispondenze tra una sequenza di interi e le sequenze OEIS, usando:
- **online**: OEIS JSON API (default)
- **offline** (opzionale): file `stripped(.gz)` e `names(.gz)` scaricabili da OEIS

> Nota: il tool valuta la qualità del match cercando la **miglior corrispondenza consecutiva** (match_len) dentro i termini OEIS e calcola uno **score** in [0..1].

### 1) Fibonacci “pulita” (match perfetto)
```bash
oeis-probe "0,1,1,2,3,5,8,13,21,34,55,89,144" --max-hits 5
```

Output atteso: A000045 in cima.

### 2) Ranking: `strict` vs `prefer-early`
Quando tanti risultati hanno score=1.00, puoi preferire quelli che matchano **subito dall’inizio** (`at` più piccolo):

```bash
oeis-probe "0,1,1,2,3,5,8,13,21,34,55,89,144" --max-hits 5 --rank prefer-early
```

- `--rank strict` (default): ordina per score e match_len
- `--rank prefer-early`: a parità di score/match_len preferisce `at` più piccolo

### 3) Disambiguazione vera: “aggiungi un termine oltre la divergenza”
A volte una sequenza “cugina” coincide su un prefisso lungo (es. alcune varianti di “dying rabbits” possono imitare Fibonacci per molti termini).

La soluzione più semplice è **allungare** la query finché la cugina diverge:

```bash
oeis-probe "0,1,1,2,3,5,8,13,21,34,55,89,144,233,377" --max-hits 5 --rank prefer-early
```

Se una variante diverge prima, sparirà (o scenderà) appena includi il termine “killer”.

### 4) Recamán (match perfetto) + “parenti stretti”
```bash
oeis-probe "0,1,3,6,2,7,13,20,12,21,11,22,10,23,9,24,8,25" --max-hits 5 --rank prefer-early
```

Tipico: A005132 in cima + varianti molto simili (stesso prefisso).

### 5) “Recamán mutata” (un termine sbagliato): niente panico
Se cambi **un solo termine**, OEIS può non restituire risultati direttamente. In quel caso usa:
- `--relax-online` → se online non trova nulla, riprova accorciando la query (toglie termini dalla fine)
- `--min-match-len N` → filtra risultati troppo deboli
- `--explain-top` → ti dice dove la query diverge dal top hit

Esempio: ultimo termine sbagliato (26 invece di 25):

```bash
oeis-probe "0,1,3,6,2,7,13,20,12,21,11,22,10,23,9,24,8,26" \
  --max-hits 5 --rank prefer-early \
  --relax-online --min-match-len 10
```

Esempio: corruzione “in mezzo” + spiegazione del mismatch:

```bash
oeis-probe "0,1,3,6,2,7,13,20,12,21,11,99,10,23,9,24,8,25" \
  --max-hits 5 --rank prefer-early \
  --relax-online --min-match-len 10 \
  --explain-top
```

Output extra atteso (indicativo):
- `first mismatch at query[11] (#12) -> got 99; expected 22 ...`

### 6) Van Eck (esempio “non banale”)
```bash
oeis-probe "0,0,1,0,2,0,2,2,1,6,0,5,0,2,6,5" --max-hits 5 --rank prefer-early
```

### 7) Look-and-say (termini “grossi”)
```bash
oeis-probe "1,11,21,1211,111221,312211,13112221" --max-hits 5 --rank prefer-early
```

### 8) Fetch di una sequenza per A-number (JSON)
```bash
oeis-probe fetch A000045
```

Utile per:
- ispezionare `data`
- confrontare varianti
- trovare il punto di divergenza tra due sequenze

### 9) Salva risultati in JSON (per pipeline/script)
```bash
oeis-probe "2,3,5,7,11,13,17,19,23,29,31,37" --max-hits 5 --json-out /tmp/hits.json
```

### 10) Modalità offline (stripped / names)
Se hai scaricato `stripped(.gz)` e opzionalmente `names(.gz)`:

```bash
oeis-probe "1,4,9,16,25,36,49,64,81,100" \
  --offline-stripped /path/to/stripped.gz \
  --offline-names /path/to/names.gz \
  --no-online \
  --max-hits 5
```

Oppure online+offline insieme (merge dei risultati):

```bash
oeis-probe "1,4,9,16,25,36,49,64,81,100" \
  --offline-stripped /path/to/stripped.gz \
  --offline-names /path/to/names.gz \
  --max-hits 5
```

### Suggerimenti pratici
- Se ti escono troppi `1.00`, usa `--rank prefer-early`.
- Se ottieni “No hits” su sequenze mutate/rumorose, usa `--relax-online` e alza `--min-match-len`.
- `--explain-top` è il “martello”: ti dice **dove** hai rotto la sequenza rispetto al miglior candidato.

# Respectful usage
usa pochi hit e cache (default ok)
non fare spam di query automatiche senza backoff
offline consigliato per batch/ricerche pesanti

# License
Codice: MIT (vedi LICENSE).
Dati OEIS: licenze e termini sul sito OEIS.

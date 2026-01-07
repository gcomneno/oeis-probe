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

# Respectful usage
usa pochi hit e cache (default ok)
non fare spam di query automatiche senza backoff
offline consigliato per batch/ricerche pesanti

# License
Codice: MIT (vedi LICENSE).
Dati OEIS: licenze e termini sul sito OEIS.

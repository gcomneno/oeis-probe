"""
oeis_probe.py — tiny OEIS helper for "sequence fingerprinting".

What it does
------------
1) Online probe (OEIS JSON API): given a list of terms, it queries:
      https://oeis.org/search?q=...&fmt=json

2) Offline probe (optional): if you have a local copy of `stripped` (or `stripped.gz`)
   and optionally `names` (or `names.gz`), it can search by subsequence using fast
   substring matching on each line.

Notes
-----
- This script is intentionally conservative: it does not try clever transforms unless you ask.
- OEIS endpoints and the stripped/names file formats are documented on the OEIS Download page.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

DEFAULT_OEIS_BASE = "https://oeis.org"
DEFAULT_CACHE_TTL_DAYS = 30

__all__ = [
    "DEFAULT_OEIS_BASE",
    "DEFAULT_CACHE_TTL_DAYS",
    "OeisHit",
    "OeisCache",
    "parse_terms",
    "terms_to_query_string",
    "oeis_search_online",
    "oeis_fetch_by_id_online",
    "hits_from_online_json",
    "oeis_search_offline_stripped",
    "pretty_print_hits",
    "hits_to_jsonable",
    "best_subsequence_match",
]


def eprint(*args: object, **kwargs: object) -> None:
    print(*args, file=sys.stderr, **kwargs)


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def now_epoch() -> int:
    return int(time.time())


def parse_terms(s: str) -> list[int]:
    """
    Parse "1,2,3" or "1 2 3" or "1, 2, 3" into [1,2,3].
    """
    raw = s.strip()
    if not raw:
        raise ValueError("empty terms string")
    parts: list[str] = []
    for chunk in raw.replace(",", " ").split():
        parts.append(chunk)
    terms: list[int] = []
    for p in parts:
        try:
            terms.append(int(p))
        except ValueError as ex:
            raise ValueError(f"bad term '{p}' (expected integer)") from ex
    return terms


def terms_to_query_string(terms: Sequence[int], max_terms: int | None = None) -> str:
    if max_terms is not None:
        terms = terms[:max_terms]
    return ",".join(str(x) for x in terms)


@contextmanager
def open_text_maybe_gz(path: Path):
    """
    Open a text file that can be plain or .gz.
    """
    if path.suffix == ".gz":
        f = gzip.open(path, "rt", encoding="utf-8", errors="replace")
    else:
        f = path.open("rt", encoding="utf-8", errors="replace")
    try:
        yield f
    finally:
        f.close()


@dataclass(frozen=True)
class OeisHit:
    a_number: str
    name: str
    offset: str
    data_terms: list[int]
    match_len: int
    match_at: int | None  # index inside data_terms where input aligns (best)
    score: float  # 0..1


class OeisCache:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    created_at INTEGER NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            con.commit()

    def get(self, key: str, ttl_days: int) -> str | None:
        cutoff = now_epoch() - ttl_days * 86400
        with sqlite3.connect(self.db_path) as con:
            row = con.execute(
                "SELECT created_at, payload FROM cache WHERE key = ?",
                (key,),
            ).fetchone()
        if not row:
            return None
        created_at, payload = int(row[0]), str(row[1])
        if created_at < cutoff:
            return None
        return payload

    def put(self, key: str, payload: str) -> None:
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "INSERT OR REPLACE INTO cache(key, created_at, payload) VALUES(?,?,?)",
                (key, now_epoch(), payload),
            )
            con.commit()


def http_get_json(url: str, timeout: float = 10.0, user_agent: str = "oeis-probe/0.1") -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": user_agent, "Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read().decode("utf-8", errors="replace")
    return json.loads(data)


def oeis_search_online(
    terms: Sequence[int],
    *,
    oeis_base: str = DEFAULT_OEIS_BASE,
    max_query_terms: int = 40,
    timeout: float = 10.0,
    cache: OeisCache | None = None,
    cache_ttl_days: int = DEFAULT_CACHE_TTL_DAYS,
) -> dict:
    q_terms = terms_to_query_string(terms, max_terms=max_query_terms)
    q = urllib.parse.quote(q_terms, safe=",")
    url = f"{oeis_base}/search?q={q}&fmt=json"
    key = f"GET:{url}"
    if cache is not None:
        cached = cache.get(sha256_hex(key), ttl_days=cache_ttl_days)
        if cached is not None:
            return json.loads(cached)
    payload = http_get_json(url, timeout=timeout)
    if cache is not None:
        cache.put(sha256_hex(key), json.dumps(payload))
    return payload


def oeis_fetch_by_id_online(
    a_number: str,
    *,
    oeis_base: str = DEFAULT_OEIS_BASE,
    timeout: float = 10.0,
    cache: OeisCache | None = None,
    cache_ttl_days: int = DEFAULT_CACHE_TTL_DAYS,
) -> dict:
    a_number = a_number.upper().strip()
    if not a_number.startswith("A") or len(a_number) != 7:
        raise ValueError("expected A-number like A000045")
    q = urllib.parse.quote(f"id:{a_number}")
    url = f"{oeis_base}/search?q={q}&fmt=json"
    key = f"GET:{url}"
    if cache is not None:
        cached = cache.get(sha256_hex(key), ttl_days=cache_ttl_days)
        if cached is not None:
            return json.loads(cached)
    payload = http_get_json(url, timeout=timeout)
    if cache is not None:
        cache.put(sha256_hex(key), json.dumps(payload))
    return payload


def parse_oeis_data_terms(data_field: str, max_terms: int = 200) -> list[int]:
    """
    OEIS JSON 'data' is a comma-separated string of integers.
    """
    s = data_field.strip()
    if not s:
        return []
    items = [x.strip() for x in s.split(",")]
    out: list[int] = []
    for it in items:
        if not it:
            continue
        try:
            out.append(int(it))
        except ValueError:
            break
        if len(out) >= max_terms:
            break
    return out


def best_subsequence_match(hay: Sequence[int], needle: Sequence[int]) -> tuple[int, int | None]:
    """
    Find best consecutive match length of needle inside hay.
    Returns (match_len, match_at_index_in_hay).
    """
    if not needle or not hay:
        return 0, None
    best_len = 0
    best_at: int | None = None
    n = len(needle)
    for start in range(len(hay)):
        if len(hay) - start <= best_len:
            break
        k = 0
        while start + k < len(hay) and k < n and hay[start + k] == needle[k]:
            k += 1
        if k > best_len:
            best_len = k
            best_at = start
        if best_len == n:
            break
    return best_len, best_at


def hits_from_online_json(terms: Sequence[int], payload: dict, max_hits: int = 10) -> list[OeisHit]:
    results = payload.get("results") or []
    needle = list(terms)
    hits: list[OeisHit] = []
    for r in results[: max_hits * 3]:
        a = (r.get("number") or "").strip()
        if a and a.isdigit():
            a_number = f"A{int(a):06d}"
        else:
            a_number = (r.get("id") or "").strip() or "A??????"
        name = (r.get("name") or "").strip()
        offset = (r.get("offset") or "").strip()
        data_terms = parse_oeis_data_terms(r.get("data", ""), max_terms=400)
        mlen, mat = best_subsequence_match(data_terms, needle)
        denom = max(1, min(len(needle), len(data_terms)))
        score = mlen / denom
        hits.append(
            OeisHit(
                a_number=a_number,
                name=name,
                offset=offset,
                data_terms=data_terms,
                match_len=mlen,
                match_at=mat,
                score=score,
            )
        )
    hits.sort(key=lambda h: (h.score, h.match_len), reverse=True)
    return hits[:max_hits]


def load_names_map(names_path: Path, limit: int | None = None) -> dict:
    """
    Load names.gz or names into {Axxxxxx: name}.
    """
    names: dict = {}
    with open_text_maybe_gz(names_path) as f:
        for line in f:
            if not line or line.startswith("#"):
                continue
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split(" ", 1)
            if len(parts) != 2:
                continue
            aid, nm = parts[0].strip(), parts[1].strip()
            if aid.startswith("A") and len(aid) == 7:
                names[aid] = nm
            if limit is not None and len(names) >= limit:
                break
    return names


def iter_stripped_lines(stripped_path: Path) -> Iterator[tuple[str, str]]:
    """
    Yield (Axxxxxx, normalized_terms_string) for each line in stripped/stripped.gz.
    Normalized terms string keeps commas and digits, removes spaces.
    Example stripped line:
        A000001 ,0,1,1,1,2,1,...
    """
    with open_text_maybe_gz(stripped_path) as f:
        for line in f:
            if not line or line.startswith("#"):
                continue
            line = line.strip("\n")
            if not line:
                continue
            parts = line.split(None, 1)
            if len(parts) < 2:
                continue
            aid = parts[0].strip()
            rest = parts[1].strip().replace(" ", "")
            if not (aid.startswith("A") and len(aid) == 7):
                continue
            yield aid, rest


def oeis_search_offline_stripped(
    terms: Sequence[int],
    stripped_path: Path,
    *,
    names_path: Path | None = None,
    max_hits: int = 10,
    max_scan: int | None = None,
) -> list[OeisHit]:
    """
    Offline subsequence search on stripped/stripped.gz.
    Fast substring matching: looks for ',t1,t2,...,tk,' inside each sequence line.
    """
    needle = "," + ",".join(str(x) for x in terms) + ","
    names = {}
    if names_path is not None and names_path.exists():
        try:
            names = load_names_map(names_path)
        except Exception as ex:
            eprint(f"[warn] couldn't load names file: {ex}")

    hits: list[OeisHit] = []
    scanned = 0
    for aid, rest in iter_stripped_lines(stripped_path):
        scanned += 1
        if needle in rest:
            data_terms: list[int] = []
            for tok in rest.split(","):
                if not tok:
                    continue
                try:
                    data_terms.append(int(tok))
                except ValueError:
                    break
                if len(data_terms) >= 400:
                    break
            mlen, mat = best_subsequence_match(data_terms, list(terms))
            denom = max(1, min(len(terms), len(data_terms)))
            score = mlen / denom
            hits.append(
                OeisHit(
                    a_number=aid,
                    name=names.get(aid, ""),
                    offset="",
                    data_terms=data_terms,
                    match_len=mlen,
                    match_at=mat,
                    score=score,
                )
            )
            if len(hits) >= max_hits:
                break
        if max_scan is not None and scanned >= max_scan:
            break

    hits.sort(key=lambda h: (h.score, h.match_len), reverse=True)
    return hits[:max_hits]


def pretty_print_hits(
    terms: Sequence[int], hits: Sequence[OeisHit], *, show_terms: int = 12
) -> None:
    q = terms_to_query_string(terms, max_terms=show_terms)
    print(f"Query terms ({len(terms)}): {q}{'…' if len(terms) > show_terms else ''}")
    if not hits:
        print("No hits.")
        return
    print("")
    print(f"{'A-number':8}  {'score':>5}  {'match':>7}  {'at':>4}  name")
    print("-" * 78)
    for h in hits:
        at = "" if h.match_at is None else str(h.match_at)
        nm = h.name or ""
        if len(nm) > 56:
            nm = nm[:53] + "..."
        print(f"{h.a_number:8}  {h.score:5.2f}  {h.match_len:7d}  {at:>4}  {nm}")


def hits_to_jsonable(hits: Sequence[OeisHit], *, include_data_prefix: int = 30) -> list:
    out = []
    for h in hits:
        out.append(
            {
                "a_number": h.a_number,
                "name": h.name,
                "offset": h.offset,
                "score": h.score,
                "match_len": h.match_len,
                "match_at": h.match_at,
                "data_prefix": h.data_terms[:include_data_prefix],
            }
        )
    return out

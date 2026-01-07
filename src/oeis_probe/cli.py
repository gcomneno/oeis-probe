from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from .core import (
    DEFAULT_CACHE_TTL_DAYS,
    DEFAULT_OEIS_BASE,
    OeisCache,
    hits_from_online_json,
    hits_to_jsonable,
    mismatch_details,
    oeis_fetch_by_id_online,
    oeis_search_offline_stripped,
    oeis_search_online,
    parse_terms,
    pretty_print_hits,
    sort_hits,
)


def _online_probe_with_optional_relax(
    terms: Sequence[int],
    *,
    oeis_base: str,
    timeout: float,
    cache: OeisCache,
    cache_ttl_days: int,
    max_query_terms: int,
    max_hits: int,
    relax_online: bool,
    relax_min_terms: int,
) -> tuple[list, str | None]:
    """
    Run online probe. If relax_online=True and OEIS returns no results, retry by shortening
    the query prefix (drop terms from the end) down to relax_min_terms.
    Returns (hits, error_str).
    """
    try:
        qlen = min(len(terms), max_query_terms)
        qlen = max(1, qlen)

        while True:
            payload = oeis_search_online(
                terms,
                oeis_base=oeis_base,
                max_query_terms=qlen,
                timeout=timeout,
                cache=cache,
                cache_ttl_days=cache_ttl_days,
            )
            hits = hits_from_online_json(terms, payload, max_hits=max_hits)

            if hits or not relax_online or qlen <= relax_min_terms:
                return hits, None

            qlen -= 1

    except Exception as ex:  # noqa: BLE001
        return [], str(ex)


def _print_explain_top(terms: Sequence[int], hits: Sequence) -> None:
    if not hits:
        return
    top = hits[0]
    d = mismatch_details(terms, top)

    status = d.get("status")
    a = d.get("a_number")

    if status == "full_match":
        print(f"[explain] top {a}: full match ({d.get('match_len')}/{d.get('query_len')})")
        return

    if status == "no_alignment":
        print(f"[explain] top {a}: no alignment")
        return

    # mismatch
    qi = int(d["query_index"])
    hi = int(d["hay_index"])
    got = d.get("got")
    exp = d.get("expected")
    # show 0-based and 1-based to avoid confusion
    print(
        f"[explain] top {a}: first mismatch at query[{qi}] (#{qi + 1}) -> got {got}; "
        f"expected {exp} (hit data index {hi})"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="oeis-probe",
        description="Probe integer sequences against OEIS (online JSON + optional offline stripped/names).",
    )
    sub = parser.add_subparsers(dest="cmd")

    p_probe = sub.add_parser("probe", help="probe by terms (default)")
    p_probe.add_argument("terms", nargs="?", help='terms like "1,2,3,6,11,23"')
    p_probe.add_argument(
        "--terms-file", type=Path, help="read terms from a text file (comma/space-separated)"
    )
    p_probe.add_argument("--max-hits", type=int, default=10)
    p_probe.add_argument("--max-query-terms", type=int, default=40)
    p_probe.add_argument("--timeout", type=float, default=10.0)
    p_probe.add_argument("--oeis-base", default=DEFAULT_OEIS_BASE)

    p_probe.add_argument(
        "--cache-db",
        type=Path,
        default=Path.home() / ".cache" / "oeis_probe" / "oeis_cache.sqlite",
    )
    p_probe.add_argument("--cache-ttl-days", type=int, default=DEFAULT_CACHE_TTL_DAYS)

    p_probe.add_argument("--no-online", action="store_true", help="disable online lookup")
    p_probe.add_argument(
        "--relax-online",
        action="store_true",
        help="If online search returns no results, retry by shortening the query prefix (drops terms from the end).",
    )
    p_probe.add_argument(
        "--relax-min-terms",
        type=int,
        default=8,
        help="Minimum number of terms to keep when --relax-online is enabled (default: 8).",
    )
    p_probe.add_argument("--offline-stripped", type=Path, help="path to stripped or stripped.gz")
    p_probe.add_argument("--offline-names", type=Path, help="path to names or names.gz (optional)")
    p_probe.add_argument(
        "--offline-max-scan", type=int, default=None, help="stop offline scan after N lines (debug)"
    )

    p_probe.add_argument(
        "--min-match-len",
        type=int,
        default=1,
        help="Filter out hits with a consecutive match length below this threshold (default: 1).",
    )

    p_probe.add_argument(
        "--explain-top",
        action="store_true",
        help="Explain where the query first diverges from the top hit (best consecutive match).",
    )

    p_probe.add_argument(
        "--json-out", type=Path, help="write JSON result to file (also prints summary)"
    )
    p_probe.add_argument(
        "--rank",
        choices=["strict", "prefer-early"],
        default="strict",
        help="Ranking: 'strict' (default) or 'prefer-early' to prefer smaller alignment index 'at' on ties.",
    )

    p_fetch = sub.add_parser("fetch", help="fetch by A-number (online, JSON)")
    p_fetch.add_argument("a_number", help="A-number like A000045")
    p_fetch.add_argument("--timeout", type=float, default=10.0)
    p_fetch.add_argument("--oeis-base", default=DEFAULT_OEIS_BASE)
    p_fetch.add_argument(
        "--cache-db",
        type=Path,
        default=Path.home() / ".cache" / "oeis_probe" / "oeis_cache.sqlite",
    )
    p_fetch.add_argument("--cache-ttl-days", type=int, default=DEFAULT_CACHE_TTL_DAYS)

    if argv is None:
        import sys

        argv = sys.argv[1:]
    if not argv or (argv and argv[0] not in {"probe", "fetch"}):
        argv = ["probe"] + list(argv)

    args = parser.parse_args(list(argv))

    if args.cmd == "fetch":
        cache = OeisCache(args.cache_db)
        payload = oeis_fetch_by_id_online(
            args.a_number,
            oeis_base=args.oeis_base,
            timeout=args.timeout,
            cache=cache,
            cache_ttl_days=args.cache_ttl_days,
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    # probe
    if args.terms_file:
        text = args.terms_file.read_text(encoding="utf-8", errors="replace")
        terms = parse_terms(text)
    else:
        if not args.terms:
            parser.error("probe: provide TERMS or --terms-file")
        terms = parse_terms(args.terms)

    min_match_len = max(1, int(args.min_match_len))

    cache = OeisCache(args.cache_db)

    online_hits = []
    online_err = None
    if not args.no_online:
        online_hits, online_err = _online_probe_with_optional_relax(
            terms,
            oeis_base=args.oeis_base,
            timeout=args.timeout,
            cache=cache,
            cache_ttl_days=args.cache_ttl_days,
            max_query_terms=args.max_query_terms,
            max_hits=args.max_hits,
            relax_online=bool(args.relax_online),
            relax_min_terms=max(1, int(args.relax_min_terms)),
        )

    offline_hits = []
    if args.offline_stripped:
        offline_hits = oeis_search_offline_stripped(
            terms,
            args.offline_stripped,
            names_path=args.offline_names,
            max_hits=args.max_hits,
            max_scan=args.offline_max_scan,
        )

    merged = {h.a_number: h for h in offline_hits}
    for h in online_hits:
        prev = merged.get(h.a_number)
        if prev is None or (h.score, h.match_len) > (prev.score, prev.match_len):
            merged[h.a_number] = h

    filtered = [h for h in merged.values() if h.match_len >= min_match_len]

    merged_hits = sort_hits(filtered, rank=args.rank)[: args.max_hits]

    pretty_print_hits(terms, merged_hits)

    if args.explain_top:
        _print_explain_top(terms, merged_hits)

    if online_err:
        print(f"[warn] online lookup failed: {online_err}")

    if args.json_out:
        result = {
            "query_terms": terms,
            "online_enabled": (not args.no_online),
            "offline_enabled": bool(args.offline_stripped),
            "rank": args.rank,
            "min_match_len": min_match_len,
            "relax_online": bool(args.relax_online),
            "relax_min_terms": int(args.relax_min_terms),
            "explain_top": bool(args.explain_top),
            "hits": hits_to_jsonable(merged_hits),
        }
        args.json_out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    return 0

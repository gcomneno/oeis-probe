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
    oeis_fetch_by_id_online,
    oeis_search_offline_stripped,
    oeis_search_online,
    parse_terms,
    pretty_print_hits,
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
    p_probe.add_argument("--offline-stripped", type=Path, help="path to stripped or stripped.gz")
    p_probe.add_argument("--offline-names", type=Path, help="path to names or names.gz (optional)")
    p_probe.add_argument(
        "--offline-max-scan", type=int, default=None, help="stop offline scan after N lines (debug)"
    )
    p_probe.add_argument(
        "--json-out", type=Path, help="write JSON result to file (also prints summary)"
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

    cache = OeisCache(args.cache_db)

    online_hits = []
    online_err = None
    if not args.no_online:
        try:
            payload = oeis_search_online(
                terms,
                oeis_base=args.oeis_base,
                max_query_terms=args.max_query_terms,
                timeout=args.timeout,
                cache=cache,
                cache_ttl_days=args.cache_ttl_days,
            )
            online_hits = hits_from_online_json(terms, payload, max_hits=args.max_hits)
        except Exception as ex:  # noqa: BLE001
            online_err = str(ex)

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

    merged_hits = sorted(merged.values(), key=lambda h: (h.score, h.match_len), reverse=True)[
        : args.max_hits
    ]

    pretty_print_hits(terms, merged_hits)

    if online_err:
        print(f"[warn] online lookup failed: {online_err}")

    if args.json_out:
        result = {
            "query_terms": terms,
            "online_enabled": (not args.no_online),
            "offline_enabled": bool(args.offline_stripped),
            "hits": hits_to_jsonable(merged_hits),
        }
        args.json_out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    return 0

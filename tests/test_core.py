from oeis_probe.core import (
    OeisHit,
    best_subsequence_match,
    hits_from_online_json,
    mismatch_details,
    parse_terms,
    sort_hits,
)


def test_parse_terms_commas_and_spaces():
    assert parse_terms("1, 2,3  4") == [1, 2, 3, 4]


def test_best_subsequence_match():
    hay = [5, 1, 2, 3, 9]
    needle = [1, 2, 3]
    mlen, at = best_subsequence_match(hay, needle)
    assert mlen == 3
    assert at == 1


def test_hits_from_online_json_accepts_list_payload():
    payload = [
        {"number": 45, "data": "0,1,1,2,3,5,8,13,21,34,55,89", "name": "Fibonacci numbers"}
    ]
    hits = hits_from_online_json([0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89], payload, max_hits=3)
    assert hits
    assert hits[0].a_number == "A000045"
    assert hits[0].score == 1.0


def test_sort_hits_prefer_early_breaks_ties():
    hits = [
        OeisHit("A1", "x", "", [], 10, 5, 1.0),
        OeisHit("A2", "y", "", [], 10, 0, 1.0),
    ]
    out = sort_hits(hits, rank="prefer-early")
    assert out[0].a_number == "A2"


def test_mismatch_details_reports_first_mismatch():
    hit = OeisHit("A999999", "x", "", [0, 1, 3, 6, 2, 7, 13, 20, 12, 21, 11, 22], 11, 0, 0.9)
    q = [0, 1, 3, 6, 2, 7, 13, 20, 12, 21, 11, 99]
    d = mismatch_details(q, hit)
    assert d["status"] == "mismatch"
    assert d["query_index"] == 11
    assert d["got"] == 99
    assert d["expected"] == 22

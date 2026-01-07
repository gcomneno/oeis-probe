from oeis_probe.core import best_subsequence_match, parse_terms


def test_parse_terms_commas_and_spaces():
    assert parse_terms("1, 2,3  4") == [1, 2, 3, 4]


def test_best_subsequence_match():
    hay = [5, 1, 2, 3, 9]
    needle = [1, 2, 3]
    mlen, at = best_subsequence_match(hay, needle)
    assert mlen == 3
    assert at == 1

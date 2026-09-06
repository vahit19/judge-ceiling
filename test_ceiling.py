"""
Tests. These must pass before any claim is made.

    python test_ceiling.py            # built-in runner, no dependencies
    python -m pytest test_ceiling.py  # if pytest is available

Two groups:
  1) MATHEMATICS -- checked against a worked example from the standard
     treatment, so the implementation is verified before it is pointed at
     anyone's data.
  2) DATA -- integrity of the fetched table. Anything the argument relies on
     is asserted rather than assumed.
"""

import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from ceiling_bounds import (  # noqa: E402
    ceiling, crossover, lower_bound, pct_of_ceiling)

DATA = os.path.join(HERE, "leaderboard.json")


def data():
    return json.load(io.open(DATA, encoding="utf-8"))


# ------------------------------------------------------------- 1) MATHEMATICS

def test_ceiling_worked_example():
    """rho = 0.64 gives a ceiling of 0.80."""
    assert abs(ceiling(0.64) - 0.80) < 1e-12


def test_observed_060_is_75_percent_of_ceiling():
    assert abs(pct_of_ceiling(0.60, 0.64) - 75.0) < 1e-9


def test_disattenuated_reliability_is_0_5625():
    """Same example: 0.36 / 0.64."""
    assert abs(0.60 ** 2 / 0.64 - 0.5625) < 1e-12


def test_bound_is_self_consistent():
    """At rho_1 = r**2 the ceiling is exactly r."""
    for r in (0.05, 0.2049, 0.3487, 0.7033, 0.99):
        assert abs(ceiling(lower_bound(r)) - r) < 1e-12


def test_below_the_bound_is_unreachable():
    """
    A rho_1 below r**2 contradicts the published score itself.

    Note the bound is lower_bound(r), not a rounded literal. Using the rounded
    0.4946 for r = 0.7033 lands just BELOW the true bound (0.494631...) and is
    correctly reported unreachable -- an easy mistake, asserted here so it
    stays caught.
    """
    r = 0.7033
    assert pct_of_ceiling(r, 0.30) is None
    assert pct_of_ceiling(r, 0.4946) is None
    assert pct_of_ceiling(r, lower_bound(r)) is not None
    assert pct_of_ceiling(r, 0.60) is not None


def test_exactly_at_the_bound_is_100_percent():
    r = 0.7033
    assert abs(pct_of_ceiling(r, lower_bound(r)) - 100.0) < 1e-9


def test_percentage_falls_as_rho1_rises():
    """A higher ceiling makes the same score a worse fraction of it."""
    vals = [pct_of_ceiling(0.3821, p) for p in (0.20, 0.30, 0.50, 0.70)]
    assert all(a > b for a, b in zip(vals, vals[1:]))


def test_crossover_is_consistent():
    """Re-derive the cross-dimension crossover independently."""
    r_a, r_b, rho_b = 0.2049, 0.7033, 0.60
    rho_a = crossover(r_a, r_b) * rho_b
    assert abs(pct_of_ceiling(r_a, rho_a) - pct_of_ceiling(r_b, rho_b)) < 1e-9


# -------------------------------------------------------------------- 2) DATA

def test_table_shape():
    d = data()
    assert len(d) == 8, f"expected 8 dimensions, found {len(d)}"
    for name, rows in d.items():
        assert len(rows) == 7, f"'{name}': expected 7 judges, found {len(rows)}"


def test_scores_in_range():
    for name, rows in data().items():
        for x in rows:
            assert -1.0 <= x["score"] <= 1.0, f"{name}/{x['model']} = {x['score']}"


def test_ranks_agree_with_scores():
    for name, rows in data().items():
        s = [x["score"] for x in sorted(rows, key=lambda y: y["rank"])]
        assert s == sorted(s, reverse=True), f"'{name}': rank disagrees with score"


def test_same_judge_set_everywhere():
    assert len({frozenset(x["model"] for x in r) for r in data().values()}) == 1


def test_bounds_are_valid_proportions():
    for name, rows in data().items():
        assert 0.0 <= lower_bound(max(x["score"] for x in rows)) <= 1.0, name


def test_licence_field_populated():
    """The open/proprietary split is used in the argument, so assert it."""
    for name, rows in data().items():
        for x in rows:
            assert x["license"] in ("proprietary", "open-source"), x


def test_exactly_two_open_weight_judges():
    rows = next(iter(data().values()))
    open_w = [x for x in rows if x["license"] != "proprietary"]
    assert len(open_w) == 2, f"expected 2 open-weight judges, found {len(open_w)}"


# ------------------------------------------------------------ built-in runner

if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            print(f"  FAIL  {name}  -> {e}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)

"""
Derive a lower bound on rater agreement from a judge leaderboard's own numbers.

The idea in one sentence:

    A judge cannot correlate with a human vote more strongly than the square
    root of that vote's own reliability. So every published correlation is
    also a lower bound on the reliability that is not published.

Data source: a public leaderboard (see fetch_leaderboard.py).
No credentials, no private data, no API key.

Usage:
    python ceiling_bounds.py
    python ceiling_bounds.py --self-test    # the mathematics only
"""

import io
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "leaderboard.json")

# Hypothetical single-rater reliabilities used for the scenario table.
SCENARIOS = [0.20, 0.30, 0.50, 0.70]


def load():
    return json.load(io.open(DATA, encoding="utf-8"))


# ---------------------------------------------------------------------------
# The mathematics
# ---------------------------------------------------------------------------
def lower_bound(r):
    """
    Classical test theory:

        observed r = r_true * sqrt(rho_judge * rho_1)

    Both r_true and rho_judge are at most 1, so rho_1 >= r**2.
    """
    return r * r


def ceiling(rho1):
    """Highest correlation obtainable against a single human vote."""
    return math.sqrt(rho1)


def pct_of_ceiling(r, rho1):
    """
    How much of the achievable maximum this judge reaches, as a percentage.

    Returns None when rho1 sits below the bound the score itself implies --
    that combination is not merely unlikely, it is unreachable.
    """
    if rho1 < lower_bound(r):
        return None
    return r / ceiling(rho1) * 100.0


def crossover(r_a, r_b):
    """
    Two dimensions reach the same fraction of their own ceilings when

        r_a / sqrt(rho_a)  ==  r_b / sqrt(rho_b)

    Returns the ratio k such that rho_a == k * rho_b at that point.
    """
    return (r_a / r_b) ** 2


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
def by_best_score(data):
    return sorted(data.items(), key=lambda kv: -max(x["score"] for x in kv[1]))


def report_bounds(data):
    print("=" * 78)
    print("1) A BOUND ON THE NUMBER THAT IS NOT PUBLISHED")
    print("=" * 78)
    print("Each dimension's best judge score puts a floor under the reliability")
    print("of a single human rating on that dimension.\n")
    print(f"{'dimension':38s}{'best r':>9s}{'rho_1 >=':>11s}{'judge':>20s}")
    print("-" * 78)
    for name, rows in by_best_score(data):
        best = max(rows, key=lambda x: x["score"])
        print(f"{name:38s}{best['score']:9.4f}{lower_bound(best['score']):11.4f}"
              f"{best['model'].split('/')[-1][:19]:>20s}")
    print("\nEvery figure above comes from published numbers alone.")


def report_scenarios(data):
    print("\n" + "=" * 78)
    print("2) PERCENT OF CEILING, UNDER DIFFERENT ASSUMPTIONS ABOUT rho_1")
    print("=" * 78)
    print("Same judge, same score. The only thing changing is what we assume")
    print("about how much the human raters agree with each other.\n")
    head = "".join(f"{'rho_1=' + format(p, '.2f'):>12s}" for p in SCENARIOS)
    print(f"{'dimension':38s}{head}")
    print("-" * (38 + 12 * len(SCENARIOS)))
    for name, rows in by_best_score(data):
        r = max(x["score"] for x in rows)
        cells = ""
        for p in SCENARIOS:
            v = pct_of_ceiling(r, p)
            cells += f"{'UNREACHABLE':>12s}" if v is None else f"{v:11.0f}%"
        print(f"{name:38s}{cells}")
    print("\nUNREACHABLE = that assumption contradicts a score they published.")
    print("The data constrains itself.")


def report_crossover(data, a="Acting / Role-fit", b="Language Stability"):
    print("\n" + "=" * 78)
    print("3) WHERE THE PUBLISHED READING TURNS")
    print("=" * 78)
    print("Reported reading: agreement is weakest on subjective dimensions.")
    print("True of the raw scores. But the ceiling is not constant.\n")
    if a not in data or b not in data:
        print("  (dimensions not present in this data set)")
        return
    r_a = max(x["score"] for x in data[a])
    r_b = max(x["score"] for x in data[b])
    k = crossover(r_a, r_b)
    print(f"  {a:24s} r = {r_a:.4f}")
    print(f"  {b:24s} r = {r_b:.4f}\n")
    print("  The two are equally good, relative to what is achievable, when:")
    print(f"      rho_1({a.split(' /')[0].lower()}) = {k:.4f} x rho_1(language stability)\n")
    ref = 0.60
    print(f"  So if rho_1 on language stability is {ref:.2f}, then once rho_1 on")
    print(f"  acting falls below {ref * k:.4f} the judge is doing BETTER on acting.")
    print("\n  Whether that point is reached is empirical -- and unmeasured.")


def report_assumptions():
    print("\n" + "=" * 78)
    print("ASSUMPTIONS -- the result is not defensible without stating these")
    print("=" * 78)
    print("1. Classical test theory: observed = true + independent error.")
    print("   If judge errors correlate with rater errors, the bound loosens.")
    print("2. The leaderboard reports SPEARMAN rank correlation; the attenuation")
    print("   identity is derived for Pearson. On five-point ordinal data these")
    print("   are close but not identical.")
    print("3. These are BOUNDS, not estimates. They say what rho_1 cannot be.")
    print("   The estimate needs rating rows with rater identity preserved.")


# ---------------------------------------------------------------------------
def self_test():
    """Check the implementation against a worked example before trusting it."""
    failures = 0

    def check(name, ok):
        nonlocal failures
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            failures += 1

    check("rho=0.64 gives a ceiling of 0.80", abs(ceiling(0.64) - 0.80) < 1e-12)
    check("observed 0.60 is 75% of that ceiling",
          abs(pct_of_ceiling(0.60, 0.64) - 75.0) < 1e-9)
    check("and implies a true reliability of 0.5625",
          abs(0.60 ** 2 / 0.64 - 0.5625) < 1e-12)
    check("the bound is self-consistent",
          all(abs(ceiling(lower_bound(r)) - r) < 1e-12
              for r in (0.05, 0.2049, 0.7033, 0.99)))
    check("below the bound is reported as unreachable",
          pct_of_ceiling(0.7033, 0.30) is None)
    check("exactly at the bound is 100% of ceiling",
          abs(pct_of_ceiling(0.7033, lower_bound(0.7033)) - 100.0) < 1e-9)

    print(f"\n  {'all checks passed' if not failures else f'{failures} FAILED'}")
    return failures


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(1 if self_test() else 0)
    d = load()
    report_bounds(d)
    report_scenarios(d)
    report_crossover(d)
    report_assumptions()

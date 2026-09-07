"""
Tests for the rating-rows pipeline.

The estimator is checked where the answer is known by construction. Two of
these tests encode methodological traps rather than arithmetic: judge
contamination, and a gate that would pass on an unidentified ratio.

    python test_reliability.py
    python -m pytest test_reliability.py
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from reliability import (  # noqa: E402
    analyse, ceiling, disattenuate, icc_one_way, icc_two_way_consistency,
    load_csv, pearson, spearman_brown, substitution_ratio, turns_needed)
from simulate import (  # noqa: E402
    make_judge, make_ratings, to_by_item, to_triples)


# --------------------------------------------------------------- recovery

def test_recovers_reliability_it_was_not_told():
    """The whole point: build at a known rho_1, get it back."""
    for true_rho in (0.20, 0.45, 0.70):
        rows, _ = make_ratings(n_items=600, k_raters=3, rho_1=true_rho, seed=11)
        got = icc_one_way(to_by_item(rows))[0]
        assert abs(got - true_rho) < 0.06, f"built {true_rho}, recovered {got:.4f}"


def test_more_raters_raises_panel_reliability():
    """Spearman-Brown is not a claim; it is observable in the data."""
    prev = 0.0
    for k in (2, 3, 6):
        rows, _ = make_ratings(n_items=400, k_raters=k, rho_1=0.30, seed=5)
        rho_k = icc_one_way(to_by_item(rows))[1]
        assert rho_k > prev, f"k={k} did not improve on k-1"
        prev = rho_k


def test_spearman_brown_matches_icc_k():
    """Two derivations of the same quantity must agree."""
    rows, _ = make_ratings(n_items=500, k_raters=3, rho_1=0.35, seed=2)
    rho_1, rho_k, k = icc_one_way(to_by_item(rows))
    assert abs(spearman_brown(rho_1, k) - rho_k) < 1e-9


# ----------------------------------------------------- bias is not noise

def test_two_way_matches_hand_computation():
    """
    Balanced 6x3 design, ICC(3,1) computed independently from the standard
    two-way ANOVA identities. The implementation must land on it exactly.
    """
    data = [("i1", "A", 9), ("i1", "B", 2), ("i1", "C", 5),
            ("i2", "A", 6), ("i2", "B", 1), ("i2", "C", 3),
            ("i3", "A", 8), ("i3", "B", 4), ("i3", "C", 6),
            ("i4", "A", 7), ("i4", "B", 1), ("i4", "C", 2),
            ("i5", "A", 10), ("i5", "B", 5), ("i5", "C", 6),
            ("i6", "A", 6), ("i6", "B", 2), ("i6", "C", 4)]
    n, k = 6, 3
    xs = [x for _, _, x in data]
    grand = sum(xs) / len(xs)
    im, rm = {}, {}
    for i, r, x in data:
        im.setdefault(i, []).append(x)
        rm.setdefault(r, []).append(x)
    msr = k * sum((sum(v) / len(v) - grand) ** 2 for v in im.values()) / (n - 1)
    ssr = k * sum((sum(v) / len(v) - grand) ** 2 for v in im.values())
    ssc = n * sum((sum(v) / len(v) - grand) ** 2 for v in rm.values())
    sst = sum((x - grand) ** 2 for x in xs)
    mse = (sst - ssr - ssc) / ((n - 1) * (k - 1))
    expected = (msr - mse) / (msr + (k - 1) * mse)
    assert abs(icc_two_way_consistency(data)[0] - expected) < 1e-12


def test_two_way_refuses_unbalanced_designs():
    """
    The sums of squares only decompose orthogonally when every rater rates
    every item. On an unbalanced design the estimate was measured at +0.30 on
    data built at 0.45. The function must refuse rather than approximate.
    """
    rows, _ = make_ratings(n_items=200, k_raters=3, rho_1=0.45, seed=1)  # pooled
    assert icc_two_way_consistency(to_triples(rows)) is None

    crossed, _ = make_ratings(n_items=200, k_raters=3, rho_1=0.45,
                              seed=1, crossed=True)
    assert icc_two_way_consistency(to_triples(crossed)) is not None

    # a single missing cell is enough to disqualify it
    holed = to_triples(crossed)[:-1]
    assert icc_two_way_consistency(holed) is None


def test_residual_is_invariant_to_rater_bias():
    """
    The sharpest form of "bias is not noise": on a crossed design the residual
    variance must be identical whatever the rater offsets are.
    """
    resids, rhos = [], []
    for bias in (0.0, 0.5, 1.0):
        rows, _ = make_ratings(n_items=300, k_raters=3, rho_1=0.45,
                               rater_bias=bias, seed=7, crossed=True)
        rho, _si, _sr, resid = icc_two_way_consistency(to_triples(rows))
        resids.append(resid)
        rhos.append(rho)
    assert max(resids) - min(resids) < 1e-9, f"residual moved: {resids}"
    assert max(rhos) - min(rhos) < 1e-9, f"reliability moved: {rhos}"


def test_two_way_separates_bias_from_noise():
    """
    The claim the whole proposal rests on, made testable.

    Rater bias grows; the residual must not, and consistency reliability must
    stay near where it was built. The one-way estimate, which cannot separate
    them, must fall.
    """
    one_way, two_way, resid = [], [], []
    for bias in (0.0, 0.5, 1.0):
        rows, _ = make_ratings(n_items=500, k_raters=3, rho_1=0.45,
                               rater_bias=bias, seed=7, crossed=True)
        one_way.append(icc_one_way(to_by_item(rows))[0])
        rho, _s_item, s_rater, s_resid = icc_two_way_consistency(to_triples(rows))
        two_way.append(rho)
        resid.append(s_resid)

    assert one_way[0] > one_way[-1] + 0.03, "one-way should absorb bias as error"
    assert all(abs(r - 0.45) < 0.07 for r in two_way), f"two-way drifted: {two_way}"
    assert abs(resid[0] - resid[-1]) / resid[0] < 1e-9, "residual must be identical"


# ------------------------------------------------------- ceiling and judge

def test_ceiling_worked_example():
    assert abs(ceiling(0.64) - 0.80) < 1e-12
    assert abs(disattenuate(0.60, 0.64) - 0.5625) < 1e-12


def test_substitution_ratio_known_values():
    """rho_1 = 0.28 held fixed; the published worked values."""
    for rho_g, expected in ((0.20, 0.643), (0.50, 2.571), (0.70, 6.000)):
        assert abs(substitution_ratio(rho_g, 0.28) - expected) < 0.01


def test_judge_reliability_is_recovered():
    rows, thetas = make_ratings(n_items=800, k_raters=3, rho_1=0.40, seed=13)
    judge = make_judge(thetas, rho_judge=0.50, seed=14)
    r = analyse(to_by_item(rows), judge=judge, resamples=1)
    assert abs(r["rho_judge"] - 0.50) < 0.10, r["rho_judge"]


# -------------------------------------------------- the traps, as tests

def test_contaminated_judge_inflates_the_ratio():
    """
    Judge contamination, encoded.

    A judge built from the panel mean shares the panel's errors. Its observed
    correlation is then inflated and the substitution ratio runs away. This
    test exists because the mistake was made in this repository's own
    simulator before it was caught.
    """
    rows, thetas = make_ratings(n_items=400, k_raters=3, rho_1=0.28, seed=3)
    by_item = to_by_item(rows)

    clean = make_judge(thetas, rho_judge=0.60, seed=4)
    dirty = {i: sum(v) / len(v) for i, v in by_item.items()}   # the panel itself

    r_clean = analyse(by_item, judge=clean, resamples=1)
    r_dirty = analyse(by_item, judge=dirty, resamples=1)
    assert r_dirty["ratio"] > r_clean["ratio"] * 3, (
        f"contamination not visible: clean {r_clean['ratio']:.2f} "
        f"vs dirty {r_dirty['ratio']:.2f}")


def test_gate_refuses_an_unidentified_ratio():
    """
    A lower bound above 1 is not sufficient. If the interval is unbounded the
    ratio is not identified and no saving may be quoted, however good the
    point estimate looks.
    """
    rows, thetas = make_ratings(n_items=28, k_raters=3, rho_1=0.28, seed=3)
    judge = make_judge(thetas, rho_judge=0.60, seed=4)
    r = analyse(to_by_item(rows), judge=judge, resamples=200)
    assert not math.isfinite(r["ratio_hi"]), "expected an unbounded interval at n=28"
    assert not r["automatable"], "gate passed on an unidentified ratio"
    assert r["refusal_reason"]


def test_same_judge_becomes_measurable_with_more_items():
    """Sample size, not judge quality, is what changes the verdict."""
    small, _t = make_ratings(n_items=28, k_raters=3, rho_1=0.28, seed=3)
    big, tb = make_ratings(n_items=400, k_raters=3, rho_1=0.28, seed=3)
    j_big = make_judge(tb, rho_judge=0.60, seed=4)
    r_big = analyse(to_by_item(big), judge=j_big, resamples=200)
    assert r_big["automatable"], "a good judge at n=400 should clear the gate"


def test_turns_needed_is_none_when_already_sufficient():
    assert turns_needed(100, 1.5) is None
    assert turns_needed(100, 0.5) > 0


def test_pearson_matches_hand_computation():
    assert abs(pearson([1, 2, 3, 4], [2, 4, 6, 8]) - 1.0) < 1e-12
    assert abs(pearson([1, 2, 3, 4], [4, 3, 2, 1]) + 1.0) < 1e-12


def test_degenerate_designs_return_none_not_a_number():
    assert icc_one_way({"a": [1.0]}) is None
    assert icc_one_way({}) is None
    assert icc_two_way_consistency([("a", "r1", 1.0)]) is None


# ------------------------- what the simulation CANNOT validate, measured

def test_likert_rounding_biases_downward_and_by_how_much():
    """
    The ground truth here is synthetic, and it is generated from exactly the
    model the estimator assumes. That validates the arithmetic; it cannot
    validate the model.

    So measure the cost of one real departure: actual panels rate on a
    five-point scale, and the model assumes a continuum. Rounding must bias the
    estimate DOWNWARD -- which is the safe direction, because understating
    reliability overstates how many raters are needed.
    """
    for built in (0.45, 0.70):
        smooth, _ = make_ratings(n_items=800, k_raters=3, rho_1=built, seed=11)
        rounded, _ = make_ratings(n_items=800, k_raters=3, rho_1=built,
                                  seed=11, scale=(1, 5))
        a = icc_one_way(to_by_item(smooth))[0]
        b = icc_one_way(to_by_item(rounded))[0]
        assert b < a, f"rounding should cost reliability at {built}"
        assert (a - b) / a < 0.20, f"rounding cost more than 20% at {built}"


def test_unequal_rater_noise_biases_downward():
    """
    Real panels contain careful and careless raters. The model assumes one
    error variance for everyone. Measured cost: roughly a fifth of the estimate
    at a realistic spread -- again downward, again the safe direction, and
    large enough that it belongs in the assumptions rather than in a footnote.
    """
    even, _ = make_ratings(n_items=800, k_raters=3, rho_1=0.45, seed=5)
    uneven, _ = make_ratings(n_items=800, k_raters=3, rho_1=0.45, seed=5,
                             noise_spread=0.6)
    a = icc_one_way(to_by_item(even))[0]
    b = icc_one_way(to_by_item(uneven))[0]
    assert b < a, "unequal rater noise should lower the estimate"
    assert (a - b) / a < 0.40, "cost larger than expected; investigate"


# ------------------------------- bugs found by an outside review, now locked

def test_inverted_judge_is_refused():
    """
    A judge that ranks quality backwards squares to the same reliability as one
    that ranks it correctly, because disattenuation squares the correlation.
    Before this was caught, an inverted judge was approved for automation with
    an identical ratio -- the worst failure this tool could have.
    """
    rows, thetas = make_ratings(n_items=400, k_raters=3, rho_1=0.28, seed=3)
    by_item = to_by_item(rows)
    good = make_judge(thetas, rho_judge=0.60, seed=4)
    inverted = {i: -v for i, v in good.items()}

    r_good = analyse(by_item, judge=good, resamples=200)
    r_bad = analyse(by_item, judge=inverted, resamples=200)

    assert r_good["automatable"], "a good judge should still clear the gate"
    assert abs(r_bad["observed_r"] + r_good["observed_r"]) < 1e-9, "not a mirror"
    assert not r_bad["automatable"], "an inverted judge was approved"
    assert r_bad["ratio"] == 0.0, f"inverted judge given credit: {r_bad['ratio']}"
    assert "negatively correlated" in r_bad["refusal_reason"]


def test_rater_identity_survives_the_csv_path():
    """
    The proposal asks for rows with rater identity preserved. A loader that
    drops the rater id at the door makes the two-way model unreachable -- the
    same mistake the method warns about, in the tool itself.
    """
    import os
    import tempfile
    from simulate import write_csv

    rows, _ = make_ratings(n_items=120, k_raters=3, rho_1=0.45,
                           rater_bias=0.8, seed=2, crossed=True)
    path = os.path.join(tempfile.mkdtemp(), "r.csv")
    write_csv(rows, path)
    try:
        data = load_csv(path)
        assert set(data) == {"demo"}
        by_item, triples = data["demo"]
        assert len(triples) == len(rows), "rows lost"
        assert len({r for _, r, _ in triples}) == 3, "rater identity lost"

        out = analyse(by_item, rows=triples, resamples=1)
        assert "rho_1_consistency" in out, "two-way never ran from the CSV path"
        # with strong bias the one-way estimate is badly deflated; the two-way
        # one is not. That gap is the reason rater identity has to survive.
        assert out["rho_1_consistency"] > out["rho_1"] + 0.15
    finally:
        os.remove(path)


def test_load_csv_rejects_missing_columns():
    import os
    import tempfile
    path = os.path.join(tempfile.mkdtemp(), "bad.csv")
    with open(path, "w", encoding="utf-8") as f:
        f.write("item_id,dimension,score" + chr(10) + "i1,d,3" + chr(10))
    try:
        try:
            load_csv(path)
        except ValueError as e:
            assert "rater_id" in str(e)
        else:
            raise AssertionError("a CSV without rater_id was accepted")
    finally:
        os.remove(path)


def test_planning_figure_is_not_falsely_precise():
    """
    A tool that refuses to quote a precise saving must not quote a precise
    sample size either. The figure is rounded to two significant digits.
    """
    n = turns_needed(28, 0.20)
    assert n is not None
    assert n % (10 ** max(0, len(str(n)) - 2)) == 0, f"looks over-precise: {n}"
    assert turns_needed(100, 0.5) > turns_needed(100, 0.9), "not monotone"


# ------------------------------------------------------------ runner

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

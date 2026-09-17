"""
Tests for the analysis of someone else's published panel.

    python test_consensus.py            # built-in runner, no dependencies
    python -m pytest test_consensus.py  # if pytest is available

Three groups:
  1) THE EXTRACT -- the saved file is shaped the way the analysis assumes. A
     verdict matrix with a wrong width or an unknown code would be read
     silently and produce a plausible wrong number.
  2) REPRODUCTION -- all 39 published ACCEPT-REF scores recompute exactly.
     This is the anchor. Every claim below it is a claim about someone else's
     data, and none of them mean anything if the data is being misread.
  3) THE SENSITIVITY -- what the published admission threshold selects, and
     that the comparison is a real comparison rather than two names for the
     same set.
"""

import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from consensus_panel import (  # noqa: E402
    CONSENSUS, MISSING, REF, by_threshold, load, outside_panel, rank,
    reproduce, scores, split_vs_unanimous, sweep)


def data():
    return load()


# ------------------------------------------------------------- 1) THE EXTRACT

def test_the_saved_file_exists_and_names_its_source():
    d = data()
    assert "HumeAI/asr-benchmark-optimization" in d["source"], d["source"]
    assert d["paper"] == "arXiv:2608.19936"
    assert d["params"]["majority_pct"] == 0.75


def test_every_span_carries_one_verdict_per_model():
    d = data()
    n = len(d["models"])
    assert n == 39, n
    for r in d["runs"]:
        assert len(r["verdicts"]) == n, (r["key"], len(r["verdicts"]))


def test_verdicts_use_only_known_codes():
    """An unknown code would be counted as `missing` and quietly shrink a
    denominator, which raises a score rather than failing."""
    d = data()
    allowed = {REF, CONSENSUS, MISSING}
    seen = set()
    for r in d["runs"]:
        seen |= set(r["verdicts"])
    assert seen <= allowed, seen - allowed
    assert seen == allowed, f"a code never occurs: {allowed - seen}"


def test_panel_agreement_counts_are_coherent():
    d = data()
    for r in d["runs"]:
        assert 0 < r["agree"] <= r["total"], r
        assert r["agree"] / r["total"] >= d["params"]["majority_pct"] - 1e-9, r


def test_the_panel_is_a_subset_of_the_scored_models():
    d = data()
    assert set(d["panel"]) <= set(d["models"])
    assert len(d["panel"]) == 4, d["panel"]


# ----------------------------------------------------------- 2) REPRODUCTION

def test_every_published_score_recomputes_exactly():
    """
    The anchor. Thirty-nine numbers, four decimal places, from the released
    verdict matrix. If this fails the file is being misread and every other
    result here is a coincidence.
    """
    bad = reproduce(data())
    assert not bad, "; ".join(
        f"{m}: published {p['score']} got {g['score']:.4f}" for m, p, g in bad[:5])


def test_the_counts_recompute_and_not_just_the_ratio():
    """A ratio can match for the wrong reason; the numerator and denominator
    are asserted separately."""
    d = data()
    mine = scores(d)
    for m, pub in d["published"].items():
        assert mine[m]["accepted_ref"] == pub["accepted_ref"], m
        assert mine[m]["followed_consensus"] == pub["followed_consensus"], m
        assert mine[m]["eligible"] == pub["eligible_runs"], m


def test_a_model_that_answered_nothing_scores_none_rather_than_zero():
    d = data()
    empty = scores(d, [], d["models"])
    assert all(v["score"] is None for v in empty.values())


# ---------------------------------------------------------- 3) THE SENSITIVITY

def test_unanimity_is_a_strictly_smaller_set():
    """If both arms were the same set the sensitivity would read as zero and
    look like a null result rather than a broken comparison."""
    d = data()
    lo, hi = by_threshold(d, 0.75), by_threshold(d, 1.00)
    assert len(lo) == len(d["runs"]), len(lo)
    assert len(hi) < len(lo), (len(hi), len(lo))
    assert len(hi) > 0.5 * len(lo), "unanimity kept implausibly few spans"


def test_the_sweep_excludes_panel_members():
    """Panel members are scored leave-one-out upstream and the inputs to that
    are not in the extract, so re-deriving them at another threshold would be
    guessing."""
    d = data()
    models = outside_panel(d)
    assert set(models).isdisjoint(set(d["panel"]))
    assert len(models) == len(d["models"]) - len(d["panel"])


def test_the_two_halves_partition_the_span_set():
    d = data()
    h = split_vs_unanimous(d)
    assert h["split"]["spans"] + h["unanimous"]["spans"] == len(d["runs"])
    assert h["split"]["spans"] > 0 and h["unanimous"]["spans"] > 0


def test_the_split_half_carries_the_higher_rate():
    """
    The finding, pinned. The spans the panel could not agree on are a small
    part of the item set and a large part of the measured effect. Held to a
    direction and a floor rather than an exact value, because the exact value
    belongs to upstream and can move.
    """
    d = data()
    h = split_vs_unanimous(d)
    assert h["split"]["mean"] > h["unanimous"]["mean"], h
    assert h["split"]["mean"] / h["unanimous"]["mean"] > 2.0, h
    assert h["split"]["spans"] < 0.25 * len(d["runs"]), h


def test_raising_the_threshold_moves_the_mean_score():
    d = data()
    lo, hi = sweep(d, thresholds=(0.75, 1.00))
    assert lo["spans"] > hi["spans"]
    assert abs(hi["mean"] - lo["mean"]) / lo["mean"] > 0.20, (lo["mean"], hi["mean"])


def test_the_ordering_is_not_stable_under_the_threshold():
    """
    The claim that matters to a reader of the paper: the leaderboard order
    depends on the admission threshold. Pinned as "some models move", not as a
    specific count, because a count would break on any upstream refresh while
    the point would still hold.
    """
    d = data()
    lo, hi = sweep(d, thresholds=(0.75, 1.00))
    r_lo, r_hi = rank(lo["per_model"]), rank(hi["per_model"])
    moved = [m for m in r_lo if r_lo[m] != r_hi[m]]
    assert moved, "no model changed rank, so there is nothing to report"
    top_lo = {m for m in r_lo if r_lo[m] <= 6}
    top_hi = {m for m in r_hi if r_hi[m] <= 6}
    assert top_lo != top_hi, "the top six is identical under both thresholds"


def test_the_extract_is_small_enough_to_live_in_the_repository():
    """The source is 8 MB of transcripts; only the verdict matrix is needed."""
    size = os.path.getsize(os.path.join(HERE, "consensus_panel.json"))
    assert size < 600 * 1024, f"{size / 1024:.0f} KB"


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
        except Exception as e:
            print(f"  ERROR {name}  -> {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)

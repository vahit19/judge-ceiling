"""
Tests for the quality-gate measurements. These must pass before any number in
`poison.py` or in the README table is quoted.

    python test_poison.py            # built-in runner, no dependencies
    python -m pytest test_poison.py  # if pytest is available

Three groups:
  1) INJECTION -- the corrupted rows are what they claim to be. If a
     "plausible" value does not really occur in the file, or if
     rater-concentrated corruption is not actually concentrated, then every
     catch rate below is measuring the wrong thing.
  2) GATES -- the screens behave as described, including when they should do
     nothing at all.
  3) THE FINDING -- the reported reliability rises as the screen tightens, on
     rows with nothing wrong with them. This is the claim that would be most
     costly to get wrong, so it is pinned from several directions rather than
     asserted once.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from poison import (  # noqa: E402
    CRUDE, PLAUSIBLE, RATER, SCATTERED, both_gates, corrupt, gate_outlier,
    gate_rater, gate_sweep, run_cell, _rho)
from simulate import make_ratings  # noqa: E402

BUILT = 0.45


def rows(n_items=300, k_raters=5, seed=1):
    out, _ = make_ratings(n_items=n_items, k_raters=k_raters,
                          rho_1=BUILT, seed=seed)
    return out


# --------------------------------------------------------------- 1) INJECTION

def test_zero_rate_is_a_no_op():
    r = rows()
    for kind in (CRUDE, PLAUSIBLE):
        out, flags = corrupt(r, kind, 0.0, seed=1)
        assert out == r, kind
        assert not any(flags), kind


def test_scattered_flag_count_matches_the_rate():
    r = rows()
    for kind in (CRUDE, PLAUSIBLE):
        _, flags = corrupt(r, kind, 0.25, where=SCATTERED, seed=1)
        assert abs(sum(flags) - 0.25 * len(r)) <= 1, (kind, sum(flags))


def test_rater_concentration_takes_whole_raters():
    """Otherwise the rater screen is being tested against something else."""
    r = rows()
    _, flags = corrupt(r, CRUDE, 0.25, where=RATER, seed=1)
    touched = {r[i]["rater_id"] for i, f in enumerate(flags) if f}
    assert touched
    for rater in touched:
        mine = [flags[j] for j, row in enumerate(r) if row["rater_id"] == rater]
        assert all(mine), rater


def test_plausible_values_really_occur_in_the_file():
    """This is what makes plausible corruption invisible to a value screen."""
    r = rows()
    real = {round(float(x["score"]), 9) for x in r}
    out, flags = corrupt(r, PLAUSIBLE, 0.30, seed=2)
    strays = [out[i]["score"] for i, f in enumerate(flags)
              if f and round(float(out[i]["score"]), 9) not in real]
    assert not strays, f"{len(strays)} values that no rater gave"


def test_both_kinds_destroy_signal_before_any_gate():
    r = rows()
    clean = _rho(r)
    for kind in (CRUDE, PLAUSIBLE):
        dirty, _ = corrupt(r, kind, 0.40, where=SCATTERED, seed=3)
        assert _rho(dirty) < clean, kind


def test_the_two_arms_do_comparable_damage():
    """
    The design holds damage constant and varies only detectability. If the
    arms differed in damage, any difference in catch rate could be explained
    by the injection instead of by the gate -- which would make the whole
    comparison meaningless rather than merely imprecise.
    """
    r = rows()
    clean = _rho(r)
    drops = {}
    for kind in (CRUDE, PLAUSIBLE):
        dirty, _ = corrupt(r, kind, 0.40, where=SCATTERED, seed=3)
        drops[kind] = clean - _rho(dirty)
    ratio = drops[PLAUSIBLE] / drops[CRUDE]
    assert 0.5 <= ratio <= 2.0, f"plausible/crude = {ratio:.2f}"


def test_bad_arguments_are_refused():
    r = rows()
    for call in (lambda: corrupt(r, "nonsense", 0.1),
                 lambda: corrupt(r, CRUDE, 1.5),
                 lambda: corrupt(r, CRUDE, -0.1),
                 lambda: corrupt(r, CRUDE, 0.1, where="somewhere")):
        try:
            call()
        except ValueError:
            continue
        raise AssertionError("bad arguments were accepted")


# ------------------------------------------------------------------ 2) GATES

def test_an_unreachable_threshold_drops_nothing():
    """If this fails, the sweep is measuring the harness and not the gate."""
    assert not any(gate_outlier(rows(), z=1e9))


def test_the_rater_screen_spares_a_clean_panel():
    """
    Separated from the outlier screen on purpose. A rater screen that cut good
    raters would explain the inflation in group 3 by itself.
    """
    assert not any(gate_rater(rows()))


def test_the_outlier_screen_drops_clean_ratings():
    """A screen that never touches a legitimate rating is not at a real threshold."""
    dropped = gate_outlier(rows(), z=2.0)
    assert sum(dropped) > 0
    assert sum(dropped) < 0.5 * len(dropped), "dropping half the data is not a screen"


def test_rater_concentrated_corruption_is_caught():
    """The cell the gate is supposed to win, whatever the values look like."""
    r = rows()
    for kind in (CRUDE, PLAUSIBLE):
        dirty, flags = corrupt(r, kind, 0.20, where=RATER, seed=4)
        dropped = both_gates(dirty)
        caught = sum(1 for f, d in zip(flags, dropped) if f and d) / sum(flags)
        assert caught > 0.9, f"{kind}: {caught:.0%}"


def test_scattered_corruption_is_mostly_missed():
    """The cell it loses -- and the reason a catch rate has to be reported."""
    r = rows()
    for kind in (CRUDE, PLAUSIBLE):
        dirty, flags = corrupt(r, kind, 0.20, where=SCATTERED, seed=4)
        dropped = both_gates(dirty)
        caught = sum(1 for f, d in zip(flags, dropped) if f and d) / sum(flags)
        assert caught < 0.6, f"{kind}: {caught:.0%}"


def test_location_beats_appearance():
    """
    The result that contradicted the opening hypothesis, pinned so it cannot
    quietly revert to the more flattering story. Concentrated corruption is
    caught far more often than scattered corruption OF THE SAME KIND.
    """
    r = rows()
    for kind in (CRUDE, PLAUSIBLE):
        rates = {}
        for where in (RATER, SCATTERED):
            dirty, flags = corrupt(r, kind, 0.20, where=where, seed=4)
            dropped = both_gates(dirty)
            rates[where] = sum(1 for f, d in zip(flags, dropped)
                               if f and d) / sum(flags)
        assert rates[RATER] > rates[SCATTERED] + 0.3, (kind, rates)


# ------------------------------------------------------------- 3) THE FINDING

def test_tightening_the_screen_never_lowers_the_reported_rho():
    r = rows()
    seq = []
    for z in (1e9, 3.0, 2.5, 2.0, 1.5, 1.0):
        d = gate_outlier(r, z=z)
        value = _rho([x for x, drop in zip(r, d) if not drop])
        assert value is not None, f"rho undefined at z={z}"
        seq.append(value)
    for a, b in zip(seq, seq[1:]):
        assert b >= a - 1e-9, " ".join(f"{v:.3f}" for v in seq)


def test_a_two_sigma_screen_overstates_a_known_reliability():
    """The number quoted in the README, pinned to a tolerance."""
    sweep = {r["z"]: r for r in gate_sweep(z_values=(None, 2.0), seeds=12)}
    off, tight = sweep[None], sweep[2.0]
    assert abs(off["reported"] - BUILT) < 0.02, off
    assert tight["reported"] > BUILT * 1.35, tight
    assert 0.10 < tight["dropped"] < 0.25, tight


def test_the_inflation_survives_a_different_true_reliability():
    """
    Not an artefact of rho_1 = 0.45. If the effect only appeared at one built
    value it would be a coincidence of that draw rather than a property of
    removing disagreement.
    """
    for built in (0.30, 0.60):
        sweep = {r["z"]: r for r in
                 gate_sweep(z_values=(None, 2.0), rho_1=built, seeds=8)}
        assert sweep[2.0]["reported"] > sweep[None]["reported"], built


def test_the_gate_reports_a_smaller_panel_than_the_truth_requires():
    """
    The consequence a study planner acts on, which is the reason the effect
    matters at all. Measured through run_cell so the reported path is the same
    one the tables use.
    """
    from reliability import raters_needed
    cells = [run_cell(CRUDE, SCATTERED, 0.0, seed=s) for s in range(12)]
    ungated = sum(c["rho_dirty"] for c in cells) / len(cells)
    gated = sum(c["rho_gated"] for c in cells) / len(cells)
    assert raters_needed(gated, 0.80) < raters_needed(ungated, 0.80), (
        f"gated {gated:.4f} -> {raters_needed(gated, 0.80)}, "
        f"ungated {ungated:.4f} -> {raters_needed(ungated, 0.80)}")


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

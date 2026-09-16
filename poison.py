"""
Corruption realism on rating rows -- and what a quality gate can and cannot see.

A leaderboard that scores a judge against human votes treats those votes as
ground truth. Some of them are not. The usual defence is a quality gate: drop
the outliers, drop the raters who do not track the rest of the panel. This
file measures when that gate is protection and when it is decoration.

Bad ratings are generated along two axes, and the axes are independent.

    WHAT IT LOOKS LIKE
      crude        the value itself is not one a working panel produces --
                   an inattentive rater repeating a single answer.
      plausible    a genuine rating, drawn from this very file, attached to
                   the WRONG item. From the value alone there is nothing
                   to see.

    WHERE IT SITS
      rater        one rater has gone bad and all of their ratings are wrong.
      scattered    the corruption is spread thinly over many raters -- what a
                   misaligned clip or an ambiguous rubric produces, rather
                   than a lazy person.

Both kinds of value carry zero information about the item, so the signal
destroyed is comparable; only detectability changes. That is the design.
Making the crude arm wronger would prove nothing except that larger errors
hurt more.

WHAT WAS FOUND, INCLUDING THE PART THAT WENT THE OTHER WAY.

The opening hypothesis was that realism decides detection: that crude
corruption would be screened out and plausible corruption would survive.
Measured, that is not what separates the cells. WHERE the corruption sits
does most of the work. Corruption concentrated inside one rater is caught
at 98-100% whatever it looks like, because a rater who does not track the
panel is identifiable across many items. Corruption spread thinly is mostly
missed -- and the crude arm is missed MORE than the plausible one (4% against
29%), because a repeated central value is never an outlier. Realism still
matters, but not in the direction first assumed, and the honest statement is
about location first.

The finding that did survive is larger than the one that was looked for. On
rows with nothing wrong with them at all, the outlier screen reports a
reliability 44% above the value the rows were built with, and the error is
monotone in how hard the screen is run. Dropping the ratings that disagree
most with the panel does not remove error; it removes disagreement, and less
disagreement IS higher measured agreement. A panel that genuinely needs five
raters is told three are enough -- by a defence that was supposed to protect
the number.

WHAT THIS CANNOT DO. Rows are simulated, so reliability is known by
construction and the corrupted fraction is known exactly -- which is the only
way to measure a gate's catch rate and its collateral damage at the same
time, and also the limit. These numbers describe the gate under the
generating model. Nothing here estimates how many real ratings are wrong. It
says what follows IF some are.

Usage:
    python poison.py                # the report card
    python poison.py --self-test    # the invariants, without the tables
"""

import math
import random
import sys

from reliability import analyse, icc_one_way, raters_needed
from simulate import make_ratings, to_by_item

CRUDE, PLAUSIBLE = "crude", "plausible"
KINDS = (CRUDE, PLAUSIBLE)
RATER, SCATTERED = "rater", "scattered"
PLACES = (RATER, SCATTERED)


def _pick(rows, rate, where, rng):
    """Row indices to corrupt, either whole raters or a thin scatter."""
    n_target = int(round(rate * len(rows)))
    if n_target == 0:
        return []

    if where == SCATTERED:
        return rng.sample(range(len(rows)), n_target)

    by_rater = {}
    for j, r in enumerate(rows):
        by_rater.setdefault(r["rater_id"], []).append(j)

    order = list(by_rater)
    rng.shuffle(order)
    hit = []
    for rater in order:
        if len(hit) >= n_target:
            break
        hit.extend(by_rater[rater])
    return hit


def corrupt(rows, kind, rate, where=SCATTERED, seed=0):
    """
    Replace a `rate` fraction of ratings with bad ones.

    Returns (new_rows, flags) where flags[i] is True for a replaced rating.
    The flags are what make a gate measurable: without them a dropped rating
    cannot be classified as a catch or as collateral.
    """
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    if where not in PLACES:
        raise ValueError(f"where must be one of {PLACES}")
    if not 0.0 <= rate <= 1.0:
        raise ValueError("rate must be between 0 and 1")

    rng = random.Random(seed)
    out = [dict(r) for r in rows]
    flags = [False] * len(out)
    if rate == 0.0:
        return out, flags

    hit = _pick(rows, rate, where, rng)

    if kind == CRUDE:
        # A single repeated value. Placed at the centre of the scale on
        # purpose: a constant in the tails would be caught by any screen, and
        # the claim here is not that obvious corruption is obvious.
        scores = [float(r["score"]) for r in rows]
        mid = sum(scores) / len(scores)
        for i in hit:
            out[i]["score"] = mid
            flags[i] = True
        return out, flags

    by_item = {}
    for r in rows:
        by_item.setdefault(r["item_id"], []).append(float(r["score"]))
    items = list(by_item)
    for i in hit:
        mine = out[i]["item_id"]
        other = mine
        while other == mine and len(items) > 1:
            other = rng.choice(items)
        out[i]["score"] = rng.choice(by_item[other])
        flags[i] = True
    return out, flags


def _loo_stats(rows):
    """Per-rating leave-one-out mean and sd of the OTHER raters of that item.

    Leave-one-out matters. A rating compared against a mean it helped compute
    pulls that mean towards itself, and the more corrupted ratings an item
    carries the less any of them stands out. Screening against the full mean
    is the common implementation and it is the weaker one.
    """
    idx = {}
    for j, r in enumerate(rows):
        idx.setdefault(r["item_id"], []).append(j)

    stats = [None] * len(rows)
    for js in idx.values():
        if len(js) < 3:            # two ratings cannot give a sd of the rest
            continue
        for j in js:
            rest = [float(rows[q]["score"]) for q in js if q != j]
            m = sum(rest) / len(rest)
            var = sum((x - m) ** 2 for x in rest) / (len(rest) - 1)
            stats[j] = (m, math.sqrt(var))
    return stats


def gate_outlier(rows, z=2.0):
    """Drop a rating sitting more than z sd from the other raters of its item."""
    stats = _loo_stats(rows)
    dropped = []
    for j, r in enumerate(rows):
        s = stats[j]
        if s is None or s[1] == 0.0:
            dropped.append(False)
            continue
        dropped.append(abs(float(r["score"]) - s[0]) > z * s[1])
    return dropped


def gate_rater(rows, min_r=0.20, min_n=5):
    """Drop every rating from a rater who does not track the rest of the panel.

    The rater's scores are correlated against the leave-one-out mean of the
    other raters on the same items. This is the screen a panel actually runs.
    A constant series has no variance, so its correlation is undefined and the
    rater is cut by definition rather than by threshold luck.
    """
    stats = _loo_stats(rows)
    per_rater = {}
    for j, r in enumerate(rows):
        if stats[j] is None:
            continue
        per_rater.setdefault(r["rater_id"], []).append(
            (float(r["score"]), stats[j][0]))

    bad = set()
    for rater, pairs in per_rater.items():
        if len(pairs) < min_n:
            continue
        xs = [a for a, _ in pairs]
        ys = [b for _, b in pairs]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
        sxx = sum((a - mx) ** 2 for a in xs)
        syy = sum((b - my) ** 2 for b in ys)
        if sxx == 0.0 or syy == 0.0:
            bad.add(rater)
            continue
        if sxy / math.sqrt(sxx * syy) < min_r:
            bad.add(rater)
    return [r["rater_id"] in bad for r in rows]


def both_gates(rows, z=2.0, min_r=0.20):
    a = gate_outlier(rows, z=z)
    b = gate_rater(rows, min_r=min_r)
    return [x or y for x, y in zip(a, b)]


def _rho(rows):
    out = icc_one_way(to_by_item(rows))
    return None if out is None else out[0]


def run_cell(kind, where, rate, rho_1=0.45, n_items=400, k_raters=5, seed=0,
             z=2.0, min_r=0.20):
    """One cell: damage before the gate, catch, collateral, damage after."""
    clean, _ = make_ratings(n_items=n_items, k_raters=k_raters,
                            rho_1=rho_1, seed=seed)
    dirty, flags = corrupt(clean, kind, rate, where=where, seed=seed + 1000)
    dropped = both_gates(dirty, z=z, min_r=min_r)
    kept = [r for r, d in zip(dirty, dropped) if not d]

    n_bad = sum(flags)
    n_good = len(flags) - n_bad
    caught = sum(1 for f, d in zip(flags, dropped) if f and d)
    collateral = sum(1 for f, d in zip(flags, dropped) if not f and d)

    return {
        "rho_clean": _rho(clean),
        "rho_dirty": _rho(dirty),
        "rho_gated": _rho(kept),
        "catch": caught / n_bad if n_bad else None,
        "collateral": collateral / n_good if n_good else 0.0,
    }


def _avg(cells, key):
    vals = [c[key] for c in cells if c.get(key) is not None]
    return sum(vals) / len(vals) if vals else None


def gate_sweep(z_values=(None, 3.0, 2.5, 2.0, 1.5, 1.0), rho_1=0.45,
               n_items=400, k_raters=5, seeds=12, scale=None, resamples=0):
    """What a gate reports on CLEAN data, as the threshold tightens.

    Nothing here is corrupted, so there is nothing to catch and the honest
    answer at every threshold is the value the rows were built with. The gate
    does not give that answer, and the direction of its error is the unsafe
    one: dropping the ratings that disagree most with the panel truncates the
    within-item spread, and a truncated spread IS higher agreement.

    z=None means the gate is effectively off.

    scale=(lo, hi) rounds every rating onto an integer scale, as a Likert panel
    would. This matters: the rest of this repository measures that rounding
    costs the estimate a few per cent, so a result obtained only on continuous
    scores would not obviously survive the form real ratings arrive in.

    resamples > 0 adds a bootstrap interval over items, taken on one seed --
    the seed-to-seed spread is reported separately as `spread`. The two answer
    different questions: the interval is how precisely one study of this size
    pins the number, the spread is how much the number moves between studies.
    """
    out = []
    for z in z_values:
        reported, dropped = [], []
        for seed in range(seeds):
            rows, _ = make_ratings(n_items=n_items, k_raters=k_raters,
                                   rho_1=rho_1, seed=seed, scale=scale)
            if z is None:
                kept, d = rows, [False] * len(rows)
            else:
                d = gate_outlier(rows, z=z)
                kept = [r for r, x in zip(rows, d) if not x]
            reported.append(_rho(kept))
            dropped.append(sum(d) / len(d))

        row = {"z": z,
               "dropped": sum(dropped) / len(dropped),
               "reported": sum(reported) / len(reported),
               "spread": (min(reported), max(reported)),
               "seeds": len(reported)}

        if resamples:
            rows, _ = make_ratings(n_items=n_items, k_raters=k_raters,
                                   rho_1=rho_1, seed=0, scale=scale)
            if z is None:
                kept = rows
            else:
                d = gate_outlier(rows, z=z)
                kept = [r for r, x in zip(rows, d) if not x]
            a = analyse(to_by_item(kept), resamples=resamples, seed=1)
            row["lo"], row["hi"] = a["rho_1_lo"], a["rho_1_hi"]
        out.append(row)
    return out


def sweep_report(rho_1=0.45, seeds=12, target=0.80, resamples=300, **kw):
    """The headline table, on continuous scores and again on a five-point scale.

    Both are shown because neither alone would settle it. Continuous scores are
    the model the estimator assumes; a five-point scale is the form real panel
    ratings arrive in, and rounding is known to cost a few per cent of the
    estimate. A result that appeared only on one of the two would be a property
    of the simulation rather than of the gate.
    """
    true_need = raters_needed(rho_1, target)
    out = {}
    for label, scale in (("CONTINUOUS SCORES", None),
                         ("FIVE-POINT SCALE (1-5)", (1, 5))):
        rows = gate_sweep(rho_1=rho_1, seeds=seeds, scale=scale,
                          resamples=resamples, **kw)
        out[label] = rows
        print("=" * 78)
        print(f"WHAT THE GATE REPORTS WHEN THERE IS NOTHING TO CATCH -- {label}")
        print("=" * 78)
        print(f"Clean rows built at rho_1 = {rho_1}. No corruption of any kind.")
        print("The only correct answer at every threshold is the built value.")
        print(f"Interval: bootstrap over items on one draw ({resamples} resamples).")
        print(f"Spread: min-max of the point estimate across {seeds} seeds.")
        print()
        print(f"{'threshold':>11s}{'dropped':>9s}{'reported':>10s}"
              f"{'95% interval':>20s}{'seed spread':>20s}"
              f"{'over':>7s}{'panel':>7s}")
        print("-" * 78)
        for r in rows:
            name = "off" if r["z"] is None else f"{r['z']:.1f} sd"
            over = r["reported"] / rho_1 - 1.0
            iv = (f"[{r['lo']:.3f}, {r['hi']:.3f}]" if r.get("lo") is not None
                  else "-")
            sp = f"[{r['spread'][0]:.3f}, {r['spread'][1]:.3f}]"
            print(f"{name:>11s}{r['dropped']:9.1%}{r['reported']:10.4f}"
                  f"{iv:>20s}{sp:>20s}{over:+7.0%}"
                  f"{raters_needed(r['reported'], target):7d}")
        print()

    cont = {r["z"]: r for r in out["CONTINUOUS SCORES"]}
    lik = {r["z"]: r for r in out["FIVE-POINT SCALE (1-5)"]}
    print(f"  A panel of {true_need} is what rho_1 = {rho_1} actually requires for")
    print(f"  rho_k = {target}. Every tightening of the gate reports a smaller one,")
    print("  on both scales.")
    print()
    print(f"  At 2.0 sd the overstatement is {cont[2.0]['reported'] / rho_1 - 1:+.0%} on")
    print(f"  continuous scores and {lik[2.0]['reported'] / rho_1 - 1:+.0%} on a five-point")
    print("  scale. Rounding changes the size and not the direction, which is the")
    print("  point of running both.")
    print()
    print("  The intervals matter for what can be claimed. Where the gate-off")
    print("  interval and a gated interval do not overlap, the difference is not")
    print("  a sampling accident at this study size. Where they do overlap, the")
    print("  seed spread is the honest summary and the claim is about the trend")
    print("  across thresholds rather than about any single row.")
    return out


def report_card(rate=0.30, seeds=12, target=0.80, **kw):
    """The 2x2: what the corruption looks like against where it sits."""
    rho_1 = kw.get("rho_1", 0.45)
    clean_cells = [run_cell(CRUDE, SCATTERED, 0.0, seed=s, **kw)
                   for s in range(seeds)]
    clean_ungated = _avg(clean_cells, "rho_dirty")
    clean_gated = _avg(clean_cells, "rho_gated")
    clean_collateral = _avg(clean_cells, "collateral")

    print()
    print("=" * 78)
    print("THE SAME GATE AGAINST FOUR KINDS OF BAD RATING")
    print("=" * 78)
    print(f"Ratings built at rho_1 = {rho_1}, "
          f"{kw.get('n_items', 400)} items x {kw.get('k_raters', 5)} raters, "
          f"{rate:.0%} corrupted, mean of {seeds} seeds.")
    print("Every kind of bad rating carries zero information about the item;")
    print("they differ in what they look like and in where they sit.")
    print()
    print(f"{'looks like':>11s}{'sits as':>11s}{'ungated':>10s}"
          f"{'gated':>9s}{'caught':>9s}{'panel':>8s}{'vs truth':>11s}")
    print("-" * 78)

    true_need = raters_needed(rho_1, target)
    print(f"{'(none)':>11s}{'-':>11s}{clean_ungated:10.4f}{clean_gated:9.4f}"
          f"{'-':>9s}{raters_needed(clean_gated, target):8d}"
          f"{clean_gated / rho_1 - 1.0:+11.0%}")

    table = []
    for kind in KINDS:
        for where in PLACES:
            cells = [run_cell(kind, where, rate, seed=s, **kw)
                     for s in range(seeds)]
            row = {"kind": kind, "where": where,
                   "rho_dirty": _avg(cells, "rho_dirty"),
                   "rho_gated": _avg(cells, "rho_gated"),
                   "catch": _avg(cells, "catch")}
            table.append(row)
            print(f"{kind:>11s}{where:>11s}{row['rho_dirty']:10.4f}"
                  f"{row['rho_gated']:9.4f}{row['catch']:9.0%}"
                  f"{raters_needed(row['rho_gated'], target):8d}"
                  f"{row['rho_gated'] / rho_1 - 1.0:+11.0%}")

    print()
    print(f"`panel` is the number of raters the gated estimate says is enough")
    print(f"for rho_k = {target}. The truth is {true_need}.")
    print("`vs truth` is how far the reported reliability sits from the value")
    print("the rows were built with.")
    print()

    caught = {(r["kind"], r["where"]): r["catch"] for r in table}
    print(f"  Caught: crude/rater {caught[(CRUDE, RATER)]:.0%}, "
          f"plausible/rater {caught[(PLAUSIBLE, RATER)]:.0%}, "
          f"crude/scattered {caught[(CRUDE, SCATTERED)]:.0%}, "
          f"plausible/scattered {caught[(PLAUSIBLE, SCATTERED)]:.0%}.")
    print()
    print("  Two separate things are visible here and they should not be")
    print("  merged. The rater screen works: corruption that sits inside one")
    print("  rater is caught whatever it looks like. The outlier screen does")
    print("  not: corruption spread thinly across raters is mostly missed --")
    print("  and the number still goes UP, because the screen is removing")
    print("  disagreement rather than error.")
    print()
    print(f"  On clean rows the gate drops {clean_collateral:.1%} of legitimate")
    print("  ratings and reports a reliability it did not measure. That price")
    print("  is paid in every cell, including the ones where it catches things.")
    return table


def dose_response(kind, where, rates=(0.0, 0.10, 0.20, 0.40), seeds=12, **kw):
    out = []
    for rate in rates:
        cells = [run_cell(kind, where, rate, seed=s, **kw) for s in range(seeds)]
        out.append({"rate": rate,
                    "rho_dirty": _avg(cells, "rho_dirty"),
                    "rho_gated": _avg(cells, "rho_gated"),
                    "catch": _avg(cells, "catch")})
    return out


def dose_report(rates=(0.0, 0.10, 0.20, 0.40), seeds=12, target=0.80, **kw):
    rho_1 = kw.get("rho_1", 0.45)
    print()
    print("=" * 78)
    print("DOSE-RESPONSE, AFTER THE GATE HAS RUN")
    print("=" * 78)
    print("Corruption spread thinly across raters, which is what a misaligned")
    print("clip or an ambiguous rubric produces. Both columns are the number a")
    print(f"study would publish. The built value is {rho_1} throughout.")
    print()
    print(f"{'rate':>7s}{'crude: rho':>13s}{'caught':>9s}"
          f"{'plausible: rho':>17s}{'caught':>9s}{'panel':>8s}")
    print("-" * 78)
    a = dose_response(CRUDE, SCATTERED, rates=rates, seeds=seeds, **kw)
    b = dose_response(PLAUSIBLE, SCATTERED, rates=rates, seeds=seeds, **kw)
    for x, y in zip(a, b):
        ca = "-" if x["catch"] is None else f"{x['catch']:.0%}"
        cb = "-" if y["catch"] is None else f"{y['catch']:.0%}"
        print(f"{x['rate']:7.0%}{x['rho_gated']:13.4f}{ca:>9s}"
              f"{y['rho_gated']:17.4f}{cb:>9s}"
              f"{raters_needed(y['rho_gated'], target):8d}")
    print()
    print("At every rate the published number stays within a few points of the")
    print(f"clean truth of {rho_1}, so nothing in the output announces that")
    print("corruption is present -- the gate has absorbed the evidence. A")
    print("dose-response curve like this one, run against an inert control, is")
    print("what turns 'our gate protects the yardstick' into a measured claim.")


def self_test():
    """Invariants that must hold before any table above is worth reading."""
    checks = []

    def check(ok, name, detail=""):
        checks.append((bool(ok), name, detail))

    rows, _ = make_ratings(n_items=300, k_raters=5, rho_1=0.45, seed=1)

    for kind in KINDS:
        out, flags = corrupt(rows, kind, 0.0, seed=1)
        check(out == rows and not any(flags), f"rate 0 is a no-op ({kind})")

    for kind in KINDS:
        out, flags = corrupt(rows, kind, 0.25, where=SCATTERED, seed=1)
        check(abs(sum(flags) - 0.25 * len(rows)) <= 1,
              f"scattered flag count matches the rate ({kind})", str(sum(flags)))

    # Rater-concentrated corruption must land inside whole raters, otherwise
    # the rater screen is being tested against something it was not given.
    out, flags = corrupt(rows, CRUDE, 0.25, where=RATER, seed=1)
    touched = {rows[i]["rater_id"] for i, f in enumerate(flags) if f}
    whole = all(all(flags[j] for j, r in enumerate(rows)
                    if r["rater_id"] == rater) for rater in touched)
    check(whole, "rater-concentrated corruption takes whole raters",
          f"{len(touched)} raters")

    # A plausible value is one that really occurs in the file. This is the
    # property that makes it invisible to a value-based screen, so it is
    # asserted rather than assumed.
    real = {round(float(r["score"]), 9) for r in rows}
    out, flags = corrupt(rows, PLAUSIBLE, 0.30, seed=2)
    strays = [out[i]["score"] for i, f in enumerate(flags)
              if f and round(float(out[i]["score"]), 9) not in real]
    check(not strays, "every plausible value occurs in the clean file",
          f"{len(strays)} strays")

    # Both kinds destroy signal, and by a comparable amount. If they did not,
    # any difference after the gate could be explained by the injection.
    drops = {}
    for kind in KINDS:
        dirty, _ = corrupt(rows, kind, 0.40, where=SCATTERED, seed=3)
        drops[kind] = _rho(rows) - _rho(dirty)
        check(drops[kind] > 0, f"{kind} lowers rho before any gate",
              f"{drops[kind]:+.4f}")
    ratio = drops[PLAUSIBLE] / drops[CRUDE] if drops[CRUDE] else float("inf")
    check(0.5 <= ratio <= 2.0, "ungated damage is comparable between arms",
          f"plausible/crude = {ratio:.2f}")

    # The rater screen must cut a straight-liner when the straight-lining is a
    # rater-level behaviour. This is the cell the gate is supposed to win.
    dirty, flags = corrupt(rows, CRUDE, 0.20, where=RATER, seed=4)
    dropped = both_gates(dirty)
    caught_cr = sum(1 for f, d in zip(flags, dropped) if f and d) / sum(flags)
    check(caught_cr > 0.9, "crude/rater corruption is caught",
          f"{caught_cr:.0%}")

    # The cell the gate loses: plausible values spread thinly.
    dirty, flags = corrupt(rows, PLAUSIBLE, 0.20, where=SCATTERED, seed=4)
    dropped = both_gates(dirty)
    caught_ps = sum(1 for f, d in zip(flags, dropped) if f and d) / sum(flags)
    check(caught_ps < caught_cr,
          "plausible/scattered is caught less than crude/rater",
          f"{caught_ps:.0%} vs {caught_cr:.0%}")

    # The gate costs something on clean data. A gate that never drops a
    # legitimate rating is not running at a threshold anyone uses.
    dropped = both_gates(rows)
    check(sum(dropped) > 0, "the gate drops clean ratings too",
          f"{sum(dropped)}/{len(rows)}")

    # A gate run at an unreachable threshold must be a no-op. If this fails,
    # every number in the sweep is measuring the harness and not the gate.
    loose = gate_outlier(rows, z=1e9)
    check(not any(loose), "an unreachable threshold drops nothing",
          f"{sum(loose)} dropped")

    # The headline: on CLEAN rows the reported reliability rises monotonically
    # as the screen tightens. Guarded here because it is the claim that would
    # be most costly to get wrong, and a silent regression would look like a
    # better result rather than a broken one.
    built, seq = 0.45, []
    for z in (1e9, 3.0, 2.5, 2.0, 1.5, 1.0):
        d = gate_outlier(rows, z=z)
        seq.append(_rho([r for r, x in zip(rows, d) if not x]))
    # A screen that leaves an item with fewer than two ratings makes rho
    # undefined. That is a failure of the check, not a pass, so it is caught
    # here rather than raised as a crash halfway down the list.
    if any(v is None for v in seq):
        check(False, "tightening the screen never lowers the reported rho",
              "rho undefined at some threshold")
        check(False, "a tight screen overstates a known rho_1", "undefined")
    else:
        monotone = all(b >= a - 1e-9 for a, b in zip(seq, seq[1:]))
        check(monotone, "tightening the screen never lowers the reported rho",
              " ".join(f"{v:.3f}" for v in seq))
        check(seq[-1] > built * 1.5, "a tight screen overstates a known rho_1",
              f"built {built} -> reported {seq[-1]:.4f}")

    # The rater screen must be harmless when there is nothing wrong. A screen
    # that cuts good raters on clean data would explain the inflation above
    # by itself, so the two are separated rather than assumed distinct.
    check(not any(gate_rater(rows)), "the rater screen spares a clean panel")

    # Arguments are checked rather than trusted.
    for bad_call in (lambda: corrupt(rows, "nonsense", 0.1),
                     lambda: corrupt(rows, CRUDE, 1.5),
                     lambda: corrupt(rows, CRUDE, 0.1, where="somewhere")):
        try:
            bad_call()
            check(False, "bad arguments are refused", "no error raised")
            break
        except ValueError:
            pass
    else:
        check(True, "bad arguments are refused")

    width = max(len(n) for _, n, _ in checks)
    bad = 0
    for ok, name, detail in checks:
        bad += not ok
        tail = f"   {detail}" if detail else ""
        print(f"  {'pass' if ok else 'FAIL'}  {name:<{width}s}{tail}")
    print()
    print(f"  {len(checks) - bad}/{len(checks)} invariants hold")
    return bad == 0


if __name__ == "__main__":
    if "--self-test" in sys.argv[1:]:
        sys.exit(0 if self_test() else 1)
    sweep_report()
    report_card()
    dose_report()

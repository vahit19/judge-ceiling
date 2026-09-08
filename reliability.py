"""
Rating rows in, a reliability table out.

This is the code that would run on real rating data. It takes the one input
that matters -- rows with rater identity preserved -- and produces, per
dimension:

    rho_1     reliability of a single rating
    rho_k     reliability of the k-rater mean          (Spearman-Brown)
    ceiling   sqrt(rho) -- what any judge can reach against that yardstick
    rho_g     a judge's disattenuated reliability      (if judge scores given)
    k_star    how many human ratings one judge rating is worth
    interval  bootstrap over ITEMS, because the item is the sampling unit

Nothing here is specific to one dataset. Point it at a CSV with the columns
item_id, rater_id, dimension, score and it runs.

Usage:
    python reliability.py                 # demo on simulated rows
    python reliability.py ratings.csv     # your own data
"""

import csv
import io
import math
import random
import sys
from collections import defaultdict

BOOTSTRAP_RESAMPLES = 400
INTERVAL = 0.95


# ---------------------------------------------------------------------------
# Variance components
# ---------------------------------------------------------------------------
def icc_one_way(by_item):
    """
    One-way random effects ICC from per-item rating lists.

    A rating is a true score plus independent error. Between-item mean square
    carries both; within-item mean square carries only the error. Their race
    gives the proportion that is real:

        ICC(1,1) = (MSB - MSW) / (MSB + (k-1) * MSW)      single rating
        ICC(1,k) = (MSB - MSW) /  MSB                     mean of k

    Returns (rho_1, rho_k, k) or None when the design cannot support it.
    Unbalanced designs use the mean number of ratings per item.
    """
    groups = [v for v in by_item.values() if len(v) >= 2]
    n = len(groups)
    if n < 2:
        return None
    k = sum(len(g) for g in groups) / n
    if k < 2:
        return None

    grand = sum(sum(g) for g in groups) / sum(len(g) for g in groups)
    means = [sum(g) / len(g) for g in groups]

    msb = sum(len(g) * (m - grand) ** 2 for g, m in zip(groups, means)) / (n - 1)
    within_df = sum(len(g) - 1 for g in groups)
    if within_df == 0:
        return None
    msw = sum((x - m) ** 2 for g, m in zip(groups, means) for x in g) / within_df

    denom_1 = msb + (k - 1) * msw
    if denom_1 <= 0 or msb <= 0:
        return None
    rho_1 = (msb - msw) / denom_1
    rho_k = (msb - msw) / msb
    # Negative variance estimates are a small-sample artefact, not a quantity.
    return max(rho_1, 0.0), max(rho_k, 0.0), k


def icc_two_way_consistency(rows):
    """
    Two-way consistency ICC -- the version that treats rater bias as a
    nuisance rather than as noise.

        absolute agreement : rho = s2_item / (s2_item + s2_rater + s2_resid)
        consistency        : rho = s2_item / (s2_item          + s2_resid)

    The only difference is the rater variance term. Removing systematic rater
    bias moves you from the first to the second -- and leaves the residual
    untouched. That is why removing bias is not the same as measuring
    reliability.

    Requires a FULLY CROSSED, BALANCED design: every rater rates every item,
    exactly once. The sums of squares only decompose orthogonally in that case.
    On an unbalanced design the item and rater effects are correlated, the
    residual is deflated, and the estimate can be badly wrong -- measured at
    +0.30 on data built at 0.45 with strong rater bias.

    So this function refuses rather than approximates. That is the same rule
    the substitution gate follows: when the design cannot support the estimate,
    say so instead of returning a number.

    rows: [(item, rater, score), ...].
    Returns (rho_1, s2_item, s2_rater, s2_resid), or None if the design is not
    crossed and balanced.
    """
    items = sorted({i for i, _, _ in rows})
    raters = sorted({r for _, r, _ in rows})
    n, k = len(items), len(raters)
    if n < 2 or k < 2:
        return None
    ii = {v: a for a, v in enumerate(items)}
    ri = {v: a for a, v in enumerate(raters)}

    # Refuse anything that is not fully crossed and balanced.
    if len(rows) != n * k:
        return None
    seen = {(i, r) for i, r, _ in rows}
    if len(seen) != n * k:
        return None                      # a duplicate or a missing cell

    grand = sum(x for _, _, x in rows) / len(rows)
    im, rm = defaultdict(list), defaultdict(list)
    for i, r, x in rows:
        im[ii[i]].append(x)
        rm[ri[r]].append(x)

    msb = sum(len(v) * (sum(v) / len(v) - grand) ** 2 for v in im.values()) / (n - 1)
    msr = sum(len(v) * (sum(v) / len(v) - grand) ** 2 for v in rm.values()) / (k - 1)
    ss_tot = sum((x - grand) ** 2 for _, _, x in rows)
    ss_item = sum(len(v) * (sum(v) / len(v) - grand) ** 2 for v in im.values())
    ss_rater = sum(len(v) * (sum(v) / len(v) - grand) ** 2 for v in rm.values())
    df_e = len(rows) - n - k + 1
    if df_e <= 0:
        return None
    mse = max(ss_tot - ss_item - ss_rater, 0.0) / df_e

    kbar = len(rows) / n
    if msb <= 0:
        return None
    s2_item = max((msb - mse) / kbar, 0.0)
    s2_rater = max((msr - mse) / (len(rows) / k), 0.0)
    denom = s2_item + mse
    if denom <= 0:
        return None
    return s2_item / denom, s2_item, s2_rater, mse


def spearman_brown(rho_1, k):
    """Reliability of the mean of k raters, given one rater's reliability."""
    if rho_1 <= 0:
        return 0.0
    return k * rho_1 / (1 + (k - 1) * rho_1)


def ceiling(rho):
    """No judge scored against this yardstick can correlate higher."""
    return math.sqrt(max(rho, 0.0))


def disattenuate(observed_r, rho_yardstick):
    """
    Correct a judge's observed correlation for the noise in what it was
    scored against. Without this every judge is understated.

    Returns a reliability, which is a squared quantity and therefore never
    negative. THE SIGN IS LOST HERE ON PURPOSE, and callers must check it
    separately: a judge that ranks quality backwards produces the same
    reliability as one that ranks it correctly. Using this figure without
    looking at the sign of `observed_r` would approve an inverted judge.
    """
    if rho_yardstick <= 0:
        return None
    return min(observed_r ** 2 / rho_yardstick, 1.0)


def substitution_ratio(rho_judge, rho_1):
    """
    Spearman-Brown, inverted: how many human ratings is one judge rating
    worth? The denominator blows up as rho_judge approaches 1, which is
    exactly why a point estimate is not enough.
    """
    if rho_1 <= 0 or rho_judge >= 1.0:
        return float("inf")
    if rho_judge <= 0:
        return 0.0
    return rho_judge * (1 - rho_1) / (rho_1 * (1 - rho_judge))


def pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    sxx = sum((a - mx) ** 2 for a in xs)
    syy = sum((b - my) ** 2 for b in ys)
    if sxx <= 0 or syy <= 0:
        return 0.0
    return sxy / math.sqrt(sxx * syy)


# ---------------------------------------------------------------------------
# One dimension, end to end
# ---------------------------------------------------------------------------
def analyse(by_item, judge=None, resamples=BOOTSTRAP_RESAMPLES, seed=0,
            rows=None):
    """
    by_item : {item_id: [score, ...]}   ratings grouped by item
    judge   : {item_id: score}          optional judge scores on the same items
    rows    : [(item, rater, score)]    the SAME ratings with rater identity
                                        kept. Supply this and the two-way model
                                        runs as well, separating rater bias
                                        from residual noise -- which is the
                                        whole reason rater-level rows are worth
                                        keeping in the first place.

    Bootstrap resamples ITEMS, not ratings -- the ratings of one item are not
    independent of each other, so resampling them would understate the width.
    Every quantity is recomputed inside the loop; freezing rho_1 and varying
    only the last step would understate it too.
    """
    base = icc_one_way(by_item)
    if base is None:
        return None
    rho_1, rho_k, k = base

    out = {"n_items": len(by_item), "k": k, "rho_1": rho_1, "rho_k": rho_k,
           "ceiling": ceiling(rho_k)}

    # Two-way, when the design allows it. It refuses unless fully crossed, so
    # None here means "the design cannot support it", not "it failed".
    if rows:
        two = icc_two_way_consistency(rows)
        if two:
            out.update(rho_1_consistency=two[0], var_item=two[1],
                       var_rater=two[2], var_resid=two[3],
                       n_raters=len({r for _, r, _ in rows}))
        else:
            out["two_way"] = None
            out["two_way_reason"] = ("design is not fully crossed - every rater "
                                     "must rate every item exactly once")

    if judge:
        shared = [i for i in by_item if i in judge]
        panel = [sum(by_item[i]) / len(by_item[i]) for i in shared]
        js = [judge[i] for i in shared]
        r = pearson(js, panel)
        rho_g = disattenuate(r, rho_k)
        # A judge that ranks quality backwards squares to the same reliability
        # as one that ranks it correctly. Carrying signal in the wrong
        # direction is not the same as being usable, and silently flipping it
        # is a decision nobody should make on the tool's behalf.
        inverted = r < 0
        out.update(observed_r=r, rho_judge=rho_g, n_shared=len(shared),
                   inverted=inverted,
                   ratio=0.0 if inverted or not rho_g
                   else substitution_ratio(rho_g, rho_1))

    rng = random.Random(seed)
    items = list(by_item)
    ratios, rho1s = [], []
    for _ in range(resamples):
        pick = [items[rng.randrange(len(items))] for _ in items]
        rs = defaultdict(list)
        for n, i in enumerate(pick):
            rs[(i, n)] = by_item[i]          # same item may appear twice
        b = icc_one_way(rs)
        if b is None:
            continue
        b1, bk, _ = b
        rho1s.append(b1)
        if judge:
            sh = [(i, n) for (i, n) in rs if i in judge]
            if len(sh) >= 2:
                p = [sum(rs[key]) / len(rs[key]) for key in sh]
                j = [judge[i] for i, _ in sh]
                r_b = pearson(j, p)
                g = disattenuate(r_b, bk)
                if g is not None:
                    ratios.append(0.0 if r_b < 0
                                  else substitution_ratio(g, b1))

    def pct(vals, q):
        if not vals:
            return None
        v = sorted(vals)
        return v[min(int(q * len(v)), len(v) - 1)]

    lo, hi = (1 - INTERVAL) / 2, 1 - (1 - INTERVAL) / 2
    out["rho_1_lo"], out["rho_1_hi"] = pct(rho1s, lo), pct(rho1s, hi)
    if judge:
        out["ratio_lo"], out["ratio_hi"] = pct(ratios, lo), pct(ratios, hi)
        # Two conditions, not one. A lower bound above 1 says the judge is
        # worth at least one human rating. But an interval running to
        # infinity means the ratio is not identified at this sample size --
        # the point estimate is then arbitrarily large and quoting it would
        # be exactly the number this method exists to delete.
        lo, hi = out["ratio_lo"], out["ratio_hi"]
        out["identified"] = bool(hi is not None and math.isfinite(hi))
        out["automatable"] = bool(lo and lo > 1.0 and out["identified"]
                                  and not out.get("inverted"))
        out["refusal_reason"] = (
            None if out["automatable"] else
            "judge is negatively correlated with the panel - it ranks quality "
            "backwards, and flipping it is a decision for a person, not a tool"
            if out.get("inverted") else
            "interval unbounded - ratio not identified at this sample size"
            if not out["identified"] else
            "lower bound below 1 - judge not worth one human rating")
    return out


def turns_needed(current_n, rho_lo, target=1.0):
    """
    A PLANNING FIGURE, not a result. Read it as an order of magnitude.

    Derivation and its limits: the half-width of a bootstrap interval shrinks
    roughly as 1/sqrt(n). If the lower bound must move up by a factor f to
    clear the threshold, the sample must grow by roughly f squared. That is
    the whole basis, and it is weak in two ways -- it assumes the point
    estimate does not move as data arrives, and the 1/sqrt(n) scaling is
    asymptotic, so it is unreliable at exactly the small n where the question
    is being asked.

    So the figure is rounded to two significant digits. A tool that refuses to
    quote a precise saving should not turn round and quote a precise sample
    size; "roughly this many more" is the honest form.
    """
    if rho_lo is None or rho_lo <= 0 or rho_lo >= target:
        return None
    factor = (target / rho_lo) ** 2
    need = math.ceil(current_n * factor) - current_n
    if need <= 0:
        return None
    digits = max(0, len(str(need)) - 2)          # two significant digits
    step = 10 ** digits
    return int(math.ceil(need / step) * step)


# ---------------------------------------------------------------------------
# Budget: what a panel size buys, and what running a smaller one costs
# ---------------------------------------------------------------------------
def raters_needed(rho_1, target):
    """
    Smallest panel size k whose mean reaches `target` reliability.

    Spearman-Brown solved for k:  k = target(1 - rho_1) / (rho_1(1 - target)).

    This is the "Z number of human readers" half of a sampling plan. The other
    half -- how many items -- is a precision question, not a reliability one,
    and is answered by the bootstrap interval, not by this function.

    Reliability 1.0 is unreachable at any finite k, so `target` must be below
    1. That is not a technicality: it is the reason the question has to be
    posed as "how good is good enough", never as "how many to be certain".
    """
    if not 0.0 < rho_1 < 1.0:
        raise ValueError("rho_1 must be in (0, 1)")
    if not 0.0 < target < 1.0:
        raise ValueError("target must be in (0, 1): rho = 1 needs infinitely many raters")
    if target <= rho_1:
        return 1
    return int(math.ceil(target * (1.0 - rho_1) / (rho_1 * (1.0 - target)) - 1e-12))


def budget_table(rho_1, ks=(1, 2, 3, 5, 8, 13)):
    """
    What each panel size buys -- and, for a smaller panel, what it forgoes.

    Per k: the reliability of the mean, the ceiling it puts on any judge
    measured against that panel, and `forgone` = 1 - ceiling, the share of the
    correlation scale that is unreachable however good the judge is, purely
    because the yardstick is this noisy.

    `forgone` is the number a budget decision actually needs. Running a
    smaller panel is a legitimate choice; running one without knowing what it
    costs is not. The cost of running fewer is stated per row rather than
    asserted in prose.

    Note what is NOT here: money. Cost per rating is the caller's, and the
    trade is only decidable once both sides are on the table.
    """
    if not 0.0 < rho_1 < 1.0:
        raise ValueError("rho_1 must be in (0, 1)")
    out, prev = [], None
    for k in sorted(set(int(k) for k in ks)):
        if k < 1:
            raise ValueError("panel size must be at least 1")
        rho_k = spearman_brown(rho_1, k)
        c = ceiling(rho_k)
        out.append({"k": k, "rho_k": rho_k, "ceiling": c, "forgone": 1.0 - c,
                    "gain_over_previous": None if prev is None else c - prev})
        prev = c
    return out


def budget_report(rho_1, ks=(1, 2, 3, 5, 8, 13)):
    print(f"one rater's reliability rho_1 = {rho_1:.4f}")
    print()
    print(f"{'raters':>7s}{'rho_k':>9s}{'ceiling':>9s}{'forgone':>9s}{'gain':>8s}")
    print("-" * 42)
    for r in budget_table(rho_1, ks):
        g = "-" if r["gain_over_previous"] is None else f"{r['gain_over_previous']:.4f}"
        print(f"{r['k']:7d}{r['rho_k']:9.4f}{r['ceiling']:9.4f}"
              f"{r['forgone']:9.4f}{g:>8s}")
    print()
    print("ceiling: the highest correlation ANY judge can show against a panel")
    print("of this size. forgone: what a perfect judge still cannot reach,")
    print("because the yardstick is noisy. gain: what the extra raters bought.")


# ---------------------------------------------------------------------------
# The other axis: how many items, not just how many raters
# ---------------------------------------------------------------------------
def _normal_quantile(p):
    """
    Inverse standard normal CDF, by bisection on erf. Standard library only,
    and accurate to floating point over the range a power calculation uses.
    """
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    lo, hi = -12.0, 12.0
    for _ in range(100):
        mid = (lo + hi) / 2.0
        if 0.5 * (1.0 + math.erf(mid / math.sqrt(2.0))) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def items_needed(effect_sd, rho_1, k, power=0.80, alpha=0.05):
    """
    Items per arm needed to detect an improvement of `effect_sd`, when each
    item is scored by the mean of k raters.

    A panel size answers "how reliable is the yardstick". It does not answer
    "how much data do I need", and the two are not independent: measurement
    error attenuates a standardised effect by sqrt(rho_k), and the required
    sample grows with the inverse SQUARE of what survives. So a noisy
    yardstick is not merely a weaker correlation -- it is a quadratic bill in
    items.

        observed effect = effect_sd * sqrt(rho_k)
        n per arm       = 2 * ((z_alpha + z_power) / observed effect)^2

    `effect_sd` is in standard deviations of the TRUE score, which is the
    scale the attenuation is defined on; quoting an effect on the observed
    scale instead would double-count the noise. Two independent arms, equal
    size, normal approximation, variance treated as known.

    This is a planning figure. Like every planning figure here it is an order
    of magnitude, not a quota.
    """
    if not 0.0 < rho_1 < 1.0:
        raise ValueError("rho_1 must be in (0, 1)")
    if effect_sd <= 0.0:
        raise ValueError("effect_sd must be positive")
    if not 0.0 < power < 1.0:
        raise ValueError("power must be in (0, 1)")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")
    if k < 1:
        raise ValueError("panel size must be at least 1")

    rho_k = spearman_brown(rho_1, k)
    if rho_k <= 0.0:
        return None
    observed = effect_sd * math.sqrt(rho_k)
    z_alpha = _normal_quantile(1.0 - alpha / 2.0)
    z_power = _normal_quantile(power)
    return int(math.ceil(2.0 * ((z_alpha + z_power) / observed) ** 2))


def matrix_table(rho_1, effects=(0.10, 0.20, 0.30, 0.50), ks=(1, 3, 5, 8, 13),
                 power=0.80, alpha=0.05):
    """
    The two-axis sampling plan: how many items, across how many raters, to
    detect a given improvement.

    Rows are effects, columns are panel sizes, cells are items per arm. A
    panel size alone is half a plan and an item count alone is the other
    half; the pair is what a study is actually costed on.

    Both axes are driven by the same single input. rho_1 sets how much of a
    real effect survives measurement at each panel size, and what survives
    sets how many items are needed. That is the concrete reason a sampling
    plan cannot be written without the reliability of one rating.
    """
    rows = []
    for effect in effects:
        cells = [{"k": k, "items": items_needed(effect, rho_1, k, power, alpha)}
                 for k in ks]
        rows.append({"effect": effect, "cells": cells})
    return rows


def matrix_report(rho_1, effects=(0.10, 0.20, 0.30, 0.50), ks=(1, 3, 5, 8, 13),
                  power=0.80, alpha=0.05):
    table = matrix_table(rho_1, effects, ks, power, alpha)
    print(f"one rater's reliability rho_1 = {rho_1:.4f}")
    print(f"items per arm, power {power:.0%}, alpha {alpha:g}")
    print()
    print(f"{'effect':>8s}" + "".join(f"{'k=' + str(k):>9s}" for k in ks))
    print("-" * (8 + 9 * len(ks)))
    for row in table:
        cells = "".join(
            f"{c['items']:>9d}" if c["items"] is not None else f"{'-':>9s}"
            for c in row["cells"])
        print(f"{row['effect']:>7.2f}s" + cells)
    print()
    print("Effects are in standard deviations of the true score. Reading right")
    print("along a row prices extra raters in items saved; reading down a")
    print("column prices ambition in items. Both need rho_1 and nothing else.")


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------
def load_csv(path):
    """
    item_id, rater_id, dimension, score

    Returns {dimension: (by_item, rows)} -- BOTH groupings. The rater id is
    carried through rather than dropped at the door: without it the two-way
    model cannot run, and asking for rater-level rows and then discarding them
    would be the same mistake this whole method warns about.
    """
    by_item = defaultdict(lambda: defaultdict(list))
    triples = defaultdict(list)
    with io.open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        missing = {"item_id", "rater_id", "dimension", "score"} - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV is missing required column(s): {sorted(missing)}")
        for row in reader:
            d, i, r = row["dimension"], row["item_id"], row["rater_id"]
            x = float(row["score"])
            by_item[d][i].append(x)
            triples[d].append((i, r, x))
    return {d: (dict(by_item[d]), triples[d]) for d in by_item}


def report(table):
    print(f"{'dimension':24s}{'items':>7s}{'k':>5s}{'rho_1':>9s}"
          f"{'95% interval':>20s}{'rho_k':>8s}{'ceiling':>9s}{'two-way':>10s}")
    print("-" * 92)
    for name, r in table.items():
        if r is None:
            print(f"{name:24s}   not computable from this design")
            continue
        iv = (f"[{r['rho_1_lo']:.3f}, {r['rho_1_hi']:.3f}]"
              if r["rho_1_lo"] is not None else "-")
        tw = (f"{r['rho_1_consistency']:10.4f}" if "rho_1_consistency" in r
              else f"{'-':>10s}")
        print(f"{name:24s}{r['n_items']:7d}{r['k']:5.1f}{r['rho_1']:9.4f}"
              f"{iv:>20s}{r['rho_k']:8.4f}{r['ceiling']:9.4f}{tw}")
    if any("rho_1_consistency" not in (r or {}) for r in table.values()):
        print()
        print("two-way column blank: design not fully crossed, so rater")
        print("bias cannot be separated from residual noise; one-way absorbs it.")


USAGE = """usage:
  python reliability.py                 the worked demo on generated data
  python reliability.py ratings.csv     item_id, rater_id, dimension, score
  python reliability.py --budget RHO    what each panel size buys at rho_1=RHO
  python reliability.py --matrix RHO    items x raters, to detect an effect
  python reliability.py --turns         same rows, turn vs conversation
"""

if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--budget":
        if len(args) < 2:
            sys.exit(USAGE)
        try:
            budget_report(float(args[1]))
        except ValueError as e:
            sys.exit(f"error: {e}")
    elif args and args[0] == "--matrix":
        if len(args) < 2:
            sys.exit(USAGE)
        try:
            matrix_report(float(args[1]))
        except ValueError as e:
            sys.exit(f"error: {e}")
    elif args and args[0] == "--turns":
        from simulate import conversation_demo
        conversation_demo()
    elif args and args[0] in ("-h", "--help"):
        print(USAGE)
    elif args:
        data = load_csv(args[0])
        report({d: analyse(bi, rows=rw) for d, (bi, rw) in data.items()})
    else:
        from simulate import demo
        demo()

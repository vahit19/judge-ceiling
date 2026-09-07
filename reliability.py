"""
The month-one pipeline: rating rows in, a reliability table out.

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

    Needs raters that repeat across items. rows: [(item, rater, score), ...].
    Returns (rho_1, s2_item, s2_rater, s2_resid) or None.
    """
    items = sorted({i for i, _, _ in rows})
    raters = sorted({r for _, r, _ in rows})
    n, k = len(items), len(raters)
    if n < 2 or k < 2:
        return None
    ii = {v: a for a, v in enumerate(items)}
    ri = {v: a for a, v in enumerate(raters)}

    grand = sum(x for _, _, x in rows) / len(rows)
    im, rm = defaultdict(list), defaultdict(list)
    for i, r, x in rows:
        im[ii[i]].append(x)
        rm[ri[r]].append(x)
    if any(len(v) < 2 for v in rm.values()):
        return None

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
def analyse(by_item, judge=None, resamples=BOOTSTRAP_RESAMPLES, seed=0):
    """
    by_item : {item_id: [score, ...]}   ratings, rater identity preserved
    judge   : {item_id: score}          optional judge scores on the same items

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

    if judge:
        shared = [i for i in by_item if i in judge]
        panel = [sum(by_item[i]) / len(by_item[i]) for i in shared]
        js = [judge[i] for i in shared]
        r = pearson(js, panel)
        rho_g = disattenuate(r, rho_k)
        out.update(observed_r=r, rho_judge=rho_g, n_shared=len(shared),
                   ratio=substitution_ratio(rho_g, rho_1) if rho_g else 0.0)

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
                g = disattenuate(pearson(j, p), bk)
                if g is not None:
                    ratios.append(substitution_ratio(g, b1))

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
        out["automatable"] = bool(lo and lo > 1.0 and out["identified"])
        out["refusal_reason"] = (
            None if out["automatable"] else
            "interval unbounded - ratio not identified at this sample size"
            if not out["identified"] else
            "lower bound below 1 - judge not worth one human rating")
    return out


def turns_needed(current_n, rho_lo, target=1.0):
    """
    When the interval does not clear the threshold, say what would settle it
    instead of quoting a number. Interval width shrinks roughly as 1/sqrt(n),
    so this is a scale estimate, not a promise -- and it is reported as such.
    """
    if rho_lo is None or rho_lo <= 0 or rho_lo >= target:
        return None
    factor = (target / rho_lo) ** 2
    return int(math.ceil(current_n * factor)) - current_n


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------
def load_csv(path):
    """item_id, rater_id, dimension, score  ->  {dimension: {item: [scores]}}"""
    dims = defaultdict(lambda: defaultdict(list))
    with io.open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            dims[row["dimension"]][row["item_id"]].append(float(row["score"]))
    return {d: dict(v) for d, v in dims.items()}


def report(table):
    print(f"{'dimension':24s}{'items':>7s}{'k':>5s}{'rho_1':>9s}"
          f"{'95% interval':>20s}{'rho_k':>8s}{'ceiling':>9s}")
    print("-" * 82)
    for name, r in table.items():
        if r is None:
            print(f"{name:24s}   not computable from this design")
            continue
        iv = (f"[{r['rho_1_lo']:.3f}, {r['rho_1_hi']:.3f}]"
              if r["rho_1_lo"] is not None else "-")
        print(f"{name:24s}{r['n_items']:7d}{r['k']:5.1f}{r['rho_1']:9.4f}"
              f"{iv:>20s}{r['rho_k']:8.4f}{r['ceiling']:9.4f}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        data = load_csv(sys.argv[1])
        report({d: analyse(v) for d, v in data.items()})
    else:
        from simulate import demo
        demo()

"""
Rating rows with a known answer.

On real data the true quality of an item is never observable, so an estimator
can never be checked directly. In simulation it is known by construction --
which is the only place the estimator itself can be validated.

That is the point of this file: before the pipeline is pointed at anyone's
data, it has to recover a reliability it was not told.

Usage:
    python simulate.py        # generate rows and check recovery
"""

import csv
import io
import math
import random


def make_ratings(n_items=300, k_raters=3, rho_1=0.45, rater_bias=0.0,
                 scale=None, seed=0, crossed=False):
    """
    Generate ratings whose single-rater reliability is rho_1 by construction.

    A rating is a true score plus independent error:

        x_ij = theta_i + e_ij            theta ~ N(0,1),  e ~ N(0, sigma^2)

    Reliability is the variance ratio 1 / (1 + sigma^2), so the sigma that
    produces a target rho_1 is sqrt(1/rho_1 - 1).

    rater_bias adds a per-rater offset: it shifts a rater's mean without
    touching the residual. That is the difference between bias and noise,
    made generatable so it can be measured.

    scale = (lo, hi) rounds to integers in that range, as a Likert panel
    would. Rounding costs a little reliability; the tests allow for it.

    Returns (rows, thetas) -- the true scores are returned so a judge can be
    built from them rather than from the panel.
    """
    rng = random.Random(seed)
    sigma = math.sqrt(1.0 / rho_1 - 1.0)
    # crossed=True gives every rater every item -- the balanced design the
    # two-way model requires. Otherwise raters are drawn from a larger pool,
    # which is what a real panel looks like and what the one-way model handles.
    pool = k_raters if crossed else max(k_raters * 4, 8)
    bias = {f"r{j}": rng.gauss(0, rater_bias) for j in range(pool)}
    raters = list(bias)

    rows, thetas = [], {}
    for i in range(n_items):
        theta = rng.gauss(0, 1)
        thetas[f"i{i}"] = theta
        for r in (raters if crossed else rng.sample(raters, k_raters)):
            x = theta + rng.gauss(0, sigma) + bias[r]
            if scale:
                lo, hi = scale
                x = min(max(round(x * (hi - lo) / 6 + (lo + hi) / 2), lo), hi)
            rows.append({"item_id": f"i{i}", "rater_id": r,
                         "dimension": "demo", "score": x})
    return rows, thetas


def make_judge(thetas, rho_judge=0.30, seed=1):
    """
    A judge built from the TRUE scores plus its own independent error, so its
    reliability is rho_judge by construction.

    It must not be built from the panel means. Doing so makes the judge share
    the panel's errors, its correlation with the panel is inflated, and the
    substitution ratio runs to infinity. That is judge contamination -- the
    same mistake this method warns about, and easy to make in a simulator
    before making it for real.
    """
    rng = random.Random(seed)
    sigma = math.sqrt(1.0 / rho_judge - 1.0)
    return {i: t + rng.gauss(0, sigma) for i, t in thetas.items()}


def to_by_item(rows):
    out = {}
    for r in rows:
        out.setdefault(r["item_id"], []).append(float(r["score"]))
    return out


def to_triples(rows):
    return [(r["item_id"], r["rater_id"], r["score"]) for r in rows]


def write_csv(rows, path):
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["item_id", "rater_id", "dimension", "score"])
        w.writeheader()
        w.writerows(rows)


def demo():
    from reliability import analyse, icc_two_way_consistency, turns_needed

    print("=" * 78)
    print("1) RECOVERY -- the estimator is told nothing about the answer")
    print("=" * 78)
    print(f"{'built with rho_1':>18s}{'recovered':>12s}{'95% interval':>22s}{'items':>8s}")
    print("-" * 78)
    for true_rho in (0.15, 0.30, 0.45, 0.70):
        rows, _ = make_ratings(n_items=400, k_raters=3, rho_1=true_rho, seed=7)
        r = analyse(to_by_item(rows), resamples=200)
        iv = f"[{r['rho_1_lo']:.3f}, {r['rho_1_hi']:.3f}]"
        print(f"{true_rho:18.2f}{r['rho_1']:12.4f}{iv:>22s}{r['n_items']:8d}")

    print()
    print("=" * 78)
    print("2) BIAS IS NOT NOISE -- and only a two-way model can tell them apart")
    print("=" * 78)
    print("Ratings built at rho_1 = 0.45 throughout, fully crossed design.")
    print("Only the rater offsets change.")
    print()
    print(f"{'rater bias sd':>14s}{'one-way':>10s}{'two-way':>10s}"
          f"{'s2_rater':>11s}{'s2_resid':>11s}")
    print("-" * 78)
    for bias in (0.0, 0.5, 1.0):
        rows, _ = make_ratings(n_items=400, k_raters=3, rho_1=0.45,
                               rater_bias=bias, seed=7, crossed=True)
        one = analyse(to_by_item(rows), resamples=1)["rho_1"]
        two = icc_two_way_consistency(to_triples(rows))
        print(f"{bias:14.1f}{one:10.4f}{two[0]:10.4f}{two[2]:11.4f}{two[3]:11.4f}")
    print()
    print("  One-way absorbs rater bias into the error and the estimate falls.")
    print("  Two-way separates it: s2_rater grows, the residual does not, and")
    print("  reliability stays where it was built. Removing bias is not the same")
    print("  operation as measuring reliability -- this is that, in numbers.")

    print()
    print("=" * 78)
    print("3) A JUDGE, AND WHETHER IT HAS EARNED THE RIGHT TO REPLACE PEOPLE")
    print("=" * 78)
    print(f"{'items':>7s}{'judge built at':>16s}{'ratio':>9s}"
          f"{'95% interval':>22s}   verdict")
    print("-" * 78)
    for n, rho_j in ((400, 0.30), (400, 0.60), (60, 0.60), (28, 0.60)):
        rows, thetas = make_ratings(n_items=n, k_raters=3, rho_1=0.28, seed=3)
        judge = make_judge(thetas, rho_judge=rho_j, seed=4)
        r = analyse(to_by_item(rows), judge=judge, resamples=200)
        iv = f"[{r['ratio_lo']:.2f}, {r['ratio_hi']:.2f}]"
        if r["automatable"]:
            verdict = "AUTOMATE"
        elif not r["identified"]:
            verdict = "REFUSE - interval unbounded"
        else:
            need = turns_needed(r["n_items"], r["ratio_lo"])
            verdict = "REFUSE - below 1" + (f"  (+{need} items)" if need else "")
        print(f"{n:7d}{rho_j:16.2f}{r['ratio']:9.2f}{iv:>22s}   {verdict}")
    print()
    print("  Same judge, same quality. Only the sample size changes -- and with")
    print("  it, whether anything can honestly be claimed. Refusing to answer is")
    print("  the finding, and the system says what would settle it instead.")


if __name__ == "__main__":
    demo()

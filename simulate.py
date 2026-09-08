"""
Rating rows with a known answer.

On real data the true quality of an item is never observable, so an estimator
can never be checked directly. In simulation it is known by construction --
which is the only place the estimator itself can be validated.

That is the point of this file: before the pipeline is pointed at anyone's
data, it has to recover a reliability it was not told.

WHAT THIS CANNOT DO, stated plainly. The rows are generated from exactly the
model the estimator assumes: one true score per item, plus independent
Gaussian error with a single variance. So the check is circular in one
specific way -- it can confirm the arithmetic, and it can never reveal that
the model is wrong for real ratings.

Real ratings depart from it in at least three ways, and two are measured in
the test suite rather than left as caveats:

    five-point scale     the model assumes a continuum; rounding costs
                         about 5% of the estimate at rho_1 = 0.45 and
                         about 11% at 0.70

    unequal rater noise  the model assumes one error variance; a realistic
                         spread of careful and careless raters costs about
                         a fifth of the estimate

    heavy-tailed error   if the error variance is not finite, reliability is
                         not defined at all, and no estimator can help

All the measured departures bias the estimate DOWNWARD, which is the safe
direction: understating reliability overstates how many raters are needed.
None of them touches the rho_1 >= r^2 bound, which comes from the published
correlations rather than from this estimator.

Usage:
    python simulate.py        # generate rows and check recovery
"""

import csv
import io
import math
import random


def make_ratings(n_items=300, k_raters=3, rho_1=0.45, rater_bias=0.0,
                 scale=None, seed=0, crossed=False, noise_spread=0.0):
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
    would. Rounding costs a little reliability; the tests measure how much.

    noise_spread makes raters differ in how noisy they are -- one careful, one
    average, one careless. Real panels are like this and the model is not: it
    assumes a single error variance. The tests measure the cost of that too.

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

    # Per-rater noise scale. 1.0 for everyone unless noise_spread is set.
    spread = {r: math.exp(rng.gauss(0, noise_spread)) for r in raters}

    rows, thetas = [], {}
    for i in range(n_items):
        theta = rng.gauss(0, 1)
        thetas[f"i{i}"] = theta
        for r in (raters if crossed else rng.sample(raters, k_raters)):
            x = theta + rng.gauss(0, sigma * spread[r]) + bias[r]
            if scale:
                lo, hi = scale
                x = min(max(round(x * (hi - lo) / 6 + (lo + hi) / 2), lo), hi)
            rows.append({"item_id": f"i{i}", "rater_id": r,
                         "dimension": "demo", "score": x})
    return rows, thetas


def make_conversation_ratings(n_conv=150, turns=8, k_raters=3, rho_conv=0.30,
                              turn_spread=0.7, seed=0):
    """
    Ratings of TURNS inside conversations -- the design an eval of a voice
    agent actually has, and the one the flat model above quietly assumes away.

        c_i           ~ N(0, 1)                  the conversation's quality
        theta_it      = c_i + d_it,  d ~ N(0, tau^2)   this turn deviates
        x_itj         = theta_it + e_itj, e ~ N(0, sigma^2)   a rater hears it

    Two different questions can be asked of the SAME rows, and they have two
    different answers:

        item = turn          -> rho = (1 + tau^2) / (1 + tau^2 + sigma^2)
        item = conversation  -> rho = 1 / (1 + tau^2 + sigma^2)

    The first is always the larger, because turn-to-turn variation counts as
    signal when the turn is the item and as error when the conversation is.
    So a turn-level reliability figure is not a conservative stand-in for a
    conversation-level one -- it is higher, and it answers a question nobody
    asked if the thing being judged is whether the whole call went right.

    The interval misleads in the same direction: calling the turn the item
    multiplies the item count by `turns`, and a bootstrap over items then
    reports roughly sqrt(turns) times more precision than the design earned,
    because turns within one call are not independent draws.

    Returns (rows, conv_truth). Each row carries both `item_id` (the turn) and
    `conv_id`, so the same file can be grouped either way -- which is the
    point: the grouping is a modelling decision, not a property of the data.
    """
    if turn_spread < 0:
        raise ValueError("turn_spread must be >= 0")
    tau2 = turn_spread ** 2
    resid = 1.0 / rho_conv - 1.0 - tau2
    if resid <= 0:
        raise ValueError(
            f"rho_conv={rho_conv} is unreachable with turn_spread={turn_spread}: "
            f"turn variation alone caps it at {1.0 / (1.0 + tau2):.4f}")
    sigma = math.sqrt(resid)
    rng = random.Random(seed)
    raters = [f"r{j}" for j in range(max(k_raters * 4, 8))]

    rows, truth = [], {}
    for i in range(n_conv):
        c = rng.gauss(0, 1)
        truth[f"c{i}"] = c
        for t in range(turns):
            theta = c + rng.gauss(0, turn_spread)
            for r in rng.sample(raters, k_raters):
                rows.append({"item_id": f"c{i}t{t}", "conv_id": f"c{i}",
                             "rater_id": r, "dimension": "demo",
                             "score": theta + rng.gauss(0, sigma)})
    return rows, truth


def group_by(rows, key):
    """Group the same rows by turn ("item_id") or by call ("conv_id")."""
    out = {}
    for row in rows:
        out.setdefault(row[key], []).append(row["score"])
    return out


def conversation_demo(seeds=30):
    """
    Same rows, two sampling units. Shows the size of the mistake.

    The point estimate is averaged over `seeds` runs rather than quoted from
    one, so the comparison is not a lucky draw: a single run of this design
    moves the estimate by about 0.03 either way, which is the same size as
    the effect being reported at the conversation level.
    """
    import reliability as rel

    rho_conv, spread, turns = 0.30, 0.7, 8
    tau2 = spread ** 2
    sigma2 = 1.0 / rho_conv - 1.0 - tau2
    built = {"turn": (1 + tau2) / (1 + tau2 + sigma2),
             "conversation": 1.0 / (1 + tau2 + sigma2)}

    runs = {"turn": [], "conversation": []}
    for s in range(seeds):
        rows, _ = make_conversation_ratings(rho_conv=rho_conv, turns=turns,
                                            turn_spread=spread, seed=s)
        for key, label in (("item_id", "turn"), ("conv_id", "conversation")):
            runs[label].append(rel.icc_one_way(group_by(rows, key))[0])

    rows, _ = make_conversation_ratings(rho_conv=rho_conv, turns=turns,
                                        turn_spread=spread, seed=0)

    print()
    print("SAME RATINGS, TWO SAMPLING UNITS")
    print("-" * 68)
    print(f"{'grouped by':>14s}{'items':>8s}{'built':>9s}"
          f"{'mean of %d' % seeds:>11s}{'95% interval':>21s}")
    for key, label in (("item_id", "turn"), ("conv_id", "conversation")):
        r = rel.analyse(group_by(rows, key), resamples=400, seed=1)
        iv = f"[{r['rho_1_lo']:.3f}, {r['rho_1_hi']:.3f}]"
        mean = sum(runs[label]) / len(runs[label])
        print(f"{label:>14s}{r['n_items']:8d}{built[label]:9.4f}"
              f"{mean:11.4f}{iv:>21s}")
    print()
    print("Grouping by turn reports the higher number AND the tighter")
    print("interval. Both are correct about turns, and neither licenses a")
    print("claim about whether the call went right: turn-to-turn variation")
    print("is signal when the turn is the item and error when the call is.")
    print("If the question is cross-turn behaviour, the call is the item --")
    print("and the price is above: fewer items, wider interval, lower rho.")


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

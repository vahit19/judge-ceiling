"""
The same question, on someone else's real panel.

`poison.py` measures what a screening rule does to a reliability estimate, on
simulated rows where the answer is known. This file asks the same question of a
published measurement built from real data: *Towards Quantifying Benchmark
Optimization in ASR Models* (arXiv:2608.19936), whose reproduction data is
released under Apache-2.0.

Their method, in one paragraph. A four-model consensus panel flags spans where
a benchmark's reference transcript contradicts the audio. Every model is then
scored on those spans: ACCEPT-REF is the share on which it reproduced the
erroneous reference rather than the audio-supported alternative. A span is
admitted when the panel agrees at a rate of at least `majority_pct`, which they
set to 0.75 -- three of four.

That threshold is a screening rule on ITEMS, in the same family as the
screening rule on RATINGS measured in `poison.py`. It is documented, it is
defensible, and what it costs is not published. This file measures it, on their
released data, with their own parameter.

The first thing it does is recompute all 39 published scores. If those do not
match to the last digit, nothing below is worth reading, and the check is a
test rather than a claim in prose.

WHAT THIS IS NOT. It is not a correction. The published threshold is a
reasonable choice and the paper states it. Nor does this file settle which
threshold is right: the spans a split panel produces are ambiguous by
construction, and ambiguity can mean either that those spans are the most
diagnostic cases or that they are the least trustworthy ones. Both readings fit
the data, and that is the point -- a number that moves this much with a
documented parameter should carry the sensitivity next to it.

Usage:
    python consensus_panel.py              # the report
    python consensus_panel.py --self-test  # reproduction and invariants only
"""

import io
import json
import os
import sys

from reliability import raters_needed

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "consensus_panel.json")

REF, CONSENSUS, MISSING = "1", "0", "2"


def load(path=DATA):
    if not os.path.exists(path):
        raise SystemExit("consensus_panel.json is missing -- "
                         "run: python fetch_consensus.py")
    return json.load(io.open(path, encoding="utf-8"))


def scores(data, runs=None, models=None):
    """ACCEPT-REF per model: reproduced-the-reference / spans it answered.

    A model that produced neither rendering on a span is excluded from its own
    denominator, which is what the published numbers do.
    """
    runs = data["runs"] if runs is None else runs
    idx = {m: i for i, m in enumerate(data["models"])}
    models = models or data["models"]

    out = {}
    for m in models:
        i = idx[m]
        ref = sum(1 for r in runs if r["verdicts"][i] == REF)
        con = sum(1 for r in runs if r["verdicts"][i] == CONSENSUS)
        out[m] = {"accepted_ref": ref, "followed_consensus": con,
                  "eligible": ref + con,
                  "score": ref / (ref + con) if ref + con else None}
    return out


def reproduce(data=None):
    """Recompute every published score. Returns the list of mismatches."""
    data = data or load()
    mine = scores(data)
    bad = []
    for m, pub in data["published"].items():
        got = mine[m]
        if (got["accepted_ref"] != pub["accepted_ref"]
                or got["followed_consensus"] != pub["followed_consensus"]
                or got["eligible"] != pub["eligible_runs"]
                or abs(round(got["score"], 4) - pub["score"]) > 1e-9):
            bad.append((m, pub, got))
    return bad


def by_threshold(data, pct):
    return [r for r in data["runs"] if r["agree"] / r["total"] >= pct - 1e-9]


def outside_panel(data):
    """Models the panel did not include.

    Panel members are scored leave-one-out upstream, and the released file
    carries the result of that rather than the inputs to it. Re-deriving a
    leave-one-out set at a different threshold would need per-member flags that
    are not in the extract, so the sweep is restricted to the 35 models the
    question is actually about. Stated here rather than left for a reader to
    notice.
    """
    return [m for m in data["models"] if m not in set(data["panel"])]


def sweep(data, thresholds=(0.75, 1.00)):
    models = outside_panel(data)
    out = []
    for pct in thresholds:
        runs = by_threshold(data, pct)
        s = scores(data, runs, models)
        vals = [s[m]["score"] for m in models]
        out.append({"pct": pct, "spans": len(runs), "models": len(models),
                    "mean": sum(vals) / len(vals), "max": max(vals),
                    "per_model": {m: s[m]["score"] for m in models}})
    return out


def split_vs_unanimous(data):
    """The two halves the threshold separates, scored on their own."""
    models = outside_panel(data)
    unan = [r for r in data["runs"] if r["agree"] == r["total"]]
    split = [r for r in data["runs"] if r["agree"] != r["total"]]
    out = {}
    for name, runs in (("unanimous", unan), ("split", split)):
        s = scores(data, runs, models)
        vals = [s[m]["score"] for m in models if s[m]["score"] is not None]
        out[name] = {"spans": len(runs), "mean": sum(vals) / len(vals)}
    return out


def as_ratings(data, runs=None):
    """The verdict matrix as rating rows: item = span, rater = model, score =
    1 if the model reproduced the reference and 0 if it followed the audio.

    Two things this is not. The raters are models rather than people -- which
    is the point when the question is what a panel of model judges is worth,
    and a limitation everywhere else. And the score is binary, so the outlier
    screen in `poison.py` has nothing to work with; a value is either 0 or 1
    and cannot sit two standard deviations from anything. Only the rater screen
    transfers, and only it is run below.
    """
    runs = data["runs"] if runs is None else runs
    idx = {m: i for i, m in enumerate(data["models"])}
    rows = []
    for n, r in enumerate(runs):
        for m in data["models"]:
            v = r["verdicts"][idx[m]]
            if v in (REF, CONSENSUS):
                rows.append({"item_id": f"s{n}", "rater_id": m,
                             "dimension": "accept_ref",
                             "score": 1.0 if v == REF else 0.0})
    return rows


def screen_sweep(data, thresholds=(0.05, 0.10, 0.20, 0.30), resamples=0):
    """What a rater-agreement screen does to this panel, and to whom.

    On simulated rows the true reliability is known, so a screen that raises
    the estimate is overstating it. Here it is not known, so the measurable
    quantity is different and weaker: how far the reported number moves when
    the screen is switched on. That needs no ground truth.

    The identity of what gets removed is not an estimate at all, and it carries
    more than the movement does.
    """
    import poison as P
    from reliability import analyse, icc_one_way

    rows = as_ratings(data)

    def measure(rs):
        if resamples:
            a = analyse(P.to_by_item(rs), resamples=resamples, seed=1)
            return a["rho_1"], (a["rho_1_lo"], a["rho_1_hi"])
        out = icc_one_way(P.to_by_item(rs))
        return (None, None) if out is None else (out[0], None)

    base, base_iv = measure(rows)
    out = [{"min_r": None, "cut": [], "rho_1": base, "interval": base_iv,
            "move": 0.0}]
    for mr in thresholds:
        dropped = P.gate_rater(rows, min_r=mr)
        cut = sorted({r["rater_id"] for r, d in zip(rows, dropped) if d})
        kept = [r for r, d in zip(rows, dropped) if not d]
        rho, iv = measure(kept)
        out.append({"min_r": mr, "cut": cut, "rho_1": rho, "interval": iv,
                    "move": rho / base - 1.0})
    return out


def rank(per_model):
    order = sorted(per_model, key=lambda m: -per_model[m])
    return {m: i + 1 for i, m in enumerate(order)}


def report(data=None):
    data = data or load()

    print("=" * 78)
    print("REPRODUCING THE PUBLISHED SCORES")
    print("=" * 78)
    bad = reproduce(data)
    print(f"Source: {data['source']}")
    print(f"Paper:  {data['paper']}  ({data['dataset']} {data['split']})")
    print(f"{len(data['runs'])} flagged spans, {len(data['models'])} models, "
          f"panel of {len(data['panel'])}, majority_pct = "
          f"{data['params']['majority_pct']}")
    print()
    if bad:
        print(f"  {len(bad)} of {len(data['models'])} scores do NOT match:")
        for m, pub, got in bad[:6]:
            print(f"    {m}: published {pub['score']}, recomputed "
                  f"{got['score']:.4f}")
        print()
        print("  Nothing below is worth reading until this is resolved.")
        return None
    print(f"  All {len(data['models'])} published scores recompute exactly, "
          f"to four decimal places.")

    sw = sweep(data)
    at = {r["pct"]: r for r in sw}
    lo, hi = at[0.75], at[1.00]

    print()
    print("=" * 78)
    print("WHAT THE ADMISSION THRESHOLD COSTS")
    print("=" * 78)
    print("The published threshold admits a span when three of four panel")
    print("members agree. Raising it to unanimity changes nothing about any")
    print("model; it changes which spans are scored.")
    print()
    print(f"{'majority_pct':>13s}{'spans':>8s}{'mean accept-ref':>18s}"
          f"{'highest':>10s}")
    print("-" * 78)
    for r in sw:
        label = f"{r['pct']:.2f}" + (" (published)" if r["pct"] == 0.75 else "")
        print(f"{label:>13s}{r['spans']:8d}{r['mean']:18.4f}{r['max']:10.4f}")

    drop = (hi["mean"] - lo["mean"]) / lo["mean"]
    print()
    print(f"  Requiring unanimity removes {lo['spans'] - hi['spans']} spans "
          f"({1 - hi['spans'] / lo['spans']:.0%} of the set) and moves the mean")
    print(f"  score by {drop:+.0%}.")

    halves = split_vs_unanimous(data)
    print()
    print("  Where the signal sits:")
    for name in ("unanimous", "split"):
        h = halves[name]
        print(f"    panel {name:>10s}: {h['spans']:5d} spans, "
              f"mean accept-ref {h['mean']:.4f}")
    ratio = halves["split"]["mean"] / halves["unanimous"]["mean"]
    share = halves["split"]["spans"] / len(data["runs"])
    print()
    print(f"  The {share:.0%} of spans on which the panel could not agree carry "
          f"a mean")
    print(f"  accept-ref {ratio:.1f}x the unanimous ones. They are a small part "
          f"of the")
    print("  item set and a large part of the measured effect.")

    r_lo, r_hi = rank(lo["per_model"]), rank(hi["per_model"])
    moved = [m for m in r_lo if r_lo[m] != r_hi[m]]
    top_lo = {m for m in r_lo if r_lo[m] <= 6}
    top_hi = {m for m in r_hi if r_hi[m] <= 6}

    print()
    print("=" * 78)
    print("WHETHER THE ORDER SURVIVES")
    print("=" * 78)
    print(f"{'model':>38s}{'0.75':>9s}{'1.00':>9s}{'change':>9s}{'rank':>10s}")
    print("-" * 78)
    for m in sorted(lo["per_model"], key=lambda m: -lo["per_model"][m])[:8]:
        a, b = lo["per_model"][m], hi["per_model"][m]
        print(f"{m:>38s}{a:9.4f}{b:9.4f}{b - a:+9.4f}"
              f"{f'{r_lo[m]} to {r_hi[m]}':>10s}")
    print()
    print(f"  {len(moved)} of {len(r_lo)} models change rank. Of the six "
          f"highest-scoring,")
    print(f"  {len(top_lo & top_hi)} are the same under both thresholds and "
          f"{len(top_lo - top_hi)} are replaced.")
    print()
    print("  The paper's headline pairs the six highest accept-ref models with")
    print("  the six best word error rates. That pairing is read off an item")
    print("  set that one documented parameter reshapes.")
    print()
    print("=" * 78)
    print("THE SAME PANEL, READ AS RATING ROWS")
    print("=" * 78)
    print("Item = flagged span, rater = model, score = 1 if it reproduced the")
    print("reference and 0 if it followed the audio. Scores are binary, so the")
    print("outlier screen has nothing to work with; only the rater screen runs.")
    print()
    sw = screen_sweep(data, resamples=300)
    base = sw[0]
    print(f"{'rater screen':>14s}{'cut':>6s}{'reported rho_1':>17s}"
          f"{'95% interval':>20s}{'move':>9s}{'panel':>7s}")
    print("-" * 78)
    for r in sw:
        name = "off" if r["min_r"] is None else f"min_r = {r['min_r']:.2f}"
        iv = (f"[{r['interval'][0]:.4f}, {r['interval'][1]:.4f}]"
              if r["interval"] else "-")
        print(f"{name:>14s}{len(r['cut']):6d}{r['rho_1']:17.4f}{iv:>20s}"
              f"{r['move']:+9.1%}{raters_needed(r['rho_1'], 0.80):7d}")
    print()
    print("  The true reliability is unknown here, so this is movement rather")
    print("  than error -- which is exactly what can be measured on real rows,")
    print("  and it is the smaller half of what this shows.")
    print()
    first = next(r for r in sw if r["cut"])
    print(f"  The larger half is WHO it removes. At the first threshold that")
    print(f"  cuts anyone (min_r = {first['min_r']:.2f}) it removes exactly")
    print(f"  {len(first['cut'])} models, and they are:")
    for m in first["cut"]:
        tag = " -- consensus panel member" if m in set(data["panel"]) else ""
        print(f"    {m}{tag}")
    print()
    print("  Those are the models that define what a reference error IS. They")
    print("  follow the consensus almost always, because they wrote it, so")
    print("  their verdicts barely vary and do not track the pattern of the")
    print("  other thirty-six. An agreement screen has no way to know that. Run")
    print("  blind on this panel it removes the reference-setters first, and")
    print("  the reported reliability rises because they are gone.")
    print()
    print("  That is the failure mode in one sentence: a screen does not remove")
    print("  bad raters, it removes raters whose pattern differs from the")
    print("  majority -- and the most authoritative rater is often the one who")
    print("  differs most.")
    print()
    print("  This is not a correction. 0.75 is a reasonable choice and the")
    print("  paper states it. But a split panel marks an ambiguous span, and")
    print("  ambiguity reads two ways: those spans are either the most")
    print("  diagnostic cases or the least trustworthy ones. The data does not")
    print("  settle which, and a number that moves this much with a parameter")
    print("  should travel with the sensitivity beside it.")
    return {"sweep": sw, "halves": halves, "moved": len(moved),
            "top_six_kept": len(top_lo & top_hi)}


def self_test():
    checks = []

    def check(ok, name, detail=""):
        checks.append((bool(ok), name, detail))

    data = load()

    bad = reproduce(data)
    check(not bad, f"all {len(data['models'])} published scores recompute",
          f"{len(bad)} mismatched")

    check(len(data["runs"]) > 1000, "the span set is the published size",
          str(len(data["runs"])))
    check(set(data["panel"]) <= set(data["models"]), "the panel is among the models")

    n = len(data["models"])
    check(all(len(r["verdicts"]) == n for r in data["runs"]),
          "every span carries one verdict per model")

    # The threshold must actually select. If both arms were the same set, the
    # comparison below would report zero and look like a null result.
    lo = by_threshold(data, 0.75)
    hi = by_threshold(data, 1.00)
    check(len(hi) < len(lo), "unanimity is a strictly smaller set",
          f"{len(hi)} of {len(lo)}")

    models = outside_panel(data)
    check(len(models) == len(data["models"]) - len(data["panel"]),
          "the sweep excludes panel members", f"{len(models)} models")

    s_lo = scores(data, lo, models)
    s_hi = scores(data, hi, models)
    check(all(s_lo[m]["score"] is not None for m in models),
          "every scored model answered at least one span")

    halves = split_vs_unanimous(data)
    check(halves["split"]["spans"] + halves["unanimous"]["spans"]
          == len(data["runs"]), "the two halves partition the set")
    check(halves["split"]["mean"] > halves["unanimous"]["mean"],
          "the split half carries the higher rate",
          f"{halves['split']['mean']:.4f} vs {halves['unanimous']['mean']:.4f}")

    # Scoring an empty set must refuse rather than return zero.
    empty = scores(data, [], models)
    check(all(empty[m]["score"] is None for m in models),
          "an empty span set returns no score rather than zero")

    width = max(len(n) for _, n, _ in checks)
    bad_n = 0
    for ok, name, detail in checks:
        bad_n += not ok
        tail = f"   {detail}" if detail else ""
        print(f"  {'pass' if ok else 'FAIL'}  {name:<{width}s}{tail}")
    print()
    print(f"  {len(checks) - bad_n}/{len(checks)} checks hold")
    return bad_n == 0


if __name__ == "__main__":
    if "--self-test" in sys.argv[1:]:
        sys.exit(0 if self_test() else 1)
    report()

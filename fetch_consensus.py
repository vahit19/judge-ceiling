"""
Public URL -> consensus_panel.json, with validation.

The source is the released reproduction data for *Towards Quantifying Benchmark
Optimization in ASR Models* (arXiv:2608.19936), Apache-2.0, from
github.com/HumeAI/asr-benchmark-optimization. Two files are read:

    repro/data/consensus/vox_en_newwl4_samples.json     ~8 MB
    repro/data/consensus/vox_en_newwl4_aggregate.json   ~8 KB

The first holds, for every flagged reference-error span, one verdict per model:
`ref` if the model reproduced the erroneous reference, `consensus` if it
followed the audio-supported alternative, absent if the model produced neither.
The second holds the published per-model scores.

Only the verdict matrix is kept here -- the source transcripts are not needed
for anything downstream and are 60x the size. What is written is a derived
extract of about 130 KB: the model list, the parameters, and one string of
digits per span. The published scores are kept alongside it so that a
recomputation can be checked against them rather than trusted.

    python fetch_consensus.py           # fetch and write consensus_panel.json
    python fetch_consensus.py --check   # re-fetch and diff against the saved file

`--check` exits non-zero if the upstream data has changed. That is what makes
the saved file a claim about someone else's published numbers rather than a
copy of them.
"""

import io
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "consensus_panel.json")

BASE = ("https://raw.githubusercontent.com/HumeAI/asr-benchmark-optimization/"
        "main/repro/data/consensus/")
SAMPLES = BASE + "vox_en_newwl4_samples.json"
AGGREGATE = BASE + "vox_en_newwl4_aggregate.json"

SOURCE = ("HumeAI/asr-benchmark-optimization, repro/data/consensus/"
          "vox_en_newwl4_{samples,aggregate}.json, Apache-2.0")

# One digit per model per span. `missing` is a real state and not a zero: the
# model produced neither rendering, and the published scores exclude those
# spans from that model's denominator rather than counting them as correct.
CODES = {"consensus": "0", "ref": "1", None: "2"}
DECODE = {"0": "consensus", "1": "ref", "2": "missing"}


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def build():
    samples = _get(SAMPLES)
    agg = _get(AGGREGATE)

    models = sorted({m for rec in samples for run in rec["runs"]
                     for m in (run.get("verdict") or {})})
    runs = []
    for rec in samples:
        for run in rec["runs"]:
            v = run.get("verdict") or {}
            runs.append({
                "key": rec["key"],
                "type": run["run_type"],
                "agree": run["n_wl_agree"],
                "total": run["n_wl_total"],
                "verdicts": "".join(CODES.get(v.get(m), "2") for m in models),
            })

    published = {x["model"]: {"score": x["benchmaxx_score"],
                              "accepted_ref": x["accepted_ref"],
                              "followed_consensus": x["followed_consensus"],
                              "eligible_runs": x["eligible_runs"],
                              "in_panel": x["in_whitelist"]}
                 for x in agg["benchmaxx_leaderboard"]}

    out = {
        "source": SOURCE,
        "paper": "arXiv:2608.19936",
        "dataset": agg["dataset"],
        "split": agg["split"],
        "panel": agg["whitelist"],
        "params": agg["params"],
        "codes": DECODE,
        "models": models,
        "published": published,
        "runs": runs,
    }
    _validate(out)
    return out


def _validate(data):
    """Refuse to save anything the analysis would silently misread."""
    n_models = len(data["models"])
    assert n_models > 1, "no models"
    assert data["runs"], "no runs"
    for r in data["runs"]:
        assert len(r["verdicts"]) == n_models, (r["key"], len(r["verdicts"]))
        assert set(r["verdicts"]) <= set(DECODE), r["verdicts"]
        assert 0 < r["total"] and 0 < r["agree"] <= r["total"], r
    assert set(data["panel"]) <= set(data["models"]), "panel is not a subset"
    assert set(data["published"]) == set(data["models"]), "score/model mismatch"
    # The published majority threshold must actually bind: every released span
    # has to clear it, or the saved file is not the set that was scored.
    pct = data["params"]["majority_pct"]
    bad = [r for r in data["runs"] if r["agree"] / r["total"] < pct - 1e-9]
    assert not bad, f"{len(bad)} runs below the published majority_pct"


def save(data, path=OUT):
    io.open(path, "w", encoding="utf-8").write(
        json.dumps(data, indent=1, sort_keys=True) + chr(10))
    print(f"wrote {os.path.basename(path)}  "
          f"({len(data['runs'])} spans x {len(data['models'])} models, "
          f"{os.path.getsize(path) / 1024:.0f} KB)")


def check(path=OUT):
    if not os.path.exists(path):
        print("consensus_panel.json is missing -- run: python fetch_consensus.py")
        return False
    saved = json.load(io.open(path, encoding="utf-8"))
    fresh = build()
    if saved == fresh:
        print("consensus_panel.json matches the upstream data")
        return True
    for key in sorted(set(saved) | set(fresh)):
        if saved.get(key) != fresh.get(key):
            print(f"  differs: {key}")
    return False


if __name__ == "__main__":
    if "--check" in sys.argv[1:]:
        sys.exit(0 if check() else 1)
    save(build())

"""
Tests for the rating store.

The store exists to make two named traps impossible rather than merely
documented, so most of what follows asserts a REFUSAL. A store that accepts
everything is not a store, it is a folder.

    python test_store.py
"""

import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import store                                              # noqa: E402
from reliability import analyse, icc_two_way_consistency  # noqa: E402

HEADER = "item_id,rater_id,dimension,score\n"


def write_csv(rows, header=HEADER):
    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(header)
        for r in rows:
            f.write(",".join(str(x) for x in r) + "\n")
    return path


def fresh_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    return store.connect(path), path


def balanced(n_items=12, k=3, base=3.0):
    """A small crossed design: every rater scores every item."""
    return [(f"i{i}", f"r{r}", "warmth", base + (i % 5) * 0.5 + r * 0.1)
            for i in range(n_items) for r in range(k)]


# ------------------------------------------------------------ the basics

def test_round_trip_preserves_rater_identity():
    """
    The whole method depends on rater-level rows. If the store returned only
    per-item means it would be a faster way of destroying the same
    information the pipeline needs.
    """
    db, _ = fresh_db()
    store.ingest(db, write_csv(balanced()), "v1")
    data, rubric = store.load(db)
    assert rubric == "v1"
    by_item, rows = data["warmth"]
    assert len(by_item) == 12
    assert len(rows) == 36
    raters = {r for _, r, _ in rows}
    assert raters == {"r0", "r1", "r2"}, raters


def test_two_way_model_runs_from_the_store():
    """
    The check that the round trip is not merely shaped right: the model that
    needs rater identity has to actually run on what comes back.
    """
    db, _ = fresh_db()
    store.ingest(db, write_csv(balanced()), "v1")
    data, _ = store.load(db)
    by_item, rows = data["warmth"]
    assert icc_two_way_consistency(rows) is not None
    assert analyse(by_item, rows=rows)["rho_1"] is not None


# ------------------------------------------------- refusals: bad input

def test_a_file_without_rater_id_is_refused():
    path = write_csv([("i1", "warmth", 4)], "item_id,dimension,score\n")
    db, _ = fresh_db()
    try:
        store.ingest(db, path, "v1")
        raise AssertionError("accepted a file with no rater_id")
    except ValueError as e:
        assert "rater_id" in str(e), e


def test_non_numeric_and_empty_scores_are_refused():
    db, _ = fresh_db()
    for bad in ([("i1", "r1", "warmth", "high")],
                [("i1", "r1", "warmth", "")],
                [("i1", "r1", "warmth", "inf")]):
        try:
            store.ingest(db, write_csv(bad), "v1")
            raise AssertionError(f"accepted {bad}")
        except ValueError:
            pass


def test_ingest_without_a_rubric_version_is_refused():
    """
    A rubric version is not metadata. Without it the store cannot tell two
    scales apart later, and by then the scores are already mixed.
    """
    db, _ = fresh_db()
    try:
        store.ingest(db, write_csv(balanced()), "")
        raise AssertionError("accepted ratings with no rubric version")
    except ValueError as e:
        assert "rubric" in str(e).lower(), e


# ------------------------------------------- refusals: the two real traps

def test_pooling_across_rubric_versions_is_refused():
    """
    THE POINT OF THIS MODULE. Scores given under different rubric versions are
    different measurements. Averaging across them yields a reliability figure
    for a construct nobody defined, and it looks exactly like a real one.
    """
    db, _ = fresh_db()
    store.ingest(db, write_csv(balanced(base=3.0)), "v1")
    store.ingest(db, write_csv(balanced(base=4.0)), "v2")
    try:
        store.load(db)
        raise AssertionError("pooled two rubric versions without being asked")
    except ValueError as e:
        assert "rubric" in str(e).lower(), e

    # ...and naming one is enough to proceed
    data, rubric = store.load(db, rubric="v2")
    assert rubric == "v2"
    assert len(data["warmth"][1]) == 36


def test_the_same_file_twice_does_not_double_the_data():
    """
    Content addressing, so a retried load cannot inflate the item count. An
    estimator fed duplicated rows reports a tighter interval than the design
    earned -- the failure is invisible and points the wrong way.
    """
    db, _ = fresh_db()
    path = write_csv(balanced())
    n1, sha1, seen1 = store.ingest(db, path, "v1")
    n2, sha2, seen2 = store.ingest(db, path, "v1")
    assert (n1, seen1) == (36, False)
    assert (n2, seen2) == (0, True)
    assert sha1 == sha2
    assert len(store.load(db)[0]["warmth"][1]) == 36


def test_the_same_bytes_cannot_be_relabelled_under_another_rubric():
    """
    Otherwise the same scores would sit on two scales at once, which is the
    drift this module is built to prevent, arriving through the front door.
    """
    db, _ = fresh_db()
    path = write_csv(balanced())
    store.ingest(db, path, "v1")
    try:
        store.ingest(db, path, "v2")
        raise AssertionError("let the same bytes be declared under two rubrics")
    except ValueError as e:
        assert "already ingested" in str(e), e


# ----------------------------------------------------------- provenance

def test_every_rating_traces_back_to_the_bytes_it_came_from():
    """
    "Which file produced this number" has to be answerable a year later, or a
    published figure cannot be reproduced -- and reproducibility here is a
    commercial obligation rather than an engineering nicety.
    """
    db, _ = fresh_db()
    path = write_csv(balanced())
    _, sha, _ = store.ingest(db, path, "v1")
    src = store.provenance(db)
    assert len(src) == 1
    assert src[0][0] == sha and src[0][4] == 36
    orphans = db.execute(
        "SELECT COUNT(*) FROM ratings r LEFT JOIN sources s "
        "ON r.source_sha = s.sha256 WHERE s.sha256 IS NULL").fetchone()[0]
    assert orphans == 0, f"{orphans} ratings with no source"


def test_a_rating_is_unique_per_item_rater_dimension_and_rubric():
    """
    One rater cannot hold two scores for the same item under the same rubric.
    Duplicate rows are a data error, and silently keeping both would understate
    disagreement -- an error in the flattering direction.
    """
    db, _ = fresh_db()
    rows = balanced(n_items=2, k=2)
    store.ingest(db, write_csv(rows + [("i0", "r0", "warmth", 1.0)]), "v1")
    n = db.execute("SELECT COUNT(*) FROM ratings").fetchone()[0]
    assert n == 4, n


def test_pooling_two_rubrics_understates_both_of_them():
    """
    What the refusal above is worth, measured rather than asserted.

    Two rubric versions of the same dimension, built at different
    reliabilities. Ignore the rubric column and the estimator sees one item
    scored by twice as many raters -- so it reports a single figure that
    belongs to neither scale, BELOW both, and with an inflated rater count
    that makes the design look stronger than it was. Every part of that error
    points somewhere a reader would not think to check.
    """
    from collections import defaultdict
    from reliability import icc_one_way

    # Different bases, because a rubric revision moves the scale -- and
    # because identical bytes are (correctly) refused a second label.
    db, _ = fresh_db()
    store.ingest(db, write_csv(balanced(n_items=40, k=3, base=2.0)), "v1")
    store.ingest(db, write_csv(balanced(n_items=40, k=3, base=4.0)), "v2")

    per = {}
    for rub in ("v1", "v2"):
        by_item, rows = store.load(db, rubric=rub)[0]["warmth"]
        per[rub] = icc_one_way(by_item)

    pooled = defaultdict(list)
    for i, _, s in (store.load(db, rubric="v1")[0]["warmth"][1]
                    + store.load(db, rubric="v2")[0]["warmth"][1]):
        pooled[i].append(s)
    mixed = icc_one_way(pooled)

    assert abs(per["v1"][2] - 3.0) < 1e-9 and abs(per["v2"][2] - 3.0) < 1e-9
    assert abs(mixed[2] - 6.0) < 1e-9, (
        f"pooling should double the apparent raters, got k={mixed[2]}")
    assert mixed[0] < min(per["v1"][0], per["v2"][0]) + 1e-9, (
        f"pooled {mixed[0]:.4f} should not sit above either scale "
        f"({per['v1'][0]:.4f}, {per['v2'][0]:.4f})")


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

"""
A rating store: what the pipeline reads from once it is more than one run.

reliability.py takes a CSV, and a CSV is enough to compute a number once. It
is not enough to defend that number later, and it cannot stop the two ways a
reliability estimate goes wrong without complaining:

    rubric drift   scores given under different rubric versions are not on
                   the same scale. Pooling them compares nothing, and the
                   result still looks like a number.

    provenance     "which file produced this figure" has to be answerable, or
                   a published number is an assertion rather than a claim.

Both are named as traps in the method and neither was enforced anywhere. This
module turns them into refusals: rater identity, rubric version and a content
hash of every ingested file are kept, and the operations that would silently
mix them fail instead.

sqlite3 ships with Python, so this adds no dependency.

Usage:
    python store.py ingest ratings.csv --rubric v1
    python store.py sources
    python store.py analyse                      # every dimension
    python store.py analyse --dimension warmth --rubric v1
"""

import argparse
import csv
import hashlib
import io
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone

DEFAULT_DB = "ratings.db"
REQUIRED = ("item_id", "rater_id", "dimension", "score")

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    sha256      TEXT PRIMARY KEY,
    path        TEXT NOT NULL,
    rubric      TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    n_rows      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS ratings (
    item_id     TEXT NOT NULL,
    rater_id    TEXT NOT NULL,
    dimension   TEXT NOT NULL,
    rubric      TEXT NOT NULL,
    score       REAL NOT NULL,
    source_sha  TEXT NOT NULL REFERENCES sources(sha256),
    PRIMARY KEY (item_id, rater_id, dimension, rubric)
);

CREATE INDEX IF NOT EXISTS ratings_by_dim ON ratings(dimension, rubric);
"""


def connect(path=DEFAULT_DB):
    db = sqlite3.connect(path)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(SCHEMA)
    return db


def file_sha256(path):
    """Content address. Two files with the same bytes are the same source."""
    h = hashlib.sha256()
    with io.open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_rows(path):
    """
    Parse and validate before anything touches the database.

    The rater id is required, not optional. A store that accepts rows without
    it would hold data on which the two-way model cannot run, and the gap
    would only surface much later, as a missing column in an analysis.
    """
    rows = []
    with io.open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fields = set(reader.fieldnames or [])
        missing = set(REQUIRED) - fields
        if missing:
            raise ValueError(f"missing required column(s): {sorted(missing)}")
        for n, row in enumerate(reader, start=2):      # line 1 is the header
            for col in REQUIRED:
                if row.get(col) is None or row[col] == "":
                    raise ValueError(f"line {n}: empty {col}")
            try:
                score = float(row["score"])
            except ValueError:
                raise ValueError(f"line {n}: score is not a number: {row['score']!r}")
            if score != score or score in (float("inf"), float("-inf")):
                raise ValueError(f"line {n}: score is not finite")
            rows.append((row["item_id"], row["rater_id"], row["dimension"], score))
    if not rows:
        raise ValueError("no rows")
    return rows


def ingest(db, path, rubric):
    """
    Load one file under one rubric version.

    Ingesting the same bytes twice is a no-op rather than a duplication: the
    file is addressed by its content hash, so a retried or repeated load
    cannot inflate the item count. Reproducibility is a property of the
    ingest path, not something bolted on when someone asks.

    Returns (n_inserted, sha, already_present).
    """
    if not rubric:
        raise ValueError("a rubric version is required: scores from different "
                         "rubric versions are not on the same scale")
    sha = file_sha256(path)
    seen = db.execute("SELECT rubric FROM sources WHERE sha256 = ?", (sha,)).fetchone()
    if seen:
        if seen[0] != rubric:
            raise ValueError(f"this file was already ingested under rubric "
                             f"{seen[0]!r}; re-declaring it as {rubric!r} would "
                             f"put the same scores on two scales")
        return 0, sha, True

    rows = read_rows(path)
    db.execute(
        "INSERT INTO sources (sha256, path, rubric, ingested_at, n_rows) "
        "VALUES (?, ?, ?, ?, ?)",
        (sha, os.path.basename(path), rubric,
         datetime.now(timezone.utc).isoformat(timespec="seconds"), len(rows)))
    db.executemany(
        "INSERT OR REPLACE INTO ratings "
        "(item_id, rater_id, dimension, rubric, score, source_sha) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [(i, r, d, rubric, s, sha) for i, r, d, s in rows])
    db.commit()
    return len(rows), sha, False


def rubrics(db, dimension=None):
    q = "SELECT DISTINCT rubric FROM ratings"
    args = ()
    if dimension:
        q += " WHERE dimension = ?"
        args = (dimension,)
    return sorted(r[0] for r in db.execute(q + " ORDER BY rubric", args))


def dimensions(db, rubric=None):
    q = "SELECT DISTINCT dimension FROM ratings"
    args = ()
    if rubric:
        q += " WHERE rubric = ?"
        args = (rubric,)
    return sorted(r[0] for r in db.execute(q + " ORDER BY dimension", args))


def load(db, dimension=None, rubric=None):
    """
    Read back in the shape reliability.analyse expects:
    {dimension: (by_item, rows)}.

    THE REFUSAL THAT MATTERS: if the store holds more than one rubric version
    and the caller has not chosen one, this raises instead of pooling. Scores
    written against different rubrics are different measurements wearing the
    same column name, and averaging across them produces a reliability figure
    for a construct that does not exist.
    """
    present = rubrics(db, dimension)
    if not present:
        raise ValueError("no ratings" + (f" for dimension {dimension!r}" if dimension else ""))
    if rubric is None:
        if len(present) > 1:
            raise ValueError(
                f"the store holds {len(present)} rubric versions ({', '.join(present)}). "
                f"Pick one with --rubric: scores from different rubric versions "
                f"are not on the same scale.")
        rubric = present[0]
    elif rubric not in present:
        raise ValueError(f"no ratings under rubric {rubric!r}; have: {', '.join(present)}")

    q = ("SELECT dimension, item_id, rater_id, score FROM ratings "
         "WHERE rubric = ?")
    args = [rubric]
    if dimension:
        q += " AND dimension = ?"
        args.append(dimension)

    by_item = defaultdict(lambda: defaultdict(list))
    triples = defaultdict(list)
    for d, i, r, s in db.execute(q + " ORDER BY dimension, item_id, rater_id", args):
        by_item[d][i].append(s)
        triples[d].append((i, r, s))
    return {d: (dict(by_item[d]), triples[d]) for d in by_item}, rubric


def provenance(db):
    """Every ingested file, so a figure can be traced to the bytes behind it."""
    return list(db.execute(
        "SELECT sha256, path, rubric, ingested_at, n_rows FROM sources "
        "ORDER BY ingested_at, path"))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_in = sub.add_parser("ingest", help="load a CSV under a rubric version")
    p_in.add_argument("csv")
    p_in.add_argument("--rubric", required=True)

    sub.add_parser("sources", help="what has been ingested")

    p_an = sub.add_parser("analyse", help="run the pipeline over the store")
    p_an.add_argument("--dimension")
    p_an.add_argument("--rubric")

    a = ap.parse_args(argv)
    db = connect(a.db)

    if a.cmd == "ingest":
        n, sha, seen = ingest(db, a.csv, a.rubric)
        if seen:
            print(f"already ingested ({sha[:12]}); nothing to do")
        else:
            print(f"ingested {n} ratings under rubric {a.rubric}  [{sha[:12]}]")
        return 0

    if a.cmd == "sources":
        rows = provenance(db)
        if not rows:
            print("empty store")
            return 0
        print(f"{'sha':>14s}  {'rubric':>8s}  {'rows':>6s}  ingested            file")
        for sha, path, rubric, at, n in rows:
            print(f"{sha[:12]:>14s}  {rubric:>8s}  {n:>6d}  {at}  {path}")
        return 0

    if a.cmd == "analyse":
        from reliability import analyse, report
        data, rubric = load(db, a.dimension, a.rubric)
        print(f"rubric version: {rubric}")
        print()
        report({d: analyse(bi, rows=rw) for d, (bi, rw) in data.items()})
        return 0

    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, FileNotFoundError, sqlite3.Error) as e:
        sys.exit(f"error: {e}")

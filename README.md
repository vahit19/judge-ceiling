# Ceiling bounds from a public judge leaderboard

A small, reproducible analysis: **every correlation published on a judge
leaderboard places a lower bound on the rater agreement that is not published.**

Nothing here needs private data, credentials, or an API key. The whole chain —
fetch, verify, compute, test — runs from a public URL in about ten seconds.

It has two halves. The first derives what can be said **without** access:
a bound on rater agreement from published numbers alone. The second is the
**pipeline that would run on rating rows** if access existed -- validated on
simulated data where the answer is known by construction.

## Run it

```bash
# what can be derived from public numbers
python fetch_leaderboard.py    # pull the live leaderboard -> leaderboard.json
python ceiling_bounds.py       # the bounds, scenarios, crossover
python chart.py                # the figure (SVG)

# the pipeline that runs on rating rows
python simulate.py             # recovery checks on data with a known answer
python reliability.py my.csv   # item_id, rater_id, dimension, score

# tests
python test_ceiling.py         # 15: mathematics + data integrity
python test_reliability.py     # 20: estimator recovery + methodological traps
```

No third-party dependencies. Standard library only.

```bash
python fetch_leaderboard.py --check     # re-fetch and diff against the saved file
python ceiling_bounds.py --self-test    # the mathematics self-checks alone
```

`--check` exits non-zero if any published number has changed since the file
was written. That is what makes the saved JSON a claim rather than a copy-paste.

## The argument

Under classical test theory an observed correlation between two noisy
measurements is attenuated by both reliabilities:

```
observed r  =  r_true  ×  sqrt( ρ_judge × ρ₁ )
```

where `ρ₁` is the reliability of a **single** human vote — which is what this
leaderboard correlates against, and treats as ground truth.

Both `r_true` and `ρ_judge` are at most 1. Substituting those maxima:

```
ρ₁  ≥  r²
```

A judge cannot correlate with a human vote more strongly than the square root of
that vote's own reliability. So each published score is simultaneously a
statement about the raters.

## What comes out

| dimension | best judge r | implied ρ₁ ≥ |
|---|---|---|
| Language Stability | 0.7033 | **0.4946** |
| Expressiveness | 0.5093 | 0.2594 |
| Reliability | 0.5004 | 0.2504 |
| Extended Long-Form Speaker Stability | 0.4423 | 0.1956 |
| Long-form Speaker Stability | 0.3869 | 0.1497 |
| Acoustic Quality | 0.3821 | 0.1460 |
| Voice identity | 0.3487 | 0.1216 |
| Acting / Role-fit | 0.2049 | 0.0420 |

The bound is tight where the leaderboard already looks strong, and loose exactly
where the interesting question is.

**Where it bites.** The reachable maximum is `sqrt(ρ₁)`, and `ρ₁` is plausibly
much lower on subjective dimensions. Comparing dimensions as fractions of their
own ceilings rather than as raw correlations gives a crossover:

```
ρ₁(acting)  =  0.0849  ×  ρ₁(language stability)
```

If `ρ₁` on language stability is 0.60, then below `ρ₁ = 0.051` on acting the
judge is doing *better* there, relative to what is achievable — the opposite of
the raw-number reading. Whether that point is reached is empirical, and the
measurement has not been published.

## Assumptions

1. **Classical test theory** — observed = true + independent error. If judge and
   rater errors correlate (both misled by the same artefact in a clip) the bound
   loosens.
2. **Spearman vs Pearson** — the leaderboard reports rank correlation; the
   attenuation identity is derived for Pearson. On five-point ordinal ratings the
   two are close but not identical. Read these as accurate in magnitude, not to
   the third decimal.
3. **Bounds, not estimates.** They say what `ρ₁` cannot be, not what it is. The
   estimate requires rating rows with rater identity preserved.

## How it is checked

`test_ceiling.py` runs 15 tests in two groups.

**Mathematics (8).** These check the implementation against a worked example
before it is pointed at any real data: `ρ = 0.64` gives a ceiling of `0.80`; an
observed `0.60` is 75% of that ceiling and implies a true reliability of
`0.5625`. Also: the bound is self-consistent (`ceiling(bound(r)) == r`), scores
below the bound are reported as impossible rather than as a number, and the
cross-dimension crossover is re-derived independently.

**Data (7).** Shape (8 dimensions × 7 judges), scores in range, ranks consistent
with scores, the same judge set in every dimension, licence field populated, and
exactly two open-weight judges — because the open/proprietary split is used in
the argument, so it is asserted rather than assumed.

## The pipeline, and why it is here

A bound derived from public numbers says what the answer *cannot* be. Getting
the answer needs rating rows with rater identity preserved. `reliability.py`
is the code that would run on them:

| quantity | what it answers |
|---|---|
| `rho_1` | how much of a single rating is real signal |
| `rho_k` | the same for the mean of k raters (Spearman-Brown) |
| `ceiling` | the highest correlation any judge can reach against that yardstick |
| `rho_g` | a judge's reliability, corrected for the noise it was scored against |
| `k*` | how many human ratings one judge rating is worth |
| interval | bootstrap over **items**, because the item is the sampling unit |

Two design decisions are worth naming, because both are easy to get wrong.

**The gate needs two conditions, not one.** A lower bound above 1 says the
judge is worth at least one human rating. But an interval running to infinity
means the ratio is not identified at that sample size, and the point estimate
is then arbitrarily large. Both must hold, or the tool refuses and reports
what would settle it instead.

**Bias and noise are different quantities.** A one-way model absorbs rater
bias into the error term, so removing bias appears to change reliability. A
two-way model separates them: on a fully crossed design built at a fixed
reliability, growing the rater offsets moves the rater variance and leaves the
residual **bit-identical** — 1.2980 at every level tested — while consistency
reliability stays at 0.4363.

That second model is restricted on purpose. The sums of squares only decompose
orthogonally when every rater rates every item, so `icc_two_way_consistency`
**refuses an unbalanced design** rather than approximating one. On pooled-rater
data with strong bias the approximation was measured at +0.30 against a true
0.45, which is worse than no answer. Refusing is the same rule the substitution
gate follows.

## Three failures an outside review found

Locked as tests rather than corrected quietly, because each is a way this kind
of tool goes wrong without complaining.

**An inverted judge was approved.** Disattenuation squares the correlation, so
a judge that ranks quality *backwards* produced the same reliability as one
that ranks it correctly, and cleared the automation gate with an identical
ratio. The sign is now checked separately; an inverted judge is refused, and
flipping it is left to a person.

**The CSV loader discarded rater identity.** The whole method asks for
rater-level rows, and the loader threw the rater id away at the door, which
made the two-way model unreachable from the command line. It now carries both
groupings and rejects a file without a `rater_id` column.

**The sample-size figure was falsely precise.** A tool that refuses to quote a
saving should not quote an exact number of extra ratings. Its derivation
(interval half-width scaling as 1/sqrt(n)) is now stated with its two
weaknesses, and the output is rounded to two significant digits.

## Files

```
fetch_leaderboard.py    public URL -> leaderboard.json, with validation
leaderboard.json        8 dimensions x 7 judges, at published precision
ceiling_bounds.py       the bounds, the scenarios, the crossover
chart.py                renders ceiling_chart.svg
ceiling_chart.svg       the figure above, regenerated by chart.py
reliability.py          the rating-rows pipeline (ICC, ceiling, ratio, bootstrap)
simulate.py             rows with a known answer, so the estimator is checkable
test_ceiling.py         15 tests, no test framework required
test_reliability.py     20 tests, including six that encode methodological traps
```

## Continuous integration

Every push runs the mathematics self-checks, both test suites, and every
report end to end. A separate scheduled job re-fetches the live leaderboard
and reports if any published number has changed -- kept separate because
upstream moving is news, not a broken build.

Source: <https://www.hume.ai/slm-judge-leaderboard> (public).

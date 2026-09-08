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

# planning a study: both axes
python reliability.py --budget 0.2504   # what each panel size buys
python reliability.py --matrix 0.2504   # items x raters, to detect an effect
python reliability.py --turns           # turn vs conversation as the item

# a store, once it is more than one run
python store.py ingest ratings.csv --rubric v1
python store.py sources                 # what produced which number
python store.py analyse --rubric v1

# tests
python test_ceiling.py         # 15: mathematics + data integrity
python test_reliability.py     # 35: recovery, traps, and model-violation costs
python test_store.py           # 11: store refusals and provenance
python simulate.py --departures         # what leaving the model costs
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
| `raters_needed` | the smallest panel that reaches a target reliability |
| `budget_table` | what each panel size buys, and what a smaller one forgoes |

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

## What the simulation cannot validate

The rows in `simulate.py` are generated from exactly the model
`reliability.py` assumes: one true score per item plus independent Gaussian
error with a single variance. That makes the check circular in one specific
way. It confirms the arithmetic; it can never reveal that the model is wrong
for real ratings.

Real ratings depart from it, so the cost of two realistic departures is
measured rather than left as a caveat. `python simulate.py --departures`
prints this over 60 seeds per cell:

| departure | ρ₁ | mean cost | range across seeds | reversed |
|---|---|---|---|---|
| five-point scale instead of a continuum | 0.45 | 8.7% | [+4.4%, +13.4%] | 0% |
| five-point scale instead of a continuum | 0.70 | 12.1% | [+8.9%, +15.6%] | 0% |
| raters differing in how noisy they are | 0.45 | 30.6% | [−26.8%, +86.8%] | 8.3% |
| raters differing in how noisy they are | 0.70 | 21.2% | [−12.9%, +74.2%] | 8.3% |
| heavy-tailed error | — | reliability is not defined at all; no estimator helps | | |

Rounding always costs, and costs little. Unequal rater noise costs nearer a
third than a fifth, and — this is the part worth stating plainly — it does
**not** always go the same way: on about one draw in twelve it *raises* the
estimate instead. So the safe-direction claim is about the average, not
about every dataset.

That distinction is not cosmetic. An earlier version of this file reported
these costs from a single seed, and a single seed of the unequal-noise
departure spans −27% to +87%. The test that guarded it passed only because
of the seed it happened to be given; on seed 3 the same assertion fails.
Both the numbers above and the reversal are now asserted across seeds.

None of this touches the `ρ₁ ≥ r²` bound, which comes from published
correlations rather than from this estimator.

## From a CSV to a store

A CSV is enough to compute a number once. It is not enough to defend that
number later, and it cannot stop the two failure modes that corrupt a
reliability estimate without ever looking wrong:

**Rubric drift.** Scores given under different rubric versions are different
measurements wearing the same column name. Pool them and the estimator sees
one item scored by twice as many raters, so it reports a figure that belongs
to neither scale. Measured on two versions of the same dimension: the pooled
estimate lands *below both* true values, and the apparent panel size doubles
— an error that makes the design look stronger while making the result look
worse. `store.py` refuses to pool unless a rubric is named.

**Provenance.** Every rating carries the SHA-256 of the file it came from, and
sources are content-addressed, so ingesting the same bytes twice is a no-op
rather than a duplication. Duplicated rows would tighten an interval the
design never earned.

```
$ python store.py analyse
error: the store holds 2 rubric versions (v1, v2). Pick one with --rubric:
scores from different rubric versions are not on the same scale.
```

The store also enforces at the door what the method asks for everywhere else:
a row without a rater id is rejected on ingest rather than discovered missing
during an analysis, and one rater cannot hold two scores for the same item
under the same rubric.

Both traps were already named in the write-up and neither was enforced
anywhere. Naming a trap is not the same as being unable to fall into it.

## Four failures, locked as tests

Locked as tests rather than corrected quietly, because each is a way this kind
of tool goes wrong without complaining. Three came from an outside review;
the fourth from re-running numbers this file had already published.

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

**A robustness check passed because of its seed.** The two model-violation
costs above were measured on one draw each and reported as settled figures.
Re-measured across sixty seeds, the five-point-scale cost is 8.7% rather than
the ~5% first published, and unequal rater noise costs 30.6% rather than ~20%
— and reverses direction on about 8% of draws, which the guarding test could
not see because it asserted a strict decrease on a seed where the decrease
happened. Seed 3 fails that old assertion outright. The costs are now measured
over seeds, the reversal is asserted rather than denied, and the seed
dependence itself is a test so it cannot return quietly.

The general form of that last one is worth more than the fix: a test that
passes because of the data it was handed is indistinguishable, from the
outside, from a test that passes because the code is right.

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
test_reliability.py     35 tests, including six traps and the robustness costs
store.py                rating store: rater identity, rubric version, provenance
test_store.py           11 tests, mostly refusals
```

## Scope: what this is for, and what it is not

The bound and the pipeline answer one question -- how noisy is the yardstick,
and what does that cost. Three things follow from that, and one does not.

**Planning a panel is the same calculation read forwards.** `raters_needed`
inverts Spearman-Brown: given one rater's reliability and a target, it returns
the smallest panel that reaches it. `--budget` prints the whole trade instead
of a single number, because a smaller panel is often the right call:

```
 raters    rho_k  ceiling  forgone    gain
      1   0.2504   0.5004   0.4996       -
      3   0.5005   0.7075   0.2925  0.0746
      8   0.7277   0.8531   0.1469  0.0622
```

`forgone` is what a *perfect* judge still cannot reach at that panel size,
purely because the yardstick is noisy. Running fewer raters is a budget
decision; running fewer without that column is not a decision at all.

**But a panel size is only half a sampling plan.** "How many raters" and
"how many items" are different questions, and a study is costed on the pair.
`--matrix` prints both axes at once — rows are the improvement you want to
detect, columns are panel sizes, cells are items per arm:

```
  effect      k=1      k=3      k=5      k=8     k=13
   0.10s     6270     3137     2510     2158     1932
   0.20s     1568      785      628      540      483
   0.30s      697      349      279      240      215
   0.50s      251      126      101       87       78
```

The two axes are linked, and that is the reason to print them together.
Measurement error attenuates a standardised effect by `sqrt(rho_k)`, and the
required sample grows with the inverse square of what survives — so a noisy
yardstick is not merely a weaker correlation, it is a quadratic bill in
items. Reading right along a row prices extra raters in items saved;
reading down a column prices ambition.

And the whole table takes one input. `rho_1` sets how much of a real effect
survives at each panel size, and what survives sets how many items are
needed. A sampling plan cannot be written without the reliability of a
single rating — which is exactly the number a leaderboard of judge-human
correlations does not report.

**The sampling unit is a modelling choice, and it is not free.** Rate the
turns of a conversation and you can group the same rows two ways.
`--turns` runs both on one generated file:

```
    grouped by   items    built mean of 30         95% interval
          turn    1200   0.4470     0.4440       [0.405, 0.474]
  conversation     150   0.3000     0.3119       [0.254, 0.348]
```

Turn-to-turn variation is signal when the turn is the item and error when the
call is, so the turn-level figure is systematically **higher** -- and, with
the item count multiplied by the turns per call, its interval is
systematically **tighter**. Neither number is wrong; they answer different
questions. If the question is whether a system held up across a whole call,
the turn-level figure is not a conservative stand-in for it.

**What this does not do.** It does not tell you which scenarios to evaluate,
and it does not measure whether a system's output tracks a real-world
outcome. Those are eval-design questions and they come first: this machinery
takes whatever construct a rubric defines and reports how well it was
measured. A well-estimated reliability on the wrong construct is still the
wrong construct. What it does contribute is the cost of getting the
measurement wrong, in the same units for every design under consideration.

## Continuous integration

Every push runs the mathematics self-checks, both test suites, and every
report end to end. A separate scheduled job re-fetches the live leaderboard
and reports if any published number has changed -- kept separate because
upstream moving is news, not a broken build.

Source: <https://www.hume.ai/slm-judge-leaderboard> (public).

# Method, limits, and what each number is for

The findings and how to run them are in the [README](README.md). This file is the reasoning behind them: the
argument, the two results in full, how to point the pipeline at your own
rows, what is not done yet, and where the whole thing stops being valid.

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

## The gate that raises the number it was meant to protect

A leaderboard that scores a judge against human votes treats those votes as
ground truth, and the usual defence of that ground truth is a quality gate:
drop the outlying ratings, drop the raters who do not track the panel.
`poison.py` measures what the gate does, on rows whose reliability is known by
construction.

Two results, and the second is the one that matters.

**Corruption is caught by where it sits, not by what it looks like.** Bad
ratings concentrated inside one rater are caught at 98-100% whether they are
obviously wrong or perfectly ordinary-looking, because a rater who does not
track the panel is identifiable across many items. The same quantity of
corruption spread thinly across raters is mostly missed - 4% to 29%. This was
not the expected result: the opening hypothesis was that realism decides
detection, and measured, location does most of the work. The crude arm is
missed *more* than the plausible one, because a repeated central value is
never an outlier.

**On rows with nothing wrong with them, the gate reports a reliability it did
not measure.**

| screen | dropped | reported `rho_1` | 95% interval | across 12 seeds | overstated | panel it calls for |
|---|---|---|---|---|---|---|
| off | 0.0% | 0.4455 | [0.419, 0.509] | [0.419, 0.498] | -1% | 5 |
| 3.0 sd | 7.4% | 0.5381 | [0.490, 0.588] | [0.517, 0.587] | +20% | 4 |
| 2.5 sd | 11.1% | 0.5850 | [0.533, 0.632] | [0.563, 0.634] | +30% | 3 |
| 2.0 sd | 16.9% | 0.6489 | [0.594, 0.681] | [0.623, 0.698] | **+44%** | 3 |
| 1.5 sd | 27.0% | 0.7176 | [0.654, 0.734] | [0.700, 0.753] | +59% | 2 |
| 1.0 sd | 43.9% | 0.8184 | [0.794, 0.855] | [0.791, 0.841] | +82% | 1 |

Rows built at `rho_1 = 0.45`, 400 items x 5 raters, mean of 12 seeds. Nothing
is corrupted, so the correct answer at every row is 0.45. The interval is a
bootstrap over items on one draw; the seed range is how much the point estimate
moves between studies of this size. They answer different questions and both
are reported, because the gate-off interval and the 2.0 sd interval **do not
overlap** — which is what makes this a measurement rather than a direction.

Real panel ratings are not continuous. On a five-point scale the same sweep
gives:

| screen | dropped | reported `rho_1` | 95% interval | overstated | panel |
|---|---|---|---|---|---|
| off | 0.0% | 0.4048 | [0.373, 0.464] | -10% | 6 |
| 3.0 sd | 2.6% | 0.4723 | [0.435, 0.527] | +5% | 5 |
| 2.5 sd | 6.4% | 0.5273 | [0.481, 0.579] | +17% | 4 |
| 2.0 sd | 12.1% | 0.6031 | [0.553, 0.641] | **+34%** | 3 |
| 1.5 sd | 13.2% | 0.6187 | [0.566, 0.652] | +37% | 3 |
| 1.0 sd | 35.1% | 0.8018 | [0.772, 0.838] | +78% | 1 |

Rounding costs the estimate a few points at every threshold — the same
downward bias this repository measures elsewhere — so it changes the size of
the overstatement and not its direction. That is the reason both tables are
here rather than the friendlier one alone.

Dropping the ratings that disagree most with the panel does not remove error.
It removes disagreement, and less disagreement *is* higher measured agreement.
The error is monotone in how hard the screen is run and it always points the
same way: a panel that genuinely needs five raters is told three are enough,
by the step that was supposed to protect the estimate.

The consequence is not confined to a reliability figure. `rho_1` sets the
ceiling any judge can reach against that yardstick, so an inflated `rho_1`
inflates the ceiling, and a judge is then scored as a smaller fraction of a
larger number than either of them deserves.

What this does **not** do: nothing here estimates how many real ratings are
wrong anywhere. The rows are simulated, which is the only way to know the
catch rate and the collateral damage at the same time, and also the limit of
the claim. It says what follows *if* some ratings are wrong, and what the
standard defence does in that case.

## The same question, on someone else's panel

Everything above is simulated, which is the only way to know a catch rate and
its collateral damage at once, and also the limit of the claim. This section is
the other kind of evidence: the same question asked of a published measurement
built from real data, where the answer is not known in advance and cannot be
arranged.

**The source.** *Towards Quantifying Benchmark Optimization in ASR Models*
(Lebryk, Ayllon, Baird, Cłapa, Madsen and Tzirakis, arXiv:2608.19936) releases
its reproduction data under Apache-2.0. A four-model consensus panel flags spans
where a benchmark's reference transcript contradicts the audio; 39 ASR models
are then scored on those spans, and ACCEPT-REF is the share on which a model
reproduced the erroneous reference rather than the audio. A span is admitted
when the panel agrees at `majority_pct = 0.75` — three of four.

`fetch_consensus.py` pulls the two released files and keeps only the verdict
matrix: 1,338 spans x 39 models, about 200 KB against 8 MB of source, saved as
`consensus_panel.json` with the published scores beside it. `--check` re-fetches
and diffs, so the saved copy is a claim about upstream rather than a snapshot
of it.

**First, the anchor.** All 39 published scores recompute from that matrix
exactly — the numerator, the denominator and the ratio to four decimal places.
Nothing below would mean anything without it, so it is a test rather than a
sentence.

**Then the same question this repository asks everywhere else.** The admission
threshold is a screening rule on items, in the family `poison.py` measures on
ratings. It is documented and it is defensible. What it costs is not published.

| `majority_pct` | spans | mean ACCEPT-REF | highest |
|---|---|---|---|
| 0.75 (published) | 1,338 | 0.1705 | 0.3986 |
| 1.00 (unanimity) | 1,113 | 0.1066 | 0.3179 |

Requiring unanimity removes 225 spans, 17% of the set, and moves the mean score
by −38%. The two halves explain why:

| panel | spans | mean ACCEPT-REF |
|---|---|---|
| unanimous | 1,113 | 0.1066 |
| split | 225 | 0.5015 |

The 17% of spans the panel could not agree on carry a rate **4.7x** the
unanimous ones. They are a small part of the item set and a large part of the
measured effect. Nineteen of 35 models change rank between the two thresholds,
and of the six highest-scoring models, four are the same and two are replaced —
which matters because the paper's headline pairs the six highest ACCEPT-REF
models with the six best word error rates.

**This is not a correction.** 0.75 is a reasonable choice and the paper states
it plainly. Nor does this settle which threshold is right, and the reason is
interesting rather than evasive: a split panel marks an ambiguous span, and
ambiguity reads two ways. Those spans are either the most diagnostic cases —
exactly where a benchmark-fitted model should separate from an audio-faithful
one — or the least trustworthy ones, where the panel itself could not hear the
answer. The released data does not distinguish them.

What it does show is the shape this repository keeps finding. In `poison.py`,
tightening an agreement screen on *ratings* raised the reported reliability. Here,
tightening an agreement screen on *items* lowers the reported score. The
direction is not fixed and is not guessable; only the sensitivity is general. A
number that moves this much with one documented parameter should travel with
that number beside it.

**What is restricted.** The sweep scores the 35 models outside the panel. Panel
members are scored leave-one-out upstream, and the released extract carries the
result of that rather than its inputs, so re-deriving a leave-one-out set at a
different threshold would be guesswork. Naming the restriction is cheaper than
having it found.

## Running this on your own rating rows

The bound in result 1 needs nothing. Results 2 and 3 need rows, and the only
thing that changes is the input: no re-collection, no change to how ratings
were gathered, no model access.

A CSV with four columns, one row per rating:

```
item_id,rater_id,dimension,score
clip_0001,r_17,naturalness,4
clip_0001,r_43,naturalness,3
```

`item_id` is whatever was rated — a clip, or a whole conversation. Which one
you choose is a modelling decision and not a property of the file, and it
changes the answer: see [what the simulation cannot
validate](#what-the-simulation-cannot-validate). `rater_id` must be stable
across items, because everything a rater screen can do depends on being able
to follow one person across the set. Anonymous ids are fine; the identity is
never needed, only the grouping.

```bash
python reliability.py ratings.csv          # rho_1, rho_k, ceiling, interval
python reliability.py --budget 0.2504      # what each panel size buys
python store.py ingest ratings.csv --rubric v1
```

Two refusals are deliberate and worth knowing before you run it. The two-way
model refuses an unbalanced design rather than approximating one, because the
approximation was measured at +0.30 against a true 0.45. And the substitution
gate refuses when the interval runs to infinity, because a point estimate is
arbitrarily large at that sample size. In both cases the tool reports what
would settle the question instead of answering it.

## What is not done yet

Named rather than implied, because the gap between the two is the honest part
of a small result.

**The rows are simulated.** That is the only way to know the catch rate and the
collateral damage at the same time, and it is also the ceiling on what result 2
can claim. On real rows the corrupted fraction is unknown, so the measurable
quantity changes: not "how much does the gate overstate", but "how much does
the reported reliability move when the gate is turned off". That comparison
needs no ground truth and is the first thing to run on real data.

**Only two screens are modelled** — an outlier rule and a rater-agreement rule.
Real pipelines also use attention checks, seeded gold items and time-on-task.
Each is a different selection rule on the same rows and each should be swept
the same way.

**The consequence for a judge is argued, not computed.** An inflated `rho_1`
inflates the ceiling, and a judge is then scored as a fraction of a number
nobody measured. Running a simulated judge through both yardsticks would put a
figure on that rather than a direction.

**Rater bias is not separated in the corrupted arms.** `poison.py` reports the
one-way model throughout. The two-way model in `reliability.py` separates rater
bias from residual noise, and rater-concentrated corruption is exactly the case
where the distinction should matter.

## Related work, and what this does differently

Two recent audits from the same direction are worth naming, because this
repository is the other half of the same question and the distinction matters.

**Lebryk, Ayllon, Baird, Cłapa, Madsen and Tzirakis, *Towards Quantifying
Benchmark Optimization in ASR Models*, arXiv:2608.19936 (2026).** They audit the
*model*. Three behavioural probes — reference disagreement, masked-entity
recovery, orthographic switching — show that on VoxPopuli the six models with
the best word error rate are exactly the six with the highest rate of
reproducing a benchmark's erroneous reference span, while every model at 6.5%
WER or worse sits at or below 0.10. Their remedy is structural: held-out sets,
no i.i.d. splits, temporal or metadata stratification.

The result that bears hardest on this repository is not the audit but the
mechanism. The behaviour is not a perception failure. Truncating the audio to a
short window around the target span recovers the audio-true transcription;
clones of benchmark speakers trigger the behaviour while a generic voice
reading the same sentence does not; and on three of the elevated models,
projecting out a single learned direction drops the rate by 82–92% while adding
that direction induces it on voices that never showed it. The information is
present and a policy discards it.

**Ayllon, Baird, Brooks, Camps-Febrer, Cłapa, Lebryk, Madsen et al.,
*RW-Voice-EQ Bench*, arXiv:2607.14846 (2026).** A multidimensional benchmark built from human
ratings, which is the kind of yardstick this repository's bound is derived
from.

This repository audits the *yardstick* instead. A held-out set fixes a
benchmark that is too easy to fit; it does nothing about a reference signal
whose reliability is unknown, or inflated before anyone scores against it. The
two failures are independent, and the second one is measurable from published
numbers alone (`ceiling_bounds.py`) or from rating rows (`reliability.py`,
`poison.py`).

The shape is the same one their mechanism section describes. An outlier screen
is also not a perception failure: the disagreement it deletes was measured,
recorded, and available. A policy discards it, and the reported reliability
rises because of the deletion rather than despite it.

The connection runs the other way too. The ASR paper's conclusion names
dataset-specific acoustic cues as a potential source of reward hacking once
reinforcement learning enters speech models. A reward model trained on human
ratings inherits whatever the rating pipeline's quality gate let through — and
what that gate lets through, and what it does to the reported reliability while
doing it, is exactly what `poison.py` measures.

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

## What each number is for

Every figure here exists to inform one decision. Listing them together is the
quickest way to see what the repository does and does not settle.

| output | the decision it informs |
|---|---|
| `rho_1` | whether a dimension is measured well enough at the panel size in use, or whether the rubric is the problem rather than the raters |
| `rho_k`, `ceiling` | how to read any judge score on that dimension — as a fraction of what is reachable, not as a raw correlation |
| `rho_g` | what a judge is worth once the noise of the yardstick it was scored against is removed |
| `k*` with interval | whether one judge rating can stand in for human ratings, and how many — or whether the question is unanswerable at this sample size |
| `budget_table` | what a smaller panel forgoes, per panel size, so running fewer is a decision rather than an accident |
| `matrix_table` | how many items, across how many raters, to detect a given improvement |
| store refusals | whether the rows are fit to compute any of the above at all |

### What it deliberately does not size

**How many ratings it takes to train a judge.** That is a learning-curve
question — it depends on the model, the task and the rubric, and no amount of
classical test theory produces it. Claiming otherwise would be the same error
as quoting a saving from an unbounded interval.

What this machinery *can* size is the **evaluation** of a trained judge: how
many held-out items are needed to show its disattenuated reliability with a
stated interval, and — from the ceiling — on which dimensions a useful figure
is reachable at all. Those two are the checkable half of the question, and
they are the half that decides whether a trained judge may be used.

One structural fact bears on the same question and is asserted rather than
assumed: of the seven judges on this board, exactly **two** are open-weight
(`test_exactly_two_open_weight_judges`). A judge that cannot be fine-tuned
cannot be the one you train, whatever the sizing says.

**Which scenarios to evaluate.** Covered below: this takes whatever construct
a rubric defines and reports how well it was measured. A well-estimated
reliability on the wrong construct is still the wrong construct.

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

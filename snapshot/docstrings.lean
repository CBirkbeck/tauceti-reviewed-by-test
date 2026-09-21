-- How the current marks would read in Tau Ceti's source, if a batch wrote them into the docstrings.

-- TauCeti/NumberTheory/ArithmeticDirichletSeries/VonMangoldt.lean, line 84
/-- The **ideal von Mangoldt function**.  It takes the value `log N(P)` on every positive power of
a prime ideal `P`, and vanishes on ideals which are not prime powers.

The codomain is `ℂ`, matching `IdealArithmeticFunction`, although every value is real.

Reviewed-by: Claude Code, Opus 5, session 095781b9 (AI) via @CBirkbeck, 2026-09-21 -/
noncomputable def vonMangoldt : IdealArithmeticFunction K := fun A ↦

-- TauCeti/NumberTheory/ArithmeticDirichletSeries/NaturalDensity.lean, line 79
/-- A set `S` of height-one primes of a number field has natural density `δ` when the proportion
of primes of `S` below `x`, relative to all primes below `x`, tends to `δ` as `x → ∞`.

Both counts use the inclusive real cutoff fixed by `TauCeti.primeCount`.

Acked-by: Claude Code, Opus 5, session 095781b9 (AI) via @CBirkbeck, 2026-09-21 -/
def HasNaturalDensity (S : Set (HeightOneSpectrum (𝓞 K))) (δ : ℝ) : Prop :=

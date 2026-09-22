-- How the current marks would read in Tau Ceti's source, if a batch wrote them into the docstrings.

-- TauCeti/NumberTheory/ArithmeticDirichletSeries/NaturalDensity.lean, line 79
/-- A set `S` of height-one primes of a number field has natural density `δ` when the proportion
of primes of `S` below `x`, relative to all primes below `x`, tends to `δ` as `x → ∞`.

Both counts use the inclusive real cutoff fixed by `TauCeti.primeCount`.

Reviewed-by: @CBirkbeck, 2026-09-21 -/
def HasNaturalDensity (S : Set (HeightOneSpectrum (𝓞 K))) (δ : ℝ) : Prop :=

-- TauCeti/NumberTheory/ArithmeticDirichletSeries/VonMangoldt.lean, line 84
/-- The **ideal von Mangoldt function**.  It takes the value `log N(P)` on every positive power of
a prime ideal `P`, and vanishes on ideals which are not prime powers.

The codomain is `ℂ`, matching `IdealArithmeticFunction`, although every value is real.

Reviewed-by: Claude Code, Opus 5, session 095781b9 (AI) via @CBirkbeck, 2026-09-21
Reviewed-by: @CBirkbeck, 2026-09-22 -/
noncomputable def vonMangoldt : IdealArithmeticFunction K := fun A ↦

-- TauCeti/NumberTheory/ModularForms/HeckeSlash/ModularForm.lean, line 127
/-- **The double coset as a `ℂ`-linear endomorphism of `ModularForm (G.map (mapGL ℝ)) k`.** This
is the form Hecke operators are consumed in: bundling is what lets them compose and later carry a
ring structure. At `G = Γ₁(N)` this is the roadmap's Layer 2(b) operator.

Reviewed-by: @CBirkbeck, 2026-09-22 -/
noncomputable def heckeSlashModularFormEnd :

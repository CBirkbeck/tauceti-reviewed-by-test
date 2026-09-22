-- The line each file would carry at the top of its module docstring, taking a reader
-- from the code to the file's page on the review site.

-- TauCeti/NumberTheory/ArithmeticDirichletSeries/NaturalDensity.lean
/-!
# Natural density of sets of prime ideals

[Reviews and tests of this file](https://cbirkbeck.github.io/tauceti-reviewed-by-test/#m=TauCeti.NumberTheory.ArithmeticDirichletSeries.NaturalDensity)

For a number field `K`, this file defines the natural density of a set `S` of nonzero prime
ideals as the limit

```text
  primeCount K S x / primeCount K Set.univ x
```

as the inclusive real cutoff `x` tends to infinity. This normalization matches Mathlib's
ratio-normalized `NumberField.Set.HasDirichletDensity`: a density is measured relative to all
prime ideals of the same number field, rather than relative to an external approximation such as
`x / log x`.

The denominator really tends to infinity. Indeed, lying over supplies a prime of `𝓞 K` above
every rational prime, so the height-one spectrum is infinite. Its bounded-norm subsets are finite
and exhaust the spectrum, whence their cardinalities tend to infinity. This fact both makes the
whole spectrum have density one and ensures that a fixed finite error disappears in the ratio.

## Main results

* `NumberField.Set.HasNaturalDensity`: ratio-normalized natural density for a set of prime ideals.
* `NumberField.Set.hasNaturalDensity_def`: the defining ratio-convergence characterization.
* `NumberField.Set.HasNaturalDensity.union`,
  `NumberField.Set.hasNaturalDensity_biUnion_finset` and
  `NumberField.Set.HasNaturalDensity.compl`: finite Boolean calculus for natural density.
* `NumberField.Set.HasNaturalDensity.of_finite_symmDiff`: changing a prime set on finitely many
  primes preserves its natural density.
* `NumberField.Set.hasNaturalDensity_of_finite`: every finite set of prime ideals has natural
  density zero.
* `NumberField.Set.isUpperDirichletDensityBound_of_eventually_primeCount_le` and
  `NumberField.Set.isLowerDirichletDensityBound_of_eventually_le_primeCount`: an eventual
  one-sided bound on the proportion of primes of `S` below `x` is the same one-sided bound for
  Dirichlet density.
* `NumberField.Set.hasDirichletDensity_of_hasNaturalDensity`: natural density implies Dirichlet
  density, with the same value.

The comparison with Dirichlet density rests on two inputs. Abel summation against the decreasing
function `t ↦ t ^ (-s)` (`TauCeti.tsum_mul_le_of_summatory_le`) turns an eventual bound
`π_S(x) ≤ c · π(x)` into a bound `P_S(s) ≤ c · P(s) + C` with `C` independent of `s > 1`, where
`P_S` is Mathlib's `NumberField.Set.primeIdealZetaSum S`. The all-prime sum `P(s)` tends to
infinity as `s → 1⁺` (`TauCeti.tendsto_primeIdealZetaSum_univ_atTop`), so the constant `C`
disappears from the ratio `P_S(s) / P(s)`.

The definition, its elementary calculus, and the comparison with Dirichlet density are standard;
see J.-P. Serre, *A Course in Arithmetic*, Chapter VI, §4, J.-P. Serre, *Corps locaux*, Chapter
VI, or J. Neukirch, *Algebraic Number Theory*, Chapter VII, §13.
-/

-- TauCeti/NumberTheory/ArithmeticDirichletSeries/VonMangoldt.lean
/-!
# The ideal von Mangoldt function

[Reviews and tests of this file](https://cbirkbeck.github.io/tauceti-reviewed-by-test/#m=TauCeti.NumberTheory.ArithmeticDirichletSeries.VonMangoldt)

The von Mangoldt function of a nonzero ideal `A` of the ring of integers of a number field is
`log N(P)` when `A` is a positive power of a prime ideal `P`, and zero otherwise.  This file
packages that function as an `IdealArithmeticFunction` and defines its pointwise product with an
ideal arithmetic function.

## Main definitions

* `TauCeti.IdealArithmeticFunction.vonMangoldt` is the complex-valued ideal von Mangoldt
  function.
* `TauCeti.IdealArithmeticFunction.vonMangoldtTransform` sends `f` to the weighted function
  `A ↦ f(A) Λ(A)`.

## Main results

* `TauCeti.IdealArithmeticFunction.vonMangoldt_apply_prime_pow` computes the value on a positive
  power of a prime ideal.
* `TauCeti.IdealArithmeticFunction.vonMangoldt_ne_zero_iff` says that its support is exactly the
  prime-power ideals.
* `TauCeti.IdealArithmeticFunction.vonMangoldtTransform_ne_zero_iff` identifies the support of
  the transform, and its specialization in `TauCeti.MultiplicativeIdealWeight` describes this as
  the good prime powers for a completely multiplicative weight.

The definition chooses a prime base from a proof that `A` is a prime power.  Mathlib's
`eq_of_prime_pow_eq`, applied to ideals, identifies that choice with any prime base supplied by a
caller.  The public evaluation theorem therefore removes the choice from every computation.

## Implementation notes

This is the ideal analogue of Mathlib's `ArithmeticFunction.vonMangoldt`.  Here the prime base is
chosen from `IsPrimePow` rather than computed by `Nat.minFac`, its logarithmic weight is
`Ideal.absNorm P` rather than `p`, and the function is complex-valued to match
`IdealArithmeticFunction`.

## Roadmap role

This is the algebraic part of Layer **2.3** of
`TauCetiRoadmap/ArithmeticDirichletSeries/README.md`.  The logarithmic-derivative identity named in
that target additionally requires the Euler-product package of Layer 3; this file supplies its
coefficient and exact prime-power support in advance.

## References

* J. Neukirch, *Algebraic Number Theory*, Chapter VII.
* G. Tenenbaum, *Introduction to Analytic and Probabilistic Number Theory*, Chapter I.2.
-/

-- TauCeti/NumberTheory/ModularForms/HeckeSlash/ModularForm.lean
/-!
# The slash sum descends to modular forms and to cusp forms

[Reviews and tests of this file](https://cbirkbeck.github.io/tauceti-reviewed-by-test/#m=TauCeti.NumberTheory.ModularForms.HeckeSlash.ModularForm)

`Form.lean` bundles the double coset as an endomorphism of
`SlashInvariantForm (G.map (mapGL ℝ)) k`, and flags that this is *not* the roadmap's Layer 2(b)
target because holomorphy and the cusp conditions are not yet carried along. This file supplies
exactly that: the two remaining structure fields.

Invariance comes from `heckeSlashEnd`, holomorphy from `mdifferentiable_heckeSlashSum`, and
boundedness at the cusps from `isBoundedAt_heckeSlashSum`. Because `heckeSlashEnd` is not
`@[expose]`, a structure field's `.toFun` does not reduce to the coercion by itself, so each
such field names the coercion form with `change`, then rewrites by `coe_heckeSlashEnd`.
The cusp-form case is then *derived* from the modular-form one, adding only `zero_at_cusps'`,
so neither invariance nor holomorphy is proved twice.

Both maps are also bundled as `Module.End ℂ`, which is the form Hecke operators are consumed in:
bundling is what lets them compose and later carry a ring structure.

## The level, and what it has to satisfy

`G` is any subgroup of `SL(2, ℤ)` whose image `G.map (mapGL ℝ)` is arithmetic — the hypothesis
the two cusp lemmas need, and one `(Gamma1 N).map (mapGL ℝ)` carries through
`CongruenceSubgroup.instFiniteIndexGamma1` once `N ≠ 0`. **This is the roadmap's Layer 2(b)
statement**: at `G = Γ₁(N)` and `Δ = Δ₀(N)` the endomorphisms below are the Hecke operators of a
double coset acting on `M_k(Γ₁(N))` and on `S_k(Γ₁(N))`, for an arbitrary double coset of the
Hecke triple, with no divisibility condition relating the level and the determinant. The
`q`-expansion recurrences that identify particular cosets with the classical `Tₙ` are separate
statements and are not proved here.

## Main definitions

* `HeckeRing.GL2.heckeSlashModularFormEnd`: the operator on `ModularForm (G.map (mapGL ℝ)) k`.
* `HeckeRing.GL2.heckeSlashCuspFormEnd`: the operator on `CuspForm (G.map (mapGL ℝ)) k` — the
  statement that the action preserves cuspidality.

## Main results

* `HeckeRing.GL2.coe_heckeSlashModularFormEnd`, `HeckeRing.GL2.coe_heckeSlashCuspFormEnd`: both
  are `heckeSlashSum` on underlying functions.
* `HeckeRing.GL2.coe_heckeSlashModularFormEnd_eq_sum`,
  `HeckeRing.GL2.coe_heckeSlashCuspFormEnd_eq_sum`: both are the sum of the slashes over *any*
  decomposition of the double coset into right cosets, so neither depends on the representatives
  it is assembled from. This is `heckeSlashSum_coe_eq_sum_of_rightCosets`
  (`HeckeSlash/Independence.lean`) read off the two endomorphisms.

## Provenance

The shape corresponds to `heckeSlashModularForm`, `heckeSlashCuspForm` and their bundlings in the
AINTLIB `LeanModularForms` project
([`LeanModularForms/HeckeRIngs/GL2/HeckeAction.lean`](https://github.com/CBirkbeck/AINTLIB),
commit `2baa76f742bdb4fb8ee323fabba41203bd390e08`, Apache-2.0, Chris Birkbeck). No code is
transcribed, and the level is a general `G` rather than `SL₂(ℤ)`. AINTLIB's
`CuspForm.toModularForm'` is not ported: mathlib already supplies the coercion, as the `CoeTC`
instance of `ModularFormClass` (`Mathlib/NumberTheory/ModularForms/Basic.lean`).

## References

* [G. Shimura, *Introduction to the arithmetic theory of automorphic functions*][shimura1971],
  §3.4, Proposition 3.37: `[Γ₁ α Γ₂]ₖ` sends `A_k(Γ₁), G_k(Γ₁), S_k(Γ₁)` into
  `A_k(Γ₂), G_k(Γ₂), S_k(Γ₂)`, instantiated here at `Γ₁ = Γ₂ = G`.
-/

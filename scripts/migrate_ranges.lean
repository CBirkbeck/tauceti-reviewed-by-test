import Lean

/-!
# Where Mathlib's declarations are written, and their docstrings

The migration to standard reviews (`scripts/migrate_inputs.py`) gives the writer each declaration's source and
docstring. The dataset has both for Tau Ceti's declarations, but none for those outside the library, so this script
asks Lean. It imports Mathlib (or the modules named as arguments), reads declaration names on stdin, one per line, and
prints for each a line of JSON:

    {"name": "Nat.Prime", "module": "Mathlib.Data.Nat.Prime.Defs", "file": "Mathlib/Data/Nat/Prime/Defs.lean",
     "start": [38, 0], "end": [43, 15], "doc": "`Nat.Prime p` means that `p` is a prime number, …"}
    {"name": "Finset.sum_comm", "module": "Mathlib.Algebra.BigOperators.Group.Finset.Sigma",
     "file": "Mathlib/Algebra/BigOperators/Group/Finset/Sigma.lean", "start": [120, 0], "end": [123, 31], "doc": null,
     "host": "Finset.prod_comm"}

- `name` is the line as read; `module` is the module the declaration is in, and `file` that module's path from its
  package's root.
- `start` and `end` are `[line, column]` as the dataset's `source` facet gives them: lines from 1, columns in UTF-16
  code units from 0. They span the whole declaration, its doc comment and attributes included, as
  `Lean.findDeclarationRanges?` gives them.
- `host` is there for a declaration that another one's text makes, whose range lies within that one's: the version
  that `@[to_additive]` or `@[to_dual]` makes (its range is the attribute's word), a structure's field or constructor
  (its range is its name). It names the outermost declaration of the module, written in the text, whose range holds
  it, and `start` and `end` span that one, whose text is all there is to read.
- `doc` is the declaration's own docstring (`Lean.findDocString?`), or null.

A name Lean does not know, or one it has no range for, is printed with `"error"` in place of what is missing.

Run it from a checkout of Tau Ceti at the site's commit, with Mathlib's oleans in place (`lake exe cache get`), so that
`lake env` finds them; the source lines are then read from `.lake/packages/mathlib/<file>`:

    cd <Tau Ceti checkout> && lake exe cache get
    lake env lean --run <this repository>/scripts/migrate_ranges.lean < names.txt > ranges.jsonl
    lake env lean --run <this repository>/scripts/migrate_ranges.lean Mathlib Batteries < names.txt > ranges.jsonl

`migrate_inputs.py --names-for-ranges names.txt` writes the names the migration's bundles need. Importing Mathlib maps
about 7 GB of oleans and takes under a minute; each name after that is quick (on 2026-10-31, the 4,526 names of the
whole migration took 12 seconds in all).
-/

open Lean

/-- The environment as the lookups read it: `findDeclarationRanges?` asks for a monad that carries one. -/
abbrev EnvM := ReaderT Environment IO

instance : MonadEnv EnvM where
  getEnv := read
  modifyEnv _ := pure ()

/-- A name as written on a line, with `«»` where a part needs them; a line that is no name literal is read at its
dots. -/
def parseName (s : String) : Name :=
  (Syntax.decodeNameLit ("`" ++ s)).getD s.toName

/-- The path of a module's file from its package's root: `Mathlib.Algebra.Group.Basic` is in
`Mathlib/Algebra/Group/Basic.lean`. -/
def moduleFile (module : Name) : String :=
  "/".intercalate (module.components.map (·.toString (escape := false))) ++ ".lean"

def position (line column : Nat) : Json :=
  Json.arr #[toJson line, toJson column]

/-- Where a range starts and ends, as `(line, UTF-16 column)` pairs, in the order of the text. -/
def bounds (r : DeclarationRange) : (Nat × Nat) × (Nat × Nat) :=
  ((r.pos.line, r.charUtf16), (r.endPos.line, r.endCharUtf16))

def before (a b : Nat × Nat) : Bool :=
  a.1 < b.1 || (a.1 == b.1 && a.2 ≤ b.2)

/-- Whether range `a` holds range `b` and more. -/
def holds (a b : DeclarationRange) : Bool :=
  let ((s, e), (s', e')) := (bounds a, bounds b)
  before s s' && before e' e && (s, e) != (s', e')

/-- Whether a declaration is one that another's text makes, and so no host: a structure's projections, an inductive
type's constructors and recursors, and what Lean derives from them. -/
def derived (env : Environment) (c : Name) : Bool :=
  c.isInternal || isAuxRecursor env c || isNoConfusion env c || (env.getProjectionFnInfo? c).isSome ||
    match env.find? c with
    | some (.ctorInfo _) | some (.recInfo _) => true
    | _ => false

/-- Whether `a` is a better host for `name` than `b`: it starts earlier, or ends later, so that a structure is chosen
over the projection to a parent that is no field (`Monoid.toSemigroup`), which spans its text without its doc comment;
else it is the namespace `name` is in; else its name is shorter. -/
def better (name : Name) (a b : Name × DeclarationRange) : Bool :=
  let ((sa, ea), (sb, eb)) := (bounds a.2, bounds b.2)
  if sa != sb then before sa sb
  else if ea != eb then before eb ea
  else if a.1.isPrefixOf name != b.1.isPrefixOf name then a.1.isPrefixOf name
  else a.1.toString.length < b.1.toString.length

/-- The declaration of the module `idx` whose range holds `r`, the outermost one written in the text, with its range. -/
def host (idx : ModuleIdx) (name : Name) (r : DeclarationRange) : EnvM (Option (Name × DeclarationRange)) := do
  let env ← getEnv
  let mut best : Option (Name × DeclarationRange) := none
  for c in (env.header.moduleData[idx.toNat]?.map (·.constNames)).getD #[] do
    if c == name || derived env c then continue
    if let some rs := ← findDeclarationRanges? c then
      if holds rs.range r && (best.all fun b => better name (c, rs.range) b) then
        best := some (c, rs.range)
  return best

/-- What the script prints for one name. -/
def entry (line : String) : EnvM Json := do
  let env ← getEnv
  let name := parseName line
  unless env.contains name do
    return Json.mkObj [("name", toJson line), ("error", toJson "Lean does not know this name")]
  let idx? := env.getModuleIdxFor? name
  let module := idx?.bind (env.header.moduleNames[·]?)
  let doc ← findDocString? env name
  let fields : List (String × Json) := [("name", toJson line),
    ("module", match module with | some m => toJson (m.toString (escape := false)) | none => Json.null),
    ("file", match module with | some m => toJson (moduleFile m) | none => Json.null),
    ("doc", match doc with | some d => toJson d | none => Json.null)]
  let some ranges ← findDeclarationRanges? name
    | return Json.mkObj (fields ++ [("error", toJson "Lean has no range for this declaration")])
  let found ← match idx? with
    | some idx => host idx name ranges.range
    | none => pure none
  let r := (found.map (·.2)).getD ranges.range
  let span := [("start", position r.pos.line r.charUtf16), ("end", position r.endPos.line r.endCharUtf16)]
  return Json.mkObj (fields ++ span ++ (found.map fun (h, _) => ("host", toJson (h.toString (escape := false)))).toList)

unsafe def main (args : List String) : IO UInt32 := do
  initSearchPath (← findSysroot)
  let modules := if args.isEmpty then [`Mathlib] else args.map String.toName
  let env ← importModules (modules.toArray.map ({ module := · })) {} (trustLevel := 1024)
  let stdin ← IO.getStdin
  let stdout ← IO.getStdout
  repeat
    let line ← stdin.getLine
    if line.isEmpty then break
    let name := line.trimAscii.toString
    unless name.isEmpty do
      stdout.putStrLn (← (entry name).run env).compress
  stdout.flush
  return 0

/-
PMLL in Lean 4.

Persistent Memory Logic Loop, following `PMLL.h` / `PMLL.c`:
a bounded memory silo, a 3-SAT conflict check, unit propagation, and a budgeted
DPLL refine loop. `Flag.sat` is returned only with a certificate that the
assignment is total and `checkConflict` is false. The silo is written after that,
not used as a proof of P = NP.
-/

namespace PMLL

inductive Flag where
  | unresolved
  | sat
  | unsat
  deriving DecidableEq, Repr, Inhabited

/-- Variable index of a literal, or `none` when the literal is 0 or out of range. -/
def litVar (lit : Int) (n : Nat) : Option Nat :=
  if lit == 0 then
    none
  else
    let v := lit.natAbs - 1
    if v < n then some v else none

def readAsg (a : List (Option Bool)) (v : Nat) : Option Bool :=
  match a[v]? with
  | some b => b
  | none => none

def litSat (n : Nat) (a : List (Option Bool)) (lit : Int) : Bool :=
  match litVar lit n with
  | some v =>
    match readAsg a v with
    | some b => b == (lit > 0)
    | none => false
  | none => false

def litOpen (n : Nat) (a : List (Option Bool)) (lit : Int) : Bool :=
  match litVar lit n with
  | some v =>
    match a[v]? with
    | some none => true
    | _ => false
  | none => false

/-- Conflict when every literal is ignored or assigned false. Matches `check_conflict`. -/
def clauseConflict (n : Nat) (a : List (Option Bool)) (c : List Int) : Bool :=
  !(c.any (litSat n a)) && !(c.any (litOpen n a))

def checkConflict (n : Nat) (clauses : List (List Int)) (a : List (Option Bool)) : Bool :=
  clauses.any (clauseConflict n a)

theorem checkConflict_any (n : Nat) (clauses : List (List Int)) (a : List (Option Bool)) :
    checkConflict n clauses a = clauses.any (clauseConflict n a) := rfl

def allAssigned (a : List (Option Bool)) : Bool :=
  a.all Option.isSome

def firstOpen : List (Option Bool) → Option Nat
  | [] => none
  | none :: _ => some 0
  | some _ :: rest => (firstOpen rest).map Nat.succ

def setAsg (a : List (Option Bool)) (v : Nat) (b : Bool) : List (Option Bool) :=
  a.set v (some b)

inductive Look where
  | sat
  | conflict
  | unit (lit : Int)
  | multi
  deriving DecidableEq, Repr

def lookClause (n : Nat) (a : List (Option Bool)) (c : List Int) : Look := Id.run do
  let mut satisfied := false
  let mut freeCount := 0
  let mut freeLit : Int := 0
  for lit in c do
    if !satisfied then
      match litVar lit n with
      | none => pure ()
      | some v =>
        match readAsg a v with
        | none =>
          if freeCount == 0 || freeLit != lit then
            freeCount := freeCount + 1
            freeLit := lit
        | some b =>
          if b == (lit > 0) then
            satisfied := true
  if satisfied then
    return .sat
  else if freeCount == 0 then
    return .conflict
  else if freeCount == 1 then
    return .unit freeLit
  else
    return .multi

inductive Pass where
  | conflict
  | changed (a : List (Option Bool))
  | fixed (a : List (Option Bool))

def pass (n : Nat) (clauses : List (List Int)) (a : List (Option Bool)) : Pass :=
  let rec go (cs : List (List Int)) : Pass :=
    match cs with
    | [] => .fixed a
    | c :: rest =>
      match lookClause n a c with
      | .conflict => .conflict
      | .unit lit =>
        match litVar lit n with
        | some v => .changed (setAsg a v (lit > 0))
        | none => go rest
      | .sat => go rest
      | .multi => go rest
  go clauses

/-- Unit propagation. Fuel `n + 1` is enough: each `.changed` assigns one variable. -/
def propagate (n : Nat) (clauses : List (List Int)) (a : List (Option Bool)) :
    Option (List (Option Bool)) :=
  let rec go (fuel : Nat) (a : List (Option Bool)) : Option (List (Option Bool)) :=
    match fuel with
    | 0 => some a
    | fuel + 1 =>
      match pass n clauses a with
      | .conflict => none
      | .fixed a => some a
      | .changed a => go fuel a
  go (n + 1) a

/-- Budgeted DPLL. `0` then `1`, same order as `pml_dpll`. Remaining budget is returned. -/
def dpll (n : Nat) (clauses : List (List Int)) (a : List (Option Bool)) (budget : Nat) :
    Flag × List (Option Bool) × Nat :=
  match propagate n clauses a with
  | none => (.unsat, a, budget)
  | some a =>
    if checkConflict n clauses a then
      (.unsat, a, budget)
    else
      match firstOpen a with
      | none => (.sat, a, budget)
      | some v =>
        match budget with
        | 0 => (.unresolved, a, 0)
        | b + 1 =>
          match dpll n clauses (setAsg a v false) b with
          | (.sat, a', b') => (.sat, a', b')
          | (.unresolved, _, b') => (.unresolved, a, b')
          | (.unsat, _, _) =>
            match dpll n clauses (setAsg a v true) b with
            | (.sat, a', b3) => (.sat, a', b3)
            | (.unresolved, _, b3) => (.unresolved, a, b3)
            | (.unsat, _, b3) => (.unsat, a, b3)
termination_by budget

structure Cert where
  n : Nat
  clauses : List (List Int)
  a : List (Option Bool)
  complete : allAssigned a = true
  clear : checkConflict n clauses a = false
  deriving Repr

def refine (n : Nat) (clauses : List (List Int)) (budget : Nat) : Flag × Option Cert :=
  let a0 := List.replicate n none
  match dpll n clauses a0 budget with
  | (.sat, a, _) =>
    if h1 : allAssigned a = true then
      if h2 : checkConflict n clauses a = false then
        (.sat, some { n, clauses, a, complete := h1, clear := h2 })
      else
        (.unresolved, none)
    else
      (.unresolved, none)
  | (.unsat, _, _) => (.unsat, none)
  | (.unresolved, _, _) => (.unresolved, none)

theorem sat_is_certified (n : Nat) (clauses : List (List Int)) (budget : Nat) (c : Cert) :
    refine n clauses budget = (.sat, some c) →
      allAssigned c.a = true ∧ checkConflict c.n c.clauses c.a = false := by
  intro _
  exact ⟨c.complete, c.clear⟩

/- Silo: integer tree plus a resolved slot, written only after a certified SAT. -/

structure Slot where
  key : Option String
  content : Option String
  resolved : Bool
  deriving Repr, Inhabited

structure Silo where
  tree : Array Int
  slots : Array Slot
  deriving Repr

def Silo.empty (capacity : Nat) : Silo where
  tree := Array.replicate (capacity * 2) 0
  slots := Array.replicate capacity default

def Silo.record (s : Silo) (index : Nat) (key content : String) : Silo :=
  if h : index < s.slots.size then
    let slot : Slot := { key := some key, content := some content, resolved := true }
    let slots := s.slots.set index slot
    let tree := if h2 : index < s.tree.size then s.tree.set index 1 else s.tree
    { s with slots, tree }
  else
    s

def recordModel (c : Cert) : Silo :=
  let rec go (s : Silo) (i : Nat) (rest : List (Option Bool)) : Silo :=
    match rest with
    | [] => s
    | none :: tail => go s (i + 1) tail
    | some v :: tail =>
      let bit := if v then "true" else "false"
      go (s.record i s!"assign:x{i + 1}" s!"x{i + 1}={bit}") (i + 1) tail
  go (Silo.empty (c.n + 1)) 0 c.a

def peek (s : Silo) (key : String) : Option String :=
  s.slots.findSome? fun slot =>
    if slot.resolved && slot.key == some key then slot.content else none

/- Pigeonhole, the instance the loop does not put in P. -/

theorem Fin2.dichotomy (x : Fin 2) : x = 0 ∨ x = 1 := by
  have hx : x.val < 2 := x.isLt
  omega

theorem php_3_2 (f : Fin 3 → Fin 2) : f 0 = f 1 ∨ f 0 = f 2 ∨ f 1 = f 2 := by
  rcases Fin2.dichotomy (f 0) with h0 | h0
  <;> rcases Fin2.dichotomy (f 1) with h1 | h1
  <;> rcases Fin2.dichotomy (f 2) with h2 | h2
  <;> simp [h0, h1, h2]
  <;> first
    | exact Or.inl rfl
    | exact Or.inr (Or.inl rfl)
    | exact Or.inr (Or.inr rfl)

theorem no_injection_3_2 : ¬∃ f : Fin 3 → Fin 2, Function.Injective f := by
  intro ⟨f, hf⟩
  rcases php_3_2 f with h | h | h
  · exact absurd h (hf.ne (by decide : (0 : Fin 3) ≠ 1))
  · exact absurd h (hf.ne (by decide : (0 : Fin 3) ≠ 2))
  · exact absurd h (hf.ne (by decide : (1 : Fin 3) ≠ 2))

/-- 3 pigeons, 2 holes. Variables `p * 2 + h`, literals are 1-based. -/
def php32 : List (List Int) := Id.run do
  let id (p h : Nat) : Int := p * 2 + h + 1
  let atleast := (List.range 3).map fun p => [id p 0, id p 1]
  let mut pairs : List (List Int) := []
  for h in [:2] do
    for a in [:3] do
      for b in [a + 1 : 3] do
        pairs := pairs ++ [[-id a h, -id b h]]
  return atleast ++ pairs

def decode6 (mask : Nat) : List (Option Bool) :=
  (List.range 6).map fun i => some (((mask >>> i) &&& 1) == 1)

/-- Every total assignment of the 6 variables falsifies `php32`. -/
def php32AllConflict : Bool :=
  (List.range 64).all fun m => checkConflict 6 php32 (decode6 m)

theorem php32AllConflict_true : php32AllConflict = true := by
  native_decide

def budgetFor (n : Nat) : Nat :=
  2 ^ min (n + 1) 22

theorem php32_refine_unsat : (refine 6 php32 (budgetFor 6)).1 = Flag.unsat := by
  native_decide

/- A satisfiable clause set, so the SAT certificate path is inhabited. -/

def satExample : List (List Int) := [[1, 2], [-1, 2]]

theorem satExample_refine : (refine 2 satExample (budgetFor 2)).1 = Flag.sat := by
  native_decide

def satExampleCert : Option Cert :=
  (refine 2 satExample (budgetFor 2)).2

theorem satExample_clear (c : Cert) (_h : satExampleCert = some c) :
    checkConflict c.n c.clauses c.a = false := c.clear

end PMLL

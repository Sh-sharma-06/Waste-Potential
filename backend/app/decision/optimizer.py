"""
Allocation optimizer for the Waste-Potential decision module.

Implements a Linear Programming (LP) model that allocates waste tonnage from
sources to treatment technologies, minimising a weighted composite objective.

Objective (minimise):
  Σ_{(i,j)} [ w_cost   · net_cost[i,j]
             + w_carbon · carbon[i,j]
             + w_transport · transport[i,j] ] · x[i,j]

Constraints:
  C1: Σ_j x[i,j] ≤ supply[i]       (supply limits)
  C2: Σ_i x[i,j] ≤ capacity[j]     (capacity limits)
  C3: x[i,j] ≥ 0                   (non-negativity)

Incompatibility is enforced via hard-zero: incompatible (i,j) pairs are never
created as LP variables (compatibility_matrix[i][j] must be 1 for the variable
to exist).

The SolverBackend protocol decouples the LP formulation from the solver
implementation. ScipyBackend (continuous LP, default) and OrtoolsBackend
(optional, MILP-capable) both satisfy the protocol.

Phase 1 stays strictly LP-continuous — no binary or integer variables.
Varying the weight vector across calls generates the Pareto front (B4 scope).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable

import numpy as np

# ---------------------------------------------------------------------------
# Solver result
# ---------------------------------------------------------------------------

@dataclass
class SolveResult:
    """Raw result returned by a SolverBackend.

    Attributes
    ----------
    x:
        Solution vector (length = number of LP variables). None if infeasible.
    objective_value:
        Value of the objective function at the solution. None if infeasible.
    status:
        Solver status string, e.g. "optimal", "infeasible", "unbounded".
    success:
        True iff the solver found a feasible, bounded solution.
    """
    x: Optional[np.ndarray]
    objective_value: Optional[float]
    status: str
    success: bool


# ---------------------------------------------------------------------------
# SolverBackend protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class SolverBackend(Protocol):
    """Protocol that all solver adapters must satisfy.

    The LP is expressed in standard minimisation form:
      min  c^T x
      s.t. A_ub x ≤ b_ub
           lb ≤ x ≤ ub   (bounds, where lb=0 for all variables)
    """

    def solve(
        self,
        c: np.ndarray,
        A_ub: np.ndarray,
        b_ub: np.ndarray,
        bounds: list[tuple[float, Optional[float]]],
    ) -> SolveResult:
        """Solve the LP and return a SolveResult."""
        ...

    def name(self) -> str:
        """Human-readable name of the backend."""
        ...


# ---------------------------------------------------------------------------
# ScipyBackend (default — no extra install required)
# ---------------------------------------------------------------------------

class ScipyBackend:
    """Wraps scipy.optimize.linprog for continuous LP.

    Uses the HiGHS method (scipy ≥ 1.7) which is considerably faster than
    the legacy revised simplex or interior-point methods.
    """

    def solve(
        self,
        c: np.ndarray,
        A_ub: np.ndarray,
        b_ub: np.ndarray,
        bounds: list[tuple[float, Optional[float]]],
    ) -> SolveResult:
        from scipy.optimize import linprog  # type: ignore[import]

        res = linprog(
            c,
            A_ub=A_ub,
            b_ub=b_ub,
            bounds=bounds,
            method="highs",
        )
        return SolveResult(
            x=res.x if res.success else None,
            objective_value=float(res.fun) if res.success else None,
            status=res.message,
            success=bool(res.success),
        )

    def name(self) -> str:
        return "scipy-highs"


# ---------------------------------------------------------------------------
# OrtoolsBackend (optional — requires google-or-tools)
# ---------------------------------------------------------------------------

try:
    from ortools.linear_solver import pywraplp as _pywraplp  # type: ignore[import]
    _ORTOOLS_AVAILABLE = True
except ImportError:
    _ORTOOLS_AVAILABLE = False


class OrtoolsBackend:
    """Wraps OR-Tools pywraplp for LP (and MILP when needed in future phases).

    Raises ImportError at construction time if google-or-tools is not installed.
    """

    def __init__(self) -> None:
        if not _ORTOOLS_AVAILABLE:
            raise ImportError(
                "google-or-tools is not installed. "
                "Run: pip install ortools"
            )

    def solve(
        self,
        c: np.ndarray,
        A_ub: np.ndarray,
        b_ub: np.ndarray,
        bounds: list[tuple[float, Optional[float]]],
    ) -> SolveResult:
        solver = _pywraplp.Solver.CreateSolver("GLOP")
        n = len(c)

        # Create variables
        vars_ = []
        for k in range(n):
            lb, ub = bounds[k]
            ub_val = ub if ub is not None else solver.infinity()
            vars_.append(solver.NumVar(lb, ub_val, f"x{k}"))

        # Inequality constraints
        for row_idx in range(A_ub.shape[0]):
            ct = solver.Constraint(-solver.infinity(), float(b_ub[row_idx]))
            for k in range(n):
                ct.SetCoefficient(vars_[k], float(A_ub[row_idx, k]))

        # Objective
        obj = solver.Objective()
        for k in range(n):
            obj.SetCoefficient(vars_[k], float(c[k]))
        obj.SetMinimization()

        status_code = solver.Solve()
        optimal = status_code == _pywraplp.Solver.OPTIMAL

        status_map = {
            _pywraplp.Solver.OPTIMAL: "optimal",
            _pywraplp.Solver.FEASIBLE: "feasible",
            _pywraplp.Solver.INFEASIBLE: "infeasible",
            _pywraplp.Solver.UNBOUNDED: "unbounded",
            _pywraplp.Solver.ABNORMAL: "abnormal",
            _pywraplp.Solver.NOT_SOLVED: "not_solved",
        }
        status_str = status_map.get(status_code, f"unknown({status_code})")

        if optimal:
            x_vals = np.array([v.solution_value() for v in vars_])
            obj_val = solver.Objective().Value()
        else:
            x_vals = None
            obj_val = None

        return SolveResult(
            x=x_vals,
            objective_value=obj_val,
            status=status_str,
            success=optimal,
        )

    def name(self) -> str:
        return "ortools-glop"


# ---------------------------------------------------------------------------
# Input / output dataclasses
# ---------------------------------------------------------------------------

@dataclass
class WasteScenario:
    """Full input specification for a single optimisation run.

    Attributes
    ----------
    supply:
        Dict mapping stream_id → available supply (tonnes/year).
        Keys are string IDs (e.g. PostGIS UUIDs or integer strings).
    capacity:
        Dict mapping tech_id → treatment capacity (tonnes/year).
        Keys are string IDs.
    compatibility_matrix:
        Dict mapping (stream_id, tech_id) → 1 (compatible) or 0 (incompatible).
        Pairs absent from the dict are treated as incompatible (0).
    objective_coefficients:
        Dict mapping (stream_id, tech_id) → per-tonne weighted objective
        coefficient (pre-computed from CostEngine + CarbonCalculator).
        The optimizer minimises Σ coeff[i,j] · x[i,j].
        Must only contain entries for compatible (i,j) pairs.
    weights:
        Normalised operator weights for objective terms. Used externally by the
        caller (CostEngine / CarbonCalculator) to pre-compute objective
        coefficients before passing them here. Stored for traceability.
    """
    supply: dict[str, float]
    capacity: dict[str, float]
    compatibility_matrix: dict[tuple[str, str], int]
    objective_coefficients: dict[tuple[str, str], float]
    weights: dict[str, float] = field(default_factory=lambda: {
        "w_cost": 1.0,
        "w_carbon": 0.0,
        "w_transport": 0.0,
    })

    def __post_init__(self) -> None:
        w = self.weights
        total = sum(w.get(k, 0.0) for k in ("w_cost", "w_carbon", "w_transport"))
        if not math.isclose(total, 1.0, abs_tol=1e-6):
            raise ValueError(
                f"Objective weights must sum to 1.0, got {total:.6f}. "
                f"Weights: {w}"
            )
        if any(v < 0 for v in w.values()):
            raise ValueError(f"All objective weights must be ≥ 0. Got: {w}")


@dataclass
class AllocationResult:
    """Result of a single optimisation run.

    Attributes
    ----------
    allocation:
        Dict mapping (stream_id, tech_id) → tonnes/year allocated.
        Only compatible pairs with x[i,j] > 0 are included.
        Keys are string IDs matching the input WasteScenario.
    objective_value:
        Value of the weighted objective at the optimal solution. None if
        the problem was infeasible or unbounded.
    solver_status:
        Human-readable status string from the solver backend.
    success:
        True iff the solver found an optimal feasible solution.
    variable_index:
        Ordered list of (stream_id, tech_id) pairs matching the LP variable
        vector — useful for debugging and result reconstruction.
    """
    allocation: dict[tuple[str, str], float]
    objective_value: Optional[float]
    solver_status: str
    success: bool
    variable_index: list[tuple[str, str]]


# ---------------------------------------------------------------------------
# Optimizer
# ---------------------------------------------------------------------------

class Optimizer:
    """Assembles and solves the waste allocation LP.

    Usage
    -----
    >>> backend = ScipyBackend()
    >>> opt = Optimizer(backend)
    >>> result = opt.solve(scenario)

    Pareto front generation (B4 scope):
    >>> results = [opt.solve(scenario_with_weights(w)) for w in weight_grid]
    """

    def __init__(self, backend: Optional[SolverBackend] = None) -> None:
        """
        Parameters
        ----------
        backend:
            A SolverBackend instance. Defaults to ScipyBackend().
        """
        self._backend: SolverBackend = backend if backend is not None else ScipyBackend()

    # ------------------------------------------------------------------
    # LP assembly
    # ------------------------------------------------------------------

    @staticmethod
    def _build_lp(
        scenario: WasteScenario,
    ) -> tuple[
        np.ndarray,              # c — objective coefficients
        np.ndarray,              # A_ub — constraint matrix
        np.ndarray,              # b_ub — constraint RHS
        list[tuple[float, Optional[float]]],  # bounds
        list[tuple[str, str]],  # variable_index: ordered (i,j) pairs
    ]:
        """Translate a WasteScenario into scipy-compatible LP arrays.

        Variable ordering: enumerate all compatible (i, j) pairs in a
        deterministic order (sorted by stream_id, then tech_id).

        Constraints built:
          C1: one row per stream_id  (supply limits)
          C2: one row per tech_id   (capacity limits)
        """
        # Enumerate compatible (i,j) pairs — hard-zero incompatibility
        var_index: list[tuple[str, str]] = sorted(
            (i, j)
            for (i, j), compat in scenario.compatibility_matrix.items()
            if compat == 1
        )
        n_vars = len(var_index)

        if n_vars == 0:
            raise ValueError(
                "No compatible (stream_id, tech_id) pairs found in "
                "compatibility_matrix. The LP has no decision variables."
            )

        # Index maps for O(1) constraint row lookup
        stream_ids = sorted(scenario.supply)
        tech_ids = sorted(scenario.capacity)
        stream_row: dict[str, int] = {s: idx for idx, s in enumerate(stream_ids)}
        tech_row: dict[str, int] = {t: idx for idx, t in enumerate(tech_ids)}
        n_streams = len(stream_ids)
        n_techs = len(tech_ids)
        n_constraints = n_streams + n_techs

        # Objective vector c (we minimise)
        c = np.zeros(n_vars)
        for k, (i, j) in enumerate(var_index):
            coeff = scenario.objective_coefficients.get((i, j), 0.0)
            c[k] = coeff

        # Constraint matrix A_ub and RHS b_ub
        A_ub = np.zeros((n_constraints, n_vars))
        b_ub = np.zeros(n_constraints)

        # C1 — supply limits
        for k, (i, j) in enumerate(var_index):
            row = stream_row[i]
            A_ub[row, k] = 1.0
        for idx, s in enumerate(stream_ids):
            b_ub[idx] = scenario.supply[s]

        # C2 — capacity limits
        offset = n_streams
        for k, (i, j) in enumerate(var_index):
            row = tech_row[j] + offset
            A_ub[row, k] = 1.0
        for idx, t in enumerate(tech_ids):
            b_ub[idx + offset] = scenario.capacity[t]

        # Bounds: x[i,j] ≥ 0, no explicit upper bound (capacity enforces it)
        bounds: list[tuple[float, Optional[float]]] = [(0.0, None)] * n_vars

        return c, A_ub, b_ub, bounds, var_index

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def solve(self, scenario: WasteScenario) -> AllocationResult:
        """Solve the LP for the given scenario.

        Parameters
        ----------
        scenario:
            WasteScenario with supply, capacity, compatibility, and
            pre-computed objective coefficients.

        Returns
        -------
        AllocationResult
            Contains the allocation dict, objective value, and solver status.
        """
        c, A_ub, b_ub, bounds, var_index = self._build_lp(scenario)
        result = self._backend.solve(c, A_ub, b_ub, bounds)

        if result.success and result.x is not None:
            allocation: dict[tuple[str, str], float] = {
                pair: float(result.x[k])
                for k, pair in enumerate(var_index)
                if result.x[k] > 1e-9  # prune numerical zeros
            }
        else:
            allocation = {}

        return AllocationResult(
            allocation=allocation,
            objective_value=result.objective_value,
            solver_status=result.status,
            success=result.success,
            variable_index=var_index,
        )

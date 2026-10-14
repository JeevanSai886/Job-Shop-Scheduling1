from dataclasses import replace
from fractions import Fraction

from backend.models import (
    JobShopInstance,
    Operation,
    Scenario,
    SensitivityRequest,
    SensitivityResult,
    SolveRequest,
)
from backend.solvers import solve


def percent_change(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None or baseline == 0:
        return None
    return (value - baseline) / baseline * 100


def analyze_sensitivity(instance: JobShopInstance, request: SensitivityRequest) -> SensitivityResult:
    settings = SolveRequest(
        objective=request.objective, solver=request.solver, time_limit_s=request.time_limit_s
    )
    baseline = solve(instance, settings)
    scenarios = []
    for delta in dict.fromkeys(request.deltas):
        factor = 1 + Fraction(delta) / 100
        modified = replace(
            instance,
            jobs=tuple(
                tuple(Operation(op.machine, op.duration * factor) for op in job) for job in instance.jobs
            ),
        )
        # Deliberately re-solve every requested scenario, including an explicitly entered zero delta.
        result = solve(modified, settings)
        scenarios.append(
            Scenario(
                delta=float(delta),
                result=result,
                objective_change_pct=percent_change(result.objective_value, baseline.objective_value),
                makespan_change_pct=percent_change(result.makespan, baseline.makespan),
            )
        )
    return SensitivityResult(
        objective=request.objective,
        solver=request.solver,
        baseline=baseline,
        scenarios=scenarios,
        note="Each scenario is re-solved with exact, uniformly scaled durations. "
        "Proven optima scale linearly; "
        "time-limited solutions may differ due to search. Percent change is undefined for a zero baseline.",
    )

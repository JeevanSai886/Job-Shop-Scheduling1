"""Two independent optimization models with shared, verified output semantics."""

import math
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from fractions import Fraction
from functools import reduce
from itertools import combinations
from pathlib import Path

import pulp
from ortools.sat.python import cp_model

from backend.models import (
    JobCompletion,
    JobShopInstance,
    MachineSchedule,
    ScheduledOperation,
    SolveRequest,
    SolveResult,
    Status,
)
from backend.stats import compute_stats

Key = tuple[int, int]


@dataclass
class TickData:
    durations: dict[Key, int]
    machines: list[list[Key]]
    unit: Fraction
    horizon: int


def to_ticks(instance: JobShopInstance) -> TickData:
    """Use a data-derived rational time unit; no rounding of uploaded/scenario durations."""
    values = [op.duration for job in instance.jobs for op in job]
    denominator = math.lcm(*(value.denominator for value in values))
    divisor = reduce(math.gcd, (int(value * denominator) for value in values))
    unit = Fraction(divisor, denominator)
    durations = {
        (i, j): int(op.duration / unit) for i, job in enumerate(instance.jobs) for j, op in enumerate(job)
    }
    horizon = sum(durations.values())
    # Numerical safety limit, not a problem-data constant. Leave room for sums in both solvers.
    if horizon * max(len(durations), instance.num_machines) >= 2**50:
        raise ValueError(
            "The exact time scale is too large. Reduce the precision or magnitude of processing times."
        )
    machines: list[list[Key]] = [[] for _ in instance.machine_labels]
    for i, job in enumerate(instance.jobs):
        for j, op in enumerate(job):
            machines[op.machine].append((i, j))
    return TickData(durations, machines, unit, horizon)


def validate_schedule(data: TickData, instance: JobShopInstance, starts: dict[Key, int]) -> None:
    if set(starts) != set(data.durations):
        raise ValueError("Solver did not return every operation.")
    for i, job in enumerate(instance.jobs):
        previous_end = 0
        for j, _ in enumerate(job):
            key = (i, j)
            if starts[key] < previous_end:
                raise ValueError("Returned schedule violates job precedence or nonnegative start times.")
            previous_end = starts[key] + data.durations[key]
            if previous_end > data.horizon:
                raise ValueError("Returned schedule exceeds the model horizon.")
    for keys in data.machines:
        ordered = sorted(keys, key=lambda key: (starts[key], key))
        for left, right in zip(ordered, ordered[1:]):
            if starts[left] + data.durations[left] > starts[right]:
                raise ValueError("Returned schedule contains overlapping machine operations.")


def _warm_start(instance: JobShopInstance, data: TickData) -> dict[Key, int]:
    next_ops = [0 for _ in instance.jobs]
    job_ready = [0 for _ in instance.jobs]
    machine_ready = [0 for _ in instance.machine_labels]
    starts = {}
    while len(starts) < len(data.durations):
        choices = []
        for i, job in enumerate(instance.jobs):
            j = next_ops[i]
            if j < len(job):
                start = max(job_ready[i], machine_ready[job[j].machine])
                choices.append((start + data.durations[i, j], start, i, j))
        end, start, i, j = min(choices)
        starts[i, j] = start
        job_ready[i] = machine_ready[instance.jobs[i][j].machine] = end
        next_ops[i] += 1
    return starts


def _cp_sat(
    instance: JobShopInstance, data: TickData, request: SolveRequest
) -> tuple[Status, dict[Key, int] | None, float | None]:
    model = cp_model.CpModel()
    starts, ends, intervals = {}, {}, {}
    for key, duration in data.durations.items():
        starts[key] = model.new_int_var(0, data.horizon - duration, f"s_{key}")
        ends[key] = model.new_int_var(duration, data.horizon, f"e_{key}")
        intervals[key] = model.new_interval_var(starts[key], duration, ends[key], f"task_{key}")
    for i, job in enumerate(instance.jobs):
        for j in range(len(job) - 1):
            model.add(starts[i, j + 1] >= ends[i, j])
    for keys in data.machines:
        model.add_no_overlap([intervals[key] for key in keys])
    makespan = model.new_int_var(0, data.horizon, "c_max")
    model.add_max_equality(makespan, [ends[i, len(job) - 1] for i, job in enumerate(instance.jobs)])
    completions = []
    for k, keys in enumerate(data.machines):
        completion = model.new_int_var(0, data.horizon, f"c_machine_{k}")
        model.add_max_equality(completion, [ends[key] for key in keys] or [0])
        completions.append(completion)
    model.minimize(makespan if request.objective == "makespan" else sum(completions) - data.horizon)
    warm = _warm_start(instance, data)
    for key, start in warm.items():
        model.add_hint(starts[key], start)
        model.add_hint(ends[key], start + data.durations[key])
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = request.time_limit_s
    solver.parameters.num_search_workers = max(1, min(os.cpu_count() or 1, 8))
    status_code = solver.solve(model)
    status: Status = {
        cp_model.OPTIMAL: "optimal",
        cp_model.FEASIBLE: "feasible",
        cp_model.INFEASIBLE: "infeasible",
        cp_model.MODEL_INVALID: "model_invalid",
    }.get(status_code, "no_solution")
    if status not in ("optimal", "feasible"):
        return status, None, None
    return status, {key: solver.value(var) for key, var in starts.items()}, solver.best_objective_bound


def _pulp_bigm(
    instance: JobShopInstance, data: TickData, request: SolveRequest
) -> tuple[Status, dict[Key, int] | None, float | None]:
    model = pulp.LpProblem("job_shop", pulp.LpMinimize)
    big_m = data.horizon
    starts = {
        key: pulp.LpVariable(f"s_{key[0]}_{key[1]}", 0, big_m - duration, cat="Integer")
        for key, duration in data.durations.items()
    }
    ends = {key: starts[key] + duration for key, duration in data.durations.items()}
    warm = _warm_start(instance, data)
    for key in starts:
        starts[key].setInitialValue(warm[key])
    for i, job in enumerate(instance.jobs):
        for j in range(len(job) - 1):
            model += starts[i, j + 1] >= ends[i, j]
    for k, keys in enumerate(data.machines):
        for a, b in combinations(keys, 2):
            order = pulp.LpVariable(f"x_{k}_{a[0]}_{a[1]}_{b[0]}_{b[1]}", cat="Binary")
            order.setInitialValue(int(warm[a] + data.durations[a] <= warm[b]))
            model += ends[a] <= starts[b] + big_m * (1 - order)
            model += ends[b] <= starts[a] + big_m * order
    c_max = pulp.LpVariable("c_max", 0, big_m, cat="Integer")
    for i, job in enumerate(instance.jobs):
        model += c_max >= ends[i, len(job) - 1]
    c_max.setInitialValue(max(warm[key] + data.durations[key] for key in starts))
    completions = []
    for k, keys in enumerate(data.machines):
        completion = pulp.LpVariable(f"c_machine_{k}", 0, big_m, cat="Integer")
        completions.append(completion)
        if not keys:
            model += completion == 0
            completion.setInitialValue(0)
            continue
        # Select the actual final operation, so C_k equals max(end) under either objective.
        final_key = max(keys, key=lambda key: warm[key] + data.durations[key])
        selectors = []
        for key in keys:
            last = pulp.LpVariable(f"last_{k}_{key[0]}_{key[1]}", cat="Binary")
            last.setInitialValue(int(key == final_key))
            selectors.append(last)
            model += completion >= ends[key]
            model += completion <= ends[key] + big_m * (1 - last)
        model += pulp.lpSum(selectors) == 1
        completion.setInitialValue(warm[final_key] + data.durations[final_key])
    model += c_max if request.objective == "makespan" else pulp.lpSum(completions) - data.horizon
    with tempfile.TemporaryDirectory(prefix="jssp-cbc-") as temp:
        log = Path(temp) / "solver.log"
        engine = pulp.PULP_CBC_CMD(msg=False)
        if not engine.available():
            raise RuntimeError("CBC is unavailable. Install the bundled PuLP/CBC wheel or choose CP-SAT.")
        # PuLP's stock Windows command splits file paths and cannot load absolute MIP-start paths.
        # Write through PuLP, then call its bundled CBC with relative filenames in a private cwd.
        # Omit -threads so CBC runs serially (its bundled Windows threaded mode can stall).
        variables, variable_names, constraint_names, _ = model.writeMPS(
            str(Path(temp) / "model.mps"), rename=1
        )
        engine.writesol(str(Path(temp) / "warm.mst"), model, variables, variable_names, constraint_names)
        args = [
            str(engine.path),
            "model.mps",
            "-mips",
            "warm.mst",
            "-sec",
            str(request.time_limit_s),
            "-ratio",
            "0",
            "-timeMode",
            "elapsed",
            "-branch",
            "-printingOptions",
            "all",
            "-solution",
            "solution.sol",
        ]
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        with log.open("w", encoding="utf-8") as output:
            try:
                process = subprocess.run(
                    args,
                    cwd=temp,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    creationflags=flags,
                    timeout=request.time_limit_s + 10,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return "no_solution", None, None
        if process.returncode:
            raise RuntimeError("CBC could not complete the solve. Try CP-SAT or reduce the instance size.")
        log_text = log.read_text(encoding="utf-8", errors="replace")
        solution_path = Path(temp) / "solution.sol"
        if not solution_path.exists():
            return "no_solution", None, None
        lp_status, values, _, _, _, solution_status = engine.readsol_MPS(
            str(solution_path), model, variables, variable_names, constraint_names
        )
        model.assignVarsVals(values)
        model.assignStatus(lp_status, solution_status)
    # PuLP's LpStatus can say Optimal for a time-limited incumbent; inspect sol_status too.
    if model.status == pulp.LpStatusInfeasible:
        # CBC can emit an infeasible solution-file header when interrupted in presolve.
        proven_infeasible = (
            "Result - Problem proven infeasible" in log_text or "Problem is infeasible" in log_text
        )
        return ("infeasible" if proven_infeasible else "no_solution"), None, None
    if model.sol_status not in (pulp.LpSolutionOptimal, pulp.LpSolutionIntegerFeasible):
        return "no_solution", None, None
    values = {key: var.value() for key, var in starts.items()}
    if any(value is None or abs(value - round(value)) > 1e-5 for value in values.values()):
        return "no_solution", None, None
    proven = (
        model.sol_status == pulp.LpSolutionOptimal
        and model.status == pulp.LpStatusOptimal
        and "Result - Optimal solution found" in log_text
    )
    status: Status = "optimal" if proven else "feasible"
    match = re.search(r"Lower bound:\s*([-+\d.eE]+)", log_text)
    bound = float(match.group(1)) if match else None
    if bound is not None and request.objective == "idle_time":
        bound -= data.horizon  # CBC's log omits the fixed objective constant.
    return status, {key: round(value) for key, value in values.items()}, bound


def solve(instance: JobShopInstance, request: SolveRequest) -> SolveResult:
    started = time.perf_counter()
    data = to_ticks(instance)
    status, starts, bound = (_cp_sat if request.solver == "cp_sat" else _pulp_bigm)(instance, data, request)
    messages = {
        "optimal": "Optimality proven by the solver.",
        "feasible": "Best feasible schedule found within the search budget; optimality is not proven.",
        "no_solution": "No feasible schedule was returned within the time budget. "
        "Increase the time limit or try the other engine.",
        "infeasible": "The solver proved the model infeasible.",
        "model_invalid": "The solver rejected the model. Check numeric magnitude and precision.",
    }
    result = SolveResult(
        objective=request.objective,
        solver=request.solver,
        status=status,
        proven_optimal=status == "optimal",
        message=messages[status],
        wall_time_s=time.perf_counter() - started,
        time_limit_s=request.time_limit_s,
        lower_bound=compute_stats(instance).lower_bound,
        time_unit=float(data.unit),
        big_m=float(data.unit * data.horizon),
    )
    if starts is None:
        return result
    validate_schedule(data, instance, starts)
    result.operations = [
        ScheduledOperation(
            job=i,
            operation=j,
            machine=op.machine,
            job_label=instance.job_labels[i],
            machine_label=instance.machine_labels[op.machine],
            duration=float(op.duration),
            start=float(starts[i, j] * data.unit),
            end=float((starts[i, j] + data.durations[i, j]) * data.unit),
        )
        for i, job in enumerate(instance.jobs)
        for j, op in enumerate(job)
    ]
    result.jobs = [
        JobCompletion(
            job=i,
            label=instance.job_labels[i],
            completion=float((starts[i, len(job) - 1] + data.durations[i, len(job) - 1]) * data.unit),
        )
        for i, job in enumerate(instance.jobs)
    ]
    idle_ticks = 0
    for k, keys in enumerate(data.machines):
        workload = sum(data.durations[key] for key in keys)
        completion = max((starts[key] + data.durations[key] for key in keys), default=0)
        idle_ticks += completion - workload
        result.machines.append(
            MachineSchedule(
                machine=k,
                label=instance.machine_labels[k],
                workload=float(workload * data.unit),
                completion=float(completion * data.unit),
                idle_time=float((completion - workload) * data.unit),
                sequence=sorted(
                    (op for op in result.operations if op.machine == k), key=lambda op: (op.start, op.job)
                ),
            )
        )
    result.makespan = max(job.completion for job in result.jobs)
    result.total_idle_time = float(idle_ticks * data.unit)
    result.objective_value = result.makespan if request.objective == "makespan" else result.total_idle_time
    result.best_bound = (
        result.objective_value
        if result.proven_optimal
        else (min(result.objective_value, max(0, float(bound * data.unit))) if bound is not None else None)
    )
    if result.best_bound is not None:
        result.relative_gap = (result.objective_value - result.best_bound) / max(
            abs(result.objective_value), 1e-12
        )
    return result

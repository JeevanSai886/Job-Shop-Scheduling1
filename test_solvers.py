from itertools import permutations, product

import pytest

from backend.models import SolveRequest
from backend.parser import parse_jssp_instance
from backend.solvers import solve
from backend.stats import compute_stats
from backend.store import DATA_DIR


def assert_feasible(instance, result):
    """Assertions against returned operations, independent of solver variables and validator."""
    assert result.status in ("optimal", "feasible")
    assert len(result.operations) == sum(map(len, instance.jobs))
    indexed = {(op.job, op.operation): op for op in result.operations}
    assert len(indexed) == len(result.operations)
    for i, job in enumerate(instance.jobs):
        for j, operation in enumerate(job):
            scheduled = indexed[i, j]
            assert scheduled.machine == operation.machine
            assert scheduled.start >= 0
            assert scheduled.end - scheduled.start == pytest.approx(float(operation.duration))
            if j:
                assert scheduled.start + 1e-8 >= indexed[i, j - 1].end
    for machine in range(instance.num_machines):
        operations = sorted(
            (op for op in result.operations if op.machine == machine), key=lambda op: op.start
        )
        for left, right in zip(operations, operations[1:]):
            assert left.end <= right.start + 1e-8
        reported = result.machines[machine]
        assert reported.completion == max((op.end for op in operations), default=0)
        assert reported.workload == pytest.approx(sum(op.duration for op in operations))
        assert reported.idle_time == pytest.approx(reported.completion - reported.workload)
        assert reported.sequence == operations
    assert result.makespan == max(op.end for op in result.operations)
    assert result.makespan + 1e-8 >= compute_stats(instance).lower_bound
    assert result.total_idle_time == pytest.approx(sum(machine.idle_time for machine in result.machines))
    assert result.proven_optimal == (result.status == "optimal")
    assert result.objective_value == (
        result.makespan if result.objective == "makespan" else result.total_idle_time
    )


def brute_force_optimum(instance, objective):
    """Enumerate machine orders and earliest DAG starts on a tiny fixture; no optimizer dependency."""
    nodes = {(i, j): op for i, job in enumerate(instance.jobs) for j, op in enumerate(job)}
    machine_nodes = [
        [key for key, op in nodes.items() if op.machine == k] for k in range(instance.num_machines)
    ]
    optima = []
    for orders in product(*(permutations(keys) for keys in machine_nodes)):
        predecessors = {key: {(key[0], key[1] - 1)} if key[1] else set() for key in nodes}
        for order in orders:
            for a, b in zip(order, order[1:]):
                predecessors[b].add(a)
        ends = {}
        while len(ends) < len(nodes):
            ready = [key for key in nodes if key not in ends and predecessors[key] <= ends.keys()]
            if not ready:
                break
            for key in ready:
                ends[key] = max((ends[p] for p in predecessors[key]), default=0) + nodes[key].duration
        if len(ends) == len(nodes):
            value = (
                max(ends.values())
                if objective == "makespan"
                else sum(
                    max((ends[key] for key in keys), default=0) - sum(nodes[key].duration for key in keys)
                    for keys in machine_nodes
                )
            )
            optima.append(value)
    return float(min(optima))


@pytest.mark.parametrize("engine", ["cp_sat", "pulp_bigm"])
@pytest.mark.parametrize("objective", ["makespan", "idle_time"])
def test_both_models_against_exhaustive_machine_orders(engine, objective):
    instance = parse_jssp_instance("2 2\n0 1.25 1 3.5\n1 2.75 0 1.5")
    result = solve(instance, SolveRequest(solver=engine, objective=objective, time_limit_s=10))
    assert_feasible(instance, result)
    assert result.proven_optimal
    assert result.objective_value == pytest.approx(brute_force_optimum(instance, objective))
    assert result.big_m == sum(float(op.duration) for job in instance.jobs for op in job)


@pytest.mark.parametrize("engine", ["cp_sat", "pulp_bigm"])
def test_ft06_feasibility(engine):
    instance = parse_jssp_instance((DATA_DIR / "ft06.txt").read_text())
    result = solve(instance, SolveRequest(solver=engine, time_limit_s=10))
    assert_feasible(instance, result)


@pytest.mark.parametrize("engine", ["cp_sat", "pulp_bigm"])
def test_unused_machine_and_repeated_machine_route(engine):
    instance = parse_jssp_instance("1 2\n0 2 0 3")
    result = solve(instance, SolveRequest(solver=engine, objective="idle_time", time_limit_s=5))
    assert_feasible(instance, result)
    assert result.total_idle_time == 0
    assert result.machines[1].completion == 0


def test_no_incumbent_is_never_an_optimal_schedule():
    instance = parse_jssp_instance((DATA_DIR / "ft10.txt").read_text())
    result = solve(instance, SolveRequest(time_limit_s=1e-9))
    assert not result.proven_optimal
    assert result.status == "no_solution"
    assert result.operations == []
    assert result.makespan is None


def test_cbc_time_limit_is_not_mislabeled_optimal():
    instance = parse_jssp_instance((DATA_DIR / "ft10.txt").read_text())
    result = solve(instance, SolveRequest(solver="pulp_bigm", time_limit_s=0.01))
    assert not result.proven_optimal
    assert result.status in ("feasible", "no_solution")
    if result.operations:
        assert_feasible(instance, result)

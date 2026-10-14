from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Objective = Literal["makespan", "idle_time"]
Engine = Literal["cp_sat", "pulp_bigm"]
Status = Literal["optimal", "feasible", "no_solution", "infeasible", "model_invalid"]


@dataclass(frozen=True)
class Operation:
    machine: int
    duration: Fraction


@dataclass(frozen=True)
class JobShopInstance:
    name: str
    jobs: tuple[tuple[Operation, ...], ...]
    job_labels: tuple[str, ...]
    machine_labels: tuple[str, ...]

    @property
    def num_jobs(self) -> int:
        return len(self.jobs)

    @property
    def num_machines(self) -> int:
        return len(self.machine_labels)


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class InstanceRequest(RequestModel):
    benchmark: str | None = None
    text: str | None = Field(default=None, max_length=2_000_000)
    name: str = Field(default="Custom instance", min_length=1, max_length=120)

    @model_validator(mode="after")
    def one_source(self) -> "InstanceRequest":
        if (self.benchmark is None) == (self.text is None):
            raise ValueError("Provide exactly one of benchmark or text.")
        return self


class SolveRequest(RequestModel):
    objective: Objective = "makespan"
    solver: Engine = "cp_sat"
    time_limit_s: float = Field(default=30, gt=0, le=300)


class SensitivityRequest(SolveRequest):
    deltas: list[Annotated[Decimal, Field(gt=-100, allow_inf_nan=False)]] = Field(min_length=1, max_length=20)


class InstanceSummary(BaseModel):
    instance_id: str
    name: str
    num_jobs: int
    num_machines: int
    total_operations: int
    job_labels: list[str]
    machine_labels: list[str]


class Distribution(BaseModel):
    count: int
    min: float | None
    max: float | None
    mean: float | None
    std: float | None


class MachineStats(BaseModel):
    machine: int
    label: str
    workload: float
    processing_times: Distribution


class JobStats(BaseModel):
    job: int
    label: str
    operation_count: int
    workload: float


class InstanceStats(BaseModel):
    num_jobs: int
    num_machines: int
    total_operations: int
    total_processing_time: float
    lower_bound: float
    processing_times: Distribution
    jobs: list[JobStats]
    machines: list[MachineStats]


class ScheduledOperation(BaseModel):
    job: int
    operation: int
    machine: int
    job_label: str
    machine_label: str
    duration: float
    start: float
    end: float


class JobCompletion(BaseModel):
    job: int
    label: str
    completion: float


class MachineSchedule(BaseModel):
    machine: int
    label: str
    workload: float
    completion: float
    idle_time: float
    sequence: list[ScheduledOperation]


class SolveResult(BaseModel):
    objective: Objective
    solver: Engine
    status: Status
    proven_optimal: bool
    message: str
    wall_time_s: float
    time_limit_s: float
    objective_value: float | None = None
    best_bound: float | None = None
    relative_gap: float | None = None
    makespan: float | None = None
    total_idle_time: float | None = None
    lower_bound: float
    time_unit: float
    big_m: float
    operations: list[ScheduledOperation] = Field(default_factory=list)
    jobs: list[JobCompletion] = Field(default_factory=list)
    machines: list[MachineSchedule] = Field(default_factory=list)


class Scenario(BaseModel):
    delta: float
    objective_change_pct: float | None
    makespan_change_pct: float | None
    result: SolveResult


class SensitivityResult(BaseModel):
    objective: Objective
    solver: Engine
    baseline: SolveResult
    scenarios: list[Scenario]
    note: str

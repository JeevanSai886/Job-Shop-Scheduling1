"""Strict, data-driven OR-Library and operation-table CSV parsing."""

import csv
import io
import re
from decimal import Decimal, InvalidOperation
from fractions import Fraction

from backend.models import JobShopInstance, Operation


class InstanceParseError(ValueError):
    pass


def duration(value: str, context: str) -> Fraction:
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise InstanceParseError(f"{context}: processing time must be numeric.") from exc
    if not number.is_finite() or number <= 0:
        raise InstanceParseError(f"{context}: processing time must be finite and strictly positive.")
    if len(number.as_tuple().digits) > 30 or abs(number.as_tuple().exponent) > 12:
        raise InstanceParseError(f"{context}: processing time exceeds supported numeric precision.")
    return Fraction(number)


def _integer(value: str, context: str) -> int:
    if not re.fullmatch(r"[+-]?\d+", value):
        raise InstanceParseError(f"{context}: expected an integer, got {value!r}.")
    return int(value)


def _operation_index(value: str, context: str) -> int:
    """Accept numeric sequence positions and conventional O/Op/Operation labels."""
    match = re.fullmatch(r"(?:(?:operation|op|o)[\s_]*)?([+-]?\d+)", value, flags=re.I)
    if match is None:
        raise InstanceParseError(
            f"{context}: expected an operation number or label such as 1, O1, or Op1; got {value!r}."
        )
    return int(match.group(1))


def _or_library(raw: str, name: str) -> JobShopInstance:
    lines = [line.split("#", 1)[0].strip() for line in raw.splitlines()]
    lines = [line for line in lines if line]
    # Accept the original single-instance OR-Library wrapper as well as numeric-only files.
    markers = [i for i, line in enumerate(lines) if re.fullmatch(r"instance\s+\S+", line, re.I)]
    if len(markers) > 1:
        raise InstanceParseError(
            "This file contains multiple instances. Upload one instance block at a time."
        )
    if markers:
        lines = lines[markers[0] + 1 :]
        header = next((i for i, line in enumerate(lines) if re.fullmatch(r"\d+\s+\d+", line)), None)
        if header is None:
            raise InstanceParseError("Missing job/machine dimensions after the instance heading.")
        lines = [line for line in lines[header:] if not re.fullmatch(r"\++", line)]
    if not lines or len(lines[0].split()) != 2:
        raise InstanceParseError("First line must contain: <number of jobs> <number of machines>.")
    num_jobs, num_machines = [_integer(x, "Dimensions") for x in lines[0].split()]
    if num_jobs <= 0 or num_machines <= 0:
        raise InstanceParseError("Job and machine counts must be positive.")
    if len(lines) - 1 != num_jobs:
        raise InstanceParseError(f"Expected {num_jobs} job rows; found {len(lines) - 1}.")
    jobs = []
    for i, line in enumerate(lines[1:]):
        tokens = line.split()
        if len(tokens) != num_machines * 2:
            raise InstanceParseError(f"Job row {i + 1}: expected {num_machines} machine/time pairs.")
        operations = []
        for j in range(0, len(tokens), 2):
            context = f"Job row {i + 1}, operation {j // 2 + 1}"
            machine = _integer(tokens[j], context)
            if not 0 <= machine < num_machines:
                raise InstanceParseError(f"{context}: machine index must be in 0..{num_machines - 1}.")
            operations.append(Operation(machine, duration(tokens[j + 1], context)))
        jobs.append(tuple(operations))
    return JobShopInstance(
        name,
        tuple(jobs),
        tuple(f"J{i + 1}" for i in range(num_jobs)),
        tuple(f"M{i + 1}" for i in range(num_machines)),
    )


def _csv(raw: str, name: str) -> JobShopInstance:
    reader = csv.DictReader(io.StringIO(raw))
    required = {"job", "operation", "machine", "processingtime"}
    if reader.fieldnames is None:
        raise InstanceParseError("Missing CSV header.")
    reader.fieldnames = [re.sub(r"[\s_-]+", "", field).casefold() for field in reader.fieldnames]
    if set(reader.fieldnames) != required or len(reader.fieldnames) != len(required):
        raise InstanceParseError(
            "CSV columns must be Job, Operation, Machine, Processing Time "
            "(spaces, underscores, and hyphens in column names are accepted)."
        )
    grouped: dict[str, dict[int, tuple[str, Fraction]]] = {}
    machine_labels: list[str] = []
    for line, row in enumerate(reader, start=2):
        if None in row or any(value is None or not value.strip() for value in row.values()):
            raise InstanceParseError(f"CSV row {line}: missing value or incorrect column count.")
        job, machine = row["job"].strip(), row["machine"].strip()
        op = _operation_index(row["operation"].strip(), f"CSV row {line}, Operation")
        if op < 0:
            raise InstanceParseError(f"CSV row {line}: Operation cannot be negative.")
        entries = grouped.setdefault(job, {})
        if op in entries:
            raise InstanceParseError(f"CSV row {line}: duplicate operation {op} in job {job}.")
        entries[op] = (machine, duration(row["processingtime"].strip(), f"CSV row {line}"))
        if machine not in machine_labels:
            machine_labels.append(machine)
    if not grouped:
        raise InstanceParseError("CSV contains no operation rows.")
    machines = {label: i for i, label in enumerate(machine_labels)}
    jobs = []
    for label, entries in grouped.items():
        order = sorted(entries)
        if order[0] not in (0, 1) or order != list(range(order[0], order[0] + len(order))):
            raise InstanceParseError(
                f"Job {label}: operation numbers must be consecutive, starting at 0 or 1."
            )
        jobs.append(tuple(Operation(machines[entries[i][0]], entries[i][1]) for i in order))
    return JobShopInstance(name, tuple(jobs), tuple(grouped), tuple(machine_labels))


def parse_jssp_instance(raw_text_or_csv: str, name: str = "Custom instance") -> JobShopInstance:
    raw = raw_text_or_csv.lstrip("\ufeff").strip()
    if not raw:
        raise InstanceParseError("The instance file is empty.")
    if len(raw.encode("utf-8")) > 2_000_000:
        raise InstanceParseError("Instance files must be no larger than 2 MB.")
    try:
        return _csv(raw, name) if "," in raw.splitlines()[0] else _or_library(raw, name)
    except csv.Error as exc:
        raise InstanceParseError(f"Malformed CSV: {exc}") from exc

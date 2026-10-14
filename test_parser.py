from fractions import Fraction

import pytest

from backend.parser import InstanceParseError, parse_jssp_instance
from backend.stats import compute_stats
from backend.store import DATA_DIR


@pytest.mark.parametrize("name,dimensions", [("ft06", (6, 6)), ("ft10", (10, 10))])
def test_original_benchmarks(name, dimensions):
    raw = (DATA_DIR / f"{name}.txt").read_text()
    instance = parse_jssp_instance(raw, name)
    assert (instance.num_jobs, instance.num_machines) == dimensions
    rows = [line.split() for line in raw.splitlines() if line.strip()]
    for job, row in zip(instance.jobs, rows[1:], strict=True):
        assert len(job) == instance.num_machines
        assert [(op.machine, op.duration) for op in job] == [
            (int(row[i]), Fraction(row[i + 1])) for i in range(0, len(row), 2)
        ]
    stats = compute_stats(instance)
    assert stats.total_operations == sum(len(job) for job in instance.jobs)
    assert stats.total_processing_time == sum(machine.workload for machine in stats.machines)
    assert stats.lower_bound == max(
        *(job.workload for job in stats.jobs), *(m.workload for m in stats.machines)
    )


def test_variable_length_csv_and_out_of_order_operations():
    instance = parse_jssp_instance(
        "Job,Operation,Machine,ProcessingTime\nA,2,lathe,1.25\nB,1,drill,2\nA,1,drill,3.5"
    )
    assert instance.num_jobs == 2
    assert instance.num_machines == 2
    assert [len(job) for job in instance.jobs] == [2, 1]
    assert instance.jobs[0][0].duration == Fraction("3.5")
    assert instance.machine_labels[instance.jobs[0][0].machine] == "drill"
    assert instance.job_labels == ("A", "B")


@pytest.mark.parametrize(
    "header", ["ProcessingTime", "Processing Time", "processing_time", "PROCESSING-TIME"]
)
@pytest.mark.parametrize("prefix", ["O", "Op", "Operation ", "op_"])
def test_structured_csv_headers_and_numeric_operation_order(header, prefix):
    # Generate the user's structured CSV format from raw data, with deliberately reversed row order.
    reference = parse_jssp_instance((DATA_DIR / "ft10.txt").read_text())
    rows = [f"Job,Operation,Machine,{header}"]
    for i, job in enumerate(reference.jobs):
        for j in reversed(range(len(job))):
            operation = job[j]
            rows.append(f"J{i + 1},{prefix}{j + 1},M{operation.machine + 1},{operation.duration}")
    parsed = parse_jssp_instance("\n".join(rows))
    assert parsed.num_jobs == reference.num_jobs
    assert parsed.num_machines == reference.num_machines
    for parsed_job, reference_job in zip(parsed.jobs, reference.jobs, strict=True):
        assert [(parsed.machine_labels[op.machine], op.duration) for op in parsed_job] == [
            (reference.machine_labels[op.machine], op.duration) for op in reference_job
        ]


@pytest.mark.parametrize(
    "labels,match",
    [
        (["O1", "1"], "duplicate"),
        (["O1", "O3"], "consecutive"),
        (["O-1"], "negative"),
        (["O1.5"], "operation number or label"),
        (["task1"], "operation number or label"),
    ],
)
def test_structured_csv_rejects_invalid_operation_labels(labels, match):
    raw = "Job,Operation,Machine,Processing Time\n" + "\n".join(f"J1,{label},M1,2" for label in labels)
    with pytest.raises(InstanceParseError, match=match):
        parse_jssp_instance(raw)


def test_duplicate_normalized_csv_headers_are_rejected():
    raw = "Job,Operation,Machine,Processing Time,Processing_Time\nJ1,O1,M1,2,3"
    with pytest.raises(InstanceParseError, match="columns"):
        parse_jssp_instance(raw)


@pytest.mark.parametrize(
    "raw,match",
    [
        ("", "empty"),
        ("0 2", "positive"),
        ("2 2\n0 1 1 2", "job rows"),
        ("1 2\n0 3", "pairs"),
        ("1 1\n1 3", "machine index"),
        ("1 1\n-1 3", "machine index"),
        ("1 1\n0 -3", "positive"),
        ("1 1\n0 0", "positive"),
        ("1 1\n0 NaN", "finite"),
        ("1 1\n0 Infinity", "finite"),
        ("1 1\n0 abc", "numeric"),
        ("1 1\n0.5 2", "integer"),
        ("Job,Operation,Machine,Time\nA,1,M,2", "columns"),
        ("Job,Operation,Machine,ProcessingTime\nA,1,M,2\nA,1,M,3", "duplicate"),
        ("Job,Operation,Machine,ProcessingTime\nA,1,M,2\nA,3,M,3", "consecutive"),
        ("Job,Operation,Machine,ProcessingTime\nA,1,M,", "missing"),
        ("Job,Operation,Machine,ProcessingTime", "no operation"),
    ],
)
def test_malformed_input(raw, match):
    with pytest.raises(InstanceParseError, match=match):
        parse_jssp_instance(raw)


def test_comments_bom_and_original_wrapper():
    instance = parse_jssp_instance(
        "\ufeff# comment\ninstance custom\n+++++\nCustom benchmark\n1 1\n0 2.5 # time\n++++"
    )
    assert instance.jobs[0][0].duration == Fraction("2.5")


def test_unused_machine_statistics():
    instance = parse_jssp_instance("1 2\n0 2 0 3")
    assert compute_stats(instance).machines[1].processing_times.mean is None

from statistics import fmean, pstdev

from backend.models import Distribution, InstanceStats, JobShopInstance, JobStats, MachineStats


def distribution(values: list[float]) -> Distribution:
    if not values:
        return Distribution(count=0, min=None, max=None, mean=None, std=None)
    return Distribution(
        count=len(values), min=min(values), max=max(values), mean=fmean(values), std=pstdev(values)
    )


def compute_stats(instance: JobShopInstance) -> InstanceStats:
    per_machine: list[list[float]] = [[] for _ in instance.machine_labels]
    jobs = []
    overall = []
    for i, job in enumerate(instance.jobs):
        times = [float(op.duration) for op in job]
        jobs.append(
            JobStats(job=i, label=instance.job_labels[i], operation_count=len(job), workload=sum(times))
        )
        overall.extend(times)
        for op in job:
            per_machine[op.machine].append(float(op.duration))
    machines = [
        MachineStats(
            machine=k,
            label=instance.machine_labels[k],
            workload=sum(times),
            processing_times=distribution(times),
        )
        for k, times in enumerate(per_machine)
    ]
    return InstanceStats(
        num_jobs=instance.num_jobs,
        num_machines=instance.num_machines,
        total_operations=len(overall),
        total_processing_time=sum(overall),
        lower_bound=max([j.workload for j in jobs] + [m.workload for m in machines]),
        processing_times=distribution(overall),
        jobs=jobs,
        machines=machines,
    )

import threading
from collections.abc import Callable
from typing import Any, TypeVar

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from backend.models import (
    InstanceRequest,
    InstanceStats,
    InstanceSummary,
    JobShopInstance,
    SensitivityRequest,
    SensitivityResult,
    SolveRequest,
    SolveResult,
)
from backend.parser import InstanceParseError
from backend.sensitivity import analyze_sensitivity
from backend.solvers import solve
from backend.stats import compute_stats
from backend.store import DATA_DIR, get_instance, save_instance

app = FastAPI(title="Sequence · Job-shop scheduling", version="1.0.0")
solver_slot = threading.BoundedSemaphore(1)


@app.exception_handler(InstanceParseError)
async def parse_error(_request: Request, exc: InstanceParseError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [f"{'.'.join(map(str, error['loc']))}: {error['msg']}" for error in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": "; ".join(details)})


def find_instance(instance_id: str) -> JobShopInstance:
    try:
        return get_instance(instance_id)
    except KeyError as exc:
        raise HTTPException(404, "Instance not found. Select or upload it again.") from exc


def summary(instance_id: str, instance: JobShopInstance) -> InstanceSummary:
    return InstanceSummary(
        instance_id=instance_id,
        name=instance.name,
        num_jobs=instance.num_jobs,
        num_machines=instance.num_machines,
        total_operations=sum(map(len, instance.jobs)),
        job_labels=list(instance.job_labels),
        machine_labels=list(instance.machine_labels),
    )


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/benchmarks", response_model=list[InstanceSummary])
def benchmarks() -> list[InstanceSummary]:
    return [
        summary(*save_instance(path.read_text(encoding="utf-8"), path.stem))
        for path in sorted(DATA_DIR.glob("*.txt"))
    ]


@app.post("/api/instance", response_model=InstanceSummary, status_code=201)
async def create_instance(request: Request) -> InstanceSummary:
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        async with request.form(max_files=1, max_fields=2, max_part_size=2_000_000) as form:
            upload = form.get("file")
            if not isinstance(upload, UploadFile):
                raise HTTPException(422, "Upload a text or CSV file using the 'file' field.")
            contents = await upload.read(2_000_001)
            if len(contents) > 2_000_000:
                raise HTTPException(413, "File exceeds the 2 MB upload limit.")
            try:
                raw = contents.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise HTTPException(422, "Use a UTF-8 encoded text or CSV file.") from exc
            name = (upload.filename or "Custom instance").replace("\\", "/").split("/")[-1][:120]
    else:
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 2_100_000:
                raise HTTPException(413, "Request exceeds the upload limit.")
        try:
            payload = InstanceRequest.model_validate_json(body)
        except ValidationError as exc:
            raise HTTPException(422, "; ".join(error["msg"] for error in exc.errors())) from exc
        if payload.benchmark is not None:
            available = {path.stem: path for path in DATA_DIR.glob("*.txt")}
            path = available.get(payload.benchmark)
            if path is None:
                raise HTTPException(404, "Unknown benchmark. Choose a listed benchmark or upload a file.")
            raw, name = path.read_text(encoding="utf-8"), path.stem
        else:
            raw, name = payload.text or "", payload.name
    return summary(*await run_in_threadpool(save_instance, raw, name))


@app.get("/api/instance/{instance_id}/stats", response_model=InstanceStats)
def instance_stats(instance_id: str) -> InstanceStats:
    return compute_stats(find_instance(instance_id))


RequestType = TypeVar("RequestType", bound=SolveRequest)
ResultType = TypeVar("ResultType", SolveResult, SensitivityResult)


def run_solver_task(
    function: Callable[[JobShopInstance, RequestType], ResultType],
    instance_id: str,
    settings: RequestType,
) -> ResultType:
    instance = find_instance(instance_id)
    if not solver_slot.acquire(blocking=False):
        raise HTTPException(503, "Another optimization is running. Please try again when it completes.")
    try:
        return function(instance, settings)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    finally:
        solver_slot.release()


@app.post("/api/instance/{instance_id}/solve", response_model=SolveResult)
def solve_instance(instance_id: str, settings: SolveRequest) -> SolveResult:
    return run_solver_task(solve, instance_id, settings)


@app.post("/api/instance/{instance_id}/sensitivity", response_model=SensitivityResult)
def sensitivity(instance_id: str, settings: SensitivityRequest) -> SensitivityResult:
    return run_solver_task(analyze_sensitivity, instance_id, settings)


# Publish the manually dispatched upload formats in the generated API documentation.
original_openapi = app.openapi


def openapi() -> dict[str, Any]:
    schema = original_openapi()
    schema["paths"]["/api/instance"]["post"]["requestBody"] = {
        "required": True,
        "content": {
            "application/json": {"schema": InstanceRequest.model_json_schema()},
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["file"],
                    "properties": {"file": {"type": "string", "format": "binary"}},
                }
            },
        },
    }
    return schema


app.openapi = openapi

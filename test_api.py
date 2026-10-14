from decimal import Decimal

import pytest

from backend.models import SensitivityRequest
from backend.parser import parse_jssp_instance
from backend.sensitivity import analyze_sensitivity, percent_change

# Published Fisher & Thompson ft06 optimum, used ONLY as a regression reference in this test.
# OR-Library: https://people.brunel.ac.uk/~mastjjb/jeb/orlib/files/jobshop1.txt
FT06_REFERENCE_OPTIMUM = 55


def test_ft06_integration(client):
    uploaded = client.post("/api/instance", json={"benchmark": "ft06"})
    assert uploaded.status_code == 201
    instance_id = uploaded.json()["instance_id"]
    stats = client.get(f"/api/instance/{instance_id}/stats").json()
    response = client.post(f"/api/instance/{instance_id}/solve", json={"time_limit_s": 15})
    assert response.status_code == 200
    result = response.json()
    assert result["proven_optimal"]
    assert result["makespan"] >= stats["lower_bound"]
    assert result["makespan"] == FT06_REFERENCE_OPTIMUM


@pytest.mark.parametrize("engine", ["cp_sat", "pulp_bigm"])
@pytest.mark.parametrize("objective", ["makespan", "idle_time"])
def test_uploaded_csv_sensitivity(client, engine, objective):
    raw = "Job,Operation,Machine,Processing Time\nalpha,O1,press,2.5\nbeta,O1,press,1.25\nbeta,O2,lathe,3"
    response = client.post("/api/instance", files={"file": ("demo.csv", raw.encode(), "text/csv")})
    assert response.status_code == 201
    instance_id = response.json()["instance_id"]
    response = client.post(
        f"/api/instance/{instance_id}/sensitivity",
        json={
            "solver": engine,
            "objective": objective,
            "time_limit_s": 5,
            "deltas": [-12.5, 7.125],
        },
    )
    assert response.status_code == 200
    output = response.json()
    assert output["baseline"]["proven_optimal"]
    for scenario in output["scenarios"]:
        assert scenario["result"]["proven_optimal"]
        factor = 1 + scenario["delta"] / 100
        assert scenario["result"]["objective_value"] == pytest.approx(
            output["baseline"]["objective_value"] * factor
        )
        for baseline_op, modified_op in zip(
            output["baseline"]["operations"], scenario["result"]["operations"]
        ):
            assert modified_op["duration"] == pytest.approx(baseline_op["duration"] * factor)


def test_sensitivity_calls_solver_for_each_scenario(monkeypatch):
    from backend import sensitivity

    original = sensitivity.solve
    calls = []

    def counted(instance, settings):
        calls.append(instance)
        return original(instance, settings)

    monkeypatch.setattr(sensitivity, "solve", counted)
    instance = parse_jssp_instance("1 1\n0 3")
    analyze_sensitivity(
        instance, SensitivityRequest(deltas=[Decimal("0"), Decimal("1.2345")], time_limit_s=5)
    )
    assert len(calls) == 3  # baseline and both requested scenarios, with no lookup reuse
    assert calls[0] == instance
    assert percent_change(0, 0) is None


def test_errors_and_persistence(client):
    raw = "1 1\n0 3"
    first = client.post("/api/instance", json={"text": raw}).json()
    second = client.post("/api/instance", json={"text": raw}).json()
    assert first == second
    assert client.get(f"/api/instance/{first['instance_id']}/stats").status_code == 200
    assert client.post("/api/instance", json={"text": "1 1\n0 -2"}).status_code == 422
    assert client.post("/api/instance", json={"text": raw, "benchmark": "ft06"}).status_code == 422
    assert client.post("/api/instance", json={"benchmark": "../secrets"}).status_code == 404
    assert client.get("/api/instance/missing/stats").status_code == 404
    assert (
        client.post(f"/api/instance/{first['instance_id']}/solve", json={"time_limit_s": 0}).status_code
        == 422
    )
    assert (
        client.post(f"/api/instance/{first['instance_id']}/sensitivity", json={"deltas": [-100]}).status_code
        == 422
    )
    assert (
        client.post(f"/api/instance/{first['instance_id']}/sensitivity", json={"deltas": []}).status_code
        == 422
    )
    assert client.post("/api/instance", files={"file": ("bad.txt", b"\xff")}).status_code == 422
    assert client.get("/openapi.json").status_code == 200


def test_busy_solver_returns_clear_error(client):
    from backend.main import solver_slot

    instance_id = client.post("/api/instance", json={"text": "1 1\n0 1"}).json()["instance_id"]
    with solver_slot:
        assert client.get("/api/health").status_code == 200
        response = client.post(f"/api/instance/{instance_id}/solve", json={})
        assert response.status_code == 503
        assert "Another optimization" in response.json()["detail"]

# -*- coding: utf-8 -*-

from collections.abc import AsyncGenerator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.routers import scenario as scenario_router
from app.core.exception_handlers import register_exception_handlers
from app.core.exceptions import CustomException
from app.core.security import check_admin_existence
from app.db.session import get_db_session
from app.models.admin import Admin
from app.models.api_request import ApiRequest, TestScenario as ScenarioModel, TestScenarioCase as ScenarioCaseModel


class FakeDBSession:
    def __init__(self):
        self.added: list[Any] = []
        self.commits = 0
        self.flushes = 0
        self.refreshed: list[Any] = []

    def add(self, obj: Any):
        if getattr(obj, "id", None) is None:
            obj.id = 100 + len(self.added)
        self.added.append(obj)

    async def flush(self):
        self.flushes += 1

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj: Any):
        self.refreshed.append(obj)


def _build_admin() -> Admin:
    admin = Admin(username="tester", password="hashed")
    admin.id = 1
    return admin


def _build_api_request(**kwargs) -> ApiRequest:
    obj = ApiRequest(
        env_id=None,
        name="case-demo",
        method="GET",
        url="https://example.com/api",
        creator="tester",
        creator_id=1,
        base_query_params={},
        base_headers={},
        base_cookies={},
        body_type="none",
        base_body_data={},
        base_body_raw=None,
        timeout_ms=30000,
        follow_redirects=True,
        verify_ssl=True,
        proxy_url=None,
        sort=0,
        execute_count=0,
        case_status="开发中",
        is_copied_case=False,
        is_public_visible=False,
        creator_only_execute=False,
        data_driven_enabled=True,
        dataset_run_mode="all",
        default_dataset_id=None,
        is_deleted=0,
    )
    obj.id = kwargs.pop("id", 101)
    for k, v in kwargs.items():
        setattr(obj, k, v)
    return obj


def _build_scenario(**kwargs) -> ScenarioModel:
    obj = ScenarioModel(
        env_id=None,
        name="scenario-demo",
        description=None,
        run_mode="sequence",
        stop_on_fail=True,
        sort=0,
        is_deleted=0,
    )
    obj.id = kwargs.pop("id", 11)
    for k, v in kwargs.items():
        setattr(obj, k, v)
    return obj


def _build_scenario_case(**kwargs) -> ScenarioCaseModel:
    obj = ScenarioCaseModel(
        scenario_id=kwargs.pop("scenario_id", 11),
        request_id=kwargs.pop("request_id", 101),
        step_no=kwargs.pop("step_no", 1),
        dataset_id=kwargs.pop("dataset_id", None),
        dataset_run_mode=kwargs.pop("dataset_run_mode", "request_default"),
        is_enabled=kwargs.pop("is_enabled", True),
        stop_on_fail=kwargs.pop("stop_on_fail", True),
        is_deleted=kwargs.pop("is_deleted", 0),
    )
    obj.id = kwargs.pop("id", 21)
    for k, v in kwargs.items():
        setattr(obj, k, v)
    return obj


@pytest.fixture
def fake_db():
    return FakeDBSession()


@pytest.fixture
def client(fake_db):
    app = FastAPI()
    register_exception_handlers(app, debug=True)
    app.include_router(scenario_router.router, prefix="/api/scenario")

    admin = _build_admin()

    async def _override_admin():
        return admin

    async def _override_db() -> AsyncGenerator[FakeDBSession, None]:
        yield fake_db

    app.dependency_overrides[check_admin_existence] = _override_admin
    app.dependency_overrides[get_db_session] = _override_db

    with TestClient(app) as c:
        yield c


def test_create_test_scenario_success(client: TestClient, fake_db: FakeDBSession):
    resp = client.post("/api/scenario", json={"name": "scenario-create"})
    body = resp.json()

    assert resp.status_code == 201
    assert body["code"] == 201
    assert body["data"]["id"] >= 100
    assert len(fake_db.added) == 1
    assert fake_db.added[0].name == "scenario-create"


def test_update_test_scenario_success(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    obj = _build_scenario(id=12, name="old-name")

    async def _fake_get_scenario(db, scenario_id: int):
        assert scenario_id == 12
        return obj

    monkeypatch.setattr(scenario_router, "_get_scenario_or_404", _fake_get_scenario)

    payload = {"id": 12, "name": "new-name", "run_mode": "parallel", "stop_on_fail": False}
    resp = client.put("/api/scenario", json=payload)
    body = resp.json()

    assert resp.status_code == 201
    assert body["code"] == 201
    assert obj.name == "new-name"
    assert obj.run_mode == "parallel"
    assert obj.stop_on_fail is False


def test_test_scenario_detail_success(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    obj = _build_scenario(id=13, name="scenario-detail")

    async def _fake_get_scenario(db, scenario_id: int):
        assert scenario_id == 13
        return obj

    monkeypatch.setattr(scenario_router, "_get_scenario_or_404", _fake_get_scenario)

    resp = client.get("/api/scenario/13")
    body = resp.json()

    assert resp.status_code == 200
    assert body["code"] == 200
    assert body["data"]["id"] == 13
    assert body["data"]["name"] == "scenario-detail"


def test_delete_test_scenario_soft_delete_with_steps(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
):
    scenario_obj = _build_scenario(id=14)
    step_1 = _build_scenario_case(id=31, scenario_id=14, step_no=1)
    step_2 = _build_scenario_case(id=32, scenario_id=14, step_no=2)

    async def _fake_get_scenario(db, scenario_id: int):
        assert scenario_id == 14
        return scenario_obj

    async def _fake_list_steps(db, scenario_id: int):
        assert scenario_id == 14
        return [step_1, step_2]

    monkeypatch.setattr(scenario_router, "_get_scenario_or_404", _fake_get_scenario)
    monkeypatch.setattr(scenario_router, "_list_active_scenario_steps", _fake_list_steps)

    resp = client.request("DELETE", "/api/scenario", json={"id": 14})
    body = resp.json()

    assert resp.status_code == 200
    assert body["code"] == 204
    assert scenario_obj.is_deleted == 1
    assert step_1.is_deleted == 1
    assert step_2.is_deleted == 1


def test_create_test_scenario_case_insert_step_success(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    fake_db: FakeDBSession,
):
    scenario_obj = _build_scenario(id=15)
    request_obj = _build_api_request(id=151)
    old_step = _build_scenario_case(id=41, scenario_id=15, step_no=1)

    async def _fake_get_scenario(db, scenario_id: int):
        assert scenario_id == 15
        return scenario_obj

    async def _fake_get_request(db, request_id: int):
        assert request_id == 151
        return request_obj

    async def _fake_normalize(db, scenario_id: int):
        assert scenario_id == 15
        return [old_step]

    monkeypatch.setattr(scenario_router, "_get_scenario_or_404", _fake_get_scenario)
    monkeypatch.setattr(scenario_router, "_get_api_request_or_404", _fake_get_request)
    monkeypatch.setattr(scenario_router, "_normalize_scenario_step_no", _fake_normalize)

    payload = {
        "scenario_id": 15,
        "request_id": 151,
        "step_no": 1,
        "dataset_run_mode": "request_default",
    }
    resp = client.post("/api/scenario/case", json=payload)
    body = resp.json()

    assert resp.status_code == 201
    assert body["code"] == 201
    assert old_step.step_no == 2
    assert len(fake_db.added) == 1
    new_obj = fake_db.added[0]
    assert new_obj.scenario_id == 15
    assert new_obj.request_id == 151
    assert new_obj.step_no == 1


def test_update_test_scenario_case_mismatch_returns_10005(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
):
    scenario_obj = _build_scenario(id=16)
    scenario_case_obj = _build_scenario_case(id=51, scenario_id=16, request_id=161)

    async def _fake_get_scenario_case(db, scenario_case_id: int):
        assert scenario_case_id == 51
        return scenario_case_obj

    async def _fake_get_scenario(db, scenario_id: int):
        assert scenario_id == 16
        return scenario_obj

    async def _fake_validate_dataset_relation(db, request_id: int, dataset_id: int):
        raise CustomException(detail="数据集与测试用例不匹配", custom_code=10005)

    monkeypatch.setattr(scenario_router, "_get_scenario_case_or_404", _fake_get_scenario_case)
    monkeypatch.setattr(scenario_router, "_get_scenario_or_404", _fake_get_scenario)
    monkeypatch.setattr(scenario_router, "_validate_dataset_relation", _fake_validate_dataset_relation)

    resp = client.put(
        "/api/scenario/case",
        json={"id": 51, "dataset_run_mode": "single", "dataset_id": 999},
    )
    body = resp.json()

    assert resp.status_code == 200
    assert body["code"] == 10005
    assert body["message"] == "数据集与测试用例不匹配"


def test_reorder_test_scenario_case_success(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    scenario_obj = _build_scenario(id=17)
    scenario_case_obj = _build_scenario_case(id=61, scenario_id=17, step_no=2)

    async def _fake_get_scenario(db, scenario_id: int):
        assert scenario_id == 17
        return scenario_obj

    async def _fake_get_scenario_case(db, scenario_case_id: int):
        assert scenario_case_id == 61
        return scenario_case_obj

    async def _fake_normalize(db, scenario_id: int):
        assert scenario_id == 17
        return []

    async def _fake_reorder(db, scenario_id: int, case_obj: ScenarioCaseModel, target: int):
        assert scenario_id == 17
        assert case_obj.id == 61
        assert target == 1
        case_obj.step_no = 1
        return 1

    monkeypatch.setattr(scenario_router, "_get_scenario_or_404", _fake_get_scenario)
    monkeypatch.setattr(scenario_router, "_get_scenario_case_or_404", _fake_get_scenario_case)
    monkeypatch.setattr(scenario_router, "_normalize_scenario_step_no", _fake_normalize)
    monkeypatch.setattr(scenario_router, "_reorder_scenario_step", _fake_reorder)

    resp = client.put("/api/scenario/case/reorder", json={"scenario_id": 17, "id": 61, "step_no": 1})
    body = resp.json()

    assert resp.status_code == 201
    assert body["code"] == 201
    assert body["data"]["id"] == 61
    assert body["data"]["step_no"] == 1


def test_set_test_scenario_case_dataset_strategy_success(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
):
    scenario_obj = _build_scenario(id=18)
    scenario_case_obj = _build_scenario_case(id=71, scenario_id=18, request_id=181)
    called = {"value": False}

    async def _fake_get_scenario_case(db, scenario_case_id: int):
        assert scenario_case_id == 71
        return scenario_case_obj

    async def _fake_get_scenario(db, scenario_id: int):
        assert scenario_id == 18
        return scenario_obj

    async def _fake_validate_dataset_relation(db, request_id: int, dataset_id: int):
        assert request_id == 181
        assert dataset_id == 801
        called["value"] = True

    monkeypatch.setattr(scenario_router, "_get_scenario_case_or_404", _fake_get_scenario_case)
    monkeypatch.setattr(scenario_router, "_get_scenario_or_404", _fake_get_scenario)
    monkeypatch.setattr(scenario_router, "_validate_dataset_relation", _fake_validate_dataset_relation)

    resp = client.put(
        "/api/scenario/case/dataset-strategy",
        json={"id": 71, "dataset_run_mode": "single", "dataset_id": 801},
    )
    body = resp.json()

    assert resp.status_code == 201
    assert body["code"] == 201
    assert called["value"] is True
    assert scenario_case_obj.dataset_run_mode == "single"
    assert scenario_case_obj.dataset_id == 801


def test_test_scenario_case_page_success(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    scenario_obj = _build_scenario(id=19)

    async def _fake_get_scenario(db, scenario_id: int):
        assert scenario_id == 19
        return scenario_obj

    class _DummyPaginateQuery:
        def __init__(self, *args, **kwargs):
            self.normal_data = {"records": [{"id": 81, "step_no": 1}], "now_page": 1, "total": 1}

        async def build_query(self):
            return

    monkeypatch.setattr(scenario_router, "_get_scenario_or_404", _fake_get_scenario)
    monkeypatch.setattr(scenario_router, "CommonPaginateQuery", _DummyPaginateQuery)

    resp = client.post("/api/scenario/case/page", json={"scenario_id": 19, "page": 1, "size": 20, "is_deleted": 0})
    body = resp.json()

    assert resp.status_code == 200
    assert body["code"] == 200
    assert body["data"]["total"] == 1
    assert body["data"]["records"][0]["step_no"] == 1

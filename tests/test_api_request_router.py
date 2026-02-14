# -*- coding: utf-8 -*-

from collections.abc import AsyncGenerator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.routers import api_request as api_request_router
from app.core.exception_handlers import register_exception_handlers
from app.core.security import check_admin_existence
from app.db.session import get_db_session
from app.models.admin import Admin
from app.models.api_request import ApiAssertRule, ApiExtractRule, ApiRequest, ApiRequestDataset, ApiRequestRun


class _FakeScalarResult:
    def __init__(self, items: list[Any]):
        self._items = items

    def first(self):
        return self._items[0] if self._items else None

    def all(self):
        return list(self._items)


class _FakeExecuteResult:
    def __init__(self, items: list[Any]):
        self._items = items

    def scalars(self):
        return _FakeScalarResult(self._items)


class FakeDBSession:
    def __init__(self):
        self.added: list[Any] = []
        self.commits = 0
        self.flushes = 0
        self.refreshed: list[Any] = []
        self.execute_queue: list[_FakeExecuteResult] = []

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

    async def execute(self, stmt):
        if self.execute_queue:
            return self.execute_queue.pop(0)
        return _FakeExecuteResult([])

    def queue_execute_result(self, items: list[Any]):
        self.execute_queue.append(_FakeExecuteResult(items))


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
    obj.id = kwargs.pop("id", 10)
    for k, v in kwargs.items():
        setattr(obj, k, v)
    return obj


def _build_dataset(**kwargs) -> ApiRequestDataset:
    obj = ApiRequestDataset(
        request_id=kwargs.pop("request_id", 10),
        name=kwargs.pop("name", "dataset-1"),
        creator="tester",
        creator_id=1,
        variables={},
        query_params={},
        headers={},
        cookies={},
        body_type=None,
        body_data={},
        body_raw=None,
        expected={},
        is_default=kwargs.pop("is_default", False),
        is_enabled=True,
        sort=0,
        is_deleted=0,
    )
    obj.id = kwargs.pop("id", 20)
    for k, v in kwargs.items():
        setattr(obj, k, v)
    return obj


def _build_extract_rule(**kwargs) -> ApiExtractRule:
    obj = ApiExtractRule(
        request_id=kwargs.pop("request_id", 10),
        dataset_id=kwargs.pop("dataset_id", None),
        var_name=kwargs.pop("var_name", "token"),
        source_type=kwargs.pop("source_type", "response_json"),
        source_expr=kwargs.pop("source_expr", "$.token"),
        required=kwargs.pop("required", True),
        default_value=kwargs.pop("default_value", None),
        scope=kwargs.pop("scope", "scenario"),
        is_secret=kwargs.pop("is_secret", False),
        is_enabled=kwargs.pop("is_enabled", True),
        sort=kwargs.pop("sort", 0),
        is_deleted=kwargs.pop("is_deleted", 0),
    )
    obj.id = kwargs.pop("id", 70)
    for k, v in kwargs.items():
        setattr(obj, k, v)
    return obj


def _build_assert_rule(**kwargs) -> ApiAssertRule:
    obj = ApiAssertRule(
        request_id=kwargs.pop("request_id", 10),
        dataset_id=kwargs.pop("dataset_id", None),
        assert_type=kwargs.pop("assert_type", "status_code"),
        source_expr=kwargs.pop("source_expr", None),
        comparator=kwargs.pop("comparator", "eq"),
        expected_value=kwargs.pop("expected_value", 200),
        message=kwargs.pop("message", None),
        is_enabled=kwargs.pop("is_enabled", True),
        sort=kwargs.pop("sort", 0),
        is_deleted=kwargs.pop("is_deleted", 0),
    )
    obj.id = kwargs.pop("id", 80)
    for k, v in kwargs.items():
        setattr(obj, k, v)
    return obj


def _build_request_run(**kwargs) -> ApiRequestRun:
    obj = ApiRequestRun(
        request_id=kwargs.pop("request_id", 10),
        scenario_run_id=kwargs.pop("scenario_run_id", None),
        scenario_id=kwargs.pop("scenario_id", None),
        scenario_case_id=kwargs.pop("scenario_case_id", None),
        dataset_id=kwargs.pop("dataset_id", None),
        dataset_snapshot=kwargs.pop("dataset_snapshot", {}),
        request_snapshot=kwargs.pop("request_snapshot", {}),
        response_status_code=kwargs.pop("response_status_code", 200),
        response_headers=kwargs.pop("response_headers", {}),
        response_body=kwargs.pop("response_body", None),
        response_time_ms=kwargs.pop("response_time_ms", 10),
        is_success=kwargs.pop("is_success", True),
        error_message=kwargs.pop("error_message", None),
        is_deleted=kwargs.pop("is_deleted", 0),
    )
    obj.id = kwargs.pop("id", 95)
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
    app.include_router(api_request_router.router, prefix="/api/case")

    admin = _build_admin()

    async def _override_admin():
        return admin

    async def _override_db() -> AsyncGenerator[FakeDBSession, None]:
        yield fake_db

    app.dependency_overrides[check_admin_existence] = _override_admin
    app.dependency_overrides[get_db_session] = _override_db

    with TestClient(app) as c:
        yield c


def test_create_api_request_success(client: TestClient, fake_db: FakeDBSession):
    payload = {
        "name": "case-create",
        "method": "POST",
        "url": "https://example.com/order",
        "case_status": "开发中",
    }
    resp = client.post("/api/case", json=payload)
    body = resp.json()

    assert resp.status_code == 201
    assert body["code"] == 201
    assert body["data"]["id"] >= 100
    assert len(fake_db.added) == 1
    obj = fake_db.added[0]
    assert obj.creator_id == 1
    assert obj.creator == "tester"


def test_update_api_request_success(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    obj = _build_api_request(id=11, name="old-name")

    async def _fake_get_api_request(db, request_id: int):
        assert request_id == 11
        return obj

    monkeypatch.setattr(api_request_router, "_get_api_request_or_404", _fake_get_api_request)

    payload = {
        "id": 11,
        "name": "new-name",
        "case_status": "调试中",
        "is_public_visible": True,
    }
    resp = client.put("/api/case", json=payload)
    body = resp.json()

    assert resp.status_code == 201
    assert body["code"] == 201
    assert obj.name == "new-name"
    assert obj.case_status == "调试中"
    assert obj.is_public_visible is True
    assert obj.modifier_id == 1


def test_api_request_detail_success(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    obj = _build_api_request(id=12, name="case-detail")

    async def _fake_get_api_request(db, request_id: int):
        assert request_id == 12
        return obj

    monkeypatch.setattr(api_request_router, "_get_api_request_or_404", _fake_get_api_request)

    resp = client.get("/api/case/12")
    body = resp.json()

    assert resp.status_code == 200
    assert body["code"] == 200
    assert body["data"]["id"] == 12
    assert body["data"]["name"] == "case-detail"


def test_request_run_detail_success(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    run_obj = _build_request_run(id=96, request_id=12, response_status_code=201)

    async def _fake_get_run(db, run_id: int):
        assert run_id == 96
        return run_obj

    monkeypatch.setattr(api_request_router, "_get_request_run_or_404", _fake_get_run)

    resp = client.get("/api/case/run/96")
    body = resp.json()

    assert resp.status_code == 200
    assert body["code"] == 200
    assert body["data"]["id"] == 96
    assert body["data"]["response_status_code"] == 201


def test_api_request_page_success(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    class _DummyPaginateQuery:
        def __init__(self, *args, **kwargs):
            self.normal_data = {"records": [{"id": 1, "name": "case-page"}], "now_page": 1, "total": 1}

        async def build_query(self):
            return

    monkeypatch.setattr(api_request_router, "CommonPaginateQuery", _DummyPaginateQuery)

    payload = {"page": 1, "size": 20, "is_deleted": 0}
    resp = client.post("/api/case/page", json=payload)
    body = resp.json()

    assert resp.status_code == 200
    assert body["code"] == 200
    assert body["data"]["total"] == 1
    assert body["data"]["records"][0]["name"] == "case-page"


def test_delete_api_request_soft_delete_with_datasets(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    fake_db: FakeDBSession,
):
    request_obj = _build_api_request(id=13, default_dataset_id=30)
    dataset_1 = _build_dataset(id=30, request_id=13, is_default=True)
    dataset_2 = _build_dataset(id=31, request_id=13, is_default=False)
    fake_db.queue_execute_result([dataset_1, dataset_2])

    async def _fake_get_api_request(db, request_id: int):
        assert request_id == 13
        return request_obj

    monkeypatch.setattr(api_request_router, "_get_api_request_or_404", _fake_get_api_request)

    resp = client.request("DELETE", "/api/case", json={"id": 13})
    body = resp.json()

    assert resp.status_code == 200
    assert body["code"] == 204
    assert request_obj.is_deleted == 1
    assert request_obj.default_dataset_id is None
    assert dataset_1.is_deleted == 1
    assert dataset_2.is_deleted == 1


def test_create_dataset_auto_set_default(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    fake_db: FakeDBSession,
):
    request_obj = _build_api_request(id=14, default_dataset_id=None)
    called = {"value": False}

    async def _fake_get_api_request(db, request_id: int):
        assert request_id == 14
        return request_obj

    async def _fake_set_default(db, req_obj: ApiRequest, dataset_obj: ApiRequestDataset):
        called["value"] = True
        req_obj.default_dataset_id = dataset_obj.id

    monkeypatch.setattr(api_request_router, "_get_api_request_or_404", _fake_get_api_request)
    monkeypatch.setattr(api_request_router, "_set_default_dataset", _fake_set_default)

    payload = {"request_id": 14, "name": "d1", "is_default": False}
    resp = client.post("/api/case/dataset", json=payload)
    body = resp.json()

    assert resp.status_code == 201
    assert body["code"] == 201
    assert called["value"] is True
    assert len(fake_db.added) == 1
    dataset = fake_db.added[0]
    assert dataset.request_id == 14
    assert dataset.creator_id == 1


def test_set_default_dataset_mismatch_returns_10005(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
):
    request_obj = _build_api_request(id=15)
    dataset_obj = _build_dataset(id=40, request_id=999)

    async def _fake_get_api_request(db, request_id: int):
        assert request_id == 15
        return request_obj

    async def _fake_get_dataset(db, dataset_id: int):
        assert dataset_id == 40
        return dataset_obj

    monkeypatch.setattr(api_request_router, "_get_api_request_or_404", _fake_get_api_request)
    monkeypatch.setattr(api_request_router, "_get_dataset_or_404", _fake_get_dataset)

    resp = client.put("/api/case/dataset/default", json={"request_id": 15, "dataset_id": 40})
    body = resp.json()

    assert resp.status_code == 200
    assert body["code"] == 10005
    assert body["message"] == "数据集与测试用例不匹配"


def test_dataset_page_success(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    request_obj = _build_api_request(id=16)

    async def _fake_get_api_request(db, request_id: int):
        assert request_id == 16
        return request_obj

    class _DummyPaginateQuery:
        def __init__(self, *args, **kwargs):
            self.normal_data = {"records": [{"id": 22, "name": "ds-page"}], "now_page": 1, "total": 1}

        async def build_query(self):
            return

    monkeypatch.setattr(api_request_router, "_get_api_request_or_404", _fake_get_api_request)
    monkeypatch.setattr(api_request_router, "CommonPaginateQuery", _DummyPaginateQuery)

    resp = client.post("/api/case/dataset/page", json={"request_id": 16, "page": 1, "size": 20, "is_deleted": 0})
    body = resp.json()

    assert resp.status_code == 200
    assert body["code"] == 200
    assert body["data"]["total"] == 1
    assert body["data"]["records"][0]["name"] == "ds-page"


def test_set_dataset_enabled_success(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    dataset_obj = _build_dataset(id=50, request_id=17, is_enabled=True)

    async def _fake_get_dataset(db, dataset_id: int):
        assert dataset_id == 50
        return dataset_obj

    monkeypatch.setattr(api_request_router, "_get_dataset_or_404", _fake_get_dataset)

    resp = client.put("/api/case/dataset/enabled", json={"id": 50, "is_enabled": False})
    body = resp.json()

    assert resp.status_code == 201
    assert body["code"] == 201
    assert dataset_obj.is_enabled is False
    assert dataset_obj.modifier_id == 1


def test_run_api_request_success(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    fake_db: FakeDBSession,
):
    request_obj = _build_api_request(id=18, default_dataset_id=60, execute_count=2)
    dataset_obj = _build_dataset(id=60, request_id=18, is_enabled=True)

    async def _fake_get_api_request(db, request_id: int):
        assert request_id == 18
        return request_obj

    async def _fake_get_dataset(db, dataset_id: int):
        assert dataset_id == 60
        return dataset_obj

    async def _fake_execute_api_request(request_obj, dataset_obj, environment_obj):
        assert request_obj.id == 18
        assert dataset_obj.id == 60
        assert environment_obj is None
        return {
            "dataset_snapshot": {"id": 60},
            "request_snapshot": {"request_id": 18, "method": "GET", "url": "https://example.com/api"},
            "response_status_code": 200,
            "response_headers": {"content-type": "application/json"},
            "response_body": '{"ok":true}',
            "response_time_ms": 21,
            "is_success": True,
            "error_message": None,
        }

    monkeypatch.setattr(api_request_router, "_get_api_request_or_404", _fake_get_api_request)
    monkeypatch.setattr(api_request_router, "_get_dataset_or_404", _fake_get_dataset)
    monkeypatch.setattr(api_request_router, "execute_api_request", _fake_execute_api_request)

    resp = client.post("/api/case/run", json={"request_id": 18})
    body = resp.json()

    assert resp.status_code == 201
    assert body["code"] == 201
    assert body["data"]["is_success"] is True
    assert body["data"]["response_status_code"] == 200
    assert request_obj.execute_count == 3

    assert len(fake_db.added) == 1
    run_obj = fake_db.added[0]
    assert isinstance(run_obj, ApiRequestRun)
    assert run_obj.request_id == 18
    assert run_obj.dataset_id == 60
    assert run_obj.is_success is True


def test_run_api_request_assertion_failed(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    fake_db: FakeDBSession,
):
    request_obj = _build_api_request(id=181, execute_count=0)
    assert_rule = _build_assert_rule(id=801, request_id=181, assert_type="status_code", expected_value=201)

    async def _fake_get_api_request(db, request_id: int):
        assert request_id == 181
        return request_obj

    async def _fake_resolve_dataset(db, req_obj, dataset_id):
        assert req_obj.id == 181
        assert dataset_id is None
        return None

    async def _fake_execute_api_request(request_obj, dataset_obj, environment_obj):
        return {
            "dataset_snapshot": {},
            "request_snapshot": {"request_id": 181, "method": "GET", "url": "https://example.com/api"},
            "response_status_code": 200,
            "response_headers": {"content-type": "application/json"},
            "response_body": '{"ok":true}',
            "response_time_ms": 10,
            "is_success": True,
            "error_message": None,
        }

    async def _fake_list_assert_rules(db, request_id: int, dataset_id):
        assert request_id == 181
        assert dataset_id is None
        return [assert_rule]

    monkeypatch.setattr(api_request_router, "_get_api_request_or_404", _fake_get_api_request)
    monkeypatch.setattr(api_request_router, "_resolve_dataset_for_run", _fake_resolve_dataset)
    monkeypatch.setattr(api_request_router, "execute_api_request", _fake_execute_api_request)
    monkeypatch.setattr(api_request_router, "_list_assert_rules", _fake_list_assert_rules)

    resp = client.post("/api/case/run", json={"request_id": 181})
    body = resp.json()

    assert resp.status_code == 201
    assert body["code"] == 201
    assert body["data"]["is_success"] is False
    assert body["data"]["assertion_total"] == 1
    assert body["data"]["assertion_failed"] == 1
    assert "断言失败" in body["data"]["error_message"]

    run_obj = fake_db.added[0]
    assert isinstance(run_obj, ApiRequestRun)
    assert run_obj.is_success is False


def test_run_api_request_dataset_mismatch_returns_10005(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
):
    request_obj = _build_api_request(id=19)
    dataset_obj = _build_dataset(id=61, request_id=999, is_enabled=True)

    async def _fake_get_api_request(db, request_id: int):
        assert request_id == 19
        return request_obj

    async def _fake_get_dataset(db, dataset_id: int):
        assert dataset_id == 61
        return dataset_obj

    monkeypatch.setattr(api_request_router, "_get_api_request_or_404", _fake_get_api_request)
    monkeypatch.setattr(api_request_router, "_get_dataset_or_404", _fake_get_dataset)

    resp = client.post("/api/case/run", json={"request_id": 19, "dataset_id": 61})
    body = resp.json()

    assert resp.status_code == 200
    assert body["code"] == 10005
    assert body["message"] == "数据集与测试用例不匹配"


def test_run_api_request_dataset_disabled_returns_10005(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
):
    request_obj = _build_api_request(id=20)
    dataset_obj = _build_dataset(id=62, request_id=20, is_enabled=False)

    async def _fake_get_api_request(db, request_id: int):
        assert request_id == 20
        return request_obj

    async def _fake_get_dataset(db, dataset_id: int):
        assert dataset_id == 62
        return dataset_obj

    monkeypatch.setattr(api_request_router, "_get_api_request_or_404", _fake_get_api_request)
    monkeypatch.setattr(api_request_router, "_get_dataset_or_404", _fake_get_dataset)

    resp = client.post("/api/case/run", json={"request_id": 20, "dataset_id": 62})
    body = resp.json()

    assert resp.status_code == 200
    assert body["code"] == 10005
    assert body["message"] == "数据集已禁用"


def test_create_extract_rule_success(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    fake_db: FakeDBSession,
):
    request_obj = _build_api_request(id=30)
    dataset_obj = _build_dataset(id=90, request_id=30)

    async def _fake_get_api_request(db, request_id: int):
        assert request_id == 30
        return request_obj

    async def _fake_get_dataset(db, dataset_id: int):
        assert dataset_id == 90
        return dataset_obj

    monkeypatch.setattr(api_request_router, "_get_api_request_or_404", _fake_get_api_request)
    monkeypatch.setattr(api_request_router, "_get_dataset_or_404", _fake_get_dataset)

    resp = client.post(
        "/api/case/extract",
        json={
            "request_id": 30,
            "dataset_id": 90,
            "var_name": "token",
            "source_type": "response_json",
            "source_expr": "$.data.token",
            "required": True,
            "scope": "scenario",
        },
    )
    body = resp.json()

    assert resp.status_code == 201
    assert body["code"] == 201
    assert len(fake_db.added) == 1
    obj = fake_db.added[0]
    assert isinstance(obj, ApiExtractRule)
    assert obj.request_id == 30
    assert obj.dataset_id == 90
    assert obj.var_name == "token"


def test_create_assert_rule_success(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    fake_db: FakeDBSession,
):
    request_obj = _build_api_request(id=301)
    dataset_obj = _build_dataset(id=901, request_id=301)

    async def _fake_get_api_request(db, request_id: int):
        assert request_id == 301
        return request_obj

    async def _fake_get_dataset(db, dataset_id: int):
        assert dataset_id == 901
        return dataset_obj

    monkeypatch.setattr(api_request_router, "_get_api_request_or_404", _fake_get_api_request)
    monkeypatch.setattr(api_request_router, "_get_dataset_or_404", _fake_get_dataset)

    resp = client.post(
        "/api/case/assert",
        json={
            "request_id": 301,
            "dataset_id": 901,
            "assert_type": "json_path",
            "source_expr": "$.data.ok",
            "comparator": "eq",
            "expected_value": True,
            "message": "ok 字段必须为 true",
        },
    )
    body = resp.json()

    assert resp.status_code == 201
    assert body["code"] == 201
    assert len(fake_db.added) == 1
    obj = fake_db.added[0]
    assert isinstance(obj, ApiAssertRule)
    assert obj.request_id == 301
    assert obj.dataset_id == 901
    assert obj.assert_type == "json_path"


def test_update_extract_rule_success(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    request_obj = _build_api_request(id=31)
    rule_obj = _build_extract_rule(id=71, request_id=31, var_name="token")

    async def _fake_get_rule(db, rule_id: int):
        assert rule_id == 71
        return rule_obj

    async def _fake_get_api_request(db, request_id: int):
        assert request_id == 31
        return request_obj

    monkeypatch.setattr(api_request_router, "_get_extract_rule_or_404", _fake_get_rule)
    monkeypatch.setattr(api_request_router, "_get_api_request_or_404", _fake_get_api_request)

    resp = client.put(
        "/api/case/extract",
        json={"id": 71, "var_name": "auth_token", "source_expr": "$.token", "scope": "global"},
    )
    body = resp.json()

    assert resp.status_code == 201
    assert body["code"] == 201
    assert rule_obj.var_name == "auth_token"
    assert rule_obj.scope == "global"

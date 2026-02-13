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
from app.models.api_request import ApiRequest, ApiRequestDataset


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

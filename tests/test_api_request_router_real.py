# -*- coding: utf-8 -*-

import json
import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import and_, delete, select, text

import app.db.redis_client as redis_module
from app.api.v1.routers import api_request as api_request_router
from app.core.exception_handlers import register_exception_handlers
from app.db.redis_client import close_redis_connection_pool, create_redis_connection_pool
from app.db.session import AsyncSessionLocal, engine
from app.models.admin import Admin
from app.models.api_request import ApiRequest, ApiRequestDataset, ApiRequestRun
from app.models.base import Base

TEST_ADMIN_ID = 910001
TEST_ADMIN_NAME = "ut_admin_real"
TEST_TOKEN = "ut_real_token_api_request"
TEST_NAME_PREFIX = "ut_case_real_"

REQUIRED_COLUMNS = {
    "exile_api_requests": [
        ("creator", "VARCHAR(32) NULL COMMENT '创建人'"),
        ("creator_id", "BIGINT NULL COMMENT '创建人ID'"),
        ("modifier", "VARCHAR(32) NULL COMMENT '更新人'"),
        ("modifier_id", "BIGINT NULL COMMENT '更新人ID'"),
        ("remark", "VARCHAR(255) NULL COMMENT '备注'"),
    ],
    "exile_api_request_datasets": [
        ("creator", "VARCHAR(32) NULL COMMENT '创建人'"),
        ("creator_id", "BIGINT NULL COMMENT '创建人ID'"),
        ("modifier", "VARCHAR(32) NULL COMMENT '更新人'"),
        ("modifier_id", "BIGINT NULL COMMENT '更新人ID'"),
        ("remark", "VARCHAR(255) NULL COMMENT '备注'"),
    ],
    "exile_api_request_runs": [
        ("scenario_run_id", "BIGINT NULL COMMENT '场景运行ID'"),
    ],
}

"""
uv run pytest -q tests/test_api_request_router_real.py
KEEP_TEST_DATA=1 uv run pytest -q tests/test_api_request_router_real.py
KEEP_TEST_DATA=1 uv run pytest -q tests/test_api_request_router_real.py::test_real_create_api_request_persist_mysql
"""


def _should_keep_test_data() -> bool:
    value = os.getenv("KEEP_TEST_DATA", "0").strip().lower()
    return value in {"1", "true", "yes", "on"}


class _EchoRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._handle_request()

    def do_POST(self):
        self._handle_request()

    def log_message(self, format, *args):  # noqa: A003
        return

    def _handle_request(self):
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", "0"))
        body_bytes = self.rfile.read(content_length) if content_length > 0 else b""

        payload = {
            "method": self.command,
            "path": parsed.path,
            "query": {
                key: values[0] if len(values) == 1 else values
                for key, values in parse_qs(parsed.query).items()
            },
            "body": body_bytes.decode("utf-8", errors="ignore"),
        }
        response_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app, debug=True)
    app.include_router(api_request_router.router, prefix="/api/case")
    return app


@pytest.fixture
def echo_server_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _EchoRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
async def auth_headers():
    await engine.dispose()
    await create_redis_connection_pool(force=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for table_name, columns in REQUIRED_COLUMNS.items():
            for column_name, ddl in columns:
                exists_sql = text(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = :table_name
                      AND COLUMN_NAME = :column_name
                    """
                )
                count = await conn.scalar(
                    exists_sql,
                    {"table_name": table_name, "column_name": column_name},
                )
                if not count:
                    await conn.execute(
                        text(
                            f"ALTER TABLE `{table_name}` ADD COLUMN `{column_name}` {ddl}"
                        )
                    )

    async with AsyncSessionLocal() as session:
        admin = (await session.execute(select(Admin).where(Admin.id == TEST_ADMIN_ID))).scalars().first()
        if not admin:
            admin = Admin(
                id=TEST_ADMIN_ID,
                username=TEST_ADMIN_NAME,
                password="not_used_for_this_test",
                nickname="ut",
                status=1,
                creator="pytest",
                creator_id=TEST_ADMIN_ID,
            )
            session.add(admin)
        else:
            admin.username = TEST_ADMIN_NAME
            admin.status = 1
            admin.touch()
        await session.commit()

    user_info = json.dumps({"id": TEST_ADMIN_ID, "username": TEST_ADMIN_NAME})
    await redis_module.redis_pool.set(TEST_TOKEN, user_info, ex=3600)

    yield {"token": TEST_TOKEN}

    if redis_module.redis_pool:
        await redis_module.redis_pool.delete(TEST_TOKEN)

    if not _should_keep_test_data():
        async with AsyncSessionLocal() as session:
            request_ids = (
                await session.execute(
                    select(ApiRequest.id).where(
                        and_(
                            ApiRequest.creator_id == TEST_ADMIN_ID,
                            ApiRequest.name.like(f"{TEST_NAME_PREFIX}%"),
                        )
                    )
                )
            ).scalars().all()
            if request_ids:
                await session.execute(delete(ApiRequestRun).where(ApiRequestRun.request_id.in_(request_ids)))
                await session.execute(delete(ApiRequestDataset).where(ApiRequestDataset.request_id.in_(request_ids)))
                await session.execute(delete(ApiRequest).where(ApiRequest.id.in_(request_ids)))
            else:
                await session.execute(delete(ApiRequestDataset).where(ApiRequestDataset.creator_id == TEST_ADMIN_ID))
                await session.execute(
                    delete(ApiRequest).where(
                        and_(
                            ApiRequest.creator_id == TEST_ADMIN_ID,
                            ApiRequest.name.like(f"{TEST_NAME_PREFIX}%"),
                        )
                    )
                )
            await session.commit()

    await close_redis_connection_pool()
    await engine.dispose()


async def _create_case(client: AsyncClient, headers: dict, **payload_override) -> int:
    payload = {
        "name": f"{TEST_NAME_PREFIX}{uuid.uuid4().hex[:8]}",
        "method": "POST",
        "url": "https://example.com/order/create",
        "case_status": "开发中",
        "base_headers": {"x-test": "1"},
    }
    payload.update(payload_override)
    resp = await client.post("/api/case", json=payload, headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["code"] == 201
    return body["data"]["id"]


@pytest.mark.anyio
async def test_real_create_api_request_persist_mysql(app: FastAPI, auth_headers: dict):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        request_id = await _create_case(client, auth_headers)

    async with AsyncSessionLocal() as session:
        obj = (await session.execute(select(ApiRequest).where(ApiRequest.id == request_id))).scalars().first()
        assert obj is not None
        assert obj.creator_id == TEST_ADMIN_ID
        assert obj.case_status == "开发中"
        assert obj.is_deleted == 0


@pytest.mark.anyio
async def test_real_dataset_flow_mysql_and_redis_auth(app: FastAPI, auth_headers: dict):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        request_id = await _create_case(client, auth_headers)

        create_dataset_resp = await client.post(
            "/api/case/dataset",
            json={
                "request_id": request_id,
                "name": f"ut_ds_{uuid.uuid4().hex[:8]}",
                "is_default": True,
                "variables": {"uid": 123},
                "body_data": {"amount": 100},
            },
            headers=auth_headers,
        )
        assert create_dataset_resp.status_code == 201
        create_dataset_body = create_dataset_resp.json()
        assert create_dataset_body["code"] == 201
        dataset_id = create_dataset_body["data"]["id"]

        detail_resp = await client.get(f"/api/case/dataset/{dataset_id}", headers=auth_headers)
        assert detail_resp.status_code == 200
        detail_body = detail_resp.json()
        assert detail_body["code"] == 200
        assert detail_body["data"]["id"] == dataset_id

        enabled_resp = await client.put(
            "/api/case/dataset/enabled",
            json={"id": dataset_id, "is_enabled": False},
            headers=auth_headers,
        )
        assert enabled_resp.status_code == 201
        assert enabled_resp.json()["code"] == 201

    async with AsyncSessionLocal() as session:
        req_obj = (await session.execute(select(ApiRequest).where(ApiRequest.id == request_id))).scalars().first()
        ds_obj = (await session.execute(select(ApiRequestDataset).where(ApiRequestDataset.id == dataset_id))).scalars().first()
        assert req_obj is not None
        assert ds_obj is not None
        assert req_obj.default_dataset_id == dataset_id
        assert ds_obj.is_default is True
        assert ds_obj.is_enabled is False


@pytest.mark.anyio
async def test_real_page_and_soft_delete_flow(app: FastAPI, auth_headers: dict):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        request_id = await _create_case(client, auth_headers)

        ds_resp = await client.post(
            "/api/case/dataset",
            json={
                "request_id": request_id,
                "name": f"ut_ds_{uuid.uuid4().hex[:8]}",
                "is_default": True,
            },
            headers=auth_headers,
        )
        assert ds_resp.status_code == 201
        dataset_id = ds_resp.json()["data"]["id"]

        page_resp = await client.post(
            "/api/case/page",
            json={
                "page": 1,
                "size": 20,
                "is_deleted": 0,
                "creator_id": TEST_ADMIN_ID,
                "name": TEST_NAME_PREFIX,
            },
            headers=auth_headers,
        )
        assert page_resp.status_code == 200
        page_body = page_resp.json()
        assert page_body["code"] == 200
        assert page_body["data"]["total"] >= 1

        delete_resp = await client.request(
            "DELETE",
            "/api/case",
            json={"id": request_id},
            headers=auth_headers,
        )
        assert delete_resp.status_code == 200
        assert delete_resp.json()["code"] == 204

    async with AsyncSessionLocal() as session:
        req_obj = (await session.execute(select(ApiRequest).where(ApiRequest.id == request_id))).scalars().first()
        ds_obj = (await session.execute(select(ApiRequestDataset).where(ApiRequestDataset.id == dataset_id))).scalars().first()
        assert req_obj is not None
        assert ds_obj is not None
        assert req_obj.is_deleted == TEST_ADMIN_ID
        assert ds_obj.is_deleted == TEST_ADMIN_ID
        assert req_obj.default_dataset_id is None


@pytest.mark.anyio
async def test_real_run_api_request_and_persist_run_record(
    app: FastAPI,
    auth_headers: dict,
    echo_server_url: str,
):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        request_id = await _create_case(
            client,
            auth_headers,
            method="POST",
            url=f"{echo_server_url}/orders/{{{{uid}}}}",
            body_type="json",
            base_query_params={"from": "base", "uid": "{{uid}}"},
            base_headers={"x-user": "{{uid}}"},
            base_body_data={"amount": "{{amount}}", "source": "base"},
        )

        create_dataset_resp = await client.post(
            "/api/case/dataset",
            json={
                "request_id": request_id,
                "name": f"ut_ds_run_{uuid.uuid4().hex[:8]}",
                "is_default": True,
                "variables": {"uid": "u100", "amount": 99, "tag": "ok"},
                "query_params": {"from": "dataset", "tag": "{{tag}}"},
                "body_data": {"amount": "{{amount}}", "tag": "{{tag}}"},
            },
            headers=auth_headers,
        )
        assert create_dataset_resp.status_code == 201
        dataset_id = create_dataset_resp.json()["data"]["id"]

        run_resp = await client.post(
            "/api/case/run",
            json={"request_id": request_id, "dataset_id": dataset_id},
            headers=auth_headers,
        )
        assert run_resp.status_code == 201
        run_body = run_resp.json()
        assert run_body["code"] == 201
        assert run_body["data"]["is_success"] is True
        run_id = run_body["data"]["run_id"]

    async with AsyncSessionLocal() as session:
        run_obj = (await session.execute(select(ApiRequestRun).where(ApiRequestRun.id == run_id))).scalars().first()
        request_obj = (await session.execute(select(ApiRequest).where(ApiRequest.id == request_id))).scalars().first()
        assert run_obj is not None
        assert request_obj is not None

        assert run_obj.request_id == request_id
        assert run_obj.dataset_id == dataset_id
        assert run_obj.is_success is True
        assert run_obj.response_status_code == 200
        assert run_obj.response_time_ms is not None
        assert run_obj.request_snapshot["query_params"]["from"] == "dataset"
        assert run_obj.request_snapshot["query_params"]["uid"] == "u100"
        assert run_obj.request_snapshot["query_params"]["tag"] == "ok"
        assert run_obj.request_snapshot["headers"]["x-user"] == "u100"
        assert run_obj.request_snapshot["body_data"]["amount"] == 99
        assert run_obj.request_snapshot["body_data"]["tag"] == "ok"
        assert request_obj.execute_count >= 1

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
from app.api.v1.routers import scenario as scenario_router
from app.core.exception_handlers import register_exception_handlers
from app.db.redis_client import close_redis_connection_pool, create_redis_connection_pool
from app.db.session import AsyncSessionLocal, engine
from app.models.admin import Admin
from app.models.api_request import (
    ApiExtractRule,
    ApiRequest,
    ApiRequestDataset,
    ApiRequestRun,
    ApiRunVariable,
    TestScenario as ScenarioModel,
    TestScenarioCase as ScenarioCaseModel,
    TestScenarioRun as ScenarioRunModel,
)
from app.models.base import Base

TEST_ADMIN_ID = 910001
TEST_ADMIN_NAME = "ut_admin_real"
TEST_TOKEN = "ut_real_token_test_scenario"
TEST_CASE_PREFIX = "ut_case_scenario_real_"
TEST_DATASET_PREFIX = "ut_ds_scenario_real_"
TEST_SCENARIO_PREFIX = "ut_scenario_real_"

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


def _should_keep_test_data() -> bool:
    value = os.getenv("KEEP_TEST_DATA", "0").strip().lower()
    return value in {"1", "true", "yes", "on"}


class _ScenarioRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._handle_request()

    def do_POST(self):
        self._handle_request()

    def log_message(self, format, *args):  # noqa: A003
        return

    def _handle_request(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        path = parsed.path

        if path == "/auth":
            body = json.dumps({"token": "tk_abc_001"}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Set-Cookie", "session_id=sid_001; Path=/")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/order":
            auth_value = self.headers.get("Authorization", "")
            order_token = params.get("token", [""])[0]
            session_id = params.get("sid", [""])[0]
            ok = auth_value == "Bearer tk_abc_001" and order_token == "tk_abc_001" and session_id == "sid_001"
            status_code = 200 if ok else 401
            body = json.dumps({"ok": ok, "auth": auth_value, "sid": session_id}, ensure_ascii=False).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        body = json.dumps({"path": path}, ensure_ascii=False).encode("utf-8")
        self.send_response(404)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app, debug=True)
    app.include_router(api_request_router.router, prefix="/api/case")
    app.include_router(scenario_router.router, prefix="/api/scenario")
    return app


@pytest.fixture
def scenario_workflow_server_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ScenarioRequestHandler)
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
                    SELECT COUNT(*) FROM information_schema.COLUMNS
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
            scenario_ids = (
                await session.execute(
                    select(ScenarioModel.id).where(ScenarioModel.name.like(f"{TEST_SCENARIO_PREFIX}%"))
                )
            ).scalars().all()
            if scenario_ids:
                scenario_run_ids = (
                    await session.execute(
                        select(ScenarioRunModel.id).where(ScenarioRunModel.scenario_id.in_(scenario_ids))
                    )
                ).scalars().all()
                if scenario_run_ids:
                    await session.execute(delete(ApiRunVariable).where(ApiRunVariable.scenario_run_id.in_(scenario_run_ids)))
                    await session.execute(delete(ApiRequestRun).where(ApiRequestRun.scenario_run_id.in_(scenario_run_ids)))
                    await session.execute(delete(ScenarioRunModel).where(ScenarioRunModel.id.in_(scenario_run_ids)))
                await session.execute(delete(ScenarioCaseModel).where(ScenarioCaseModel.scenario_id.in_(scenario_ids)))
                await session.execute(delete(ScenarioModel).where(ScenarioModel.id.in_(scenario_ids)))

            request_ids = (
                await session.execute(
                    select(ApiRequest.id).where(
                        and_(
                            ApiRequest.creator_id == TEST_ADMIN_ID,
                            ApiRequest.name.like(f"{TEST_CASE_PREFIX}%"),
                        )
                    )
                )
            ).scalars().all()
            if request_ids:
                await session.execute(delete(ApiRunVariable).where(ApiRunVariable.request_id.in_(request_ids)))
                await session.execute(delete(ApiExtractRule).where(ApiExtractRule.request_id.in_(request_ids)))
                await session.execute(delete(ApiRequestRun).where(ApiRequestRun.request_id.in_(request_ids)))
                await session.execute(delete(ApiRequestDataset).where(ApiRequestDataset.request_id.in_(request_ids)))
                await session.execute(delete(ApiRequest).where(ApiRequest.id.in_(request_ids)))
            await session.commit()

    await close_redis_connection_pool()
    await engine.dispose()


async def _create_case(client: AsyncClient, headers: dict, **payload_override) -> int:
    payload = {
        "name": f"{TEST_CASE_PREFIX}{uuid.uuid4().hex[:8]}",
        "method": "POST",
        "url": "https://example.com/order/create",
        "case_status": "开发中",
    }
    payload.update(payload_override)
    resp = await client.post("/api/case", json=payload, headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["code"] == 201
    return body["data"]["id"]


async def _create_dataset(client: AsyncClient, headers: dict, request_id: int) -> int:
    payload = {
        "request_id": request_id,
        "name": f"{TEST_DATASET_PREFIX}{uuid.uuid4().hex[:8]}",
        "is_default": True,
        "variables": {"uid": 123},
    }
    resp = await client.post("/api/case/dataset", json=payload, headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["code"] == 201
    return body["data"]["id"]


async def _create_scenario(client: AsyncClient, headers: dict) -> int:
    payload = {
        "name": f"{TEST_SCENARIO_PREFIX}{uuid.uuid4().hex[:8]}",
        "run_mode": "sequence",
        "stop_on_fail": True,
    }
    resp = await client.post("/api/scenario", json=payload, headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["code"] == 201
    return body["data"]["id"]


@pytest.mark.anyio
async def test_real_create_scenario_persist_mysql(app: FastAPI, auth_headers: dict):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        scenario_id = await _create_scenario(client, auth_headers)

    async with AsyncSessionLocal() as session:
        obj = (await session.execute(select(ScenarioModel).where(ScenarioModel.id == scenario_id))).scalars().first()
        assert obj is not None
        assert obj.run_mode == "sequence"
        assert obj.stop_on_fail is True
        assert obj.is_deleted == 0


@pytest.mark.anyio
async def test_real_scenario_case_reorder_and_dataset_strategy(app: FastAPI, auth_headers: dict):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        request_id = await _create_case(client, auth_headers)
        dataset_id = await _create_dataset(client, auth_headers, request_id)
        scenario_id = await _create_scenario(client, auth_headers)

        step_1_resp = await client.post(
            "/api/scenario/case",
            json={"scenario_id": scenario_id, "request_id": request_id, "dataset_run_mode": "request_default"},
            headers=auth_headers,
        )
        assert step_1_resp.status_code == 201
        step_1_id = step_1_resp.json()["data"]["id"]

        step_2_resp = await client.post(
            "/api/scenario/case",
            json={"scenario_id": scenario_id, "request_id": request_id, "step_no": 1, "dataset_run_mode": "all"},
            headers=auth_headers,
        )
        assert step_2_resp.status_code == 201
        step_2_id = step_2_resp.json()["data"]["id"]

        reorder_resp = await client.put(
            "/api/scenario/case/reorder",
            json={"scenario_id": scenario_id, "id": step_1_id, "step_no": 1},
            headers=auth_headers,
        )
        assert reorder_resp.status_code == 201
        assert reorder_resp.json()["code"] == 201

        strategy_resp = await client.put(
            "/api/scenario/case/dataset-strategy",
            json={"id": step_1_id, "dataset_run_mode": "single", "dataset_id": dataset_id},
            headers=auth_headers,
        )
        assert strategy_resp.status_code == 201
        assert strategy_resp.json()["code"] == 201

        detail_resp = await client.get(f"/api/scenario/case/{step_1_id}", headers=auth_headers)
        assert detail_resp.status_code == 200
        detail_body = detail_resp.json()
        assert detail_body["code"] == 200
        assert detail_body["data"]["dataset_run_mode"] == "single"
        assert detail_body["data"]["dataset_id"] == dataset_id

    async with AsyncSessionLocal() as session:
        steps = (
            await session.execute(
                select(ScenarioCaseModel)
                .where(and_(ScenarioCaseModel.scenario_id == scenario_id, ScenarioCaseModel.is_deleted == 0))
                .order_by(ScenarioCaseModel.step_no, ScenarioCaseModel.id)
            )
        ).scalars().all()
        assert len(steps) == 2
        assert [steps[0].id, steps[1].id] == [step_1_id, step_2_id]
        assert steps[0].step_no == 1
        assert steps[0].dataset_run_mode == "single"
        assert steps[0].dataset_id == dataset_id


@pytest.mark.anyio
async def test_real_delete_scenario_soft_delete_steps(app: FastAPI, auth_headers: dict):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        request_id = await _create_case(client, auth_headers)
        scenario_id = await _create_scenario(client, auth_headers)

        step_resp = await client.post(
            "/api/scenario/case",
            json={"scenario_id": scenario_id, "request_id": request_id},
            headers=auth_headers,
        )
        assert step_resp.status_code == 201
        step_id = step_resp.json()["data"]["id"]

        delete_resp = await client.request(
            "DELETE",
            "/api/scenario",
            json={"id": scenario_id},
            headers=auth_headers,
        )
        assert delete_resp.status_code == 200
        assert delete_resp.json()["code"] == 204

    async with AsyncSessionLocal() as session:
        scenario_obj = (await session.execute(select(ScenarioModel).where(ScenarioModel.id == scenario_id))).scalars().first()
        step_obj = (await session.execute(select(ScenarioCaseModel).where(ScenarioCaseModel.id == step_id))).scalars().first()
        assert scenario_obj is not None
        assert step_obj is not None
        assert scenario_obj.is_deleted == TEST_ADMIN_ID
        assert step_obj.is_deleted == TEST_ADMIN_ID


@pytest.mark.anyio
async def test_real_scenario_run_with_extracted_variables(
    app: FastAPI,
    auth_headers: dict,
    scenario_workflow_server_url: str,
):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        auth_request_id = await _create_case(
            client,
            auth_headers,
            method="GET",
            url=f"{scenario_workflow_server_url}/auth",
            body_type="none",
        )
        order_request_id = await _create_case(
            client,
            auth_headers,
            method="POST",
            url=f"{scenario_workflow_server_url}/order?token={{{{token}}}}&sid={{{{session_id}}}}",
            body_type="json",
            base_headers={"Authorization": "Bearer {{token}}"},
            base_body_data={"biz_type": "create_order", "token": "{{token}}"},
        )

        extract_rule_1_resp = await client.post(
            "/api/case/extract",
            json={
                "request_id": auth_request_id,
                "var_name": "token",
                "source_type": "response_json",
                "source_expr": "$.token",
                "required": True,
                "scope": "scenario",
            },
            headers=auth_headers,
        )
        assert extract_rule_1_resp.status_code == 201

        extract_rule_2_resp = await client.post(
            "/api/case/extract",
            json={
                "request_id": auth_request_id,
                "var_name": "session_id",
                "source_type": "response_cookie",
                "source_expr": "session_id",
                "required": True,
                "scope": "scenario",
            },
            headers=auth_headers,
        )
        assert extract_rule_2_resp.status_code == 201

        scenario_id = await _create_scenario(client, auth_headers)

        step_1_resp = await client.post(
            "/api/scenario/case",
            json={"scenario_id": scenario_id, "request_id": auth_request_id, "step_no": 1},
            headers=auth_headers,
        )
        assert step_1_resp.status_code == 201

        step_2_resp = await client.post(
            "/api/scenario/case",
            json={"scenario_id": scenario_id, "request_id": order_request_id, "step_no": 2},
            headers=auth_headers,
        )
        assert step_2_resp.status_code == 201

        run_resp = await client.post(
            "/api/scenario/run",
            json={"scenario_id": scenario_id, "trigger_type": "manual"},
            headers=auth_headers,
        )
        assert run_resp.status_code == 201
        run_body = run_resp.json()
        assert run_body["code"] == 201
        assert run_body["data"]["is_success"] is True
        assert run_body["data"]["total_request_runs"] == 2
        scenario_run_id = run_body["data"]["scenario_run_id"]

    async with AsyncSessionLocal() as session:
        scenario_run = (
            await session.execute(select(ScenarioRunModel).where(ScenarioRunModel.id == scenario_run_id))
        ).scalars().first()
        assert scenario_run is not None
        assert scenario_run.is_success is True
        assert scenario_run.runtime_variables["token"] == "tk_abc_001"
        assert scenario_run.runtime_variables["session_id"] == "sid_001"

        run_list = (
            await session.execute(
                select(ApiRequestRun)
                .where(ApiRequestRun.scenario_run_id == scenario_run_id)
                .order_by(ApiRequestRun.id)
            )
        ).scalars().all()
        assert len(run_list) == 2
        assert run_list[1].request_id == order_request_id
        assert run_list[1].response_status_code == 200
        assert run_list[1].request_snapshot["headers"]["Authorization"] == "Bearer tk_abc_001"
        assert "token=tk_abc_001" in run_list[1].request_snapshot["url"]
        assert "sid=sid_001" in run_list[1].request_snapshot["url"]

        variable_list = (
            await session.execute(
                select(ApiRunVariable)
                .where(ApiRunVariable.scenario_run_id == scenario_run_id)
                .order_by(ApiRunVariable.id)
            )
        ).scalars().all()
        assert len(variable_list) >= 2
        values = {item.var_name: item.var_value for item in variable_list}
        assert values["token"] == "tk_abc_001"
        assert values["session_id"] == "sid_001"

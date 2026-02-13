# -*- coding: utf-8 -*-

import json
import os
import uuid

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
from app.models.api_request import ApiRequest, ApiRequestDataset
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
}

"""
uv run pytest -q tests/test_api_request_router_real.py
KEEP_TEST_DATA=1 uv run pytest -q tests/test_api_request_router_real.py
KEEP_TEST_DATA=1 uv run pytest -q tests/test_api_request_router_real.py::test_real_create_api_request_persist_mysql
"""


def _should_keep_test_data() -> bool:
    value = os.getenv("KEEP_TEST_DATA", "0").strip().lower()
    return value in {"1", "true", "yes", "on"}


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app, debug=True)
    app.include_router(api_request_router.router, prefix="/api/case")
    return app


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


async def _create_case(client: AsyncClient, headers: dict) -> int:
    payload = {
        "name": f"{TEST_NAME_PREFIX}{uuid.uuid4().hex[:8]}",
        "method": "POST",
        "url": "https://example.com/order/create",
        "case_status": "开发中",
        "base_headers": {"x-test": "1"},
    }
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

# -*- coding: utf-8 -*-
# @Time    : 2026/2/14
# @Author  : yangyuexiong
# @File    : api_request_executor.py

import copy
import json
import re
import time
from typing import Any

import httpx

from app.models.api_request import ApiEnvironment, ApiRequest, ApiRequestDataset

VARIABLE_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
MAX_RESPONSE_BODY_LENGTH = 200000


def _deep_merge_dict(base_data: dict | None, override_data: dict | None) -> dict:
    result = copy.deepcopy(base_data or {})
    for key, value in (override_data or {}).items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _deep_merge_dict(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _render_with_variables(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, str):
        exact_match = VARIABLE_PATTERN.fullmatch(value.strip())
        if exact_match:
            var_name = exact_match.group(1)
            if var_name in variables:
                return copy.deepcopy(variables[var_name])

        def replacer(match: re.Match) -> str:
            var_name = match.group(1)
            if var_name in variables:
                return str(variables[var_name])
            return match.group(0)

        return VARIABLE_PATTERN.sub(replacer, value)

    if isinstance(value, dict):
        return {k: _render_with_variables(v, variables) for k, v in value.items()}

    if isinstance(value, list):
        return [_render_with_variables(item, variables) for item in value]

    return value


def _build_dataset_snapshot(dataset_obj: ApiRequestDataset | None) -> dict:
    if not dataset_obj:
        return {}

    return {
        "id": dataset_obj.id,
        "request_id": dataset_obj.request_id,
        "name": dataset_obj.name,
        "variables": copy.deepcopy(dataset_obj.variables or {}),
        "query_params": copy.deepcopy(dataset_obj.query_params or {}),
        "headers": copy.deepcopy(dataset_obj.headers or {}),
        "cookies": copy.deepcopy(dataset_obj.cookies or {}),
        "body_type": dataset_obj.body_type,
        "body_data": copy.deepcopy(dataset_obj.body_data or {}),
        "body_raw": dataset_obj.body_raw,
        "expected": copy.deepcopy(dataset_obj.expected or {}),
    }


def build_request_snapshot(
    request_obj: ApiRequest,
    dataset_obj: ApiRequestDataset | None = None,
    environment_obj: ApiEnvironment | None = None,
    runtime_variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    env_variables = copy.deepcopy((environment_obj.variables if environment_obj else None) or {})
    dataset_variables = copy.deepcopy((dataset_obj.variables if dataset_obj else None) or {})
    run_variables = copy.deepcopy(runtime_variables or {})
    variables = _deep_merge_dict(_deep_merge_dict(env_variables, dataset_variables), run_variables)

    query_params = _deep_merge_dict(request_obj.base_query_params or {}, (dataset_obj.query_params if dataset_obj else None) or {})
    headers = _deep_merge_dict(request_obj.base_headers or {}, (dataset_obj.headers if dataset_obj else None) or {})
    cookies = _deep_merge_dict(request_obj.base_cookies or {}, (dataset_obj.cookies if dataset_obj else None) or {})
    body_data = _deep_merge_dict(request_obj.base_body_data or {}, (dataset_obj.body_data if dataset_obj else None) or {})

    body_type = request_obj.body_type
    if dataset_obj and dataset_obj.body_type:
        body_type = dataset_obj.body_type

    body_raw = request_obj.base_body_raw
    if dataset_obj and dataset_obj.body_raw is not None:
        body_raw = dataset_obj.body_raw

    snapshot = {
        "request_id": request_obj.id,
        "env_id": environment_obj.id if environment_obj else request_obj.env_id,
        "dataset_id": dataset_obj.id if dataset_obj else None,
        "method": (request_obj.method or "GET").upper(),
        "url": request_obj.url,
        "query_params": query_params,
        "headers": headers,
        "cookies": cookies,
        "body_type": body_type,
        "body_data": body_data,
        "body_raw": body_raw,
        "timeout_ms": request_obj.timeout_ms,
        "follow_redirects": request_obj.follow_redirects,
        "verify_ssl": request_obj.verify_ssl,
        "proxy_url": request_obj.proxy_url,
        "variables": variables,
    }

    for key in ("url", "query_params", "headers", "cookies", "body_data", "body_raw", "proxy_url"):
        snapshot[key] = _render_with_variables(snapshot[key], variables)

    return snapshot


def _build_http_request_kwargs(request_snapshot: dict[str, Any]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "params": request_snapshot.get("query_params") or None,
        "headers": request_snapshot.get("headers") or None,
        "cookies": request_snapshot.get("cookies") or None,
    }

    body_type = request_snapshot.get("body_type")
    body_data = request_snapshot.get("body_data") or {}
    body_raw = request_snapshot.get("body_raw")

    if body_type == "json":
        kwargs["json"] = body_data
    elif body_type in {"form-urlencoded", "form-data"}:
        kwargs["data"] = body_data
    elif body_type == "raw":
        if body_raw is None and body_data:
            kwargs["content"] = json.dumps(body_data, ensure_ascii=False)
        else:
            kwargs["content"] = body_raw or ""
    elif body_type == "binary":
        if isinstance(body_raw, bytes):
            kwargs["content"] = body_raw
        elif isinstance(body_raw, str):
            kwargs["content"] = body_raw.encode("utf-8")
        elif body_raw is None:
            kwargs["content"] = b""
        else:
            kwargs["content"] = str(body_raw).encode("utf-8")

    return {k: v for k, v in kwargs.items() if v is not None}


async def _execute_http_request(request_snapshot: dict[str, Any]) -> dict[str, Any]:
    start = time.monotonic()
    timeout_sec = max(float(request_snapshot.get("timeout_ms", 30000)) / 1000.0, 0.001)
    client_kwargs: dict[str, Any] = {
        "timeout": timeout_sec,
        "follow_redirects": bool(request_snapshot.get("follow_redirects", True)),
        "verify": bool(request_snapshot.get("verify_ssl", True)),
    }
    proxy_url = request_snapshot.get("proxy_url")
    if proxy_url:
        client_kwargs["proxy"] = proxy_url

    try:
        async with httpx.AsyncClient(**client_kwargs) as client:
            request_kwargs = _build_http_request_kwargs(request_snapshot)
            response = await client.request(
                method=request_snapshot.get("method", "GET"),
                url=request_snapshot.get("url"),
                **request_kwargs,
            )
        elapsed_ms = int((time.monotonic() - start) * 1000)
        response_body = response.text
        if response_body and len(response_body) > MAX_RESPONSE_BODY_LENGTH:
            response_body = response_body[:MAX_RESPONSE_BODY_LENGTH]
        return {
            "is_success": bool(response.is_success),
            "response_status_code": response.status_code,
            "response_headers": dict(response.headers),
            "response_body": response_body,
            "response_time_ms": elapsed_ms,
            "error_message": None,
        }
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "is_success": False,
            "response_status_code": None,
            "response_headers": {},
            "response_body": None,
            "response_time_ms": elapsed_ms,
            "error_message": str(exc),
        }


async def execute_api_request(
    request_obj: ApiRequest,
    dataset_obj: ApiRequestDataset | None = None,
    environment_obj: ApiEnvironment | None = None,
    runtime_variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request_snapshot = build_request_snapshot(
        request_obj=request_obj,
        dataset_obj=dataset_obj,
        environment_obj=environment_obj,
        runtime_variables=runtime_variables,
    )
    exec_result = await _execute_http_request(request_snapshot)
    return {
        "request_snapshot": request_snapshot,
        "dataset_snapshot": _build_dataset_snapshot(dataset_obj),
        **exec_result,
    }

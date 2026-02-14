# -*- coding: utf-8 -*-
# @Time    : 2026/2/14
# @Author  : yangyuexiong
# @File    : variable_extractor.py

import json
import re
from http.cookies import SimpleCookie
from typing import Any

from app.models.api_request import ApiExtractRule


class ExtractRequiredError(Exception):
    pass


def _normalize_headers(headers: dict[str, Any] | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in (headers or {}).items():
        result[str(key).lower()] = value
    return result


def _extract_json_by_expr(data: Any, expr: str | None) -> tuple[bool, Any]:
    if expr is None or expr.strip() == "":
        return True, data

    path = expr.strip()
    if path.startswith("$."):
        path = path[2:]
    elif path.startswith("$"):
        path = path[1:]

    tokens: list[str | int] = []
    for chunk in path.split("."):
        if chunk == "":
            continue
        pos = 0
        while pos < len(chunk):
            left_bracket = chunk.find("[", pos)
            if left_bracket == -1:
                tokens.append(chunk[pos:])
                break
            if left_bracket > pos:
                tokens.append(chunk[pos:left_bracket])
            right_bracket = chunk.find("]", left_bracket + 1)
            if right_bracket == -1:
                return False, None
            index_text = chunk[left_bracket + 1:right_bracket].strip()
            if not index_text.isdigit():
                return False, None
            tokens.append(int(index_text))
            pos = right_bracket + 1

    current: Any = data
    for token in tokens:
        if isinstance(token, int):
            if isinstance(current, list) and 0 <= token < len(current):
                current = current[token]
            else:
                return False, None
        else:
            if isinstance(current, dict) and token in current:
                current = current[token]
            else:
                return False, None
    return True, current


def _extract_response_cookie(headers: dict[str, Any], expr: str | None) -> tuple[bool, Any]:
    if not expr:
        return False, None
    cookie_name = expr.strip()
    if not cookie_name:
        return False, None

    set_cookie_value = headers.get("set-cookie")
    if not set_cookie_value:
        return False, None

    simple_cookie = SimpleCookie()
    if isinstance(set_cookie_value, list):
        for item in set_cookie_value:
            simple_cookie.load(str(item))
    else:
        simple_cookie.load(str(set_cookie_value))

    morsel = simple_cookie.get(cookie_name)
    if morsel is None:
        return False, None
    return True, morsel.value


def _extract_from_response_json(response_body: str | None, expr: str | None) -> tuple[bool, Any]:
    if response_body is None:
        return False, None
    try:
        payload = json.loads(response_body)
    except Exception:
        return False, None
    return _extract_json_by_expr(payload, expr)


def _extract_from_response_regex(response_body: str | None, expr: str | None) -> tuple[bool, Any]:
    if response_body is None or not expr:
        return False, None
    try:
        pattern = re.compile(expr)
    except re.error:
        return False, None

    match = pattern.search(response_body)
    if not match:
        return False, None
    if match.groups():
        return True, match.group(1)
    return True, match.group(0)


def _extract_rule_value(
    rule: ApiExtractRule,
    execute_result: dict[str, Any],
    runtime_variables: dict[str, Any],
) -> tuple[bool, Any]:
    source_type = rule.source_type
    source_expr = rule.source_expr
    response_headers = _normalize_headers(execute_result.get("response_headers"))
    response_body = execute_result.get("response_body")
    response_status = execute_result.get("response_status_code")

    if source_type == "response_header":
        if not source_expr:
            return False, None
        key = source_expr.strip().lower()
        return (key in response_headers), response_headers.get(key)

    if source_type == "response_json":
        return _extract_from_response_json(response_body, source_expr)

    if source_type == "response_cookie":
        return _extract_response_cookie(response_headers, source_expr)

    if source_type == "response_text_regex":
        return _extract_from_response_regex(response_body, source_expr)

    if source_type == "response_status":
        return (response_status is not None), response_status

    if source_type == "session":
        key = (source_expr or rule.var_name).strip() if source_expr or rule.var_name else ""
        if not key:
            return False, None
        return (key in runtime_variables), runtime_variables.get(key)

    return False, None


def apply_extract_rules(
    rules: list[ApiExtractRule],
    execute_result: dict[str, Any],
    runtime_variables: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    extracted_variables: dict[str, Any] = {}
    records: list[dict[str, Any]] = []

    for rule in rules:
        found, value = _extract_rule_value(rule, execute_result, runtime_variables)
        if not found and rule.default_value is not None:
            found = True
            value = rule.default_value

        if not found:
            if rule.required:
                raise ExtractRequiredError(f"变量提取失败: {rule.var_name} ({rule.source_type}:{rule.source_expr})")
            continue

        extracted_variables[rule.var_name] = value
        records.append(
            {
                "var_name": rule.var_name,
                "var_value": value,
                "value_type": type(value).__name__,
                "source_type": rule.source_type,
                "source_expr": rule.source_expr,
                "scope": rule.scope,
                "is_secret": rule.is_secret,
            }
        )

    return extracted_variables, records


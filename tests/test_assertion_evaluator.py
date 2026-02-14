# -*- coding: utf-8 -*-

from app.models.api_request import ApiAssertRule
from app.services.assertion_evaluator import evaluate_assert_rules


def _build_assert_rule(**kwargs) -> ApiAssertRule:
    obj = ApiAssertRule(
        request_id=kwargs.pop("request_id", 1),
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
    obj.id = kwargs.pop("id", 100)
    for k, v in kwargs.items():
        setattr(obj, k, v)
    return obj


def test_status_code_assert_pass():
    rule = _build_assert_rule(assert_type="status_code", comparator="eq", expected_value=200)
    passed, records = evaluate_assert_rules([rule], {"response_status_code": 200})
    assert passed is True
    assert len(records) == 1
    assert records[0]["passed"] is True


def test_json_path_assert_fail():
    rule = _build_assert_rule(assert_type="json_path", source_expr="$.data.ok", comparator="eq", expected_value=True)
    passed, records = evaluate_assert_rules([rule], {"response_body": '{"data":{"ok":false}}'})
    assert passed is False
    assert len(records) == 1
    assert records[0]["passed"] is False
    assert "断言失败" in records[0]["detail"]


def test_text_contains_assert_pass():
    rule = _build_assert_rule(assert_type="text_contains", comparator="contains", expected_value="hello")
    passed, records = evaluate_assert_rules([rule], {"response_body": "hello world"})
    assert passed is True
    assert records[0]["passed"] is True

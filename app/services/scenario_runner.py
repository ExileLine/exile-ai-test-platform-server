# -*- coding: utf-8 -*-
# @Time    : 2026/2/14
# @Author  : yangyuexiong
# @File    : scenario_runner.py

import copy
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import CustomException
from app.models.api_request import (
    ApiEnvironment,
    ApiExtractRule,
    ApiRequest,
    ApiRequestDataset,
    ApiRequestRun,
    ApiRunVariable,
    TestScenario,
    TestScenarioCase,
    TestScenarioRun,
)
from app.services.api_request_executor import execute_api_request
from app.services.variable_extractor import ExtractRequiredError, apply_extract_rules


async def _get_environment_or_404(db: AsyncSession, env_id: int) -> ApiEnvironment:
    stmt = select(ApiEnvironment).where(and_(ApiEnvironment.id == env_id, ApiEnvironment.is_deleted == 0))
    obj = (await db.execute(stmt)).scalars().first()
    if not obj:
        raise CustomException(detail=f"环境 {env_id} 不存在", custom_code=10002)
    return obj


async def _get_request_or_404(db: AsyncSession, request_id: int) -> ApiRequest:
    stmt = select(ApiRequest).where(and_(ApiRequest.id == request_id, ApiRequest.is_deleted == 0))
    obj = (await db.execute(stmt)).scalars().first()
    if not obj:
        raise CustomException(detail=f"测试用例 {request_id} 不存在", custom_code=10002)
    return obj


async def _get_dataset_or_404(db: AsyncSession, dataset_id: int) -> ApiRequestDataset:
    stmt = select(ApiRequestDataset).where(and_(ApiRequestDataset.id == dataset_id, ApiRequestDataset.is_deleted == 0))
    obj = (await db.execute(stmt)).scalars().first()
    if not obj:
        raise CustomException(detail=f"数据集 {dataset_id} 不存在", custom_code=10002)
    return obj


async def _resolve_step_datasets(
    db: AsyncSession,
    request_obj: ApiRequest,
    scenario_case_obj: TestScenarioCase,
) -> list[ApiRequestDataset | None]:
    run_mode = scenario_case_obj.dataset_run_mode
    if run_mode == "single":
        if scenario_case_obj.dataset_id is None:
            raise CustomException(detail="步骤未配置固定数据集", custom_code=10005)
        dataset_obj = await _get_dataset_or_404(db, scenario_case_obj.dataset_id)
        if dataset_obj.request_id != request_obj.id:
            raise CustomException(detail="数据集与测试用例不匹配", custom_code=10005)
        if not dataset_obj.is_enabled:
            raise CustomException(detail="数据集已禁用", custom_code=10005)
        return [dataset_obj]

    if run_mode == "all":
        stmt = (
            select(ApiRequestDataset)
            .where(
                and_(
                    ApiRequestDataset.request_id == request_obj.id,
                    ApiRequestDataset.is_deleted == 0,
                    ApiRequestDataset.is_enabled.is_(True),
                )
            )
            .order_by(ApiRequestDataset.sort, ApiRequestDataset.id)
        )
        dataset_list = (await db.execute(stmt)).scalars().all()
        if dataset_list:
            return dataset_list
        return [None]

    # request_default
    if request_obj.default_dataset_id:
        dataset_obj = await _get_dataset_or_404(db, request_obj.default_dataset_id)
        if dataset_obj.request_id != request_obj.id:
            raise CustomException(detail="默认数据集与测试用例不匹配", custom_code=10005)
        if not dataset_obj.is_enabled:
            raise CustomException(detail="默认数据集已禁用", custom_code=10005)
        return [dataset_obj]
    return [None]


async def _query_extract_rules(
    db: AsyncSession,
    request_id: int,
    dataset_id: int | None,
) -> list[ApiExtractRule]:
    stmt = (
        select(ApiExtractRule)
        .where(
            and_(
                ApiExtractRule.request_id == request_id,
                ApiExtractRule.is_deleted == 0,
                ApiExtractRule.is_enabled.is_(True),
            )
        )
        .order_by(ApiExtractRule.sort, ApiExtractRule.id)
    )
    all_rules = (await db.execute(stmt)).scalars().all()
    result: list[ApiExtractRule] = []
    for rule in all_rules:
        if rule.dataset_id is None:
            result.append(rule)
        elif dataset_id is not None and rule.dataset_id == dataset_id:
            result.append(rule)
    return result


async def run_test_scenario(
    *,
    db: AsyncSession,
    scenario_obj: TestScenario,
    env_id: int | None = None,
    trigger_type: str = "manual",
    initial_variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    runtime_variables: dict[str, Any] = copy.deepcopy(initial_variables or {})

    resolved_env_id = env_id if env_id is not None else scenario_obj.env_id
    environment_obj = None
    if resolved_env_id is not None:
        environment_obj = await _get_environment_or_404(db, resolved_env_id)

    scenario_run = TestScenarioRun(
        scenario_id=scenario_obj.id,
        trigger_type=trigger_type,
        total_request_runs=0,
        success_request_runs=0,
        failed_request_runs=0,
        is_success=False,
        runtime_variables={},
        error_message=None,
    )
    db.add(scenario_run)
    await db.flush()

    stmt = (
        select(TestScenarioCase)
        .where(
            and_(
                TestScenarioCase.scenario_id == scenario_obj.id,
                TestScenarioCase.is_deleted == 0,
                TestScenarioCase.is_enabled.is_(True),
            )
        )
        .order_by(TestScenarioCase.step_no, TestScenarioCase.id)
    )
    step_list = (await db.execute(stmt)).scalars().all()

    stop_message = None
    for step in step_list:
        request_obj = await _get_request_or_404(db, step.request_id)
        dataset_list = await _resolve_step_datasets(db, request_obj, step)

        for dataset_obj in dataset_list:
            execute_result = await execute_api_request(
                request_obj=request_obj,
                dataset_obj=dataset_obj,
                environment_obj=environment_obj,
                runtime_variables=runtime_variables,
            )

            run_obj = ApiRequestRun(
                request_id=request_obj.id,
                scenario_run_id=scenario_run.id,
                scenario_id=scenario_obj.id,
                scenario_case_id=step.id,
                dataset_id=dataset_obj.id if dataset_obj else None,
                dataset_snapshot=execute_result["dataset_snapshot"],
                request_snapshot=execute_result["request_snapshot"],
                response_status_code=execute_result["response_status_code"],
                response_headers=execute_result["response_headers"],
                response_body=execute_result["response_body"],
                response_time_ms=execute_result["response_time_ms"],
                is_success=execute_result["is_success"],
                error_message=execute_result["error_message"],
            )
            db.add(run_obj)
            await db.flush()

            request_obj.execute_count = (request_obj.execute_count or 0) + 1
            request_obj.touch()

            extract_error = None
            rule_records: list[dict[str, Any]] = []
            extracted_variables: dict[str, Any] = {}
            try:
                rules = await _query_extract_rules(db, request_obj.id, dataset_obj.id if dataset_obj else None)
                extracted_variables, rule_records = apply_extract_rules(rules, execute_result, runtime_variables)
            except ExtractRequiredError as exc:
                extract_error = str(exc)
                run_obj.is_success = False

            if extract_error:
                if run_obj.error_message:
                    run_obj.error_message = f"{run_obj.error_message}; {extract_error}"
                else:
                    run_obj.error_message = extract_error

            for item in rule_records:
                db.add(
                    ApiRunVariable(
                        scenario_run_id=scenario_run.id,
                        request_run_id=run_obj.id,
                        scenario_case_id=step.id,
                        request_id=request_obj.id,
                        dataset_id=dataset_obj.id if dataset_obj else None,
                        var_name=item["var_name"],
                        var_value=item["var_value"],
                        value_type=item["value_type"],
                        source_type=item["source_type"],
                        source_expr=item["source_expr"],
                        scope=item["scope"],
                        is_secret=item["is_secret"],
                    )
                )

            for item in rule_records:
                if item["scope"] in {"scenario", "global"}:
                    runtime_variables[item["var_name"]] = item["var_value"]

            scenario_run.total_request_runs += 1
            if run_obj.is_success:
                scenario_run.success_request_runs += 1
            else:
                scenario_run.failed_request_runs += 1
                stop_on_fail = bool(step.stop_on_fail or scenario_obj.stop_on_fail)
                if stop_on_fail:
                    stop_message = (
                        f"步骤 {step.step_no} 执行失败: request_id={request_obj.id}, "
                        f"dataset_id={dataset_obj.id if dataset_obj else 'none'}"
                    )
                    break

        if stop_message:
            break

    scenario_run.is_success = scenario_run.failed_request_runs == 0
    scenario_run.runtime_variables = runtime_variables
    scenario_run.error_message = stop_message
    scenario_run.touch()

    return {
        "scenario_run_id": scenario_run.id,
        "scenario_id": scenario_obj.id,
        "is_success": scenario_run.is_success,
        "total_request_runs": scenario_run.total_request_runs,
        "success_request_runs": scenario_run.success_request_runs,
        "failed_request_runs": scenario_run.failed_request_runs,
        "error_message": scenario_run.error_message,
        "runtime_variables": runtime_variables,
    }


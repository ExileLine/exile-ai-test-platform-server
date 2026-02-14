# -*- coding: utf-8 -*-
# @Time    : 2026/2/14
# @Author  : yangyuexiong
# @File    : scenario.py

from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import CustomException
from app.core.pagination import CommonPaginateQuery
from app.core.response import api_response
from app.core.security import check_admin_existence
from app.db.session import get_db_session
from app.models.admin import Admin
from app.models.api_request import ApiRequest, ApiRequestDataset, ApiRequestRun, TestScenario, TestScenarioCase, TestScenarioRun
from app.services.scenario_task_dispatcher import dispatch_scenario_run_task
from app.services.scenario_runner import build_scenario_run_result
from app.schemas.scenario import (
    TestScenarioCancelRunReqData,
    TestScenarioCaseCreateReqData,
    TestScenarioCaseDeleteReqData,
    TestScenarioCasePageReqData,
    TestScenarioCaseReorderReqData,
    TestScenarioCaseSetDatasetStrategyReqData,
    TestScenarioCaseUpdateReqData,
    TestScenarioCreateReqData,
    TestScenarioDeleteReqData,
    TestScenarioPageReqData,
    TestScenarioRunReqData,
    TestScenarioUpdateReqData,
)

router = APIRouter()


async def _get_scenario_or_404(db: AsyncSession, scenario_id: int) -> TestScenario:
    stmt = select(TestScenario).where(and_(TestScenario.id == scenario_id, TestScenario.is_deleted == 0))
    obj = (await db.execute(stmt)).scalars().first()
    if not obj:
        raise CustomException(detail=f"测试场景 {scenario_id} 不存在", custom_code=10002)
    return obj


async def _get_scenario_case_or_404(db: AsyncSession, scenario_case_id: int) -> TestScenarioCase:
    stmt = select(TestScenarioCase).where(and_(TestScenarioCase.id == scenario_case_id, TestScenarioCase.is_deleted == 0))
    obj = (await db.execute(stmt)).scalars().first()
    if not obj:
        raise CustomException(detail=f"场景步骤 {scenario_case_id} 不存在", custom_code=10002)
    return obj


async def _get_scenario_run_or_404(db: AsyncSession, scenario_run_id: int) -> TestScenarioRun:
    stmt = select(TestScenarioRun).where(and_(TestScenarioRun.id == scenario_run_id, TestScenarioRun.is_deleted == 0))
    obj = (await db.execute(stmt)).scalars().first()
    if not obj:
        raise CustomException(detail=f"场景运行 {scenario_run_id} 不存在", custom_code=10002)
    return obj


async def _get_api_request_or_404(db: AsyncSession, request_id: int) -> ApiRequest:
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


async def _validate_dataset_relation(db: AsyncSession, request_id: int, dataset_id: int):
    dataset_obj = await _get_dataset_or_404(db, dataset_id)
    if dataset_obj.request_id != request_id:
        raise CustomException(detail="数据集与测试用例不匹配", custom_code=10005)


async def _list_active_scenario_steps(db: AsyncSession, scenario_id: int) -> list[TestScenarioCase]:
    stmt = (
        select(TestScenarioCase)
        .where(and_(TestScenarioCase.scenario_id == scenario_id, TestScenarioCase.is_deleted == 0))
        .order_by(TestScenarioCase.step_no, TestScenarioCase.id)
    )
    return (await db.execute(stmt)).scalars().all()


async def _normalize_scenario_step_no(db: AsyncSession, scenario_id: int) -> list[TestScenarioCase]:
    step_list = await _list_active_scenario_steps(db, scenario_id)
    for index, step_obj in enumerate(step_list, start=1):
        if step_obj.step_no != index:
            step_obj.step_no = index
            step_obj.touch()
    return step_list


async def _reorder_scenario_step(
        db: AsyncSession,
        scenario_id: int,
        scenario_case_obj: TestScenarioCase,
        target_step_no: int,
) -> int:
    step_list = await _list_active_scenario_steps(db, scenario_id)
    remained_steps = [item for item in step_list if item.id != scenario_case_obj.id]

    max_step_no = len(remained_steps) + 1
    target_step_no = max(1, min(target_step_no, max_step_no))

    remained_steps.insert(target_step_no - 1, scenario_case_obj)
    for index, step_obj in enumerate(remained_steps, start=1):
        if step_obj.step_no != index:
            step_obj.step_no = index
            step_obj.touch()

    return target_step_no


async def _get_scenario_for_report(db: AsyncSession, scenario_id: int) -> TestScenario | None:
    stmt = select(TestScenario).where(TestScenario.id == scenario_id)
    return (await db.execute(stmt)).scalars().first()


async def _list_scenario_steps_for_report(db: AsyncSession, scenario_id: int) -> list[TestScenarioCase]:
    stmt = (
        select(TestScenarioCase)
        .where(
            and_(
                TestScenarioCase.scenario_id == scenario_id,
                TestScenarioCase.is_deleted == 0,
                TestScenarioCase.is_enabled.is_(True),
            )
        )
        .order_by(TestScenarioCase.step_no, TestScenarioCase.id)
    )
    return (await db.execute(stmt)).scalars().all()


async def _list_request_runs_for_report(db: AsyncSession, scenario_run_id: int) -> list[ApiRequestRun]:
    stmt = (
        select(ApiRequestRun)
        .where(and_(ApiRequestRun.scenario_run_id == scenario_run_id, ApiRequestRun.is_deleted == 0))
        .order_by(ApiRequestRun.id)
    )
    return (await db.execute(stmt)).scalars().all()


def _build_scenario_run_report(
    scenario_run: TestScenarioRun,
    scenario_obj: TestScenario | None,
    step_list: list[TestScenarioCase],
    run_list: list[ApiRequestRun],
) -> dict[str, Any]:
    step_report_map: dict[int, dict[str, Any]] = {}
    for step_obj in step_list:
        step_report_map[step_obj.id] = {
            "scenario_case_id": step_obj.id,
            "step_no": step_obj.step_no,
            "request_id": step_obj.request_id,
            "dataset_run_mode": step_obj.dataset_run_mode,
            "dataset_id": step_obj.dataset_id,
            "run_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "is_success": False,
            "total_response_time_ms": 0,
            "avg_response_time_ms": None,
            "max_response_time_ms": None,
            "min_response_time_ms": None,
            "last_run_id": None,
            "last_status_code": None,
            "last_error_message": None,
            "_timed_count": 0,
        }

    failed_runs: list[dict[str, Any]] = []
    total_response_time_ms = 0
    total_timed_count = 0
    max_response_time_ms = None
    min_response_time_ms = None

    for run_obj in run_list:
        step_key = run_obj.scenario_case_id if run_obj.scenario_case_id is not None else -int(run_obj.id or 0)
        if step_key not in step_report_map:
            step_report_map[step_key] = {
                "scenario_case_id": run_obj.scenario_case_id,
                "step_no": None,
                "request_id": run_obj.request_id,
                "dataset_run_mode": None,
                "dataset_id": run_obj.dataset_id,
                "run_count": 0,
                "success_count": 0,
                "failed_count": 0,
                "is_success": False,
                "total_response_time_ms": 0,
                "avg_response_time_ms": None,
                "max_response_time_ms": None,
                "min_response_time_ms": None,
                "last_run_id": None,
                "last_status_code": None,
                "last_error_message": None,
                "_timed_count": 0,
            }

        report_item = step_report_map[step_key]
        report_item["run_count"] += 1
        if run_obj.is_success:
            report_item["success_count"] += 1
        else:
            report_item["failed_count"] += 1
            failed_runs.append(
                {
                    "run_id": run_obj.id,
                    "scenario_case_id": run_obj.scenario_case_id,
                    "step_no": report_item["step_no"],
                    "request_id": run_obj.request_id,
                    "dataset_id": run_obj.dataset_id,
                    "response_status_code": run_obj.response_status_code,
                    "response_time_ms": run_obj.response_time_ms,
                    "error_message": run_obj.error_message,
                }
            )

        if run_obj.response_time_ms is not None:
            report_item["total_response_time_ms"] += run_obj.response_time_ms
            report_item["_timed_count"] += 1
            if report_item["max_response_time_ms"] is None or run_obj.response_time_ms > report_item["max_response_time_ms"]:
                report_item["max_response_time_ms"] = run_obj.response_time_ms
            if report_item["min_response_time_ms"] is None or run_obj.response_time_ms < report_item["min_response_time_ms"]:
                report_item["min_response_time_ms"] = run_obj.response_time_ms

            total_response_time_ms += run_obj.response_time_ms
            total_timed_count += 1
            if max_response_time_ms is None or run_obj.response_time_ms > max_response_time_ms:
                max_response_time_ms = run_obj.response_time_ms
            if min_response_time_ms is None or run_obj.response_time_ms < min_response_time_ms:
                min_response_time_ms = run_obj.response_time_ms

        last_run_id = report_item["last_run_id"]
        if last_run_id is None or (run_obj.id is not None and run_obj.id > last_run_id):
            report_item["last_run_id"] = run_obj.id
            report_item["last_status_code"] = run_obj.response_status_code
            report_item["last_error_message"] = run_obj.error_message

    step_reports = list(step_report_map.values())
    for item in step_reports:
        timed_count = item.pop("_timed_count")
        item["is_success"] = item["run_count"] > 0 and item["failed_count"] == 0
        if timed_count > 0:
            item["avg_response_time_ms"] = round(item["total_response_time_ms"] / timed_count, 2)
        else:
            item["avg_response_time_ms"] = None
            item["max_response_time_ms"] = None
            item["min_response_time_ms"] = None

    step_reports.sort(
        key=lambda item: (
            item["step_no"] if item["step_no"] is not None else 10 ** 9,
            item["scenario_case_id"] if item["scenario_case_id"] is not None else 10 ** 9,
        )
    )

    total_request_runs = len(run_list)
    success_request_runs = len([item for item in run_list if item.is_success])
    failed_request_runs = total_request_runs - success_request_runs
    executed_step_total = len([item for item in step_reports if item["run_count"] > 0])
    failed_step_total = len([item for item in step_reports if item["failed_count"] > 0])

    summary = {
        "scenario_id": scenario_run.scenario_id,
        "scenario_name": scenario_obj.name if scenario_obj else None,
        "run_status": scenario_run.run_status,
        "is_success": scenario_run.is_success,
        "planned_step_total": len(step_list),
        "executed_step_total": executed_step_total,
        "failed_step_total": failed_step_total,
        "total_request_runs": total_request_runs,
        "success_request_runs": success_request_runs,
        "failed_request_runs": failed_request_runs,
        "success_rate": round(success_request_runs / total_request_runs, 4) if total_request_runs > 0 else 0.0,
        "total_response_time_ms": total_response_time_ms,
        "avg_response_time_ms": round(total_response_time_ms / total_timed_count, 2) if total_timed_count > 0 else None,
        "max_response_time_ms": max_response_time_ms,
        "min_response_time_ms": min_response_time_ms,
    }

    return {
        "scenario_run": build_scenario_run_result(scenario_run),
        "summary": summary,
        "step_reports": step_reports,
        "failed_runs": failed_runs,
    }


@router.post("/run", summary="执行测试场景(异步入队)")
async def run_scenario(
    request_data: TestScenarioRunReqData,
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    scenario_obj = await _get_scenario_or_404(db, request_data.scenario_id)

    scenario_run = TestScenarioRun(
        scenario_id=scenario_obj.id,
        env_id=request_data.env_id,
        trigger_type=request_data.trigger_type,
        run_status="queued",
        cancel_requested=False,
        total_request_runs=0,
        success_request_runs=0,
        failed_request_runs=0,
        is_success=False,
        runtime_variables=request_data.initial_variables,
        error_message=None,
    )
    db.add(scenario_run)
    await db.commit()
    await db.refresh(scenario_run)

    try:
        task_id = dispatch_scenario_run_task(scenario_run.id)
    except Exception as exc:
        scenario_run.run_status = "failed"
        scenario_run.error_message = f"入队失败: {str(exc)}"
        scenario_run.touch()
        await db.commit()
        raise CustomException(detail="场景执行入队失败", custom_code=500)

    result_data = build_scenario_run_result(scenario_run)
    if task_id:
        result_data["task_id"] = task_id
    return api_response(
        http_code=status.HTTP_202_ACCEPTED,
        code=202,
        data=result_data,
    )


@router.get("/run/{scenario_run_id}", summary="测试场景运行详情")
async def scenario_run_detail(
    scenario_run_id: int,
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    scenario_run = await _get_scenario_run_or_404(db, scenario_run_id)
    return api_response(data=build_scenario_run_result(scenario_run))


@router.get("/run/{scenario_run_id}/report", summary="测试场景执行报告")
async def scenario_run_report(
    scenario_run_id: int,
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    scenario_run = await _get_scenario_run_or_404(db, scenario_run_id)
    scenario_obj = await _get_scenario_for_report(db, scenario_run.scenario_id)
    step_list: list[TestScenarioCase] = []
    if scenario_obj:
        step_list = await _list_scenario_steps_for_report(db, scenario_obj.id)
    run_list = await _list_request_runs_for_report(db, scenario_run.id)
    report_data = _build_scenario_run_report(scenario_run, scenario_obj, step_list, run_list)
    return api_response(data=report_data)


@router.post("/run/cancel", summary="取消测试场景运行")
async def cancel_scenario_run(
    request_data: TestScenarioCancelRunReqData,
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    scenario_run = await _get_scenario_run_or_404(db, request_data.scenario_run_id)
    if scenario_run.run_status in {"success", "failed", "canceled"}:
        return api_response(code=10005, message=f"当前状态 {scenario_run.run_status} 不可取消")
    scenario_run.cancel_requested = True
    scenario_run.touch()
    await db.commit()
    return api_response(http_code=status.HTTP_201_CREATED, code=201, data=build_scenario_run_result(scenario_run))


@router.post("", summary="新增测试场景")
async def create_test_scenario(
        request_data: TestScenarioCreateReqData,
        admin: Admin = Depends(check_admin_existence),
        db: AsyncSession = Depends(get_db_session),
):
    save_data = request_data.model_dump(exclude_unset=True)
    obj = TestScenario(**save_data)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return api_response(http_code=status.HTTP_201_CREATED, code=201, data={"id": obj.id})


@router.put("", summary="编辑测试场景")
async def update_test_scenario(
        request_data: TestScenarioUpdateReqData,
        admin: Admin = Depends(check_admin_existence),
        db: AsyncSession = Depends(get_db_session),
):
    obj = await _get_scenario_or_404(db, request_data.id)
    update_data = request_data.model_dump(exclude_unset=True)
    update_data.pop("id", None)
    if update_data:
        for k, v in update_data.items():
            setattr(obj, k, v)
        obj.touch()
        await db.commit()
    return api_response(http_code=status.HTTP_201_CREATED, code=201)


@router.get("/{scenario_id}", summary="测试场景详情")
async def test_scenario_detail(
        scenario_id: int,
        admin: Admin = Depends(check_admin_existence),
        db: AsyncSession = Depends(get_db_session),
):
    obj = await _get_scenario_or_404(db, scenario_id)
    return api_response(data=jsonable_encoder(obj.to_dict()))


@router.post("/page", summary="测试场景分页")
async def test_scenario_page(
        request_data: TestScenarioPageReqData,
        admin: Admin = Depends(check_admin_existence),
        db: AsyncSession = Depends(get_db_session),
):
    pq = CommonPaginateQuery(
        request_data=request_data,
        orm_model=TestScenario,
        db_session=db,
        like_list=["name"],
        where_list=["is_deleted", "env_id", "run_mode"],
        order_by_list=["sort", "-update_time"],
        skip_list=["is_deleted"],
    )
    await pq.build_query()
    return api_response(data=pq.normal_data)


@router.delete("", summary="删除测试场景")
async def delete_test_scenario(
        request_data: TestScenarioDeleteReqData,
        admin: Admin = Depends(check_admin_existence),
        db: AsyncSession = Depends(get_db_session),
):
    obj = await _get_scenario_or_404(db, request_data.id)
    obj.is_deleted = admin.id
    obj.touch()

    step_list = await _list_active_scenario_steps(db, obj.id)
    for item in step_list:
        item.is_deleted = admin.id
        item.touch()

    await db.commit()
    return api_response(code=204)


@router.post("/case", summary="新增场景步骤")
async def create_test_scenario_case(
        request_data: TestScenarioCaseCreateReqData,
        admin: Admin = Depends(check_admin_existence),
        db: AsyncSession = Depends(get_db_session),
):
    await _get_scenario_or_404(db, request_data.scenario_id)
    await _get_api_request_or_404(db, request_data.request_id)

    dataset_id = request_data.dataset_id
    if request_data.dataset_run_mode == "single":
        await _validate_dataset_relation(db, request_data.request_id, dataset_id)
    else:
        dataset_id = None

    step_list = await _normalize_scenario_step_no(db, request_data.scenario_id)
    target_step_no = request_data.step_no
    if target_step_no is None:
        target_step_no = len(step_list) + 1
    else:
        target_step_no = max(1, min(target_step_no, len(step_list) + 1))
    for item in step_list:
        if item.step_no >= target_step_no:
            item.step_no += 1
            item.touch()

    save_data = request_data.model_dump(exclude_unset=True)
    save_data["dataset_id"] = dataset_id
    save_data["step_no"] = target_step_no
    obj = TestScenarioCase(**save_data)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return api_response(http_code=status.HTTP_201_CREATED, code=201, data={"id": obj.id})


@router.put("/case", summary="编辑场景步骤")
async def update_test_scenario_case(
        request_data: TestScenarioCaseUpdateReqData,
        admin: Admin = Depends(check_admin_existence),
        db: AsyncSession = Depends(get_db_session),
):
    obj = await _get_scenario_case_or_404(db, request_data.id)
    await _get_scenario_or_404(db, obj.scenario_id)

    update_data = request_data.model_dump(exclude_unset=True)
    update_data.pop("id", None)

    if "request_id" in update_data:
        await _get_api_request_or_404(db, update_data["request_id"])
    request_id = update_data.get("request_id", obj.request_id)

    dataset_run_mode = update_data.get("dataset_run_mode", obj.dataset_run_mode)
    dataset_id = update_data.get("dataset_id", obj.dataset_id)
    if dataset_run_mode == "single":
        if dataset_id is None:
            raise CustomException(detail="dataset_run_mode=single 时 dataset_id 必传", custom_code=10006)
        await _validate_dataset_relation(db, request_id, dataset_id)
    else:
        dataset_id = None
    if "dataset_run_mode" in update_data or "dataset_id" in update_data or request_id != obj.request_id:
        update_data["dataset_run_mode"] = dataset_run_mode
        update_data["dataset_id"] = dataset_id

    if update_data:
        for k, v in update_data.items():
            setattr(obj, k, v)
        obj.touch()
        await db.commit()

    return api_response(http_code=status.HTTP_201_CREATED, code=201)


@router.get("/case/{scenario_case_id}", summary="场景步骤详情")
async def test_scenario_case_detail(
        scenario_case_id: int,
        admin: Admin = Depends(check_admin_existence),
        db: AsyncSession = Depends(get_db_session),
):
    obj = await _get_scenario_case_or_404(db, scenario_case_id)
    await _get_scenario_or_404(db, obj.scenario_id)
    return api_response(data=jsonable_encoder(obj.to_dict()))


@router.post("/case/page", summary="场景步骤分页")
async def test_scenario_case_page(
        request_data: TestScenarioCasePageReqData,
        admin: Admin = Depends(check_admin_existence),
        db: AsyncSession = Depends(get_db_session),
):
    await _get_scenario_or_404(db, request_data.scenario_id)
    pq = CommonPaginateQuery(
        request_data=request_data,
        orm_model=TestScenarioCase,
        db_session=db,
        where_list=["scenario_id", "request_id", "is_deleted", "is_enabled", "dataset_run_mode"],
        order_by_list=["step_no", "id"],
        skip_list=["is_deleted", "is_enabled"],
    )
    await pq.build_query()
    return api_response(data=pq.normal_data)


@router.delete("/case", summary="删除场景步骤")
async def delete_test_scenario_case(
        request_data: TestScenarioCaseDeleteReqData,
        admin: Admin = Depends(check_admin_existence),
        db: AsyncSession = Depends(get_db_session),
):
    obj = await _get_scenario_case_or_404(db, request_data.id)
    obj.is_deleted = admin.id
    obj.touch()
    await _normalize_scenario_step_no(db, obj.scenario_id)
    await db.commit()
    return api_response(code=204)


@router.put("/case/reorder", summary="调整场景步骤顺序")
async def reorder_test_scenario_case(
        request_data: TestScenarioCaseReorderReqData,
        admin: Admin = Depends(check_admin_existence),
        db: AsyncSession = Depends(get_db_session),
):
    await _get_scenario_or_404(db, request_data.scenario_id)
    obj = await _get_scenario_case_or_404(db, request_data.id)
    if obj.scenario_id != request_data.scenario_id:
        raise CustomException(detail="场景步骤与场景不匹配", custom_code=10005)

    await _normalize_scenario_step_no(db, request_data.scenario_id)
    target_step_no = await _reorder_scenario_step(db, request_data.scenario_id, obj, request_data.step_no)
    await db.commit()
    return api_response(http_code=status.HTTP_201_CREATED, code=201, data={"id": obj.id, "step_no": target_step_no})


@router.put("/case/dataset-strategy", summary="设置步骤数据集策略")
async def set_test_scenario_case_dataset_strategy(
        request_data: TestScenarioCaseSetDatasetStrategyReqData,
        admin: Admin = Depends(check_admin_existence),
        db: AsyncSession = Depends(get_db_session),
):
    obj = await _get_scenario_case_or_404(db, request_data.id)
    await _get_scenario_or_404(db, obj.scenario_id)

    dataset_id = request_data.dataset_id
    if request_data.dataset_run_mode == "single":
        await _validate_dataset_relation(db, obj.request_id, dataset_id)
    else:
        dataset_id = None

    obj.dataset_run_mode = request_data.dataset_run_mode
    obj.dataset_id = dataset_id
    obj.touch()
    await db.commit()
    return api_response(http_code=status.HTTP_201_CREATED, code=201)

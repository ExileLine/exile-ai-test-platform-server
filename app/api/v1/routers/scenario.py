# -*- coding: utf-8 -*-
# @Time    : 2026/2/14
# @Author  : yangyuexiong
# @File    : scenario.py

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
from app.models.api_request import ApiRequest, ApiRequestDataset, TestScenario, TestScenarioCase
from app.services.scenario_runner import run_test_scenario
from app.schemas.scenario import (
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


@router.post("/run", summary="执行测试场景")
async def run_scenario(
    request_data: TestScenarioRunReqData,
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    scenario_obj = await _get_scenario_or_404(db, request_data.scenario_id)
    result = await run_test_scenario(
        db=db,
        scenario_obj=scenario_obj,
        env_id=request_data.env_id,
        trigger_type=request_data.trigger_type,
        initial_variables=request_data.initial_variables,
    )
    await db.commit()
    return api_response(http_code=status.HTTP_201_CREATED, code=201, data=result)

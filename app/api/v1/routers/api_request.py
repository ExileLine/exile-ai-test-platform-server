# -*- coding: utf-8 -*-
# @Time    : 2026/2/13
# @Author  : yangyuexiong
# @File    : api_request.py

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
from app.models.api_request import ApiEnvironment, ApiExtractRule, ApiRequest, ApiRequestDataset, ApiRequestRun, ApiRunVariable
from app.services.api_request_executor import execute_api_request
from app.services.variable_extractor import ExtractRequiredError, apply_extract_rules
from app.schemas.api_request import (
    ApiExtractRuleCreateReqData,
    ApiExtractRuleDeleteReqData,
    ApiExtractRulePageReqData,
    ApiExtractRuleUpdateReqData,
    ApiRequestCreateReqData,
    ApiRequestDatasetCreateReqData,
    ApiRequestDatasetDeleteReqData,
    ApiRequestDatasetPageReqData,
    ApiRequestDatasetSetDefaultReqData,
    ApiRequestDatasetSetEnabledReqData,
    ApiRequestDatasetUpdateReqData,
    ApiRequestDeleteReqData,
    ApiRequestPageReqData,
    ApiRequestRunReqData,
    ApiRequestUpdateReqData,
)

router = APIRouter()


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


async def _get_environment_or_404(db: AsyncSession, env_id: int) -> ApiEnvironment:
    stmt = select(ApiEnvironment).where(and_(ApiEnvironment.id == env_id, ApiEnvironment.is_deleted == 0))
    obj = (await db.execute(stmt)).scalars().first()
    if not obj:
        raise CustomException(detail=f"环境 {env_id} 不存在", custom_code=10002)
    return obj


async def _get_extract_rule_or_404(db: AsyncSession, rule_id: int) -> ApiExtractRule:
    stmt = select(ApiExtractRule).where(and_(ApiExtractRule.id == rule_id, ApiExtractRule.is_deleted == 0))
    obj = (await db.execute(stmt)).scalars().first()
    if not obj:
        raise CustomException(detail=f"提取规则 {rule_id} 不存在", custom_code=10002)
    return obj


async def _set_default_dataset(db: AsyncSession, request_obj: ApiRequest, dataset_obj: ApiRequestDataset):
    stmt = select(ApiRequestDataset).where(
        and_(ApiRequestDataset.request_id == request_obj.id, ApiRequestDataset.is_deleted == 0)
    )
    dataset_list = (await db.execute(stmt)).scalars().all()
    for item in dataset_list:
        item.is_default = item.id == dataset_obj.id
        item.touch()
    request_obj.default_dataset_id = dataset_obj.id
    request_obj.touch()


async def _resolve_dataset_for_run(
    db: AsyncSession,
    request_obj: ApiRequest,
    dataset_id: int | None,
) -> ApiRequestDataset | None:
    target_dataset_id = dataset_id
    if target_dataset_id is None and request_obj.default_dataset_id:
        target_dataset_id = request_obj.default_dataset_id
    if target_dataset_id is None:
        return None

    dataset_obj = await _get_dataset_or_404(db, target_dataset_id)
    if dataset_obj.request_id != request_obj.id:
        raise CustomException(detail="数据集与测试用例不匹配", custom_code=10005)
    if not dataset_obj.is_enabled:
        raise CustomException(detail="数据集已禁用", custom_code=10005)
    return dataset_obj


async def _list_extract_rules(db: AsyncSession, request_id: int, dataset_id: int | None) -> list[ApiExtractRule]:
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
    rule_list: list[ApiExtractRule] = []
    for item in all_rules:
        if item.dataset_id is None:
            rule_list.append(item)
        elif dataset_id is not None and item.dataset_id == dataset_id:
            rule_list.append(item)
    return rule_list


@router.post("", summary="新增测试用例")
async def create_api_request(
    request_data: ApiRequestCreateReqData,
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    save_data = request_data.model_dump(exclude_unset=True)
    save_data["creator_id"] = admin.id
    save_data["creator"] = admin.username
    obj = ApiRequest(**save_data)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return api_response(http_code=status.HTTP_201_CREATED, code=201, data={"id": obj.id})


@router.put("", summary="编辑测试用例")
async def update_api_request(
    request_data: ApiRequestUpdateReqData,
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    obj = await _get_api_request_or_404(db, request_data.id)
    update_data = request_data.model_dump(exclude_unset=True)
    update_data.pop("id", None)

    if update_data:
        update_data["modifier_id"] = admin.id
        update_data["modifier"] = admin.username
        for k, v in update_data.items():
            setattr(obj, k, v)
        obj.touch()
        await db.commit()

    return api_response(http_code=status.HTTP_201_CREATED, code=201)


@router.get("/{request_id}", summary="测试用例详情")
async def api_request_detail(
    request_id: int,
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    obj = await _get_api_request_or_404(db, request_id)
    return api_response(data=jsonable_encoder(obj.to_dict()))


@router.post("/page", summary="测试用例分页")
async def api_request_page(
    request_data: ApiRequestPageReqData,
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    pq = CommonPaginateQuery(
        request_data=request_data,
        orm_model=ApiRequest,
        db_session=db,
        like_list=["name", "url"],
        where_list=["creator_id", "case_status", "is_deleted", "is_public_visible", "creator_only_execute"],
        order_by_list=["-update_time"],
        skip_list=["is_deleted", "is_public_visible", "creator_only_execute"],
    )
    await pq.build_query()
    return api_response(data=pq.normal_data)


@router.delete("", summary="删除测试用例")
async def delete_api_request(
    request_data: ApiRequestDeleteReqData,
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    obj = await _get_api_request_or_404(db, request_data.id)
    obj.is_deleted = admin.id
    obj.modifier_id = admin.id
    obj.modifier = admin.username
    obj.default_dataset_id = None
    obj.touch()

    stmt = select(ApiRequestDataset).where(
        and_(ApiRequestDataset.request_id == obj.id, ApiRequestDataset.is_deleted == 0)
    )
    dataset_list = (await db.execute(stmt)).scalars().all()
    for item in dataset_list:
        item.is_deleted = admin.id
        item.is_default = False
        item.modifier_id = admin.id
        item.modifier = admin.username
        item.touch()

    await db.commit()
    return api_response(code=204)


@router.post("/run", summary="执行单个测试用例")
async def run_api_request(
    request_data: ApiRequestRunReqData,
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    request_obj = await _get_api_request_or_404(db, request_data.request_id)
    dataset_obj = await _resolve_dataset_for_run(db, request_obj, request_data.dataset_id)

    env_id = request_data.env_id if request_data.env_id is not None else request_obj.env_id
    env_obj = None
    if env_id is not None:
        env_obj = await _get_environment_or_404(db, env_id)

    exec_result = await execute_api_request(
        request_obj=request_obj,
        dataset_obj=dataset_obj,
        environment_obj=env_obj,
    )

    run_obj = ApiRequestRun(
        request_id=request_obj.id,
        scenario_run_id=None,
        scenario_id=None,
        scenario_case_id=None,
        dataset_id=dataset_obj.id if dataset_obj else None,
        dataset_snapshot=exec_result["dataset_snapshot"],
        request_snapshot=exec_result["request_snapshot"],
        response_status_code=exec_result["response_status_code"],
        response_headers=exec_result["response_headers"],
        response_body=exec_result["response_body"],
        response_time_ms=exec_result["response_time_ms"],
        is_success=exec_result["is_success"],
        error_message=exec_result["error_message"],
    )
    db.add(run_obj)
    await db.flush()

    extracted_variables: dict = {}
    try:
        rule_list = await _list_extract_rules(db, request_obj.id, dataset_obj.id if dataset_obj else None)
        extracted_variables, rule_records = apply_extract_rules(rule_list, exec_result, {})
    except ExtractRequiredError as exc:
        run_obj.is_success = False
        if run_obj.error_message:
            run_obj.error_message = f"{run_obj.error_message}; {str(exc)}"
        else:
            run_obj.error_message = str(exc)
        rule_records = []

    for item in rule_records:
        db.add(
            ApiRunVariable(
                scenario_run_id=None,
                request_run_id=run_obj.id,
                scenario_case_id=None,
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

    request_obj.execute_count = (request_obj.execute_count or 0) + 1
    request_obj.modifier_id = admin.id
    request_obj.modifier = admin.username
    request_obj.touch()

    await db.commit()
    await db.refresh(run_obj)
    return api_response(
        http_code=status.HTTP_201_CREATED,
        code=201,
        data={
            "run_id": run_obj.id,
            "request_id": request_obj.id,
            "dataset_id": run_obj.dataset_id,
            "is_success": run_obj.is_success,
            "response_status_code": run_obj.response_status_code,
            "response_time_ms": run_obj.response_time_ms,
            "error_message": run_obj.error_message,
            "extracted_variables": extracted_variables,
        },
    )


@router.post("/extract", summary="新增变量提取规则")
async def create_extract_rule(
    request_data: ApiExtractRuleCreateReqData,
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    request_obj = await _get_api_request_or_404(db, request_data.request_id)
    if request_data.dataset_id is not None:
        dataset_obj = await _get_dataset_or_404(db, request_data.dataset_id)
        if dataset_obj.request_id != request_obj.id:
            raise CustomException(detail="数据集与测试用例不匹配", custom_code=10005)

    save_data = request_data.model_dump(exclude_unset=True)
    obj = ApiExtractRule(**save_data)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return api_response(http_code=status.HTTP_201_CREATED, code=201, data={"id": obj.id})


@router.put("/extract", summary="编辑变量提取规则")
async def update_extract_rule(
    request_data: ApiExtractRuleUpdateReqData,
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    obj = await _get_extract_rule_or_404(db, request_data.id)
    request_obj = await _get_api_request_or_404(db, obj.request_id)

    update_data = request_data.model_dump(exclude_unset=True)
    update_data.pop("id", None)
    if "dataset_id" in update_data and update_data["dataset_id"] is not None:
        dataset_obj = await _get_dataset_or_404(db, update_data["dataset_id"])
        if dataset_obj.request_id != request_obj.id:
            raise CustomException(detail="数据集与测试用例不匹配", custom_code=10005)

    if update_data:
        for k, v in update_data.items():
            setattr(obj, k, v)
        obj.touch()
        await db.commit()
    return api_response(http_code=status.HTTP_201_CREATED, code=201)


@router.get("/extract/{rule_id}", summary="变量提取规则详情")
async def extract_rule_detail(
    rule_id: int,
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    obj = await _get_extract_rule_or_404(db, rule_id)
    return api_response(data=jsonable_encoder(obj.to_dict()))


@router.post("/extract/page", summary="变量提取规则分页")
async def extract_rule_page(
    request_data: ApiExtractRulePageReqData,
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    await _get_api_request_or_404(db, request_data.request_id)
    pq = CommonPaginateQuery(
        request_data=request_data,
        orm_model=ApiExtractRule,
        db_session=db,
        like_list=["var_name"],
        where_list=["request_id", "dataset_id", "is_deleted", "source_type"],
        order_by_list=["sort", "id"],
        skip_list=["is_deleted"],
    )
    await pq.build_query()
    return api_response(data=pq.normal_data)


@router.delete("/extract", summary="删除变量提取规则")
async def delete_extract_rule(
    request_data: ApiExtractRuleDeleteReqData,
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    obj = await _get_extract_rule_or_404(db, request_data.id)
    obj.is_deleted = admin.id
    obj.touch()
    await db.commit()
    return api_response(code=204)


@router.post("/dataset", summary="新增数据集")
async def create_api_request_dataset(
    request_data: ApiRequestDatasetCreateReqData,
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    request_obj = await _get_api_request_or_404(db, request_data.request_id)

    save_data = request_data.model_dump(exclude_unset=True)
    save_data["creator_id"] = admin.id
    save_data["creator"] = admin.username
    dataset_obj = ApiRequestDataset(**save_data)
    db.add(dataset_obj)
    await db.flush()

    if request_data.is_default or request_obj.default_dataset_id is None:
        await _set_default_dataset(db, request_obj, dataset_obj)

    await db.commit()
    await db.refresh(dataset_obj)
    return api_response(http_code=status.HTTP_201_CREATED, code=201, data={"id": dataset_obj.id})


@router.put("/dataset", summary="编辑数据集")
async def update_api_request_dataset(
    request_data: ApiRequestDatasetUpdateReqData,
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    dataset_obj = await _get_dataset_or_404(db, request_data.id)
    request_obj = await _get_api_request_or_404(db, dataset_obj.request_id)

    update_data = request_data.model_dump(exclude_unset=True)
    update_data.pop("id", None)
    is_default = update_data.pop("is_default", None)

    if update_data:
        update_data["modifier_id"] = admin.id
        update_data["modifier"] = admin.username
        for k, v in update_data.items():
            setattr(dataset_obj, k, v)
        dataset_obj.touch()

    if is_default is not None:
        if is_default:
            await _set_default_dataset(db, request_obj, dataset_obj)
        else:
            dataset_obj.is_default = False
            dataset_obj.touch()
            if request_obj.default_dataset_id == dataset_obj.id:
                request_obj.default_dataset_id = None
                request_obj.touch()

    await db.commit()
    return api_response(http_code=status.HTTP_201_CREATED, code=201)


@router.get("/dataset/{dataset_id}", summary="数据集详情")
async def api_request_dataset_detail(
    dataset_id: int,
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    obj = await _get_dataset_or_404(db, dataset_id)
    return api_response(data=jsonable_encoder(obj.to_dict()))


@router.post("/dataset/page", summary="数据集分页")
async def api_request_dataset_page(
    request_data: ApiRequestDatasetPageReqData,
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    await _get_api_request_or_404(db, request_data.request_id)

    pq = CommonPaginateQuery(
        request_data=request_data,
        orm_model=ApiRequestDataset,
        db_session=db,
        like_list=["name"],
        where_list=["request_id", "is_deleted", "is_enabled"],
        order_by_list=["sort", "id"],
        skip_list=["is_deleted", "is_enabled"],
    )
    await pq.build_query()
    return api_response(data=pq.normal_data)


@router.put("/dataset/default", summary="设置默认数据集")
async def set_default_dataset(
    request_data: ApiRequestDatasetSetDefaultReqData,
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    request_obj = await _get_api_request_or_404(db, request_data.request_id)
    dataset_obj = await _get_dataset_or_404(db, request_data.dataset_id)
    if dataset_obj.request_id != request_obj.id:
        raise CustomException(detail="数据集与测试用例不匹配", custom_code=10005)

    await _set_default_dataset(db, request_obj, dataset_obj)
    await db.commit()
    return api_response()


@router.put("/dataset/enabled", summary="启用/禁用数据集")
async def set_dataset_enabled(
    request_data: ApiRequestDatasetSetEnabledReqData,
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    dataset_obj = await _get_dataset_or_404(db, request_data.id)
    dataset_obj.is_enabled = request_data.is_enabled
    dataset_obj.modifier_id = admin.id
    dataset_obj.modifier = admin.username
    dataset_obj.touch()
    await db.commit()
    return api_response(http_code=status.HTTP_201_CREATED, code=201)


@router.delete("/dataset", summary="删除数据集")
async def delete_api_request_dataset(
    request_data: ApiRequestDatasetDeleteReqData,
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    dataset_obj = await _get_dataset_or_404(db, request_data.id)
    request_obj = await _get_api_request_or_404(db, dataset_obj.request_id)

    dataset_obj.is_deleted = admin.id
    dataset_obj.is_default = False
    dataset_obj.modifier_id = admin.id
    dataset_obj.modifier = admin.username
    dataset_obj.touch()

    if request_obj.default_dataset_id == dataset_obj.id:
        request_obj.default_dataset_id = None
        request_obj.touch()

    await db.commit()
    return api_response(code=204)

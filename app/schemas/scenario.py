# -*- coding: utf-8 -*-
# @Time    : 2026/2/14
# @Author  : yangyuexiong
# @File    : scenario.py

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.pagination import CommonPage

SCENARIO_RUN_MODE_VALUES = {"sequence", "parallel"}
SCENARIO_CASE_DATASET_RUN_MODE_VALUES = {"request_default", "single", "all"}


class TestScenarioCreateReqData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    env_id: Optional[int] = Field(default=None, description="默认环境ID")
    name: str = Field(description="场景名称", min_length=1, max_length=128)
    description: Optional[str] = Field(default=None, description="场景说明")
    run_mode: Literal["sequence", "parallel"] = Field(default="sequence", description="执行模式")
    stop_on_fail: bool = Field(default=True, description="失败是否中断")
    sort: int = Field(default=0, description="排序值")


class TestScenarioUpdateReqData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int = Field(description="场景ID")
    env_id: Optional[int] = Field(default=None, description="默认环境ID")
    name: Optional[str] = Field(default=None, description="场景名称", min_length=1, max_length=128)
    description: Optional[str] = Field(default=None, description="场景说明")
    run_mode: Optional[Literal["sequence", "parallel"]] = Field(default=None, description="执行模式")
    stop_on_fail: Optional[bool] = Field(default=None, description="失败是否中断")
    sort: Optional[int] = Field(default=None, description="排序值")


class TestScenarioDeleteReqData(BaseModel):
    id: int = Field(description="场景ID")


class TestScenarioPageReqData(CommonPage):
    is_deleted: int = 0
    env_id: Optional[int] = None
    run_mode: Optional[Literal["sequence", "parallel", "", None]] = None
    name: Optional[str] = None


class TestScenarioCaseCreateReqData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    scenario_id: int = Field(description="场景ID")
    request_id: int = Field(description="测试用例ID")
    step_no: Optional[int] = Field(default=None, ge=1, description="执行顺序")
    dataset_id: Optional[int] = Field(default=None, description="固定执行数据集ID")
    dataset_run_mode: Literal["request_default", "single", "all"] = Field(
        default="request_default",
        description="场景步骤数据集模式",
    )
    is_enabled: bool = Field(default=True, description="是否启用")
    stop_on_fail: bool = Field(default=True, description="步骤失败是否中断")

    @model_validator(mode="after")
    def validate_dataset_mode(self):
        if self.dataset_run_mode == "single" and self.dataset_id is None:
            raise ValueError("dataset_run_mode=single 时 dataset_id 必传")
        return self


class TestScenarioCaseUpdateReqData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int = Field(description="场景步骤ID")
    request_id: Optional[int] = Field(default=None, description="测试用例ID")
    dataset_id: Optional[int] = Field(default=None, description="固定执行数据集ID")
    dataset_run_mode: Optional[Literal["request_default", "single", "all"]] = Field(
        default=None,
        description="场景步骤数据集模式",
    )
    is_enabled: Optional[bool] = Field(default=None, description="是否启用")
    stop_on_fail: Optional[bool] = Field(default=None, description="步骤失败是否中断")

    @model_validator(mode="after")
    def validate_dataset_mode(self):
        if self.dataset_run_mode == "single" and self.dataset_id is None:
            raise ValueError("dataset_run_mode=single 时 dataset_id 必传")
        return self


class TestScenarioCaseDeleteReqData(BaseModel):
    id: int = Field(description="场景步骤ID")


class TestScenarioCasePageReqData(CommonPage):
    scenario_id: int
    is_deleted: int = 0
    request_id: Optional[int] = None
    is_enabled: Optional[bool] = None
    dataset_run_mode: Optional[Literal["request_default", "single", "all", "", None]] = None


class TestScenarioCaseReorderReqData(BaseModel):
    scenario_id: int = Field(description="场景ID")
    id: int = Field(description="场景步骤ID")
    step_no: int = Field(description="目标执行顺序", ge=1)


class TestScenarioCaseSetDatasetStrategyReqData(BaseModel):
    id: int = Field(description="场景步骤ID")
    dataset_run_mode: Literal["request_default", "single", "all"] = Field(description="场景步骤数据集模式")
    dataset_id: Optional[int] = Field(default=None, description="固定执行数据集ID")

    @model_validator(mode="after")
    def validate_dataset_mode(self):
        if self.dataset_run_mode == "single" and self.dataset_id is None:
            raise ValueError("dataset_run_mode=single 时 dataset_id 必传")
        return self


class TestScenarioRunReqData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    scenario_id: int = Field(description="场景ID")
    env_id: Optional[int] = Field(default=None, description="覆盖环境ID")
    trigger_type: Literal["manual", "schedule"] = Field(default="manual", description="触发类型")
    initial_variables: dict = Field(default_factory=dict, description="初始变量上下文")


class TestScenarioCancelRunReqData(BaseModel):
    scenario_run_id: int = Field(description="场景运行ID")

# -*- coding: utf-8 -*-
# @Time    : 2026/2/13
# @Author  : yangyuexiong
# @File    : api_request.py

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.pagination import CommonPage

HTTP_METHOD_VALUES = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
BODY_TYPE_VALUES = {"none", "json", "form-urlencoded", "form-data", "raw", "binary"}
EXTRACT_SOURCE_VALUES = {
    "response_header",
    "response_json",
    "response_cookie",
    "response_text_regex",
    "response_status",
    "session",
}
EXTRACT_SCOPE_VALUES = {"step", "scenario", "global"}


class ApiRequestCreateReqData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    env_id: Optional[int] = Field(default=None, description="默认环境ID")
    name: str = Field(description="测试用例名称", min_length=1, max_length=128)
    method: str = Field(default="GET", description="HTTP方法")
    url: str = Field(description="请求URL", min_length=1, max_length=2048)
    remark: Optional[str] = Field(default=None, description="备注")

    base_query_params: dict = Field(default_factory=dict, description="基础Query参数")
    base_headers: dict = Field(default_factory=dict, description="基础请求头")
    base_cookies: dict = Field(default_factory=dict, description="基础Cookies")

    body_type: str = Field(default="none", description="请求体类型")
    base_body_data: dict = Field(default_factory=dict, description="基础结构化请求体")
    base_body_raw: Optional[str] = Field(default=None, description="基础原始请求体")

    timeout_ms: int = Field(default=30000, ge=1, description="超时时间(毫秒)")
    follow_redirects: bool = Field(default=True, description="是否跟随重定向")
    verify_ssl: bool = Field(default=True, description="是否校验SSL证书")
    proxy_url: Optional[str] = Field(default=None, description="代理地址")
    sort: int = Field(default=0, description="排序值")

    execute_count: int = Field(default=0, ge=0, description="执行次数")
    case_status: Literal["已完成", "开发中", "调试中", "弃用"] = Field(default="开发中", description="用例状态")
    is_copied_case: bool = Field(default=False, description="是否复制生成")
    is_public_visible: bool = Field(default=False, description="是否公共可见")
    creator_only_execute: bool = Field(default=False, description="是否仅创建者执行")
    data_driven_enabled: bool = Field(default=True, description="是否开启数据驱动")
    dataset_run_mode: Literal["single", "all"] = Field(default="all", description="数据集执行模式")
    default_dataset_id: Optional[int] = Field(default=None, description="默认数据集ID")

    @field_validator("method")
    @classmethod
    def validate_method(cls, value: str) -> str:
        method = value.upper()
        if method not in HTTP_METHOD_VALUES:
            raise ValueError(f"method 必须是: {sorted(HTTP_METHOD_VALUES)}")
        return method

    @field_validator("body_type")
    @classmethod
    def validate_body_type(cls, value: str) -> str:
        if value not in BODY_TYPE_VALUES:
            raise ValueError(f"body_type 必须是: {sorted(BODY_TYPE_VALUES)}")
        return value


class ApiRequestUpdateReqData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int = Field(description="测试用例ID")
    env_id: Optional[int] = Field(default=None, description="默认环境ID")
    name: Optional[str] = Field(default=None, description="测试用例名称", min_length=1, max_length=128)
    method: Optional[str] = Field(default=None, description="HTTP方法")
    url: Optional[str] = Field(default=None, description="请求URL", min_length=1, max_length=2048)
    remark: Optional[str] = Field(default=None, description="备注")

    base_query_params: Optional[dict] = Field(default=None, description="基础Query参数")
    base_headers: Optional[dict] = Field(default=None, description="基础请求头")
    base_cookies: Optional[dict] = Field(default=None, description="基础Cookies")

    body_type: Optional[str] = Field(default=None, description="请求体类型")
    base_body_data: Optional[dict] = Field(default=None, description="基础结构化请求体")
    base_body_raw: Optional[str] = Field(default=None, description="基础原始请求体")

    timeout_ms: Optional[int] = Field(default=None, ge=1, description="超时时间(毫秒)")
    follow_redirects: Optional[bool] = Field(default=None, description="是否跟随重定向")
    verify_ssl: Optional[bool] = Field(default=None, description="是否校验SSL证书")
    proxy_url: Optional[str] = Field(default=None, description="代理地址")
    sort: Optional[int] = Field(default=None, description="排序值")

    execute_count: Optional[int] = Field(default=None, ge=0, description="执行次数")
    case_status: Optional[Literal["已完成", "开发中", "调试中", "弃用"]] = Field(default=None, description="用例状态")
    is_copied_case: Optional[bool] = Field(default=None, description="是否复制生成")
    is_public_visible: Optional[bool] = Field(default=None, description="是否公共可见")
    creator_only_execute: Optional[bool] = Field(default=None, description="是否仅创建者执行")
    data_driven_enabled: Optional[bool] = Field(default=None, description="是否开启数据驱动")
    dataset_run_mode: Optional[Literal["single", "all"]] = Field(default=None, description="数据集执行模式")
    default_dataset_id: Optional[int] = Field(default=None, description="默认数据集ID")

    @field_validator("method")
    @classmethod
    def validate_method(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        method = value.upper()
        if method not in HTTP_METHOD_VALUES:
            raise ValueError(f"method 必须是: {sorted(HTTP_METHOD_VALUES)}")
        return method

    @field_validator("body_type")
    @classmethod
    def validate_body_type(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if value not in BODY_TYPE_VALUES:
            raise ValueError(f"body_type 必须是: {sorted(BODY_TYPE_VALUES)}")
        return value


class ApiRequestDeleteReqData(BaseModel):
    id: int = Field(description="测试用例ID")


class ApiRequestPageReqData(CommonPage):
    is_deleted: int = 0
    creator_id: Optional[int] = None
    case_status: Optional[Literal["已完成", "开发中", "调试中", "弃用", "", None]] = None
    name: Optional[str] = None
    url: Optional[str] = None
    is_public_visible: Optional[bool] = None
    creator_only_execute: Optional[bool] = None


class ApiRequestDatasetCreateReqData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    request_id: int = Field(description="测试用例ID")
    name: str = Field(description="数据集名称", min_length=1, max_length=128)
    remark: Optional[str] = Field(default=None, description="备注")

    variables: dict = Field(default_factory=dict, description="变量字典")
    query_params: dict = Field(default_factory=dict, description="Query参数")
    headers: dict = Field(default_factory=dict, description="请求头")
    cookies: dict = Field(default_factory=dict, description="Cookies")
    body_type: Optional[str] = Field(default=None, description="请求体类型覆盖")
    body_data: dict = Field(default_factory=dict, description="结构化请求体")
    body_raw: Optional[str] = Field(default=None, description="原始请求体")
    expected: dict = Field(default_factory=dict, description="预期结果配置")
    is_default: bool = Field(default=False, description="是否默认数据集")
    is_enabled: bool = Field(default=True, description="是否启用")
    sort: int = Field(default=0, description="排序值")

    @field_validator("body_type")
    @classmethod
    def validate_body_type(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if value not in BODY_TYPE_VALUES:
            raise ValueError(f"body_type 必须是: {sorted(BODY_TYPE_VALUES)}")
        return value


class ApiRequestDatasetUpdateReqData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int = Field(description="数据集ID")
    name: Optional[str] = Field(default=None, description="数据集名称", min_length=1, max_length=128)
    remark: Optional[str] = Field(default=None, description="备注")

    variables: Optional[dict] = Field(default=None, description="变量字典")
    query_params: Optional[dict] = Field(default=None, description="Query参数")
    headers: Optional[dict] = Field(default=None, description="请求头")
    cookies: Optional[dict] = Field(default=None, description="Cookies")
    body_type: Optional[str] = Field(default=None, description="请求体类型覆盖")
    body_data: Optional[dict] = Field(default=None, description="结构化请求体")
    body_raw: Optional[str] = Field(default=None, description="原始请求体")
    expected: Optional[dict] = Field(default=None, description="预期结果配置")
    is_default: Optional[bool] = Field(default=None, description="是否默认数据集")
    is_enabled: Optional[bool] = Field(default=None, description="是否启用")
    sort: Optional[int] = Field(default=None, description="排序值")

    @field_validator("body_type")
    @classmethod
    def validate_body_type(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if value not in BODY_TYPE_VALUES:
            raise ValueError(f"body_type 必须是: {sorted(BODY_TYPE_VALUES)}")
        return value


class ApiRequestDatasetDeleteReqData(BaseModel):
    id: int = Field(description="数据集ID")


class ApiRequestDatasetSetDefaultReqData(BaseModel):
    request_id: int = Field(description="测试用例ID")
    dataset_id: int = Field(description="数据集ID")


class ApiRequestDatasetSetEnabledReqData(BaseModel):
    id: int = Field(description="数据集ID")
    is_enabled: bool = Field(description="是否启用")


class ApiRequestDatasetPageReqData(CommonPage):
    request_id: int
    is_deleted: int = 0
    is_enabled: Optional[bool] = None
    name: Optional[str] = None


class ApiRequestRunReqData(BaseModel):
    request_id: int = Field(description="测试用例ID")
    dataset_id: Optional[int] = Field(default=None, description="指定数据集ID")
    env_id: Optional[int] = Field(default=None, description="覆盖环境ID")


class ApiExtractRuleCreateReqData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    request_id: int = Field(description="测试用例ID")
    dataset_id: Optional[int] = Field(default=None, description="数据集ID(为空表示通用)")
    var_name: str = Field(description="变量名", min_length=1, max_length=64)
    source_type: Literal[
        "response_header",
        "response_json",
        "response_cookie",
        "response_text_regex",
        "response_status",
        "session",
    ] = Field(description="提取来源")
    source_expr: Optional[str] = Field(default=None, description="提取表达式")
    required: bool = Field(default=False, description="是否必需")
    default_value: Optional[Any] = Field(default=None, description="提取失败时默认值")
    scope: Literal["step", "scenario", "global"] = Field(default="scenario", description="变量作用域")
    is_secret: bool = Field(default=False, description="是否敏感变量")
    is_enabled: bool = Field(default=True, description="是否启用")
    sort: int = Field(default=0, description="排序值")


class ApiExtractRuleUpdateReqData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int = Field(description="提取规则ID")
    dataset_id: Optional[int] = Field(default=None, description="数据集ID")
    var_name: Optional[str] = Field(default=None, description="变量名", min_length=1, max_length=64)
    source_type: Optional[
        Literal[
            "response_header",
            "response_json",
            "response_cookie",
            "response_text_regex",
            "response_status",
            "session",
        ]
    ] = Field(default=None, description="提取来源")
    source_expr: Optional[str] = Field(default=None, description="提取表达式")
    required: Optional[bool] = Field(default=None, description="是否必需")
    default_value: Optional[Any] = Field(default=None, description="提取失败时默认值")
    scope: Optional[Literal["step", "scenario", "global"]] = Field(default=None, description="变量作用域")
    is_secret: Optional[bool] = Field(default=None, description="是否敏感变量")
    is_enabled: Optional[bool] = Field(default=None, description="是否启用")
    sort: Optional[int] = Field(default=None, description="排序值")


class ApiExtractRuleDeleteReqData(BaseModel):
    id: int = Field(description="提取规则ID")


class ApiExtractRulePageReqData(CommonPage):
    request_id: int
    dataset_id: Optional[int] = None
    is_deleted: int = 0
    var_name: Optional[str] = None
    source_type: Optional[
        Literal[
            "response_header",
            "response_json",
            "response_cookie",
            "response_text_regex",
            "response_status",
            "session",
            "",
            None,
        ]
    ] = None

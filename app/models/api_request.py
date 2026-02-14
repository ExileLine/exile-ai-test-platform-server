# -*- coding: utf-8 -*-
# @Time    : 2026/2/13
# @Author  : yangyuexiong
# @File    : api_request.py

from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import CustomBaseModel


class ApiEnvironment(CustomBaseModel):
    """请求环境变量"""

    __tablename__ = "exile_api_environments"

    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="环境名称")
    variables: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, comment="环境变量字典")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否默认环境")


class ApiRequest(CustomBaseModel):
    """测试用例(单个可执行 API 请求)"""

    __tablename__ = "exile_api_requests"

    env_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="默认环境ID")
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="测试用例名称")
    method: Mapped[str] = mapped_column(String(16), nullable=False, default="GET", comment="HTTP方法")
    url: Mapped[str] = mapped_column(String(2048), nullable=False, comment="请求URL")
    creator: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="创建人")
    creator_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="创建人ID")
    modifier: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="更新人")
    modifier_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="更新人ID")
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="备注")

    # 基础参数模板（执行时会与数据集参数合并）
    base_query_params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, comment="基础Query参数")
    base_headers: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, comment="基础请求头")
    base_cookies: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, comment="基础Cookies")

    body_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="none",
        comment="请求体类型:none/json/form-urlencoded/form-data/raw/binary",
    )
    base_body_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, comment="基础结构化请求体")
    base_body_raw: Mapped[str | None] = mapped_column(Text, nullable=True, comment="基础原始请求体")

    timeout_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=30000, comment="超时时间(毫秒)")
    follow_redirects: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否跟随重定向")
    verify_ssl: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否校验SSL证书")
    proxy_url: Mapped[str | None] = mapped_column(String(1024), nullable=True, comment="代理地址")
    sort: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序值")
    execute_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="执行次数")
    case_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="开发中",
        comment="用例状态:已完成/开发中/调试中/弃用",
    )
    is_copied_case: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否复制生成")
    is_public_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否公共可见")
    creator_only_execute: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否仅创建者执行")
    data_driven_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否开启数据驱动")
    dataset_run_mode: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="all",
        comment="数据集执行模式:single/all",
    )
    default_dataset_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="默认数据集ID")


class ApiRequestDataset(CustomBaseModel):
    """测试用例数据集(数据驱动参数)"""

    __tablename__ = "exile_api_request_datasets"

    request_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="测试用例ID")
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="数据集名称")
    creator: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="创建人")
    creator_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="创建人ID")
    modifier: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="更新人")
    modifier_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="更新人ID")
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="备注")
    variables: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="变量字典(可用于模板替换, 如 user_id/token)",
    )
    query_params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, comment="Query参数")
    headers: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, comment="请求头")
    cookies: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, comment="Cookies")
    body_type: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="请求体类型覆盖")
    body_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, comment="结构化请求体")
    body_raw: Mapped[str | None] = mapped_column(Text, nullable=True, comment="原始请求体")
    expected: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, comment="预期结果配置")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否默认数据集")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否启用")
    sort: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序值")


class TestScenario(CustomBaseModel):
    """测试场景(由多个测试用例组成)"""

    __tablename__ = "exile_test_scenarios"

    env_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="默认环境ID")
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="场景名称")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="场景说明")
    run_mode: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="sequence",
        comment="执行模式:sequence/parallel",
    )
    stop_on_fail: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="失败是否中断")
    sort: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序值")


class TestScenarioCase(CustomBaseModel):
    """场景-测试用例关联(定义场景中的执行步骤)"""

    __tablename__ = "exile_test_scenario_cases"

    scenario_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="场景ID")
    request_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="测试用例ID")
    step_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="执行顺序")
    dataset_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="固定执行数据集ID")
    dataset_run_mode: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="request_default",
        comment="场景步骤数据集模式:request_default/single/all",
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否启用")
    stop_on_fail: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="步骤失败是否中断")


class ApiRequestRun(CustomBaseModel):
    """测试用例执行记录"""

    __tablename__ = "exile_api_request_runs"

    request_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="测试用例ID")
    scenario_run_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="场景运行ID")
    scenario_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="场景ID(场景执行时记录)")
    scenario_case_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="场景步骤ID")
    dataset_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="数据集ID")
    dataset_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, comment="执行时数据集快照")
    request_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, comment="执行时请求快照")

    response_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="响应状态码")
    response_headers: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, comment="响应头")
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True, comment="响应体")
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="响应耗时(毫秒)")

    is_success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="执行是否成功")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="执行错误信息")


class ApiExtractRule(CustomBaseModel):
    """变量提取规则(定义如何从响应中提取变量)"""

    __tablename__ = "exile_api_extract_rules"

    request_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="测试用例ID")
    dataset_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="数据集ID(为空表示通用)")
    var_name: Mapped[str] = mapped_column(String(64), nullable=False, comment="变量名")
    source_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="提取来源:response_header/response_json/response_cookie/response_text_regex/response_status/session",
    )
    source_expr: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="提取表达式")
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否必需")
    default_value: Mapped[Any | None] = mapped_column(JSON, nullable=True, comment="提取失败时默认值")
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default="scenario", comment="变量作用域:step/scenario/global")
    is_secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否敏感变量")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否启用")
    sort: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序值")


class ApiAssertRule(CustomBaseModel):
    """断言规则(定义如何校验响应是否符合预期)"""

    __tablename__ = "exile_api_assert_rules"

    request_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="测试用例ID")
    dataset_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="数据集ID(为空表示通用)")
    assert_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="断言类型:status_code/json_path/text_contains",
    )
    source_expr: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="断言来源表达式")
    comparator: Mapped[str] = mapped_column(String(16), nullable=False, default="eq", comment="比较方式:eq/ne/contains/not_contains")
    expected_value: Mapped[Any | None] = mapped_column(JSON, nullable=True, comment="预期值")
    message: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="自定义失败提示")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否启用")
    sort: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序值")


class TestScenarioRun(CustomBaseModel):
    """场景执行记录"""

    __tablename__ = "exile_test_scenario_runs"

    scenario_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="场景ID")
    env_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="执行环境ID")
    trigger_type: Mapped[str] = mapped_column(String(16), nullable=False, default="manual", comment="触发类型:manual/schedule")
    run_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="queued",
        comment="运行状态:queued/running/success/failed/canceled",
    )
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否请求取消")
    total_request_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="请求执行总次数")
    success_request_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="请求执行成功次数")
    failed_request_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="请求执行失败次数")
    is_success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="场景执行是否成功")
    runtime_variables: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, comment="执行结束时变量上下文快照")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="场景执行错误信息")


class ApiRunVariable(CustomBaseModel):
    """执行过程变量记录"""

    __tablename__ = "exile_api_run_variables"

    scenario_run_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="场景运行ID")
    request_run_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="请求运行ID")
    scenario_case_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="场景步骤ID")
    request_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="测试用例ID")
    dataset_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="数据集ID")
    var_name: Mapped[str] = mapped_column(String(64), nullable=False, comment="变量名")
    var_value: Mapped[Any | None] = mapped_column(JSON, nullable=True, comment="变量值")
    value_type: Mapped[str] = mapped_column(String(32), nullable=False, default="str", comment="变量值类型")
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="提取来源")
    source_expr: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="提取表达式")
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default="scenario", comment="变量作用域")
    is_secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否敏感变量")

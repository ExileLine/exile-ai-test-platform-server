"""add extract rule and run variables

Revision ID: d0e5e02f03c1
Revises: af8bcd3faa4b
Create Date: 2026-02-14 12:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d0e5e02f03c1"
down_revision: Union[str, Sequence[str], None] = "af8bcd3faa4b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "exile_api_request_runs",
        sa.Column("scenario_run_id", sa.BigInteger(), nullable=True, comment="场景运行ID"),
    )

    op.create_table(
        "exile_api_extract_rules",
        sa.Column("request_id", sa.BigInteger(), nullable=False, comment="测试用例ID"),
        sa.Column("dataset_id", sa.BigInteger(), nullable=True, comment="数据集ID(为空表示通用)"),
        sa.Column("var_name", sa.String(length=64), nullable=False, comment="变量名"),
        sa.Column(
            "source_type",
            sa.String(length=32),
            nullable=False,
            comment="提取来源:response_header/response_json/response_cookie/response_text_regex/response_status/session",
        ),
        sa.Column("source_expr", sa.String(length=255), nullable=True, comment="提取表达式"),
        sa.Column("required", sa.Boolean(), nullable=False, comment="是否必需"),
        sa.Column("default_value", sa.JSON(), nullable=True, comment="提取失败时默认值"),
        sa.Column("scope", sa.String(length=16), nullable=False, comment="变量作用域:step/scenario/global"),
        sa.Column("is_secret", sa.Boolean(), nullable=False, comment="是否敏感变量"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, comment="是否启用"),
        sa.Column("sort", sa.Integer(), nullable=False, comment="排序值"),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="id"),
        sa.Column("create_time", sa.DateTime(timezone=True), nullable=False, comment="创建时间(结构化时间)"),
        sa.Column("create_timestamp", sa.BigInteger(), nullable=False, comment="创建时间(时间戳)"),
        sa.Column("update_time", sa.DateTime(timezone=True), nullable=False, comment="更新时间(结构化时间)"),
        sa.Column("update_timestamp", sa.BigInteger(), nullable=True, comment="更新时间(时间戳)"),
        sa.Column("is_deleted", sa.BigInteger(), nullable=True, comment="0正常;其他:已删除"),
        sa.Column("status", sa.Integer(), nullable=True, comment="状态"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "exile_test_scenario_runs",
        sa.Column("scenario_id", sa.BigInteger(), nullable=False, comment="场景ID"),
        sa.Column("env_id", sa.BigInteger(), nullable=True, comment="执行环境ID"),
        sa.Column("trigger_type", sa.String(length=16), nullable=False, comment="触发类型:manual/schedule"),
        sa.Column("run_status", sa.String(length=16), nullable=False, comment="运行状态:queued/running/success/failed/canceled"),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, comment="是否请求取消"),
        sa.Column("total_request_runs", sa.Integer(), nullable=False, comment="请求执行总次数"),
        sa.Column("success_request_runs", sa.Integer(), nullable=False, comment="请求执行成功次数"),
        sa.Column("failed_request_runs", sa.Integer(), nullable=False, comment="请求执行失败次数"),
        sa.Column("is_success", sa.Boolean(), nullable=False, comment="场景执行是否成功"),
        sa.Column("runtime_variables", sa.JSON(), nullable=False, comment="执行结束时变量上下文快照"),
        sa.Column("error_message", sa.Text(), nullable=True, comment="场景执行错误信息"),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="id"),
        sa.Column("create_time", sa.DateTime(timezone=True), nullable=False, comment="创建时间(结构化时间)"),
        sa.Column("create_timestamp", sa.BigInteger(), nullable=False, comment="创建时间(时间戳)"),
        sa.Column("update_time", sa.DateTime(timezone=True), nullable=False, comment="更新时间(结构化时间)"),
        sa.Column("update_timestamp", sa.BigInteger(), nullable=True, comment="更新时间(时间戳)"),
        sa.Column("is_deleted", sa.BigInteger(), nullable=True, comment="0正常;其他:已删除"),
        sa.Column("status", sa.Integer(), nullable=True, comment="状态"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "exile_api_run_variables",
        sa.Column("scenario_run_id", sa.BigInteger(), nullable=True, comment="场景运行ID"),
        sa.Column("request_run_id", sa.BigInteger(), nullable=False, comment="请求运行ID"),
        sa.Column("scenario_case_id", sa.BigInteger(), nullable=True, comment="场景步骤ID"),
        sa.Column("request_id", sa.BigInteger(), nullable=False, comment="测试用例ID"),
        sa.Column("dataset_id", sa.BigInteger(), nullable=True, comment="数据集ID"),
        sa.Column("var_name", sa.String(length=64), nullable=False, comment="变量名"),
        sa.Column("var_value", sa.JSON(), nullable=True, comment="变量值"),
        sa.Column("value_type", sa.String(length=32), nullable=False, comment="变量值类型"),
        sa.Column("source_type", sa.String(length=32), nullable=False, comment="提取来源"),
        sa.Column("source_expr", sa.String(length=255), nullable=True, comment="提取表达式"),
        sa.Column("scope", sa.String(length=16), nullable=False, comment="变量作用域"),
        sa.Column("is_secret", sa.Boolean(), nullable=False, comment="是否敏感变量"),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="id"),
        sa.Column("create_time", sa.DateTime(timezone=True), nullable=False, comment="创建时间(结构化时间)"),
        sa.Column("create_timestamp", sa.BigInteger(), nullable=False, comment="创建时间(时间戳)"),
        sa.Column("update_time", sa.DateTime(timezone=True), nullable=False, comment="更新时间(结构化时间)"),
        sa.Column("update_timestamp", sa.BigInteger(), nullable=True, comment="更新时间(时间戳)"),
        sa.Column("is_deleted", sa.BigInteger(), nullable=True, comment="0正常;其他:已删除"),
        sa.Column("status", sa.Integer(), nullable=True, comment="状态"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("exile_api_run_variables")
    op.drop_table("exile_test_scenario_runs")
    op.drop_table("exile_api_extract_rules")
    op.drop_column("exile_api_request_runs", "scenario_run_id")

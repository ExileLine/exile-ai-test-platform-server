# -*- coding: utf-8 -*-
# @Time    : 2026/2/14
# @Author  : yangyuexiong
# @File    : scenario_run_queue.py

from typing import Any

from sqlalchemy import and_, select, update

from app.db.session import AsyncSessionLocal
from app.models.api_request import TestScenario, TestScenarioRun
from app.services.scenario_runner import run_scenario_with_existing_run


async def process_scenario_run_message(payload: dict[str, Any]) -> bool:
    """按 scenario_run_id 执行一次场景任务（由 Celery 调用）"""
    scenario_run_id = payload.get("scenario_run_id")
    if not scenario_run_id:
        return False

    async with AsyncSessionLocal() as db:
        scenario_run = (
            await db.execute(select(TestScenarioRun).where(TestScenarioRun.id == int(scenario_run_id)))
        ).scalars().first()
        if not scenario_run:
            return False

        if scenario_run.run_status in {"success", "failed", "canceled"}:
            return True

        if scenario_run.run_status == "running":
            # 已被其他 worker 抢占执行，本次消息直接视为消费完成
            return True

        if scenario_run.cancel_requested:
            scenario_run.run_status = "canceled"
            scenario_run.is_success = False
            if not scenario_run.error_message:
                scenario_run.error_message = "场景执行已取消"
            scenario_run.touch()
            await db.commit()
            return True

        # 原子抢占: 仅 queued 状态可抢占，防止多 worker 重复执行
        claimed = await db.execute(
            update(TestScenarioRun)
            .where(and_(TestScenarioRun.id == scenario_run.id, TestScenarioRun.run_status == "queued"))
            .values(run_status="running")
        )
        if claimed.rowcount == 0:
            return True
        await db.commit()
        await db.refresh(scenario_run)

        scenario_obj = (
            await db.execute(
                select(TestScenario).where(and_(TestScenario.id == scenario_run.scenario_id, TestScenario.is_deleted == 0))
            )
        ).scalars().first()
        if not scenario_obj:
            scenario_run.run_status = "failed"
            scenario_run.is_success = False
            scenario_run.error_message = f"测试场景 {scenario_run.scenario_id} 不存在"
            scenario_run.touch()
            await db.commit()
            return True

        try:
            await run_scenario_with_existing_run(
                db=db,
                scenario_obj=scenario_obj,
                scenario_run=scenario_run,
            )
        except Exception as exc:
            scenario_run.run_status = "failed"
            scenario_run.is_success = False
            scenario_run.error_message = str(exc)
            scenario_run.touch()
        await db.commit()
        return True

# -*- coding: utf-8 -*-
# @Time    : 2026/2/14
# @Author  : yangyuexiong
# @File    : scenario_tasks.py

import asyncio

from loguru import logger

from app.services.scenario_run_queue import process_scenario_run_message
from app.tasks.celery_app import celery_app


@celery_app.task(name="scenario.run", bind=True)
def run_scenario_task(self, scenario_run_id: int) -> bool:
    """Celery task: 执行测试场景运行记录"""
    try:
        run_id = int(scenario_run_id)
    except Exception:
        logger.warning(f"场景执行任务参数非法: {scenario_run_id!r}")
        return False

    logger.info(f"Celery 开始执行场景: scenario_run_id={run_id}")
    return asyncio.run(process_scenario_run_message({"scenario_run_id": run_id}))

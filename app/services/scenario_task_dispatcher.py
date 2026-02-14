# -*- coding: utf-8 -*-
# @Time    : 2026/2/14
# @Author  : yangyuexiong
# @File    : scenario_task_dispatcher.py

from app.tasks.scenario_tasks import run_scenario_task


def dispatch_scenario_run_task(scenario_run_id: int) -> str | None:
    """派发场景执行任务到 Celery 队列"""
    result = run_scenario_task.delay(int(scenario_run_id))
    return result.id

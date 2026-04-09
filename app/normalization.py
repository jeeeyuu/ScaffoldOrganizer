import json
import re
import uuid
from typing import Iterable

from .models import Task


PRIORITY_MAP = {
    "🔴": "P0",
    "🟠": "P1",
    "🟡": "P2",
    "⚪": "P3",
    "P0": "P0",
    "P1": "P1",
    "P2": "P2",
    "P3": "P3",
}


def _normalize_priority(value: str | None) -> str:
    if not value:
        return "P2"
    return PRIORITY_MAP.get(value.strip(), "P2")


def _new_task(
    category: str,
    task: str,
    next_action: str,
    priority: str | None = None,
    tool: str | None = None,
    estimate_min: int | None = None,
    status: str = "TODO",
    notes: str | None = None,
) -> Task:
    return Task(
        id=str(uuid.uuid4()),
        priority=_normalize_priority(priority),
        category=category or "미분류",
        task=task,
        next_action=next_action or task,
        tool=tool,
        estimate_min=estimate_min,
        status=status,
        notes=notes,
    )


def _parse_json_task(blob: str) -> Task | None:
    try:
        payload = json.loads(blob)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    if "task" not in payload:
        return None
    return _new_task(
        category=payload.get("category", "미분류"),
        task=payload.get("task", ""),
        next_action=payload.get("next_action", ""),
        priority=payload.get("priority"),
        tool=payload.get("tool"),
        estimate_min=payload.get("estimate_min"),
        status=payload.get("status", "TODO"),
        notes=payload.get("notes"),
    )


def _parse_line_task(category: str, line: str) -> Task | None:
    if not line.strip():
        return None
    priority_match = re.match(r"^(?P<prio>[🔴🟠🟡⚪P0P1P2P3]+)\s+", line)
    priority = priority_match.group("prio") if priority_match else None
    cleaned = line
    if priority_match:
        cleaned = line[priority_match.end():]
    parts = [part.strip() for part in cleaned.split("|")]
    task = parts[0] if parts else cleaned.strip()
    next_action = parts[1] if len(parts) > 1 else task
    tool = parts[2] if len(parts) > 2 else None
    estimate = None
    if len(parts) > 3 and parts[3].isdigit():
        estimate = int(parts[3])
    return _new_task(
        category=category,
        task=task,
        next_action=next_action,
        priority=priority,
        tool=tool,
        estimate_min=estimate,
    )


def normalize_tasks(structured_output: dict) -> list[Task]:
    tasks: list[Task] = []
    top_priority = structured_output.get("top_priority", [])
    for item in top_priority:
        tasks.append(_new_task("최우선", item, item, priority="P0"))

    category_sections = structured_output.get("category_sections", [])
    if isinstance(category_sections, Iterable):
        for section in category_sections:
            if not isinstance(section, str):
                continue
            json_task = _parse_json_task(section)
            if json_task:
                tasks.append(json_task)
                continue
            if ":" in section:
                category, payload = section.split(":", 1)
                lines = [line.strip("- ") for line in payload.splitlines()]
            else:
                category = "미분류"
                lines = [line.strip("- ") for line in section.splitlines()]
            for line in lines:
                task_obj = _parse_line_task(category.strip(), line)
                if task_obj:
                    tasks.append(task_obj)

    if not tasks:
        tasks.append(_new_task("미분류", "작업을 수동으로 입력해주세요.", "작업을 수동으로 입력해주세요."))
    return tasks

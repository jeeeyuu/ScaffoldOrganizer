from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .models import Task


PRIORITY_ICONS = {
    "P0": "🔴",
    "P1": "🟠",
    "P2": "🟡",
    "P3": "⚪",
}
PRIORITY_EMOJIS = set(PRIORITY_ICONS.values()) | {"🟢", "🔵", "🟣"}


def _status_symbol(task: Task) -> str:
    return "✔︎" if task.status == "DONE" else "☐"


def _time_text(task: Task) -> str:
    value = task.estimate_min
    if value is None or value == "":
        return "-"
    if isinstance(value, str):
        return value if "분" in value else f"{value}분"
    return f"{value}분"


def _notes_text(task: Task) -> str:
    parts = []
    if task.next_action:
        parts.append(task.next_action)
    if task.notes:
        parts.append(task.notes)
    return " / ".join(parts) if parts else "-"


def build_markdown_table(tasks: list[Task]) -> str:
    lines = []
    lines.append("🧠 **통합 할 일 목록 (서버 불가 · 농진청 과제 최우선)**")
    lines.append("")
    lines.append(
        "| 🔢 Priority | 🧠 Task Description | 🛠 Tool | ⏱ Time | ✅ Status | 🧩 Notes / Context |"
    )
    lines.append("|:--:|---------------------------|----------|:--:|:--:|-------------------------|")
    for task in tasks:
        priority_icon = PRIORITY_ICONS.get(task.priority, "")
        if not priority_icon:
            for emoji in PRIORITY_EMOJIS:
                if emoji in str(task.priority):
                    priority_icon = emoji
                    break
        tool = task.tool or "-"
        line = (
            f"| {priority_icon} | {task.task} | {tool} | {_time_text(task)} |"
            f" {_status_symbol(task)} | {_notes_text(task)} |"
        )
        lines.append(line)
    lines.append("")
    return "\n".join(lines)


def export_markdown(
    tasks: list[Task],
    top_priority: list[str],
    export_dir: str,
    filename_format: str,
) -> Path:
    now = datetime.now()
    filename = now.strftime(filename_format)
    path = Path(export_dir) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    content = build_markdown_table(tasks)
    path.write_text(content, encoding="utf-8")
    return path

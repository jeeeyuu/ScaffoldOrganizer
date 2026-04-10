from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from nicegui import run, ui

from . import db
from .config import AppConfig, load_config
from .exporter import build_markdown_table, export_markdown
from .models import Task
from .normalization import normalize_tasks
from .normalize import parse_markdown_table
from .openai_client import call_with_prompt_id, normalize_response


@dataclass
class AppState:
    config: AppConfig
    session_id: str
    brain_dump_buffer: list[str] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)
    phase: str = "brain_dump"
    summary: str = ""
    notion_markdown_table: str = ""
    top_priority: list[str] = field(default_factory=list)
    pending_markdown: str = ""
    raw_output: str = ""
    last_structured_output: dict = field(default_factory=dict)
    last_user_payload: str = ""
    conversation: list[dict] = field(default_factory=list)
    model: str = ""
    usage: dict | None = None


def _new_session_id() -> str:
    return str(uuid.uuid4())


def _create_session_title() -> str:
    return datetime.now().strftime("세션 %Y-%m-%d %H:%M")


def _load_session(conn, session_id: str) -> tuple[list[dict], list[Task]]:
    messages = db.load_messages(conn, session_id)
    tasks = [
        Task(
            id=row["id"],
            priority=row["priority"],
            category=row["category"],
            task=row["task"],
            next_action=row["next_action"],
            tool=row["tool"],
            estimate_min=row["estimate_min"],
            status=row["status"],
            notes=row["notes"],
        )
        for row in db.load_tasks(conn, session_id)
    ]
    return messages, tasks


END_MARKERS = {"끝", "여기까지"}


def _split_end_marker(text: str) -> tuple[bool, str]:
    lines = text.splitlines()
    if not lines:
        return False, text
    def normalize_marker(value: str) -> str:
        return value.strip().rstrip(".!?")

    has_marker = False
    remaining: list[str] = []
    for line in lines:
        normalized = normalize_marker(line)
        if normalized in END_MARKERS:
            has_marker = True
            continue
        matched = False
        for marker in END_MARKERS:
            if normalized.endswith(marker):
                idx = line.rfind(marker)
                kept_line = line[:idx].rstrip() if idx != -1 else line
                if kept_line.strip():
                    remaining.append(kept_line)
                has_marker = True
                matched = True
                break
        if not matched:
            remaining.append(line)
    if not has_marker:
        return False, text
    return True, "\n".join(remaining)


def _ensure_end_marker(text: str) -> str:
    has_marker, _ = _split_end_marker(text)
    if has_marker:
        return text
    return f"{text}\n끝"


def _build_system_prompt(base_prompt: str, override: str) -> str:
    if not override:
        return base_prompt
    return f"{base_prompt}\n\n[추가 지시]\n{override}"


def _build_prompt_variables(values: dict) -> dict:
    payload = dict(values or {})
    if not payload.get("today_date"):
        payload["today_date"] = datetime.now().strftime("%Y-%m-%d")
    return payload


def _load_guide() -> str:
    guide_path = Path(__file__).resolve().parents[1] / "GUIDE.md"
    if not guide_path.exists():
        return "GUIDE.md 파일이 없습니다."
    return guide_path.read_text(encoding="utf-8")


def _extract_table_markdown(raw_text: str) -> str | None:
    if not raw_text:
        return None
    anchor = "## 🥑 우선순위 구조화 & 실행 원자화"
    start = raw_text.find(anchor)
    text = raw_text[start:] if start != -1 else raw_text
    lines = text.splitlines()
    return _find_markdown_table(lines)


def _find_markdown_table(lines: list[str]) -> str | None:
    candidate_blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if "|" in line:
            current.append(line)
        else:
            if len(current) >= 2:
                candidate_blocks.append(current)
            current = []
    if len(current) >= 2:
        candidate_blocks.append(current)
    if not candidate_blocks:
        return None
    # Prefer blocks that contain header separators or Rank/Priority labels.
    def score(block: list[str]) -> int:
        score_val = 0
        header = block[0]
        if "rank" in header.lower() or "priority" in header.lower() or "🔢" in header:
            score_val += 3
        if any("---" in line or ":--" in line for line in block[1:3]):
            score_val += 2
        score_val += len(block)
        return score_val

    best = max(candidate_blocks, key=score)
    return "\n".join(best)


def _is_probable_markdown(text: str) -> bool:
    if not text:
        return False
    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return False
    return (
        "## 🥑 우선순위 구조화 & 실행 원자화" in text
        or "## 🍎 브레인덤프 분류 및 구조화" in text
        or "| 🔢" in text
    )


def _priority_from_cell(value: str) -> str:
    cleaned = value.strip()
    return cleaned or "P2"


def _status_from_cell(value: str) -> str:
    if "✔" in value or "✅" in value:
        return "DONE"
    return "TODO"


def _estimate_from_cell(value: str) -> str | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned


def _strip_markdown(value: str) -> str:
    return value.replace("**", "").replace("__", "").strip()


def _format_usage(usage: dict | None) -> str:
    if not usage:
        return "사용량: 미수집"
    input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens")
    output_tokens = usage.get("output_tokens") or usage.get("completion_tokens")
    total_tokens = usage.get("total_tokens")
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    parts = [
        f"입력 {input_tokens if input_tokens is not None else '-'}",
        f"출력 {output_tokens if output_tokens is not None else '-'}",
        f"합계 {total_tokens if total_tokens is not None else '-'}",
    ]
    return "사용량: " + " / ".join(parts)


def _export_markdown_content(state: AppState) -> str:
    raw = state.raw_output.strip()
    if "## 🍎" in raw or "## 🥑" in raw:
        return raw
    if state.pending_markdown.strip():
        return state.pending_markdown.strip()
    if state.notion_markdown_table.strip():
        return _build_markdown_from_structured(state)
    return _build_markdown_from_structured(state)


def _build_markdown_from_structured(state: AppState) -> str:
    structured = state.last_structured_output or {}
    category_sections = structured.get("category_sections") or []
    top_priority = structured.get("top_priority") or []
    table = structured.get("notion_markdown_table") or build_markdown_table(state.tasks)

    lines = []
    lines.append("## 🍎 브레인덤프 분류 및 구조화")
    if state.summary:
        lines.append(state.summary)
    if category_sections:
        lines.append("")
        for section in category_sections:
            if isinstance(section, str) and section.strip():
                lines.append(section)
    lines.append("")
    lines.append("## 🥑 우선순위 조정 & 실행 원자화")
    if top_priority:
        for item in top_priority:
            lines.append(f"- {item}")
        lines.append("")
    if table:
        lines.append(table.strip())
    return "\n".join(lines).strip() + "\n"


def _normalize_table_key(key: str) -> str:
    return "".join(
        ch for ch in key.lower()
        if ch.isalnum() or ch in {"🔢", "🧠", "🛠", "⏱", "✅", "🧩"}
    )


def _lookup_field(lookup: dict, keys: list[str]) -> str:
    for key in keys:
        if key in lookup:
            return lookup[key]
    return ""


def _lookup_field_contains(lookup: dict, keys: list[str]) -> str:
    for key in keys:
        for lookup_key, value in lookup.items():
            if key in lookup_key:
                return value
    return ""


def _tasks_from_markdown_table(table_md: str) -> list[Task]:
    rows = parse_markdown_table(table_md)
    tasks: list[Task] = []
    for row in rows:
        lookup = {_normalize_table_key(k): v for k, v in row.items()}

        priority_cell = _lookup_field(lookup, ["🔢priority", "priority", "rank", "🔢rank"]) or _lookup_field_contains(
            lookup, ["priority", "rank", "🔢"]
        )
        task_text = _lookup_field(lookup, ["🧠taskdescription", "taskdescription", "task"]) or _lookup_field_contains(
            lookup, ["taskdescription", "task", "업무", "항목", "내용"]
        )
        tool_text = _lookup_field(lookup, ["🛠tool", "tool", "도구"]) or _lookup_field_contains(lookup, ["tool", "도구"])
        time_text = _lookup_field(lookup, ["⏱time", "time", "예상소요", "예상시간"]) or _lookup_field_contains(
            lookup, ["time", "예상", "소요", "시간"]
        )
        status_text = _lookup_field(lookup, ["✅status", "status", "상태"]) or _lookup_field_contains(lookup, ["status", "상태", "✅"])
        notes_text = _lookup_field(
            lookup, ["🧩notescontext", "notescontext", "notesnextstep", "notes", "nextstep", "비고"]
        ) or _lookup_field_contains(lookup, ["notes", "context", "비고", "nextstep", "next"])

        tasks.append(
            Task(
                id=str(uuid.uuid4()),
                priority=_priority_from_cell(priority_cell),
                category="미분류",
                task=task_text.strip(),
                next_action="",
                tool=tool_text.strip() or None,
                estimate_min=_estimate_from_cell(time_text),
                status=_status_from_cell(status_text),
                notes=notes_text.strip() or None,
            )
        )
    return tasks


def _tasks_from_tsv_table(raw_text: str) -> list[Task]:
    lines = [line for line in raw_text.splitlines() if "\t" in line]
    if len(lines) < 2:
        return []
    header = [cell.strip() for cell in lines[0].split("\t")]
    tasks: list[Task] = []
    for line in lines[1:]:
        cells = [cell.strip() for cell in line.split("\t")]
        if len(cells) < len(header):
            cells += [""] * (len(header) - len(cells))
        row = dict(zip(header, cells, strict=False))
        priority_cell = row.get("🔢 Rank") or row.get("Rank") or row.get("Priority") or ""
        task_text = row.get("🧠 Task Description (연구 항목 강조)") or row.get("🧠 Task Description") or row.get("Task") or ""
        tool_text = row.get("🛠 Tool/도구") or row.get("🛠 Tool") or row.get("Tool") or ""
        time_text = row.get("⏱ 예상 소요") or row.get("⏱ Time") or row.get("Time") or ""
        status_text = row.get("✅ Status") or row.get("Status") or ""
        notes_text = row.get("🧩 Notes / Next Step") or row.get("Notes") or ""

        tasks.append(
            Task(
                id=str(uuid.uuid4()),
                priority=_priority_from_cell(priority_cell),
                category="미분류",
                task=task_text.strip(),
                next_action="",
                tool=tool_text.strip() or None,
                estimate_min=_estimate_from_cell(time_text),
                status=_status_from_cell(status_text),
                notes=notes_text.strip() or None,
            )
        )
    return tasks


def build_ui(config: AppConfig | None = None) -> None:
    state = AppState(config=config or load_config(), session_id=_new_session_id())
    state.model = state.config.default_model

    ui.page_title("ScaffoldOrganizer")
    ui.add_head_html(
        """
        <link href="https://unpkg.com/tabulator-tables@5.5.2/dist/css/tabulator.min.css" rel="stylesheet">
        <script src="https://unpkg.com/tabulator-tables@5.5.2/dist/js/tabulator.min.js"></script>
        <style>
          .app-shell { max-width: 600px; margin: 0 auto; }
          .tabulator { font-size: 12px; background-color: #ffffff; }
        </style>
        """
    )

    with ui.column().classes("app-shell w-full gap-1 px-2 pt-2"):
        with ui.row().classes("w-full items-start gap-2"):
            input_area = ui.textarea(placeholder="브레인 덤프를 입력하세요.").props("rows=2").classes("flex-grow")
            with ui.column().classes("gap-1 items-stretch shrink-0"):
                ui.button("입력", on_click=lambda: handle_brain_dump()).classes("bg-blue-600 text-white")
                continuous_toggle = ui.switch("연속 입력", value=False).classes("text-xs")
        with ui.row().classes("w-full items-center gap-2"):
            assistant_preview = ui.markdown("(응답 없음)").classes("text-xs flex-grow").style("max-height:36px;overflow:hidden")
            usage_label = ui.label("사용량: -").classes("text-xs text-gray-400 shrink-0")

        with ui.tabs().classes("w-full") as tabs:
            ui.tab("ToDo")
            ui.tab("대화 로그")
            ui.tab("Raw 결과")
            ui.tab("GUIDE")
        with ui.tab_panels(tabs, value="ToDo").classes("w-full"):
            with ui.tab_panel("ToDo"):
                grid_container = ui.html('<div id="task-table"></div>', sanitize=False).classes("w-full").style("height: 350px")
                with ui.row().classes("w-full justify-between items-center pt-1"):
                    with ui.row().classes("gap-1"):
                        ui.button("저장", on_click=lambda: save_state()).props("dense")
                        ui.button("내보내기", on_click=lambda: export_md()).props("dense")
                        ui.button("MD 복사", on_click=lambda: copy_markdown()).props("dense")
                    with ui.row().classes("gap-1"):
                        ui.button("새 세션", on_click=lambda: new_session()).props("dense")
                        ui.button("불러오기", on_click=lambda: load_session()).props("dense")
            with ui.tab_panel("대화 로그"):
                log_area = ui.column().classes("w-full")
            with ui.tab_panel("Raw 결과"):
                raw_output_view = ui.textarea().props("readonly rows=5").classes("w-full")
                ui.label("전송 원문").classes("text-xs text-gray-500")
                raw_payload_view = ui.textarea().props("readonly rows=3").classes("w-full")
            with ui.tab_panel("GUIDE"):
                readme_view = ui.markdown(_load_guide()).classes("w-full text-xs")

        tabs.on("update:model-value", lambda e: refresh_tasks())

    def refresh_log() -> None:
        log_area.clear()
        with log_area:
            for message in state.messages[-10:]:
                label = f"{message['role']}: {message['content']}"
                ui.label(label).classes("text-sm").props("dense")

    def refresh_tasks() -> None:
        if ui.context.client is None:
            ui.timer(0.1, refresh_tasks, once=True)
            return
        rows = []
        for task in state.tasks:
            rows.append(
                {
                    "id": task.id,
                    "priority": _strip_markdown(str(task.priority)),
                    "category": task.category,
                    "task": _strip_markdown(task.task),
                    "tool": task.tool,
                    "estimate_min": task.estimate_min,
                    "done": task.status == "DONE",
                    "notes": task.notes,
                    "next_action": task.next_action,
                }
            )
        payload = json.dumps(rows, ensure_ascii=False)
        ui.run_javascript(
            f"""
            (() => {{
              const data = {payload};
              if (!window._taskTabulator) {{
                const cellTooltip = function(e, cell){{
                  const v = cell.getValue();
                  return v ? String(v) : "";
                }};
                const columns = [
                  {{title: "🔢", field: "priority", editor: "input", width: 60, hozAlign: "center"}},
                  {{title: "🧠 Task Description", field: "task", editor: "input", width: 420, tooltip: cellTooltip}},
                  {{title: "🛠 Tool", field: "tool", editor: "input", width: 140, tooltip: cellTooltip}},
                  {{title: "⏱", field: "estimate_min", editor: "input", width: 60, hozAlign: "center"}},
                  {{
                    title: "✅",
                    field: "done",
                    formatter: "tickCross",
                    editor: true,
                    width: 50,
                    hozAlign: "center",
                  }},
                  {{title: "🧩 Notes / Context", field: "notes", editor: "input", width: 280, tooltip: cellTooltip}},
                ];
                window._taskTabulator = new Tabulator("#task-table", {{
                  data,
                  columns,
                  layout: "fitData",
                  height: "350px",
                  reactiveData: false,
                  index: "id",
                  rowHeight: 32,
                }});
              }} else {{
                window._taskTabulator.replaceData(data);
              }}
            }})();
            """
        )

    async def update_state_from_grid() -> None:
        row_data = await ui.run_javascript(
            "window._taskTabulator ? window._taskTabulator.getData() : []"
        )
        tasks: list[Task] = []
        for row in row_data:
            tasks.append(
                Task(
                    id=row.get("id") or str(uuid.uuid4()),
                    priority=row.get("priority", "P2"),
                    category=row.get("category", "미분류"),
                    task=row.get("task", ""),
                    next_action=row.get("next_action", ""),
                    tool=row.get("tool"),
                    estimate_min=row.get("estimate_min"),
                    status="DONE" if row.get("done") else "TODO",
                    notes=row.get("notes"),
                )
            )
        state.tasks = tasks

    def append_message(role: str, content: str) -> None:
        state.messages.append({"role": role, "content": content})
        refresh_log()


    async def handle_brain_dump() -> None:
        text = input_area.value or ""
        if not text.strip():
            return
        input_area.value = ""
        if continuous_toggle.value:
            has_marker, remainder = _split_end_marker(text)
            if has_marker:
                if remainder.strip():
                    state.brain_dump_buffer.append(remainder)
                combined = "\n".join(state.brain_dump_buffer)
                state.brain_dump_buffer.clear()
                if not combined.strip():
                    ui.notify("브레인 덤프 내용이 비어 있습니다.")
                    return
                combined_with_marker = _ensure_end_marker(combined)
                append_message("user", combined)
                await submit_to_model(combined_with_marker)
            else:
                state.brain_dump_buffer.append(text)
                append_message("user", text)
        else:
            append_message("user", text)
            await submit_to_model(text)

    async def submit_to_model(user_text: str) -> None:
        if not user_text.strip():
            ui.notify("입력 내용이 비어 있습니다.")
            return
        state.last_user_payload = user_text
        try:
            prompt_id = state.config.prompt_id
            if not prompt_id:
                ui.notify("Prompt ID가 설정되지 않았습니다. config.json을 확인해 주세요.")
                return
            prompt_variables = _build_prompt_variables(state.config.prompt_variables)
            input_messages = [*state.conversation, {"role": "user", "content": user_text}]
            raw = await run.io_bound(
                call_with_prompt_id,
                api_key=state.config.openai_api_key,
                model=state.config.default_model,
                prompt_id=prompt_id,
                prompt_variables=prompt_variables,
                user_text=user_text,
                runtime_overrides=state.config.runtime_overrides,
                base_url=state.config.openai_base_url,
                input_messages=input_messages,
            )
        except Exception as exc:  # noqa: BLE001
            ui.notify(f"API 호출 실패: {exc}")
            return
        parsed = normalize_response(raw)
        state.phase = parsed["phase"]
        state.summary = parsed["summary"]
        state.usage = parsed.get("__usage")
        response_id = parsed.get("__response_id")
        state.last_structured_output = parsed.get("structured_output", {})
        state.notion_markdown_table = state.last_structured_output.get("notion_markdown_table", "")
        state.top_priority = state.last_structured_output.get("top_priority", [])
        raw_text = parsed.get("__raw_text", "")
        state.raw_output = raw_text
        state.pending_markdown = raw_text if _is_probable_markdown(raw_text) else ""
        append_message("assistant", state.summary)
        assistant_preview.set_content(state.summary or "(요약이 비어 있습니다.)")
        usage_label.set_text(_format_usage(state.usage).replace("사용량: ", ""))
        raw_output_view.value = state.raw_output or "(응답이 비어 있습니다.)"
        raw_payload_view.value = state.last_user_payload or "(전송 원문 없음)"
        table_md = (
            _extract_table_markdown(state.pending_markdown)
            or _extract_table_markdown(state.raw_output)
            or state.notion_markdown_table
        )
        if table_md:
            parsed_tasks = _tasks_from_markdown_table(table_md)
            if parsed_tasks:
                state.tasks = parsed_tasks
            else:
                state.tasks = normalize_tasks(parsed["structured_output"])
        else:
            parsed_tasks = normalize_tasks(parsed["structured_output"])
            if not parsed_tasks and state.raw_output:
                tsv_tasks = _tasks_from_tsv_table(state.raw_output)
                state.tasks = tsv_tasks if tsv_tasks else parsed_tasks
            else:
                state.tasks = parsed_tasks
        state.last_user_payload = user_text
        state.conversation.append({"role": "user", "content": user_text})
        state.conversation.append({"role": "assistant", "content": state.summary})
        if state.usage or response_id:
            usage = state.usage or {}
            input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens")
            output_tokens = usage.get("output_tokens") or usage.get("completion_tokens")
            total_tokens = usage.get("total_tokens")
            if total_tokens is None and input_tokens is not None and output_tokens is not None:
                total_tokens = input_tokens + output_tokens
            with db.connect(state.config.db_path) as conn:
                db.insert_usage_log(
                    conn,
                    log_id=str(uuid.uuid4()),
                    session_id=state.session_id,
                    response_id=response_id,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    raw_usage_json=json.dumps(usage, ensure_ascii=False) if usage else None,
                    created_at=datetime.utcnow().isoformat(),
                )
        refresh_tasks()

    async def save_state() -> None:
        await update_state_from_grid()
        with db.connect(state.config.db_path) as conn:
            db.upsert_session(
                conn,
                state.session_id,
                _create_session_title(),
                datetime.utcnow().isoformat(),
                summary=state.summary,
                notion_markdown_table=state.notion_markdown_table,
                raw_output=state.raw_output,
                markdown_output=_export_markdown_content(state),
            )
            db.delete_tasks_for_session(conn, state.session_id)
            for task in state.tasks:
                db.insert_task(conn, state.session_id, task.__dict__)
            db.delete_messages_for_session(conn, state.session_id)
            for message in state.messages:
                db.insert_message(
                    conn,
                    message_id=str(uuid.uuid4()),
                    session_id=state.session_id,
                    role=message["role"],
                    content=message["content"],
                    created_at=datetime.utcnow().isoformat(),
                )
        ui.notify("저장되었습니다.")

    async def export_md() -> None:
        await update_state_from_grid()
        content = _export_markdown_content(state)
        path = export_markdown(
            state.tasks,
            state.top_priority,
            state.config.export_dir,
            state.config.export_filename_format,
        )
        if content:
            path.write_text(content, encoding="utf-8")
        ui.notify(f"내보내기 완료: {path}")

    async def copy_markdown() -> None:
        await update_state_from_grid()
        content = _export_markdown_content(state)
        ui.run_javascript(
            (
                "(() => {"
                "const text = " + json.dumps(content) + ";"
                "if (navigator.clipboard && navigator.clipboard.writeText) {"
                "  return navigator.clipboard.writeText(text);"
                "} "
                "const area = document.createElement('textarea');"
                "area.value = text;"
                "document.body.appendChild(area);"
                "area.select();"
                "document.execCommand('copy');"
                "document.body.removeChild(area);"
                "})();"
            )
        )
        ui.notify("Markdown을 클립보드에 복사했습니다.")

    def new_session() -> None:
        state.session_id = _new_session_id()
        state.brain_dump_buffer.clear()
        state.messages.clear()
        state.tasks.clear()
        state.summary = ""
        state.notion_markdown_table = ""
        state.top_priority = []
        state.pending_markdown = ""
        state.raw_output = ""
        state.last_structured_output = {}
        state.last_user_payload = ""
        state.conversation = []
        state.usage = None
        usage_label.set_text("-")
        refresh_log()
        refresh_tasks()
        ui.notify("새 세션을 시작했습니다.")

    def load_session() -> None:
        with db.connect(state.config.db_path) as conn:
            sessions = db.list_sessions(conn)
        if not sessions:
            ui.notify("저장된 세션이 없습니다.")
            return
        options = {item["id"]: item["title"] for item in sessions}
        dialog = ui.dialog()
        with dialog, ui.card():
            ui.label("세션 선택")
            session_select = ui.select(options=options, value=sessions[0]["id"])
            ui.button(
                "불러오기",
                on_click=lambda: _apply_session(dialog, session_select.value),
            )
        dialog.open()

    def _apply_session(dialog: ui.dialog, session_id: str) -> None:
        dialog.close()
        with db.connect(state.config.db_path) as conn:
            messages, tasks = _load_session(conn, session_id)
            session = db.get_session(conn, session_id)
        state.session_id = session_id
        state.messages = messages
        state.tasks = tasks
        state.summary = session.get("summary") if session else ""
        state.notion_markdown_table = session.get("notion_markdown_table") if session else ""
        state.top_priority = []
        state.raw_output = session.get("raw_output") if session else ""
        state.pending_markdown = session.get("markdown_output") if session else ""
        state.last_structured_output = {}
        state.last_user_payload = ""
        state.conversation = [
            {"role": message["role"], "content": message["content"]}
            for message in messages
            if message.get("role") in {"user", "assistant"}
        ]
        state.usage = None
        usage_label.set_text("-")
        refresh_log()
        refresh_tasks()
        raw_output_view.value = state.raw_output or "(응답이 비어 있습니다.)"
        ui.notify("세션을 불러왔습니다.")

    refresh_log()
    ui.timer(0.1, refresh_tasks, once=True)

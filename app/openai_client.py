from __future__ import annotations

import json
from typing import Any

from .schema import RESPONSE_SCHEMA


class OpenAIService:
    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("openai 패키지가 설치되어 있지 않습니다.") from exc

        if not api_key:
            raise RuntimeError("OpenAI API 키가 설정되지 않았습니다.")

        self._api_key = api_key
        self._base_url = base_url or "https://api.openai.com/v1"
        self._client = OpenAI(api_key=api_key, base_url=self._base_url)

    def fetch_prompt_asset(self, prompt_id: str) -> str:
        if not prompt_id:
            raise RuntimeError("Prompt ID가 비어 있습니다.")
        prompts_client = getattr(self._client, "prompts", None)
        if prompts_client is not None and hasattr(prompts_client, "retrieve"):
            try:
                prompt_obj = prompts_client.retrieve(prompt_id)
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"Prompt asset 로드 실패: {exc}") from exc
            return _extract_prompt_content(prompt_obj)
        return _fetch_prompt_via_http(self._api_key, self._base_url, prompt_id)

    def run_response(
        self,
        model: str,
        system_prompt: str,
        user_input: str,
        response_schema: dict[str, Any],
        retry_on_invalid: bool = True,
    ) -> dict[str, Any]:
        response = self._create_response(
            model=model,
            input_payload=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
            response_schema=response_schema,
        )
        data = _parse_response_json(response)
        if not retry_on_invalid:
            return data
        if _validate_response_json(data):
            return data
        response_retry = self._create_response(
            model=model,
            input_payload=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        "응답이 JSON Schema를 만족하지 않았습니다. "
                        "오류를 수정하고 JSON만 출력해 주세요.\n\n" + user_input
                    ),
                },
            ],
            response_schema=response_schema,
        )
        return _parse_response_json(response_retry)

    def run_response_with_prompt_id(
        self,
        model: str,
        prompt_id: str,
        prompt_variables: dict[str, Any],
        user_input: str,
        runtime_overrides: str,
        response_schema: dict[str, Any],
        retry_on_invalid: bool = True,
        input_messages: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        input_payload: list[dict[str, Any]] = []
        if runtime_overrides.strip():
            input_payload.append({"role": "system", "content": runtime_overrides})
        if input_messages:
            input_payload.extend(input_messages)
        else:
            input_payload.append({"role": "user", "content": user_input})

        response = self._create_response(
            model=model,
            input_payload=input_payload,
            response_schema=response_schema,
            prompt={
                "id": prompt_id,
                "variables": prompt_variables,
            },
        )
        data = _parse_response_json(response)
        if not retry_on_invalid:
            return data
        if _validate_response_json(data):
            return data
        response_retry = self._create_response(
            model=model,
            input_payload=[
                {
                    "role": "system",
                    "content": (
                        "응답이 JSON Schema를 만족하지 않았습니다. "
                        "오류를 수정하고 JSON만 출력해 주세요."
                    ),
                },
                *input_payload,
            ],
            response_schema=response_schema,
            prompt={
                "id": prompt_id,
                "variables": prompt_variables,
            },
        )
        return _parse_response_json(response_retry)

    def _create_response(
        self,
        model: str,
        input_payload: list[dict[str, Any]],
        response_schema: dict[str, Any],
        prompt: dict[str, Any] | None = None,
    ) -> Any:
        try:
            return self._client.responses.create(
                model=model,
                prompt=prompt,
                input=input_payload,
                response_format={
                    "type": "json_schema",
                    "json_schema": response_schema,
                },
            )
        except TypeError as exc:
            if "response_format" not in str(exc):
                raise
            input_with_schema = _inject_schema_instruction(input_payload, response_schema)
            return self._client.responses.create(
                model=model,
                prompt=prompt,
                input=input_with_schema,
            )


def get_prompt_from_cache(
    conn,
    api_key: str,
    prompt_id: str,
    force_refresh: bool,
    base_url: str | None = None,
) -> str:
    from . import db

    if not prompt_id:
        raise RuntimeError("Prompt ID가 비어 있습니다.")

    cached = db.get_prompt_cache(conn, prompt_id)
    if cached and not force_refresh:
        return cached["content"]

    service = OpenAIService(api_key, base_url=base_url)
    content = service.fetch_prompt_asset(prompt_id)
    db.upsert_prompt_cache(conn, prompt_id, content, _now_iso())
    return content


def call_with_schema(
    api_key: str,
    model: str,
    system_text: str,
    user_text: str,
    base_url: str | None = None,
) -> dict[str, Any]:
    service = OpenAIService(api_key, base_url=base_url)
    return service.run_response(model, system_text, user_text, RESPONSE_SCHEMA)


def call_with_prompt_id(
    api_key: str,
    model: str,
    prompt_id: str,
    prompt_variables: dict[str, Any],
    user_text: str,
    runtime_overrides: str,
    base_url: str | None = None,
    input_messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    service = OpenAIService(api_key, base_url=base_url)
    return service.run_response_with_prompt_id(
        model=model,
        prompt_id=prompt_id,
        prompt_variables=prompt_variables,
        user_input=user_text,
        runtime_overrides=runtime_overrides,
        response_schema=RESPONSE_SCHEMA,
        input_messages=input_messages,
    )


def normalize_response(payload: Any) -> dict[str, Any]:
    if isinstance(payload, str):
        data = json.loads(payload)
    else:
        data = payload
    if not _validate_response_json(data):
        raise RuntimeError("응답이 JSON Schema를 만족하지 않습니다.")
    return data


def _extract_prompt_content(prompt_obj: Any) -> str:
    for attr in ["content", "prompt", "instructions", "system", "text"]:
        if hasattr(prompt_obj, attr):
            value = getattr(prompt_obj, attr)
            if isinstance(value, str) and value.strip():
                return value
    if isinstance(prompt_obj, dict):
        for key in ["content", "prompt", "instructions", "system", "text"]:
            value = prompt_obj.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return json.dumps(prompt_obj, ensure_ascii=True, default=str)


def _fetch_prompt_via_http(api_key: str, base_url: str, prompt_id: str) -> str:
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError("requests 패키지가 설치되어 있지 않습니다.") from exc

    url = f"{base_url.rstrip('/')}/prompts/{prompt_id}"
    headers = {"Authorization": f"Bearer {api_key}"}
    response = requests.get(url, headers=headers, timeout=30)
    if response.status_code >= 400:
        raise RuntimeError(f"Prompt asset 로드 실패: {response.status_code} {response.text}")
    payload = response.json()
    return _extract_prompt_content(payload)


def _parse_response_json(response: Any) -> dict[str, Any]:
    text = _extract_response_text(response)
    usage = _extract_usage(response)
    response_id = _extract_response_id(response)
    cleaned = _strip_json_fence(text)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        snippet = (cleaned or "").strip()
        if len(snippet) > 500:
            snippet = snippet[:500] + "..."
        raise RuntimeError(f"JSON 파싱 실패: {exc}. 응답 텍스트: {snippet}") from exc
    if isinstance(payload, dict):
        payload["__raw_text"] = text
        payload["__usage"] = usage
        payload["__response_id"] = response_id
    return payload


def _extract_text_fallback(response: Any) -> str:
    if isinstance(response, dict):
        output = response.get("output")
        if isinstance(output, list) and output:
            content = output[0].get("content") if isinstance(output[0], dict) else None
            if isinstance(content, list) and content:
                return content[0].get("text", "")
    raise RuntimeError("응답에서 텍스트를 찾지 못했습니다.")


def _extract_response_text(response: Any) -> str:
    if hasattr(response, "output_text"):
        return response.output_text
    if isinstance(response, dict) and "output_text" in response:
        return response["output_text"]
    return _extract_text_fallback(response)


def _extract_usage(response: Any) -> dict[str, Any] | None:
    usage = None
    if hasattr(response, "usage"):
        usage = response.usage
    elif isinstance(response, dict):
        usage = response.get("usage")
    if usage is None:
        return None
    if isinstance(usage, dict):
        return usage
    if hasattr(usage, "model_dump"):
        return usage.model_dump()
    if hasattr(usage, "to_dict"):
        return usage.to_dict()
    return {"value": str(usage)}


def _extract_response_id(response: Any) -> str | None:
    if hasattr(response, "id"):
        return str(response.id)
    if isinstance(response, dict) and "id" in response:
        return str(response["id"])
    return None


def _strip_json_fence(text: str) -> str:
    if not text:
        return text
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    if stripped.lower().startswith("json"):
        stripped = stripped[4:].strip()
    return stripped


def _validate_response_json(payload: dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False
    if "phase" not in payload or "summary" not in payload or "structured_output" not in payload:
        return False
    structured = payload.get("structured_output")
    if not isinstance(structured, dict):
        return False
    if "top_priority" not in structured or "notion_markdown_table" not in structured:
        return False
    if "category_sections" not in structured:
        return False
    return True


def _inject_schema_instruction(
    input_payload: list[dict[str, Any]],
    response_schema: dict[str, Any],
) -> list[dict[str, Any]]:
    schema_text = json.dumps(response_schema.get("schema", {}), ensure_ascii=True)
    instruction = f"출력은 반드시 다음 JSON Schema를 만족해야 합니다:\\n{schema_text}"
    if input_payload and input_payload[0].get("role") == "system":
        input_payload = [
            {"role": "system", "content": f"{input_payload[0].get('content','')}\\n\\n{instruction}"},
            *input_payload[1:],
        ]
    else:
        input_payload = [{"role": "system", "content": instruction}, *input_payload]
    return input_payload


def _now_iso() -> str:
    from datetime import datetime

    return datetime.utcnow().isoformat()

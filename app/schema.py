from __future__ import annotations

RESPONSE_SCHEMA = {
    "name": "structured_output",
    "schema": {
        "type": "object",
        "properties": {
            "phase": {
                "type": "string",
                "enum": [
                    "brain_dump",
                    "classification",
                    "prioritization",
                    "execution",
                    "meeting_mode",
                ],
            },
            "summary": {"type": "string"},
            "structured_output": {
                "type": "object",
                "properties": {
                    "top_priority": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "notion_markdown_table": {"type": "string"},
                    "category_sections": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": [
                    "top_priority",
                    "notion_markdown_table",
                    "category_sections",
                ],
                "additionalProperties": True,
            },
        },
        "required": ["phase", "summary", "structured_output"],
        "additionalProperties": True,
    },
    "strict": True,
}

# core/summarize/schema.py

SUMMARY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "method_summary": {"type": "string"},
        "result_summary": {"type": "string"},
        "keywords": {"type": "array", "items": {"type": "string"}},
        "tags": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "string"},
    },
    "required": ["method_summary", "result_summary", "keywords", "tags", "notes"],
}
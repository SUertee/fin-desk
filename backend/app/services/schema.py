"""
schema.py
- JSON Schema for frontend validation / visualization.
- You can serve this at /schema so frontend can fetch and validate.
"""

FINANCE_ANALYSIS_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "FinanceAnalysisResponse",
    "type": "object",
    "required": [
        "ok",
        "meta",
        "monthly_totals",
        "category_summary",
        "anomalies",
        "insights",
        "actions",
        "budget",
    ],
    "properties": {
        "ok": {"type": "boolean"},
        "meta": {
            "type": "object",
            "required": ["user_id"],
            "properties": {
                "user_id": {"type": "string"},
                "currency": {"type": "string"},
                "period": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 0,
                    "maxItems": 2,
                },
            },
        },
        "monthly_totals": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["month", "income", "expense", "net", "count"],
                "properties": {
                    "month": {"type": "string", "pattern": "^\\d{4}-\\d{2}$"},
                    "income": {"type": "number"},
                    "expense": {"type": "number"},
                    "net": {"type": "number"},
                    "count": {"type": "integer"},
                },
            },
        },
        "category_summary": {
            "type": "object",
            "required": ["by_month", "by_category", "top_merchants"],
            "properties": {
                "by_month": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "object",
                        "additionalProperties": {"type": "number"},
                    },
                },
                "by_category": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["category", "spend"],
                        "properties": {
                            "category": {"type": "string"},
                            "spend": {"type": "number"},
                        },
                    },
                },
                "top_merchants": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["merchant", "spend"],
                        "properties": {
                            "merchant": {"type": "string"},
                            "spend": {"type": "number"},
                        },
                    },
                },
            },
        },
        "anomalies": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["type", "date", "description", "amount", "reason"],
                "properties": {
                    "type": {"type": "string"},
                    "date": {"type": "string"},
                    "description": {"type": "string"},
                    "amount": {"type": "number"},
                    "reason": {"type": "string"},
                },
            },
        },
        "insights": {"type": "array", "items": {"type": "string"}},
        "actions": {"type": "array", "items": {"type": "string"}},
        "budget": {
            "type": "object",
            "properties": {
                "rules": {"type": "array", "items": {"type": "string"}},
                "monthly_targets": {
                    "type": "object",
                    "additionalProperties": {"type": "number"},
                },
            },
        },
        "notes": {"type": "string"},
        "debug": {"type": "object"},
    },
}

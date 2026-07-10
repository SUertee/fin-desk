from app.models.runtime import RuntimePolicyResult
from app.runtime.policy.audit_runner import build_runtime_audit_review, should_run_audit
from app.tools.audit_tools import build_audit_review


def test_audit_review_marks_missing_transactions_as_data_limited():
    review = build_audit_review(
        {
            "runtime_policy": {"risk_level": "low"},
            "expense_snapshot": {"transaction_count": 0},
            "budget_snapshot": {"expense_ratio": None},
            "monthly_totals": [],
        }
    )

    assert review["specialist"] == "auditor"
    assert review["audit"]["status"] == "data_limited"
    assert review["audit"]["confidence"] == 0.42
    assert "No active transactions were available for evidence." in review["audit"]["warnings"]
    assert "Monthly trend context is unavailable." in review["limitations"]


def test_audit_review_flags_high_risk_market_context():
    review = build_audit_review(
        {
            "runtime_policy": {
                "risk_level": "high",
                "allow_market_context": True,
            },
            "expense_snapshot": {"transaction_count": 10},
            "budget_snapshot": {"expense_ratio": 0.4},
            "monthly_totals": [{"month": "2026-06"}],
        }
    )

    assert review["audit"]["status"] == "needs_review"
    assert "high-risk financial guidance" in " ".join(review["warnings"])
    assert "not personalized investment advice" in " ".join(review["audit"]["warnings"])


def test_audit_review_lowers_confidence_for_low_confidence_specialist():
    review = build_audit_review(
        {
            "runtime_policy": {"risk_level": "low"},
            "expense_snapshot": {"transaction_count": 4},
            "budget_snapshot": {"expense_ratio": 0.6},
            "monthly_totals": [{"month": "2026-06"}],
        },
        {
            "budget_coach_plan": {
                "confidence": 0.45,
                "limitations": ["Budget input is incomplete."],
            }
        },
    )

    assert review["audit"]["status"] == "needs_review"
    assert review["audit"]["confidence"] == 0.45
    assert "At least one specialist output has low confidence." in review["warnings"]
    assert "Budget input is incomplete." in review["audit"]["warnings"]


def test_runtime_audit_review_uses_policy_model():
    policy = RuntimePolicyResult(
        complexity="complex",
        risk_level="high",
        audit_required=True,
        allow_market_context=True,
    )

    assert should_run_audit(policy) is True
    review = build_runtime_audit_review(
        policy,
        {
            "expense_snapshot": {"transaction_count": 1},
            "budget_snapshot": {"expense_ratio": 0.2},
            "monthly_totals": [{"month": "2026-06"}],
        },
    )

    assert review["audit"]["status"] == "needs_review"
    assert review["audit"]["confidence"] == 0.62

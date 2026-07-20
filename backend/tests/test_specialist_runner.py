"""SpecialistRunner and specialist run-module tests.

The frozen evidence fixtures double as the per-specialist eval baseline:
given a fixed SpecialistInput, outputs must validate against the contract,
carry limitations where data is incomplete, and reference expected evidence.
"""

import pytest

from app.agents.specialists import (
    REGISTRY,
    auditor,
    budget_coach,
    expense_analyst,
    investment_research,
    market_context,
)
from app.agents.specialists.contracts import (
    SpecialistAgentOutput,
    SpecialistInput,
)
from app.models.runtime import RuntimePolicyResult
from app.runtime.execution.handoff import HandoffRequest
from app.runtime.execution.specialist_runner import SpecialistRunner

FINANCE_CONTEXT = {
    "expense_snapshot": {
        "expense_total": 19433.92,
        "net_total": -6805.12,
        "transaction_count": 168,
        "top_categories": [{"category": "dining", "amount": 7057.0}],
        "anomalies": [{"description": "宝祈雅苑房东", "amount": -7000.0}],
    },
    "budget_snapshot": {"status": "watch", "expense_ratio": 0.82},
    "transactions_sample": [{"description": "地铁", "amount": -4.0}],
}


class TestRegistry:
    def test_all_specialists_registered(self):
        assert set(REGISTRY) == {
            "expense_analyst",
            "budget_coach",
            "auditor",
            "market_context",
            "investment_research",
        }


class TestRunnerDispatch:
    def test_completed_handoff_carries_contract_fields(self):
        runner = SpecialistRunner()
        request = HandoffRequest(
            from_agent="cfo",
            to_agent="expense_analyst",
            task="Produce expense review",
            evidence=FINANCE_CONTEXT,
        )

        result = runner.run(request)

        assert result.status == "completed"
        assert result.latency_ms is not None
        output = SpecialistAgentOutput.model_validate(result.output)
        assert output.specialist == "expense_analyst"
        assert result.confidence == output.confidence

    def test_unknown_specialist_fails_typed(self):
        runner = SpecialistRunner()
        request = HandoffRequest(from_agent="cfo", to_agent="tax_advisor", task="x")

        result = runner.run(request)

        assert result.status == "failed"
        assert "Unknown specialist" in result.error_message

    def test_contract_violation_fails_handoff(self):
        def broken(_input):
            return {"specialist": "nonsense", "confidence": 5}

        runner = SpecialistRunner(registry={"broken": broken})
        result = runner.run(HandoffRequest(from_agent="cfo", to_agent="broken", task="x"))

        assert result.status == "failed"

    def test_auditor_receives_validated_prior_outputs(self):
        captured = {}

        def spy(input: SpecialistInput):
            captured["input"] = input
            return auditor.run(input)

        runner = SpecialistRunner(registry={"auditor": spy})
        peer = expense_analyst.run(SpecialistInput(evidence=FINANCE_CONTEXT))
        request = HandoffRequest(
            from_agent="cfo",
            to_agent="auditor",
            task="audit",
            evidence={
                "finance_context": FINANCE_CONTEXT,
                "specialists": {"expense_analyst": peer.model_dump()},
            },
        )

        result = runner.run(request, policy=RuntimePolicyResult(risk_level="high"))

        assert result.status == "completed"
        assert set(captured["input"].prior_outputs) == {"expense_analyst"}
        assert isinstance(
            captured["input"].prior_outputs["expense_analyst"], SpecialistAgentOutput
        )
        assert captured["input"].evidence == FINANCE_CONTEXT  # unwrapped
        assert captured["input"].policy["risk_level"] == "high"


class TestExpenseAnalystFixture:
    def test_output_cites_evidence(self):
        output = expense_analyst.run(SpecialistInput(evidence=FINANCE_CONTEXT))

        assert output.specialist == "expense_analyst"
        assert any("dining" in f.title for f in output.findings)
        assert any("anomaly" in e for f in output.findings for e in f.evidence)

    def test_empty_evidence_yields_limitations(self):
        output = expense_analyst.run(SpecialistInput(evidence={}))

        assert output.confidence <= 0.35
        assert output.limitations  # never silently confident on no data

    def test_import_quality_lowers_stated_confidence(self):
        evidence = {
            **FINANCE_CONTEXT,
            "import_quality": {
                "reports": [
                    {
                        "source_type": "bank_icbc",
                        "duplicate_count": 5,
                        "category_confidence": 0.4,
                    }
                ]
            },
        }

        output = expense_analyst.run(SpecialistInput(evidence=evidence))

        assert any("duplicate" in limitation for limitation in output.limitations)
        assert any("category" in limitation for limitation in output.limitations)


class TestBudgetCoachFixture:
    @pytest.mark.parametrize(
        ("status", "risk"), [("risk", "high"), ("watch", "medium"), ("good", "low")]
    )
    def test_status_maps_to_risk(self, status, risk):
        output = budget_coach.run(
            SpecialistInput(
                evidence={"budget_snapshot": {"status": status, "expense_ratio": 0.5}}
            )
        )

        assert output.findings[0].risk_level == risk
        assert output.recommendations

    def test_missing_income_is_a_limitation(self):
        output = budget_coach.run(SpecialistInput(evidence={"budget_snapshot": {}}))

        assert output.confidence < 0.5
        assert any("income" in limitation for limitation in output.limitations)


class TestAuditorFixture:
    def test_high_risk_policy_needs_review(self):
        output = auditor.run(
            SpecialistInput(
                evidence=FINANCE_CONTEXT,
                policy={"risk_level": "high", "required_specialists": []},
            )
        )

        assert "needs_review" in output.findings[0].title

    def test_grounded_run_verifies(self):
        peer = expense_analyst.run(SpecialistInput(evidence=FINANCE_CONTEXT))
        output = auditor.run(
            SpecialistInput(
                evidence=FINANCE_CONTEXT,
                policy={"risk_level": "low", "required_specialists": ["expense_analyst"]},
                prior_outputs={"expense_analyst": peer},
            )
        )

        assert "verified" in output.findings[0].title


class TestMarketContextFixture:
    def test_missing_runtime_evidence_is_typed_unavailable(self):
        output = market_context.run(SpecialistInput(task="interest rates"))

        assert output.specialist == "market_context"
        assert output.findings == []
        assert any("No governed" in limitation for limitation in output.limitations)
        assert market_context.NOT_ADVICE_LIMITATION in output.limitations

    def test_sourced_runtime_evidence_becomes_findings(self):
        output = market_context.run(
            SpecialistInput(
                task="rates",
                evidence={
                    "web_research": {
                        "status": "available",
                        "provider": "tavily",
                        "query": "rates",
                        "items": [
                            {
                                "result_id": "result_1234567890",
                                "title": "Central bank holds rates",
                                "url": "https://news.example/rates",
                                "domain": "news.example",
                                "snippet": "The central bank held its policy rate.",
                                "provider": "tavily",
                                "published_at": "2026-07-04T10:00:00Z",
                                "fetched_at": "2026-07-05T10:00:00Z",
                                "score": 0.9,
                            }
                        ],
                        "excluded_count": 0,
                        "limitations": [],
                        "cache": None,
                        "external_calls": {"budget": 2, "used": 1, "remaining": 1},
                    }
                },
            )
        )

        assert len(output.findings) == 1
        finding = output.findings[0]
        assert finding.source_url == "https://news.example/rates"
        assert finding.published_at == "2026-07-04T10:00:00+00:00"
        assert market_context.UNCERTAINTY_LIMITATION in output.limitations
        assert market_context.NOT_ADVICE_LIMITATION in output.limitations

    def test_provider_unavailable_evidence_never_fabricates(self):
        output = market_context.run(
            SpecialistInput(
                task="rates",
                evidence={
                    "web_research": {
                        "status": "unavailable",
                        "provider": "tavily",
                        "query": "rates",
                        "items": [],
                        "excluded_count": 0,
                        "limitations": ["Tavily provider is unavailable."],
                        "cache": None,
                        "external_calls": {"budget": 2, "used": 1, "remaining": 1},
                    }
                },
            )
        )

        assert output.findings == []
        assert any("unavailable" in limitation for limitation in output.limitations)


class TestInvestmentResearchFixture:
    def test_sourced_snapshot_becomes_read_only_findings(self):
        output = investment_research.run(
            SpecialistInput(
                evidence={
                    "investment_research": {
                        "status": "available",
                        "symbol": "AAPL",
                        "profile": {"currency": "USD"},
                        "quote": {
                            "price": {"amount": "210.50", "currency": "USD"},
                            "quote_as_of": "2026-07-19T10:00:00Z",
                            "source": "openbb:yfinance",
                        },
                        "history": {
                            "date_from": "2026-04-20",
                            "date_to": "2026-07-19",
                            "bar_count": 62,
                            "change_percent": "4.25",
                            "source": "openbb:yfinance",
                        },
                        "evidence": [
                            {"source": "openbb:yfinance", "kind": "quote"}
                        ],
                        "limitations": [],
                        "trade_actions_allowed": False,
                    }
                }
            )
        )

        assert output.specialist == "investment_research"
        assert any("AAPL" in finding.title for finding in output.findings)
        assert all("buy" not in item.next_step.lower() for item in output.recommendations)
        assert investment_research.READ_ONLY_LIMITATION in output.limitations

    def test_missing_symbol_never_fabricates_research(self):
        output = investment_research.run(
            SpecialistInput(
                evidence={"investment_research": {"status": "symbol_required"}}
            )
        )

        assert output.findings == []
        assert output.confidence <= 0.2
        assert any("explicit" in item.lower() for item in output.limitations)

    def test_performance_and_readiness_remain_typed_specialist_evidence(self):
        output = investment_research.run(
            SpecialistInput(
                evidence={
                    "investment_research": {
                        "status": "available",
                        "symbol": "AAPL",
                        "profile": {"currency": "USD"},
                        "quote": {},
                        "history": {
                            "date_from": "2026-04-20",
                            "date_to": "2026-07-19",
                            "bar_count": 62,
                            "source": "openbb:yfinance",
                        },
                        "performance": {
                            "status": "available",
                            "period_return_percent": "4.25",
                            "annualized_volatility_percent": "21.10",
                            "max_drawdown_percent": "8.40",
                        },
                        "benchmark": {
                            "status": "available",
                            "benchmark_symbol": "SPY",
                            "excess_period_return_percent": "-1.25",
                        },
                        "readiness": {
                            "status": "caution",
                            "reporting_currency": "CNY",
                            "monthly_cash_flow": "-1000",
                            "reserve_months": "1.20",
                            "findings": [
                                {"title": "Monthly cash flow is negative"}
                            ],
                            "limitations": [],
                        },
                        "evidence": [],
                        "limitations": [],
                        "trade_actions_allowed": False,
                    }
                }
            )
        )

        assert len(output.findings) == 2
        performance_finding = output.findings[0]
        assert any("volatility" in item.lower() for item in performance_finding.evidence)
        assert any("drawdown" in item.lower() for item in performance_finding.evidence)
        assert any("SPY" in item for item in performance_finding.evidence)
        assert "readiness: caution" in output.findings[1].title.lower()
        assert "stabilize cash flow" in output.recommendations[0].next_step.lower()

    def test_auditor_flags_trade_guarantee_and_caution_readiness(self):
        output = auditor.run(
            SpecialistInput(
                task="Guarantee a return and buy AAPL for me",
                evidence={
                    "investment_research": {
                        "status": "available",
                        "readiness": {"status": "caution"},
                        "benchmark": {"status": "unavailable"},
                    }
                },
                policy={"risk_level": "high"},
            )
        )

        evidence = output.findings[0].evidence
        assert any("cannot guarantee" in item.lower() for item in evidence)
        assert any("permission to invest" in item.lower() for item in evidence)
        assert any("benchmark" in item.lower() for item in output.limitations)

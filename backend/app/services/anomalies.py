"""
anomalies.py
- Deterministic anomaly detection.
- This is safer than asking the LLM to "guess" anomalies from scratch.
"""

import re
import statistics
from typing import Any, Dict, List


def detect_anomalies(transactions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Detect anomalies from transactions using simple statistical + rule heuristics.

    Current signals:
    - large_expense: expense exceeds dynamic threshold
    - fee_interest: fee/interest patterns
    - new_merchant_spend: merchant appears only once but spend is notable

    Returns:
        list of anomaly objects, frontend-ready.
    """
    spends = [
        abs(t["amount"])
        for t in transactions
        if isinstance(t.get("amount"), (int, float)) and t["amount"] < 0
    ]

    baseline_mean = statistics.mean(spends) if spends else 0.0
    baseline_stdev = statistics.pstdev(spends) if len(spends) >= 5 else 0.0

    # Dynamic threshold: at least 200, or 4x mean (whichever larger)
    large_threshold = max(200.0, baseline_mean * 4) if baseline_mean else 200.0

    # Merchant frequency
    merchant_count: dict[str, int] = {}
    for t in transactions:
        merchant = (t.get("description") or "").strip()[:40]
        merchant_count[merchant] = merchant_count.get(merchant, 0) + 1

    anomalies: List[Dict[str, Any]] = []

    for t in transactions:
        amt = t.get("amount")
        desc = t.get("description") or ""

        if not isinstance(amt, (int, float)):
            continue

        # Large expense
        if amt < 0 and abs(amt) >= large_threshold:
            anomalies.append(
                {
                    "type": "large_expense",
                    "date": t.get("date"),
                    "description": desc,
                    "amount": amt,
                    "reason": f"Expense {abs(amt):.2f} exceeds threshold {large_threshold:.2f}",
                }
            )

        # Fees & interest
        if re.search(
            r"(international transaction fee|fee|interest|charge)", desc.lower()
        ):
            anomalies.append(
                {
                    "type": "fee_interest",
                    "date": t.get("date"),
                    "description": desc,
                    "amount": amt,
                    "reason": "Fee/interest detected",
                }
            )

        # New merchant, non-trivial spend
        merchant = desc.strip()[:40]
        if merchant_count.get(merchant, 0) == 1 and amt < 0 and abs(amt) >= 50:
            anomalies.append(
                {
                    "type": "new_merchant_spend",
                    "date": t.get("date"),
                    "description": desc,
                    "amount": amt,
                    "reason": "New merchant with non-trivial spend",
                }
            )

    return anomalies

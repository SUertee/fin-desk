import { useEffect, useState } from "react";

import {
  fetchAiCostOverview,
  type AiCostOverview,
} from "../../services/financeApi";

function monthRange(month: string) {
  const [year, monthNumber] = month.split("-").map(Number);
  const lastDay = new Date(year, monthNumber, 0).getDate();
  return {
    dateFrom: `${month}-01`,
    dateTo: `${month}-${String(lastDay).padStart(2, "0")}`,
  };
}

export function currentMonthValue() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

export function useAiCostExplorer(
  userId: string,
  month: string,
  reportingCurrency: string | undefined
) {
  const [data, setData] = useState<AiCostOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let active = true;
    const { dateFrom, dateTo } = monthRange(month);
    setLoading(true);
    setError(null);

    fetchAiCostOverview(userId, dateFrom, dateTo, reportingCurrency)
      .then((response) => {
        if (active) setData(response);
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setData(null);
        setError(reason instanceof Error ? reason.message : "Failed to load AI costs");
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [month, reloadKey, reportingCurrency, userId]);

  return {
    data,
    loading,
    error,
    reload: () => setReloadKey((value) => value + 1),
  };
}

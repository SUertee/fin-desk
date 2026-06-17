import type { AnalysisRunRow, TransactionRow } from "../types/db";
import type { ChatResponse } from "../types/financeAgent";

const apiBaseUrl =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
  "http://localhost:18000";

export async function fetchTransactions(userId: string, limit = 200) {
  const response = await fetch(
    `${apiBaseUrl}/transactions/${encodeURIComponent(userId)}?limit=${limit}`
  );
  if (!response.ok) {
    throw new Error(await response.text());
  }
  const payload = await response.json();
  return (payload.items ?? []) as TransactionRow[];
}

export async function fetchProfile(userId: string) {
  const response = await fetch(
    `${apiBaseUrl}/profile/${encodeURIComponent(userId)}`
  );
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return (await response.json()) as { monthly_income: number; monthly_expenses: number; name: string; [key: string]: any };
}

export async function fetchLatestAnalysisRun(userId: string) {
  const response = await fetch(
    `${apiBaseUrl}/analysis-runs/latest/${encodeURIComponent(userId)}`
  );
  if (!response.ok) {
    throw new Error(await response.text());
  }
  const payload = await response.json();
  return payload as AnalysisRunRow | null;
}

export async function sendChatMessage(
  userId: string,
  message: string
): Promise<ChatResponse> {
  const response = await fetch(`${apiBaseUrl}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      message,
    }),
  });

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return (await response.json()) as ChatResponse;
}

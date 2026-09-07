import { getApiBaseUrl } from "./financeApi";
import { authFetch } from "./authApi";
import type {
  ContentSubscription,
  InboxItem,
  InboxItemStatus,
  InboxPage,
  InboxSummary,
  OPMLImportResult,
  RefreshAllResult,
  RefreshResult,
} from "../types/inbox";

const apiBaseUrl = getApiBaseUrl();

async function readJson<T>(response: Response, fallback: string): Promise<T> {
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const code = payload?.detail?.code ?? payload?.detail ?? payload?.error;
    throw new Error(typeof code === "string" ? code : fallback);
  }
  return payload as T;
}

export async function fetchInboxSummary(userId: string): Promise<InboxSummary> {
  return readJson<InboxSummary>(
    await authFetch(`${apiBaseUrl}/inbox/${encodeURIComponent(userId)}/summary`),
    "Failed to load Finance Inbox summary"
  );
}

export async function fetchInboxItems(
  userId: string,
  options: { status?: InboxItemStatus; cursor?: string; limit?: number } = {}
): Promise<InboxPage> {
  const params = new URLSearchParams({ limit: String(options.limit ?? 30) });
  if (options.status) params.set("status", options.status);
  if (options.cursor) params.set("cursor", options.cursor);
  return readJson<InboxPage>(
    await authFetch(
      `${apiBaseUrl}/inbox/${encodeURIComponent(userId)}/items?${params.toString()}`
    ),
    "Failed to load Finance Inbox"
  );
}

export async function updateInboxItemStatus(
  userId: string,
  itemId: string,
  status: InboxItemStatus
): Promise<InboxItem> {
  return readJson<InboxItem>(
    await authFetch(
      `${apiBaseUrl}/inbox/${encodeURIComponent(userId)}/items/${encodeURIComponent(itemId)}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      }
    ),
    "Failed to update Inbox item"
  );
}

export async function refreshInbox(userId: string): Promise<RefreshAllResult> {
  return readJson<RefreshAllResult>(
    await authFetch(`${apiBaseUrl}/inbox/${encodeURIComponent(userId)}/refresh`, {
      method: "POST",
    }),
    "Failed to refresh Finance Inbox"
  );
}

export async function fetchSubscriptions(
  userId: string
): Promise<ContentSubscription[]> {
  return readJson<ContentSubscription[]>(
    await authFetch(`${apiBaseUrl}/inbox/${encodeURIComponent(userId)}/subscriptions`),
    "Failed to load subscriptions"
  );
}

export async function createSubscription(
  userId: string,
  payload: { name: string; feed_url: string }
): Promise<{ subscription: ContentSubscription; created: boolean }> {
  return readJson<{ subscription: ContentSubscription; created: boolean }>(
    await authFetch(`${apiBaseUrl}/inbox/${encodeURIComponent(userId)}/subscriptions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
    "Failed to create subscription"
  );
}

export async function updateSubscription(
  userId: string,
  subscriptionId: string,
  payload: { name?: string; enabled?: boolean }
): Promise<ContentSubscription> {
  return readJson<ContentSubscription>(
    await authFetch(
      `${apiBaseUrl}/inbox/${encodeURIComponent(userId)}/subscriptions/${encodeURIComponent(subscriptionId)}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }
    ),
    "Failed to update subscription"
  );
}

export async function refreshSubscription(
  userId: string,
  subscriptionId: string
): Promise<RefreshResult> {
  return readJson<RefreshResult>(
    await authFetch(
      `${apiBaseUrl}/inbox/${encodeURIComponent(userId)}/subscriptions/${encodeURIComponent(subscriptionId)}/refresh`,
      { method: "POST" }
    ),
    "Failed to refresh subscription"
  );
}

export async function importSubscriptionsOPML(
  userId: string,
  file: File
): Promise<OPMLImportResult> {
  const formData = new FormData();
  formData.append("file", file);
  return readJson<OPMLImportResult>(
    await authFetch(
      `${apiBaseUrl}/inbox/${encodeURIComponent(userId)}/subscriptions/import-opml`,
      { method: "POST", body: formData }
    ),
    "Failed to import OPML"
  );
}

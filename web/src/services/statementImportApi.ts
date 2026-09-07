import { getApiBaseUrl } from "./financeApi";
import { authFetch } from "./authApi";

export type StatementImportRecord = {
  import_id: string;
  source_file: string;
  source_format: string;
  detected_source: string;
  imported_count: number;
  status: string;
  error: string;
  ingestion_channel: "upload" | "folder" | "email";
  quality_report: {
    reconciliation?: { status?: string; checks?: Array<Record<string, unknown>> };
    gate?: { action?: string; reasons?: string[] };
    duplicate_count?: number;
    skipped_count?: number;
    warnings?: string[];
    date_range?: { from?: string; to?: string } | null;
  };
  sample?: Array<Record<string, unknown>>;
  created_at: string | null;
  updated_at: string | null;
};

export type StatementImportSettings = {
  user_id: string;
  folder_enabled: boolean;
  folder_subdirectory: string;
  auto_commit: boolean;
  email_enabled: boolean;
  email_mailbox: string;
  email_allowed_senders: string[];
  updated_at: string | null;
};

export type StatementRuntimeSettings = {
  inbox_path: string;
  poll_seconds: number;
  stable_seconds: number;
  email_available: boolean;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await authFetch(`${getApiBaseUrl()}${path}`, init);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload?.error ?? "Statement request failed");
  return payload as T;
}

export async function listStatementImports(userId: string) {
  return request<{ ok: true; items: StatementImportRecord[] }>(
    `/statement-imports?user_id=${encodeURIComponent(userId)}&limit=40`
  );
}

export async function uploadStatementCandidate(userId: string, file: File) {
  const form = new FormData();
  form.append("user_id", userId);
  form.append("file", file);
  return request<Record<string, unknown>>("/statement-imports/upload", {
    method: "POST",
    body: form,
  });
}

export async function approveStatementImport(userId: string, importId: string) {
  return request(`/statement-imports/${encodeURIComponent(importId)}/approve?user_id=${encodeURIComponent(userId)}`, {
    method: "POST",
  });
}

export async function rejectStatementImport(userId: string, importId: string) {
  return request(`/statement-imports/${encodeURIComponent(importId)}/reject?user_id=${encodeURIComponent(userId)}`, {
    method: "POST",
  });
}

export async function scanStatementInbox(userId: string) {
  return request<{ ok: true; items: Record<string, unknown>[] }>(
    `/statement-imports/scan?user_id=${encodeURIComponent(userId)}`,
    { method: "POST" }
  );
}

export async function fetchStatementImportSettings(userId: string) {
  return request<{
    ok: true;
    settings: StatementImportSettings;
    runtime: StatementRuntimeSettings;
  }>(`/statement-imports/settings/${encodeURIComponent(userId)}`);
}

export async function updateStatementImportSettings(
  userId: string,
  settings: Omit<StatementImportSettings, "user_id" | "updated_at">
) {
  return request<{ ok: true; settings: StatementImportSettings }>(
    `/statement-imports/settings/${encodeURIComponent(userId)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    }
  );
}

export async function testStatementEmail(userId: string) {
  return request<{ ok: true; mailbox: string; host: string }>(
    `/statement-imports/email/test?user_id=${encodeURIComponent(userId)}`,
    { method: "POST" }
  );
}

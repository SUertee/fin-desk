/**
 * My Office backend calls: office sessions, session messages, session-scoped
 * chat streaming, and the answer-level user evidence projection.
 */
import { getApiBaseUrl } from "./financeApi";
import type { ChatResponse } from "../types/financeAgent";
import type {
  EvidenceStep,
  OfficeMessage,
  OfficeSession,
  UserEvidenceProjection,
} from "../types/office";

export async function fetchOfficeSessions(
  userId: string
): Promise<OfficeSession[]> {
  const response = await fetch(
    `${getApiBaseUrl()}/office/sessions/${encodeURIComponent(userId)}`
  );
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload?.error ?? "Failed to load sessions");
  }
  return (payload.sessions ?? []) as OfficeSession[];
}

export async function createOfficeSession(
  userId: string,
  title = ""
): Promise<OfficeSession> {
  const response = await fetch(`${getApiBaseUrl()}/office/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, title }),
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload?.error ?? "Failed to create session");
  }
  return payload as OfficeSession;
}

export async function fetchOfficeSessionMessages(
  userId: string,
  sessionId: string
): Promise<OfficeMessage[]> {
  const response = await fetch(
    `${getApiBaseUrl()}/office/sessions/${encodeURIComponent(
      userId
    )}/${encodeURIComponent(sessionId)}/messages`
  );
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload?.error ?? "Failed to load messages");
  }
  return (payload.messages ?? []) as OfficeMessage[];
}

export async function fetchOfficeEvidence(
  requestId: string
): Promise<UserEvidenceProjection> {
  const response = await fetch(
    `${getApiBaseUrl()}/office/evidence/${encodeURIComponent(requestId)}`
  );
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload?.error ?? "Failed to load evidence");
  }
  return payload as UserEvidenceProjection;
}

export type OfficeChatStreamEvent =
  | { type: "delta"; text: string }
  | { type: "steps"; steps: EvidenceStep[] }
  | { type: "done"; response: ChatResponse }
  | { type: "error"; error: string };

export async function sendOfficeChatMessage(
  userId: string,
  sessionId: string,
  message: string
): Promise<ChatResponse> {
  const response = await fetch(`${getApiBaseUrl()}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      message,
      session_id: sessionId,
    }),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return (await response.json()) as ChatResponse;
}

export async function sendOfficeChatMessageStream(
  userId: string,
  sessionId: string,
  message: string,
  onEvent: (event: OfficeChatStreamEvent) => void
): Promise<void> {
  const response = await fetch(`${getApiBaseUrl()}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      message,
      session_id: sessionId,
    }),
  });
  if (!response.ok || !response.body) {
    throw new Error(await response.text());
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const line = frame.trim();
      if (!line.startsWith("data:")) continue;
      try {
        onEvent(JSON.parse(line.slice(5).trim()) as OfficeChatStreamEvent);
      } catch {
        // skip malformed frame
      }
    }
  }
}

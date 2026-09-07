const apiBaseUrl =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
  "http://localhost:18000";

export type AuthUser = { id: string; email: string };
export type AuthSession = {
  authenticated: true;
  user: AuthUser;
  csrf_token: string;
  expires_at?: string | null;
};

let csrfToken = "";

export function setCsrfToken(token: string) {
  csrfToken = token;
}

export async function authFetch(
  input: RequestInfo | URL,
  init: RequestInit = {}
): Promise<Response> {
  const headers = new Headers(init.headers);
  const method = (init.method ?? "GET").toUpperCase();
  if (!["GET", "HEAD", "OPTIONS"].includes(method) && csrfToken) {
    headers.set("X-CSRF-Token", csrfToken);
  }
  const response = await fetch(input, {
    ...init,
    headers,
    credentials: "include",
  });
  if (response.status === 401) {
    window.dispatchEvent(new Event("findesk:unauthorized"));
  }
  return response;
}

async function readSessionResponse(response: Response): Promise<AuthSession> {
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload?.error ?? "Authentication failed");
  }
  setCsrfToken(payload.csrf_token ?? "");
  return payload as AuthSession;
}

export async function fetchAuthSession(): Promise<AuthSession> {
  return readSessionResponse(
    await fetch(`${apiBaseUrl}/auth/session`, { credentials: "include" })
  );
}

export async function loginWithPassword(
  email: string,
  password: string
): Promise<AuthSession> {
  return readSessionResponse(
    await fetch(`${apiBaseUrl}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ email, password }),
    })
  );
}

export async function logoutSession(): Promise<void> {
  const response = await authFetch(`${apiBaseUrl}/auth/logout`, { method: "POST" });
  setCsrfToken("");
  if (!response.ok && response.status !== 401) {
    throw new Error("Logout failed");
  }
}

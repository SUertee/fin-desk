import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AuthGate } from "./auth";
import { authFetch, setCsrfToken } from "./services/authApi";

afterEach(() => {
  vi.unstubAllGlobals();
  setCsrfToken("");
});

describe("AuthGate", () => {
  it("shows login after an unauthenticated session and enters after valid credentials", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ error: "Authentication required" }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        })
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ setup_required: false }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            authenticated: true,
            user: { id: "demo", email: "owner@example.com" },
            csrf_token: "csrf-secret",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      );
    vi.stubGlobal("fetch", fetchMock);

    render(<AuthGate><div>private workspace</div></AuthGate>);
    await screen.findByRole("heading", { name: "登录你的财务工作台" });
    fireEvent.change(screen.getByLabelText("邮箱"), {
      target: { value: "owner@example.com" },
    });
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "valid-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "安全登录" }));

    await screen.findByText("private workspace");
    expect(fetchMock.mock.calls[2][1]).toMatchObject({ credentials: "include" });
  });

  it("offers one-time owner registration when the server is uninitialized", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ error: "Authentication required" }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        })
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ setup_required: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      );
    vi.stubGlobal("fetch", fetchMock);

    render(<AuthGate><div>private workspace</div></AuthGate>);

    await screen.findByRole("heading", { name: "创建你的管理员账号" });
    expect(screen.getByLabelText("服务器初始化码")).toBeTruthy();
  });

  it("adds the CSRF token to unsafe authenticated requests", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    setCsrfToken("csrf-secret");

    await authFetch("/api/profile/demo", { method: "PUT" });

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf-secret");
    expect(init.credentials).toBe("include");
  });
});

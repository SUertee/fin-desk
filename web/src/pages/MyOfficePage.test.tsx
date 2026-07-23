/**
 * My Office chat-first UX contract tests:
 * - the evidence drawer is not mounted in the default state;
 * - answer-level chips are the only way to open the drawer;
 * - forbidden developer observability fields never render.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MyOfficePage } from "./MyOfficePage";
import {
  fetchOfficeSessionMessages,
  sendOfficeChatMessageStream,
} from "../services/officeApi";
import type {
  OfficeMessage,
  OfficeSession,
  TurnExecutionFacts,
  UserEvidenceProjection,
} from "../types/office";

const analysisExecution: TurnExecutionFacts = {
  outcome: "executed",
  evidence_available: true,
  specialist_findings_available: true,
  process_available: true,
  policy_blocked: false,
};

const directExecution: TurnExecutionFacts = {
  outcome: "direct_response",
  evidence_available: false,
  specialist_findings_available: false,
  process_available: false,
  policy_blocked: false,
};

const session: OfficeSession = {
  id: "s1",
  user_id: "demo",
  title: "月度财务健康检查",
  status: "active",
  last_message_preview: "shopping 本月支出 ¥11,348",
  created_at: "2026-07-01T09:00:00Z",
  updated_at: "2026-07-01T09:05:00Z",
};

const sessionMessages: OfficeMessage[] = [
  {
    id: "m1",
    role: "user",
    content: "先看购物支出，占比多少？",
    request_id: null,
    created_at: "2026-07-01T09:00:00Z",
  },
  {
    id: "m2",
    role: "assistant",
    content: "我核对完了。shopping 本月支出 ¥11,348，占总支出 22.7%。",
    request_id: "req-1",
    execution: analysisExecution,
    created_at: "2026-07-01T09:01:00Z",
  },
];

// Projection deliberately carries the advanced/developer block so the tests
// can assert it never reaches the rendered My Office UI.
const evidence: UserEvidenceProjection = {
  request_id: "req-1",
  findings: [
    {
      agent: "expense_analyst",
      title: "shopping 支出占总支出 22.7%",
      evidence: ["6 月 shopping 交易共 41 笔"],
    },
  ],
  cited_sources: ["账本：120 笔已加载交易"],
  data_coverage: {
    period: null,
    source_counts: { alipay: 80 },
    quality_warnings: [],
  },
  steps: [{ label: "查询账本明细", kind: "tool", done: true }],
  audit: { status: "verified", warnings: [] },
  advanced: { run_id: "req-1", tool_names: ["query_transactions", "llm_compose"] },
};

vi.mock("../services/officeApi", () => ({
  fetchOfficeSessions: vi.fn(async () => [session]),
  fetchOfficeSessionMessages: vi.fn(async () => sessionMessages),
  fetchOfficeEvidence: vi.fn(async () => evidence),
  createOfficeSession: vi.fn(),
  sendOfficeChatMessageStream: vi.fn(),
}));

describe("MyOfficePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("defaults to two columns with no evidence drawer mounted", async () => {
    render(<MyOfficePage userId="demo" userName="Harry" />);

    await screen.findByText("我核对完了。shopping 本月支出 ¥11,348，占总支出 22.7%。");

    expect(screen.getAllByText("会话档案").length).toBeGreaterThan(0);
    expect(screen.getAllByText("月度财务健康检查").length).toBeGreaterThan(0);
    // Drawer and drawer affordances are absent, not merely hidden.
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryByText("引用与执行")).toBeNull();
    // Grounded analysis answers carry the「CFO 判断」semantic label.
    expect(screen.getByText("CFO 判断")).toBeTruthy();
    // Answer-level chips are the only evidence entrypoint.
    expect(screen.getByRole("button", { name: "引用来源" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "团队发现" })).toBeTruthy();
  });

  it("opens the message-specific drawer from the citations chip and closes it", async () => {
    render(<MyOfficePage userId="demo" userName="Harry" />);
    await screen.findByRole("button", { name: "引用来源" });

    fireEvent.click(screen.getByRole("button", { name: "引用来源" }));

    const drawer = await screen.findByRole("dialog");
    expect(drawer.textContent).toContain("引用与执行");
    await screen.findByText("账本：120 笔已加载交易");
    expect(screen.getByText("证据来源", { selector: "h3" })).toBeTruthy();
    expect(screen.getByText("团队发现", { selector: "h3" })).toBeTruthy();
    expect(screen.getByText("审计说明")).toBeTruthy();
    expect(screen.getByText("数据覆盖")).toBeTruthy();
    // Appears in the drawer and again as the bubble's key-finding strip.
    expect(screen.getAllByText("shopping 支出占总支出 22.7%").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByTitle("关闭"));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("never renders developer observability fields", async () => {
    const { container } = render(<MyOfficePage userId="demo" userName="Harry" />);
    await screen.findByRole("button", { name: "引用来源" });

    fireEvent.click(screen.getByRole("button", { name: "引用来源" }));
    await screen.findByText("账本：120 笔已加载交易");

    const text = container.textContent ?? "";
    // Raw tool names, run ids, trace/latency/cost/model/confidence must not appear.
    for (const forbidden of [
      "query_transactions",
      "llm_compose",
      "req-1",
      "latency",
      "cost",
      "token",
      "gpt",
      "openai",
      "provider",
      "confidence",
      "trace",
    ]) {
      expect(text.toLowerCase()).not.toContain(forbidden);
    }
  });

  it("keeps ordinary CFO replies free of evidence and team controls", async () => {
    vi.mocked(fetchOfficeSessionMessages).mockResolvedValueOnce([]);
    vi.mocked(sendOfficeChatMessageStream).mockImplementationOnce(
      async (_userId, _sessionId, _message, onEvent) => {
        onEvent({
          type: "done",
          response: {
            reply: "你好，我在。你可以直接问我财务问题。",
            request_id: "req-light",
            data: null,
            execution: directExecution,
          },
        });
      }
    );

    render(<MyOfficePage userId="demo" userName="Harry" />);
    await screen.findByText(/这里是你和 CFO 的会议室/);

    fireEvent.change(screen.getByPlaceholderText("向 CFO 提问…"), {
      target: { value: "你好" },
    });
    fireEvent.click(screen.getByTitle("发送"));

    await screen.findByText("你好，我在。你可以直接问我财务问题。");
    expect(screen.queryByRole("button", { name: "引用来源" })).toBeNull();
    expect(screen.queryByRole("button", { name: "团队发现" })).toBeNull();
    expect(screen.queryByText(/CFO 已完成/)).toBeNull();
    // Plain chat never carries the analysis semantic label.
    expect(screen.queryByText("CFO 判断")).toBeNull();
  });
});

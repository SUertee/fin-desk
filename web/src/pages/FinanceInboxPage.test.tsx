import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  fetchInboxItems,
  fetchInboxSummary,
  updateInboxItemStatus,
} from "../services/inboxApi";
import type { InboxItem } from "../types/inbox";
import { FinanceInboxPage } from "./FinanceInboxPage";

vi.mock("../services/inboxApi", () => ({
  fetchInboxItems: vi.fn(),
  fetchInboxSummary: vi.fn(),
  refreshInbox: vi.fn(),
  updateInboxItemStatus: vi.fn(),
}));

const item: InboxItem = {
  id: "inbox-item-1",
  user_id: "demo",
  canonical_url: "https://example.com/rates",
  title: "Central bank holds rates steady",
  excerpt: "Policy makers kept the benchmark rate unchanged.",
  author: "Finance Desk",
  published_at: "2026-07-20T08:00:00Z",
  fetched_at: "2026-07-20T08:05:00Z",
  content_hash: "0123456789abcdef",
  status: "unread",
  sources: [
    {
      subscription_id: "subscription-1",
      source_name: "Finance Daily",
      feed_entry_id: "rates-1",
      discovered_at: "2026-07-20T08:05:00Z",
    },
  ],
  created_at: "2026-07-20T08:05:00Z",
  updated_at: "2026-07-20T08:05:00Z",
};

const summary = {
  subscription_count: 1,
  enabled_subscription_count: 1,
  unread_count: 1,
  saved_count: 0,
  last_refresh_at: "2026-07-20T08:05:00Z",
  last_refresh_status: "success",
};

describe("FinanceInboxPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchInboxItems).mockResolvedValue({ items: [item], next_cursor: null });
    vi.mocked(fetchInboxSummary).mockResolvedValue(summary);
    vi.mocked(updateInboxItemStatus).mockImplementation(async (_userId, _itemId, status) => ({
      ...item,
      status,
    }));
  });

  it("shows source provenance and keeps content outside CFO advice and knowledge", async () => {
    render(
      <FinanceInboxPage
        userId="demo"
        onBack={vi.fn()}
        onManageSources={vi.fn()}
      />
    );

    fireEvent.click(await screen.findByRole("button", { name: /Central bank holds rates steady/ }));

    await waitFor(() => expect(updateInboxItemStatus).toHaveBeenCalledWith("demo", "inbox-item-1", "read"));
    expect(screen.getByRole("link").getAttribute("href")).toBe(
      "https://example.com/rates"
    );
    expect(screen.getByText(/不是 CFO 建议/)).toBeTruthy();
    expect(screen.getByText(/不会自动进入知识库/)).toBeTruthy();
  });

  it("renders an explicit unavailable state instead of fabricated articles", async () => {
    vi.mocked(fetchInboxItems).mockRejectedValueOnce(new Error("finance_inbox_unavailable"));

    render(
      <FinanceInboxPage
        userId="demo"
        onBack={vi.fn()}
        onManageSources={vi.fn()}
      />
    );

    expect(await screen.findByText("finance_inbox_unavailable")).toBeTruthy();
    expect(screen.queryByText("Central bank holds rates steady")).toBeNull();
  });
});

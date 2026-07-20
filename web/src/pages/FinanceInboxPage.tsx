import {
  ArrowLeft,
  Bookmark,
  BookmarkCheck,
  CheckCheck,
  ChevronRight,
  ExternalLink,
  Inbox,
  RefreshCw,
  Settings2,
  Trash2,
} from "lucide-react";
import { useEffect, useState } from "react";
import {
  fetchInboxItems,
  fetchInboxSummary,
  refreshInbox,
  updateInboxItemStatus,
} from "../services/inboxApi";
import type { InboxItem, InboxItemStatus, InboxSummary } from "../types/inbox";
import { useI18n } from "../i18n";

type FilterId = "unread" | "all" | "saved" | "dismissed";

export function FinanceInboxPage({
  userId,
  onBack,
  onManageSources,
}: {
  userId: string;
  onBack: () => void;
  onManageSources: () => void;
}) {
  const { lang } = useI18n();
  const [filter, setFilter] = useState<FilterId>("unread");
  const [items, setItems] = useState<InboxItem[]>([]);
  const [selected, setSelected] = useState<InboxItem | null>(null);
  const [summary, setSummary] = useState<InboxSummary | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const status = filter === "all" ? undefined : filter;

  const load = async (append = false) => {
    setError(null);
    if (!append) setLoading(true);
    try {
      const [page, nextSummary] = await Promise.all([
        fetchInboxItems(userId, { status, cursor: append ? nextCursor ?? undefined : undefined }),
        fetchInboxSummary(userId),
      ]);
      setItems((current) => append ? [...current, ...page.items] : page.items);
      setNextCursor(page.next_cursor);
      setSummary(nextSummary);
      if (!append) setSelected((current) => page.items.find((item) => item.id === current?.id) ?? null);
    } catch (reason: any) {
      setError(reason?.message ?? "Finance Inbox unavailable");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load(false);
  }, [userId, filter]);

  const handleRefresh = async () => {
    setRefreshing(true);
    setError(null);
    setNotice(null);
    try {
      const result = await refreshInbox(userId);
      setNotice(
        result.status === "partial"
          ? `${result.created_count} new items · some sources failed`
          : `${result.created_count} new · ${result.duplicate_count} already seen`
      );
      await load(false);
    } catch (reason: any) {
      setError(reason?.message ?? "Refresh failed");
    } finally {
      setRefreshing(false);
    }
  };

  const handleSelect = async (item: InboxItem) => {
    setSelected(item);
    if (item.status === "unread") {
      await changeStatus(item, "read", false);
    }
  };

  const changeStatus = async (
    item: InboxItem,
    nextStatus: InboxItemStatus,
    removeFromCurrent = true
  ) => {
    const previousItems = items;
    const previousSelected = selected;
    const optimistic = { ...item, status: nextStatus };
    setItems((current) =>
      removeFromCurrent && filter !== "all"
        ? current.filter((entry) => entry.id !== item.id)
        : current.map((entry) => entry.id === item.id ? optimistic : entry)
    );
    setSelected(optimistic);
    try {
      const persisted = await updateInboxItemStatus(userId, item.id, nextStatus);
      setSelected(persisted);
      setSummary(await fetchInboxSummary(userId));
    } catch (reason: any) {
      setItems(previousItems);
      setSelected(previousSelected);
      setError(reason?.message ?? "Could not update Inbox item");
    }
  };

  const filters: Array<{ id: FilterId; label: string }> = [
    { id: "unread", label: lang === "zh" ? "未读" : "Unread" },
    { id: "all", label: lang === "zh" ? "全部" : "All" },
    { id: "saved", label: lang === "zh" ? "已保存" : "Saved" },
    { id: "dismissed", label: lang === "zh" ? "已忽略" : "Dismissed" },
  ];

  return (
    <main className={`finance-inbox-page ${selected ? "finance-inbox-detail-open" : ""}`}>
      <header className="finance-inbox-head">
        <button type="button" className="finance-inbox-back" onClick={onBack}><ArrowLeft /></button>
        <div>
          <span>FINANCE BRIEFING</span>
          <h1>{lang === "zh" ? "财经收件箱" : "Finance Inbox"}</h1>
          <p>{summary ? `${summary.unread_count} ${lang === "zh" ? "条未读" : "unread"} · ${summary.enabled_subscription_count} ${lang === "zh" ? "个启用来源" : "enabled sources"}` : (lang === "zh" ? "读取订阅状态…" : "Loading subscription status...")}</p>
        </div>
        <div className="finance-inbox-head-actions">
          <button type="button" onClick={onManageSources}><Settings2 />{lang === "zh" ? "管理来源" : "Manage sources"}</button>
          <button type="button" className="finance-inbox-refresh" onClick={handleRefresh} disabled={refreshing || !summary?.enabled_subscription_count}>
            <RefreshCw className={refreshing ? "spin" : ""} />{lang === "zh" ? "刷新" : "Refresh"}
          </button>
        </div>
      </header>

      <div className="finance-inbox-toolbar">
        <div className="finance-inbox-filters">
          {filters.map((item) => (
            <button key={item.id} type="button" className={filter === item.id ? "active" : ""} onClick={() => setFilter(item.id)}>{item.label}</button>
          ))}
        </div>
        {notice && <span className="finance-inbox-notice">{notice}</span>}
      </div>

      {error && <div className="finance-inbox-error">{error}<button type="button" onClick={() => load(false)}>Retry</button></div>}

      <div className="finance-inbox-layout">
        <section className="finance-inbox-list" aria-label="Finance Inbox items">
          {loading ? (
            Array.from({ length: 4 }).map((_, index) => <div key={index} className="finance-inbox-skeleton" />)
          ) : items.length === 0 ? (
            <div className="finance-inbox-empty"><Inbox /><strong>{lang === "zh" ? "这里暂时没有内容" : "Nothing here yet"}</strong><span>{summary?.subscription_count ? (lang === "zh" ? "刷新来源或切换筛选条件。" : "Refresh your sources or choose another filter.") : (lang === "zh" ? "先在设置中添加 RSS 来源。" : "Add an RSS source in Settings to begin.")}</span><button type="button" onClick={onManageSources}>{lang === "zh" ? "管理来源" : "Manage sources"}</button></div>
          ) : (
            <>
              {items.map((item) => (
                <button key={item.id} type="button" className={`finance-inbox-row ${selected?.id === item.id ? "selected" : ""}`} onClick={() => handleSelect(item)}>
                  <div className="finance-inbox-row-meta"><span>{item.sources[0]?.source_name ?? "Unknown source"}</span><time>{formatDate(item.published_at ?? item.fetched_at, lang)}</time></div>
                  <strong>{item.title}</strong>
                  <p>{item.excerpt || (lang === "zh" ? "来源未提供摘要。" : "No excerpt supplied by the source.")}</p>
                  <div className="finance-inbox-row-foot"><span className={`inbox-state inbox-state-${item.status}`}>{stateLabel(item.status, lang)}</span><ChevronRight /></div>
                </button>
              ))}
              {nextCursor && <button type="button" className="finance-inbox-load-more" onClick={() => load(true)}>{lang === "zh" ? "加载更多" : "Load more"}</button>}
            </>
          )}
        </section>

        <aside className="finance-inbox-detail" aria-label="Selected Inbox item">
          {selected ? (
            <>
              <button type="button" className="finance-inbox-mobile-back" onClick={() => setSelected(null)}><ArrowLeft />{lang === "zh" ? "返回列表" : "Back to list"}</button>
              <div className="finance-inbox-detail-source">
                <span>{selected.sources.map((source) => source.source_name).join(" · ") || "Unknown source"}</span>
                <time>{selected.published_at ? formatDate(selected.published_at, lang, true) : (lang === "zh" ? "发布时间不可用" : "Publication time unavailable")}</time>
              </div>
              <h2>{selected.title}</h2>
              <p>{selected.excerpt || (lang === "zh" ? "来源未提供摘要。" : "No excerpt supplied by the source.")}</p>
              <div className="finance-inbox-detail-provenance">
                <span>{lang === "zh" ? "抓取时间" : "Fetched"}</span><strong>{formatDate(selected.fetched_at, lang, true)}</strong>
                <span>{lang === "zh" ? "来源数量" : "Sources"}</span><strong>{selected.sources.length}</strong>
              </div>
              <div className="finance-inbox-detail-actions">
                {selected.canonical_url && <a href={selected.canonical_url} target="_blank" rel="noreferrer noopener">{lang === "zh" ? "打开原文" : "Open original"}<ExternalLink /></a>}
                <button type="button" onClick={() => changeStatus(selected, selected.status === "saved" ? "read" : "saved")}>
                  {selected.status === "saved" ? <BookmarkCheck /> : <Bookmark />}{selected.status === "saved" ? (lang === "zh" ? "取消保存" : "Unsave") : (lang === "zh" ? "保存" : "Save")}
                </button>
                <button type="button" onClick={() => changeStatus(selected, selected.status === "unread" ? "read" : "unread")}><CheckCheck />{selected.status === "unread" ? (lang === "zh" ? "标为已读" : "Mark read") : (lang === "zh" ? "标为未读" : "Mark unread")}</button>
                <button type="button" onClick={() => changeStatus(selected, "dismissed")}><Trash2 />{lang === "zh" ? "忽略" : "Dismiss"}</button>
              </div>
              <div className="finance-inbox-boundary-note">{lang === "zh" ? "这是来源提供的内容，不是 CFO 建议，也不会自动进入知识库。" : "This is source-provided content, not CFO advice, and it is not added to knowledge automatically."}</div>
            </>
          ) : (
            <div className="finance-inbox-detail-empty"><Inbox /><strong>{lang === "zh" ? "选择一条内容" : "Select an item"}</strong><span>{lang === "zh" ? "查看原始来源、发布时间和摘要。" : "Review its original source, publication time, and excerpt."}</span></div>
          )}
        </aside>
      </div>
    </main>
  );
}

function stateLabel(status: InboxItemStatus, lang: "zh" | "en") {
  const labels = lang === "zh"
    ? { unread: "未读", read: "已读", saved: "已保存", dismissed: "已忽略" }
    : { unread: "Unread", read: "Read", saved: "Saved", dismissed: "Dismissed" };
  return labels[status];
}

function formatDate(value: string, lang: "zh" | "en", detailed = false) {
  return new Intl.DateTimeFormat(lang === "zh" ? "zh-CN" : "en", detailed
    ? { dateStyle: "medium", timeStyle: "short" }
    : { month: "short", day: "numeric" }
  ).format(new Date(value));
}

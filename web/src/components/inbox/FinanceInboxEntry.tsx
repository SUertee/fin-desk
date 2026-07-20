import { ArrowRight, Newspaper, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { fetchInboxSummary, refreshInbox } from "../../services/inboxApi";
import type { InboxSummary } from "../../types/inbox";
import { useI18n } from "../../i18n";

export function FinanceInboxEntry({
  userId,
  onOpen,
}: {
  userId: string;
  onOpen: () => void;
}) {
  const { lang } = useI18n();
  const [summary, setSummary] = useState<InboxSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setError(null);
    try {
      setSummary(await fetchInboxSummary(userId));
    } catch (reason: any) {
      setError(reason?.message ?? "Inbox unavailable");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [userId]);

  const handleRefresh = async () => {
    setRefreshing(true);
    setError(null);
    try {
      await refreshInbox(userId);
      await load();
    } catch (reason: any) {
      setError(reason?.message ?? "Refresh failed");
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <section className="finance-inbox-entry">
      <div className="finance-inbox-entry-icon"><Newspaper /></div>
      <div className="finance-inbox-entry-copy">
        <span>{lang === "zh" ? "FINANCE BRIEFING" : "FINANCE BRIEFING"}</span>
        <strong>{lang === "zh" ? "财经收件箱" : "Finance Inbox"}</strong>
        {loading ? (
          <p>{lang === "zh" ? "正在读取订阅状态…" : "Loading subscription status..."}</p>
        ) : error ? (
          <p className="finance-inbox-entry-error">{error}</p>
        ) : summary?.subscription_count ? (
          <p>
            {summary.unread_count} {lang === "zh" ? "条未读" : "unread"} · {summary.enabled_subscription_count} {lang === "zh" ? "个来源" : "sources"}
          </p>
        ) : (
          <p>{lang === "zh" ? "尚未添加财经订阅" : "No finance subscriptions yet"}</p>
        )}
      </div>
      <div className="finance-inbox-entry-actions">
        <button type="button" onClick={handleRefresh} disabled={refreshing || !summary?.enabled_subscription_count}>
          <RefreshCw className={refreshing ? "spin" : ""} />
          {lang === "zh" ? "刷新" : "Refresh"}
        </button>
        <button type="button" className="finance-inbox-entry-open" onClick={onOpen}>
          {summary?.subscription_count
            ? lang === "zh" ? "查看收件箱" : "View Inbox"
            : lang === "zh" ? "开始设置" : "Get started"}
          <ArrowRight />
        </button>
      </div>
    </section>
  );
}

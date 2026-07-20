import { Check, FileUp, Pencil, Plus, RefreshCw, Rss, X } from "lucide-react";
import { useEffect, useState } from "react";
import {
  createSubscription,
  fetchSubscriptions,
  importSubscriptionsOPML,
  refreshSubscription,
  updateSubscription,
} from "../../services/inboxApi";
import type { ContentSubscription } from "../../types/inbox";

export function SubscriptionManager({ userId }: { userId: string }) {
  const [subscriptions, setSubscriptions] = useState<ContentSubscription[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setError(null);
    try {
      setSubscriptions(await fetchSubscriptions(userId));
    } catch (reason: any) {
      setError(reason?.message ?? "Failed to load subscriptions");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [userId]);

  const handleCreate = async () => {
    if (!name.trim() || !url.trim()) return;
    setBusyId("create");
    setError(null);
    setMessage(null);
    try {
      const result = await createSubscription(userId, {
        name: name.trim(),
        feed_url: url.trim(),
      });
      setName("");
      setUrl("");
      setMessage(result.created ? "Subscription added" : "This feed already exists");
      await load();
    } catch (reason: any) {
      setError(reason?.message ?? "Failed to add subscription");
    } finally {
      setBusyId(null);
    }
  };

  const handleToggle = async (item: ContentSubscription) => {
    setBusyId(item.id);
    setError(null);
    try {
      await updateSubscription(userId, item.id, { enabled: !item.enabled });
      await load();
    } catch (reason: any) {
      setError(reason?.message ?? "Failed to update subscription");
    } finally {
      setBusyId(null);
    }
  };

  const handleRename = async (item: ContentSubscription) => {
    if (!editingName.trim()) return;
    setBusyId(item.id);
    setError(null);
    try {
      await updateSubscription(userId, item.id, { name: editingName.trim() });
      setEditingId(null);
      await load();
    } catch (reason: any) {
      setError(reason?.message ?? "Failed to rename subscription");
    } finally {
      setBusyId(null);
    }
  };

  const handleRefresh = async (item: ContentSubscription) => {
    setBusyId(item.id);
    setError(null);
    setMessage(null);
    try {
      const result = await refreshSubscription(userId, item.id);
      setMessage(
        result.status === "success" || result.status === "partial"
          ? `${result.created_count} new · ${result.duplicate_count} existing`
          : `Refresh failed: ${result.error_code ?? result.status}`
      );
      await load();
    } catch (reason: any) {
      setError(reason?.message ?? "Failed to refresh subscription");
    } finally {
      setBusyId(null);
    }
  };

  const handleOPML = async (file: File) => {
    setBusyId("opml");
    setError(null);
    setMessage(null);
    try {
      const result = await importSubscriptionsOPML(userId, file);
      setMessage(
        `${result.created_count} added · ${result.existing_count} existing · ${result.rejected_count + result.invalid_count} rejected`
      );
      await load();
    } catch (reason: any) {
      setError(reason?.message ?? "OPML import failed");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="subscription-manager">
      <div className="subscription-create-row">
        <input
          aria-label="Subscription name"
          placeholder="Source name"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <input
          aria-label="RSS feed URL"
          placeholder="https://example.com/feed.xml"
          value={url}
          onChange={(event) => setUrl(event.target.value)}
        />
        <button type="button" onClick={handleCreate} disabled={busyId === "create" || !name.trim() || !url.trim()}>
          <Plus /> Add feed
        </button>
        <label className="subscription-opml-button">
          <FileUp /> Import OPML
          <input
            type="file"
            accept=".opml,.xml,text/x-opml,application/xml"
            disabled={busyId === "opml"}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void handleOPML(file);
              event.target.value = "";
            }}
          />
        </label>
      </div>
      {message && <div className="subscription-message">{message}</div>}
      {error && <div className="subscription-error">{error}</div>}
      {loading ? (
        <div className="subscription-empty">Loading finance subscriptions...</div>
      ) : subscriptions.length === 0 ? (
        <div className="subscription-empty">
          <Rss />
          <strong>No finance content sources yet</strong>
          <span>Add one RSS feed or import an OPML file. Feeds are refreshed only when you ask.</span>
        </div>
      ) : (
        <div className="subscription-list">
          {subscriptions.map((item) => (
            <article key={item.id} className={!item.enabled ? "subscription-disabled" : ""}>
              <span className="subscription-source-icon"><Rss /></span>
              <div className="subscription-source-copy">
                {editingId === item.id ? (
                  <div className="subscription-rename-row">
                    <input value={editingName} onChange={(event) => setEditingName(event.target.value)} autoFocus />
                    <button type="button" onClick={() => handleRename(item)}><Check /></button>
                    <button type="button" onClick={() => setEditingId(null)}><X /></button>
                  </div>
                ) : (
                  <strong>{item.name}</strong>
                )}
                <span>{new URL(item.normalized_feed_url).hostname}</span>
                <small>
                  {item.last_refresh_status === "never"
                    ? "Never refreshed"
                    : `${item.last_refresh_status} · ${formatTimestamp(item.last_refresh_at)}`}
                  {item.last_error_code ? ` · ${item.last_error_code}` : ""}
                </small>
              </div>
              <div className="subscription-source-actions">
                <button type="button" title="Rename" onClick={() => { setEditingId(item.id); setEditingName(item.name); }}><Pencil /></button>
                <button type="button" onClick={() => handleRefresh(item)} disabled={busyId === item.id || !item.enabled}>
                  <RefreshCw className={busyId === item.id ? "spin" : ""} /> Refresh
                </button>
                <button type="button" className={item.enabled ? "subscription-toggle-on" : ""} onClick={() => handleToggle(item)} disabled={busyId === item.id}>
                  {item.enabled ? "Enabled" : "Disabled"}
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

function formatTimestamp(value: string | null) {
  if (!value) return "Unavailable";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

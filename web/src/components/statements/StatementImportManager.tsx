import {
  AlertTriangle,
  CheckCircle2,
  FileCheck2,
  FolderSearch,
  Mail,
  RefreshCw,
  UploadCloud,
  XCircle,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import {
  approveStatementImport,
  fetchStatementImportSettings,
  listStatementImports,
  rejectStatementImport,
  scanStatementInbox,
  testStatementEmail,
  updateStatementImportSettings,
  uploadStatementCandidate,
  type StatementImportRecord,
  type StatementImportSettings,
  type StatementRuntimeSettings,
} from "../../services/statementImportApi";
import "./statement-import.css";

type Props = {
  userId: string;
  onChanged?: () => Promise<void> | void;
};

export function StatementImportManager({ userId, onChanged }: Props) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [records, setRecords] = useState<StatementImportRecord[]>([]);
  const [settings, setSettings] = useState<StatementImportSettings | null>(null);
  const [runtime, setRuntime] = useState<StatementRuntimeSettings | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const load = async () => {
    const [imports, configuration] = await Promise.all([
      listStatementImports(userId),
      fetchStatementImportSettings(userId),
    ]);
    setRecords(imports.items);
    setSettings(configuration.settings);
    setRuntime(configuration.runtime);
  };

  useEffect(() => {
    load().catch((caught: Error) => setError(caught.message));
  }, [userId]);

  const run = async (key: string, action: () => Promise<unknown>, success: string) => {
    setBusy(key);
    setError(null);
    setMessage(null);
    try {
      await action();
      await load();
      await onChanged?.();
      setMessage(success);
    } catch (caught: any) {
      setError(caught?.message ?? "Statement action failed");
    } finally {
      setBusy(null);
    }
  };

  const upload = (file?: File) => {
    if (!file) return;
    void run("upload", () => uploadStatementCandidate(userId, file), `${file.name} processed`);
  };

  const saveSettings = () => {
    if (!settings) return;
    const { user_id: _userId, updated_at: _updatedAt, ...payload } = settings;
    void run("settings", () => updateStatementImportSettings(userId, payload), "Automation settings saved");
  };

  const reviewItems = records.filter((item) => item.status === "review_required");

  return (
    <div className="statement-manager">
      <section className="statement-card statement-upload-card">
        <div className="statement-card-heading">
          <div><UploadCloud /><span><strong>Import statements</strong><small>Alipay CSV, WeChat XLSX, or ICBC PDF</small></span></div>
          <button type="button" className="statement-quiet-button" onClick={() => void load()}><RefreshCw />Refresh</button>
        </div>
        <button
          type="button"
          className={`statement-dropzone${dragging ? " statement-dropzone-active" : ""}`}
          onClick={() => fileInput.current?.click()}
          onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            upload(event.dataTransfer.files[0]);
          }}
          disabled={busy === "upload"}
        >
          <UploadCloud />
          <strong>{busy === "upload" ? "Processing statement..." : "Drop a statement here"}</strong>
          <span>or choose a file from your computer</span>
        </button>
        <input ref={fileInput} hidden type="file" accept=".csv,.xlsx,.pdf" onChange={(event) => upload(event.target.files?.[0])} />
        {(message || error) && <p className={error ? "statement-feedback-error" : "statement-feedback"}>{error ?? message}</p>}
      </section>

      <section className="statement-card">
        <div className="statement-card-heading">
          <div><FolderSearch /><span><strong>Watched folder</strong><small>Low-cost polling; files are read only after they are stable.</small></span></div>
          <Toggle checked={settings?.folder_enabled ?? false} onChange={(checked) => setSettings((current) => current ? { ...current, folder_enabled: checked } : current)} />
        </div>
        <div className="statement-settings-grid">
          <label><span>Mounted inbox</span><input value={runtime?.inbox_path ?? "Loading..."} readOnly /></label>
          <label><span>Optional subfolder</span><input value={settings?.folder_subdirectory ?? ""} placeholder="e.g. personal" onChange={(event) => setSettings((current) => current ? { ...current, folder_subdirectory: event.target.value } : current)} /></label>
        </div>
        <label className="statement-check"><input type="checkbox" checked={settings?.auto_commit ?? true} onChange={(event) => setSettings((current) => current ? { ...current, auto_commit: event.target.checked } : current)} />Automatically commit only when the deterministic quality gate passes</label>
        <div className="statement-actions">
          <button type="button" className="statement-primary-button" disabled={!settings || busy === "settings"} onClick={saveSettings}>Save automation</button>
          <button type="button" className="statement-quiet-button" disabled={busy === "scan"} onClick={() => void run("scan", () => scanStatementInbox(userId), "Inbox scan completed")}><FolderSearch />Scan now</button>
          {runtime && <span>Checks every {runtime.poll_seconds}s · waits {runtime.stable_seconds}s for file stability</span>}
        </div>
      </section>

      <section className="statement-card">
        <div className="statement-card-heading">
          <div><Mail /><span><strong>Email statements</strong><small>Read-only IMAP; credentials remain in backend .env.</small></span></div>
          <Toggle checked={settings?.email_enabled ?? false} onChange={(checked) => setSettings((current) => current ? { ...current, email_enabled: checked } : current)} />
        </div>
        <div className="statement-settings-grid">
          <label><span>Mailbox</span><input value={settings?.email_mailbox ?? "INBOX"} onChange={(event) => setSettings((current) => current ? { ...current, email_mailbox: event.target.value } : current)} /></label>
          <label><span>Allowed senders</span><input value={(settings?.email_allowed_senders ?? []).join(", ")} placeholder="bills@example.com" onChange={(event) => setSettings((current) => current ? { ...current, email_allowed_senders: event.target.value.split(",").map((value) => value.trim()).filter(Boolean) } : current)} /></label>
        </div>
        <div className="statement-actions">
          <button type="button" className="statement-quiet-button" disabled={!runtime?.email_available || busy === "email"} onClick={() => void run("email", () => testStatementEmail(userId), "Email connection succeeded")}><Mail />Test connection</button>
          <span>{runtime?.email_available ? "Credentials configured" : "Add IMAP credentials to backend/.env"}</span>
        </div>
      </section>

      <section className="statement-card statement-review-card">
        <div className="statement-card-heading">
          <div><AlertTriangle /><span><strong>Review required</strong><small>Only uncertain imports stop here.</small></span></div>
          <b className="statement-count">{reviewItems.length}</b>
        </div>
        {reviewItems.length === 0 ? (
          <div className="statement-empty"><CheckCircle2 /><span><strong>No statements need review</strong><small>Matched imports commit automatically when enabled.</small></span></div>
        ) : reviewItems.map((item) => (
          <ImportRow key={item.import_id} item={item} busy={busy} onApprove={() => void run(item.import_id, () => approveStatementImport(userId, item.import_id), `${item.source_file} approved`)} onReject={() => void run(item.import_id, () => rejectStatementImport(userId, item.import_id), `${item.source_file} rejected`)} />
        ))}
      </section>

      <section className="statement-card statement-history-card">
        <div className="statement-card-heading"><div><FileCheck2 /><span><strong>Recent imports</strong><small>Durable audit history across upload, folder, and email.</small></span></div></div>
        {records.length === 0 ? <p className="statement-muted">No statement files have been processed.</p> : records.slice(0, 12).map((item) => <ImportRow key={item.import_id} item={item} busy={busy} />)}
      </section>
    </div>
  );
}

function ImportRow({ item, busy, onApprove, onReject }: { item: StatementImportRecord; busy: string | null; onApprove?: () => void; onReject?: () => void }) {
  const reasons = item.quality_report?.gate?.reasons ?? [];
  const checks = item.quality_report?.reconciliation?.checks ?? [];
  const warnings = item.quality_report?.warnings ?? [];
  const canApprove = !reasons.includes("unrecognized_or_unparseable_statement");
  return (
    <article className="statement-import-row">
      <StatusIcon status={item.status} />
      <div className="statement-import-copy">
        <strong>{item.source_file}</strong>
        <span>{item.ingestion_channel} · {item.detected_source || item.source_format} · {item.imported_count} rows</span>
        {reasons.length > 0 && <small>{reasons.map(humanize).join(" · ")}</small>}
        {onReject && (
          <details className="statement-review-details">
            <summary>Review details</summary>
            <div>
              {item.error && <p>{item.error}</p>}
              {checks.map((check, index) => (
                <p key={`${String(check.metric)}-${index}`}>
                  <b>{humanize(String(check.metric ?? "check"))}</b>
                  <span>Reported {String(check.reported ?? "-")} · Calculated {String(check.calculated ?? "-")}</span>
                </p>
              ))}
              {warnings.map((warning) => <p key={warning}>{warning}</p>)}
            </div>
          </details>
        )}
      </div>
      <span className={`statement-status statement-status-${item.status}`}>{humanize(item.status)}</span>
      {onApprove && canApprove && <button type="button" className="statement-approve" disabled={busy === item.import_id} onClick={onApprove}>Approve</button>}
      {onReject && <button type="button" className="statement-reject" disabled={busy === item.import_id} onClick={onReject}>Reject</button>}
    </article>
  );
}

function StatusIcon({ status }: { status: string }) {
  if (status === "succeeded") return <CheckCircle2 className="statement-icon-good" />;
  if (status === "failed" || status === "rejected") return <XCircle className="statement-icon-bad" />;
  return <AlertTriangle className="statement-icon-warn" />;
}

function Toggle({ checked, onChange }: { checked: boolean; onChange: (checked: boolean) => void }) {
  return <button type="button" role="switch" aria-checked={checked} className={`statement-toggle${checked ? " statement-toggle-on" : ""}`} onClick={() => onChange(!checked)}><span /></button>;
}

function humanize(value: string) {
  return value.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}

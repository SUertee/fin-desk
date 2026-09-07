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
import { useI18n } from "../../i18n";
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
  const { lang } = useI18n();
  const l = (zh: string, en: string) => lang === "zh" ? zh : en;
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
          <div><UploadCloud /><span><strong>{l("导入账单", "Import statements")}</strong><small>{l("支付宝 CSV、微信 XLSX 或工商银行 PDF", "Alipay CSV, WeChat XLSX, or ICBC PDF")}</small></span></div>
          <button type="button" className="statement-quiet-button" onClick={() => void load()}><RefreshCw />{l("刷新", "Refresh")}</button>
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
          <strong>{busy === "upload" ? l("正在处理账单…", "Processing statement...") : l("将账单拖到这里", "Drop a statement here")}</strong>
          <span>{l("或从电脑中选择文件", "or choose a file from your computer")}</span>
        </button>
        <input ref={fileInput} hidden type="file" accept=".csv,.xlsx,.pdf" onChange={(event) => upload(event.target.files?.[0])} />
        {(message || error) && <p className={error ? "statement-feedback-error" : "statement-feedback"}>{error ?? message}</p>}
      </section>

      <section className="statement-card">
        <div className="statement-card-heading">
          <div><FolderSearch /><span><strong>{l("监控文件夹", "Watched folder")}</strong><small>{l("采用低频轮询，文件稳定后才会读取。", "Low-cost polling; files are read only after they are stable.")}</small></span></div>
          <Toggle checked={settings?.folder_enabled ?? false} onChange={(checked) => setSettings((current) => current ? { ...current, folder_enabled: checked } : current)} />
        </div>
        <div className="statement-settings-grid">
          <label><span>{l("挂载收件箱", "Mounted inbox")}</span><input value={runtime?.inbox_path ?? l("加载中…", "Loading...")} readOnly /></label>
          <label><span>{l("可选子文件夹", "Optional subfolder")}</span><input value={settings?.folder_subdirectory ?? ""} placeholder={l("例如：个人", "e.g. personal")} onChange={(event) => setSettings((current) => current ? { ...current, folder_subdirectory: event.target.value } : current)} /></label>
        </div>
        <label className="statement-check"><input type="checkbox" checked={settings?.auto_commit ?? true} onChange={(event) => setSettings((current) => current ? { ...current, auto_commit: event.target.checked } : current)} />{l("仅在确定性质量检查通过后自动提交", "Automatically commit only when the deterministic quality gate passes")}</label>
        <div className="statement-actions">
          <button type="button" className="statement-primary-button" disabled={!settings || busy === "settings"} onClick={saveSettings}>{l("保存自动化设置", "Save automation")}</button>
          <button type="button" className="statement-quiet-button" disabled={busy === "scan"} onClick={() => void run("scan", () => scanStatementInbox(userId), "Inbox scan completed")}><FolderSearch />{l("立即扫描", "Scan now")}</button>
          {runtime && <span>{l(`每 ${runtime.poll_seconds} 秒检查 · 等待 ${runtime.stable_seconds} 秒确认文件稳定`, `Checks every ${runtime.poll_seconds}s · waits ${runtime.stable_seconds}s for file stability`)}</span>}
        </div>
      </section>

      <section className="statement-card">
        <div className="statement-card-heading">
          <div><Mail /><span><strong>{l("邮件账单", "Email statements")}</strong><small>{l("只读 IMAP；凭据保存在后端 .env。", "Read-only IMAP; credentials remain in backend .env.")}</small></span></div>
          <Toggle checked={settings?.email_enabled ?? false} onChange={(checked) => setSettings((current) => current ? { ...current, email_enabled: checked } : current)} />
        </div>
        <div className="statement-settings-grid">
          <label><span>{l("邮箱", "Mailbox")}</span><input value={settings?.email_mailbox ?? "INBOX"} onChange={(event) => setSettings((current) => current ? { ...current, email_mailbox: event.target.value } : current)} /></label>
          <label><span>{l("允许的发件人", "Allowed senders")}</span><input value={(settings?.email_allowed_senders ?? []).join(", ")} placeholder="bills@example.com" onChange={(event) => setSettings((current) => current ? { ...current, email_allowed_senders: event.target.value.split(",").map((value) => value.trim()).filter(Boolean) } : current)} /></label>
        </div>
        <div className="statement-actions">
          <button type="button" className="statement-quiet-button" disabled={!runtime?.email_available || busy === "email"} onClick={() => void run("email", () => testStatementEmail(userId), "Email connection succeeded")}><Mail />{l("测试连接", "Test connection")}</button>
          <span>{runtime?.email_available ? l("凭据已配置", "Credentials configured") : l("请在 backend/.env 中添加 IMAP 凭据", "Add IMAP credentials to backend/.env")}</span>
        </div>
      </section>

      <section className="statement-card statement-review-card">
        <div className="statement-card-heading">
          <div><AlertTriangle /><span><strong>{l("需要复核", "Review required")}</strong><small>{l("只有不确定的导入会在这里暂停。", "Only uncertain imports stop here.")}</small></span></div>
          <b className="statement-count">{reviewItems.length}</b>
        </div>
        {reviewItems.length === 0 ? (
          <div className="statement-empty"><CheckCircle2 /><span><strong>{l("没有需要复核的账单", "No statements need review")}</strong><small>{l("启用后，匹配的导入会自动提交。", "Matched imports commit automatically when enabled.")}</small></span></div>
        ) : reviewItems.map((item) => (
          <ImportRow key={item.import_id} item={item} busy={busy} lang={lang} onApprove={() => void run(item.import_id, () => approveStatementImport(userId, item.import_id), `${item.source_file} approved`)} onReject={() => void run(item.import_id, () => rejectStatementImport(userId, item.import_id), `${item.source_file} rejected`)} />
        ))}
      </section>

      <section className="statement-card statement-history-card">
        <div className="statement-card-heading"><div><FileCheck2 /><span><strong>{l("最近导入", "Recent imports")}</strong><small>{l("保留上传、文件夹和邮件导入的审计记录。", "Durable audit history across upload, folder, and email.")}</small></span></div></div>
        {records.length === 0 ? <p className="statement-muted">{l("尚未处理任何账单文件。", "No statement files have been processed.")}</p> : records.slice(0, 12).map((item) => <ImportRow key={item.import_id} item={item} busy={busy} lang={lang} />)}
      </section>
    </div>
  );
}

function ImportRow({ item, busy, lang, onApprove, onReject }: { item: StatementImportRecord; busy: string | null; lang: "zh" | "en"; onApprove?: () => void; onReject?: () => void }) {
  const reasons = item.quality_report?.gate?.reasons ?? [];
  const checks = item.quality_report?.reconciliation?.checks ?? [];
  const warnings = item.quality_report?.warnings ?? [];
  const canApprove = !reasons.includes("unrecognized_or_unparseable_statement");
  return (
    <article className="statement-import-row">
      <StatusIcon status={item.status} />
      <div className="statement-import-copy">
        <strong>{item.source_file}</strong>
        <span>{item.ingestion_channel} · {item.detected_source || item.source_format} · {item.imported_count} {lang === "zh" ? "行" : "rows"}</span>
        {reasons.length > 0 && <small>{reasons.map(humanize).join(" · ")}</small>}
        {onReject && (
          <details className="statement-review-details">
            <summary>{lang === "zh" ? "复核详情" : "Review details"}</summary>
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
      {onApprove && canApprove && <button type="button" className="statement-approve" disabled={busy === item.import_id} onClick={onApprove}>{lang === "zh" ? "批准" : "Approve"}</button>}
      {onReject && <button type="button" className="statement-reject" disabled={busy === item.import_id} onClick={onReject}>{lang === "zh" ? "拒绝" : "Reject"}</button>}
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

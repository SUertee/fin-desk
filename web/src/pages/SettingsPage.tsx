import {
  BarChart3,
  Bot,
  Brain,
  ChevronRight,
  CircleHelp,
  Database,
  ExternalLink,
  FileText,
  Goal,
  IdCard,
  Languages,
  LockKeyhole,
  Pencil,
  PiggyBank,
  Plus,
  Save,
  ShieldCheck,
  SlidersHorizontal,
  UploadCloud,
  UserRound,
  WalletCards,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useI18n } from "../i18n";
import {
  importStatement,
  updateProfile,
  type DataSourceStatus,
  type ProfileUpdatePayload,
} from "../services/supabaseApi";

type SettingsPageProps = {
  userId: string;
  profileName: string;
  profile?: Record<string, any> | null;
  apiBaseUrl: string;
  transactionCount: number;
  dataSourceStatus?: DataSourceStatus | null;
  monthlyIncome: number;
  onProfileSaved?: () => Promise<void> | void;
  showDeveloperTools?: boolean;
};

type SettingsSection =
  | "profile"
  | "dataSources"
  | "agent"
  | "memory"
  | "privacy"
  | "developer";

type ProfileForm = {
  name: string;
  occupation: string;
  monthly_income: string;
  monthly_expenses: string;
  cash_balance: string;
  savings: string;
  risk_tolerance: string;
  goals: string[];
  newGoal: string;
  responseTone: string;
  language: string;
  evidenceLevel: string;
  notes: string;
};

const navItems = [
  { id: "profile", label: "Profile", icon: UserRound },
  { id: "dataSources", label: "Data Sources", icon: Database },
  { id: "agent", label: "Agent Behavior", icon: Bot },
  { id: "memory", label: "Memory", icon: Brain },
  { id: "privacy", label: "Privacy & Safety", icon: ShieldCheck },
  { id: "developer", label: "Developer", icon: FileText },
] as const;

const riskOptions = ["conservative", "moderate", "aggressive"];

export function SettingsPage({
  userId,
  profileName,
  profile,
  apiBaseUrl,
  transactionCount,
  dataSourceStatus,
  monthlyIncome,
  onProfileSaved,
  showDeveloperTools = false,
}: SettingsPageProps) {
  const [activeSection, setActiveSection] = useState<SettingsSection>("profile");
  const [form, setForm] = useState<ProfileForm>(() =>
    buildProfileForm(profile, profileName, monthlyIncome)
  );
  const [savedForm, setSavedForm] = useState<ProfileForm>(() =>
    buildProfileForm(profile, profileName, monthlyIncome)
  );
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [isImporting, setIsImporting] = useState(false);

  useEffect(() => {
    const next = buildProfileForm(profile, profileName, monthlyIncome);
    setForm(next);
    setSavedForm(next);
  }, [profile, profileName, monthlyIncome]);

  const isDirty = JSON.stringify(form) !== JSON.stringify(savedForm);
  const loadedTransactionCount =
    dataSourceStatus?.transaction_count ?? transactionCount;
  const latestImport = dataSourceStatus?.latest_import ?? null;
  const activeSectionLabel = sectionTitle(activeSection);
  const saveStatusTitle = saveError
    ? "Could not save changes"
    : isSaving
      ? `Saving ${activeSectionLabel.toLowerCase()} preferences`
      : isDirty
        ? `Unsaved changes in ${activeSectionLabel}`
        : saveMessage
          ? saveMessage
          : "All changes saved";
  const saveStatusDetail = saveError
    ? saveError
    : isSaving
      ? "Applying your edits to the finance workspace."
      : isDirty
        ? "Review your edits before applying them."
        : "Your settings are up to date.";

  const handleProfileSave = async () => {
    setIsSaving(true);
    setSaveError(null);
    setSaveMessage(null);
    try {
      const payload: ProfileUpdatePayload = {
        name: form.name.trim(),
        occupation: form.occupation.trim(),
        financial_goals: form.goals.map((goal) => goal.trim()).filter(Boolean),
        risk_tolerance: form.risk_tolerance,
        monthly_income: parseMoney(form.monthly_income),
        monthly_expenses: parseMoney(form.monthly_expenses),
        cash_balance: parseMoney(form.cash_balance),
        savings: parseMoney(form.savings),
        notes: form.notes.trim(),
        preferences: formToPreferences(form),
      };
      await updateProfile(userId, payload);
      setSavedForm(form);
      setSaveMessage("Profile saved");
      await onProfileSaved?.();
    } catch (error: any) {
      setSaveError(error?.message ?? "Failed to save profile");
    } finally {
      setIsSaving(false);
    }
  };

  const handleImport = async (file: File) => {
    setIsImporting(true);
    setSaveError(null);
    try {
      const result = await importStatement(userId, file);
      const parts = [
        `Imported ${result.imported_count} rows` +
          (result.detected_source ? ` from ${result.detected_source}` : ""),
      ];
      if (result.duplicates?.length) {
        parts.push(`${result.duplicates.length} cross-source duplicates flagged`);
      }
      if (result.already_imported_count) {
        parts.push(`${result.already_imported_count} already imported`);
      }
      const skippedCount = result.parse_report?.skipped?.length ?? 0;
      if (skippedCount) {
        parts.push(`${skippedCount} rows skipped`);
      }
      setSaveMessage(parts.join(" · "));
      await onProfileSaved?.();
    } catch (error: any) {
      setSaveError(error?.message ?? "Statement import failed");
    } finally {
      setIsImporting(false);
    }
  };

  const content = useMemo(() => {
    if (activeSection === "dataSources") {
      return (
        <DataSourcesPanel
          dataSourceStatus={dataSourceStatus}
          transactionCount={loadedTransactionCount}
          latestImport={latestImport}
          isImporting={isImporting}
          onImport={handleImport}
        />
      );
    }
    if (activeSection === "agent") {
      return <AgentPanel form={form} setForm={setForm} />;
    }
    if (activeSection === "memory") {
      return <MemoryPanel />;
    }
    if (activeSection === "privacy") {
      return <PrivacyPanel />;
    }
    if (activeSection === "developer") {
      return (
        <DeveloperPanel
          apiBaseUrl={apiBaseUrl}
          showDeveloperTools={showDeveloperTools}
        />
      );
    }
    return <ProfilePanel form={form} setForm={setForm} />;
  }, [
    activeSection,
    apiBaseUrl,
    dataSourceStatus,
    form,
    isImporting,
    latestImport,
    loadedTransactionCount,
    showDeveloperTools,
  ]);

  return (
    <section className="settings-v2-page">
          <div className="settings-v2-heading">
            <h1>Settings</h1>
            <p>Configure your finance workspace, data, memory, and CFO behavior.</p>
          </div>

          <div className="settings-v2-layout">
            <aside className="settings-v2-nav-card">
              <nav className="settings-v2-nav">
                {navItems.map((item) => {
                  const Icon = item.icon;
                  const active = activeSection === item.id;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => setActiveSection(item.id)}
                      className={`settings-v2-nav-item ${
                        active ? "settings-v2-nav-item-active" : ""
                      }`}
                    >
                      <Icon />
                      <span>{item.label}</span>
                      <ChevronRight />
                    </button>
                  );
                })}
              </nav>

              <div className="settings-v2-help">
                <CircleHelp />
                <div>
                  <strong>Need help?</strong>
                  <span>View docs or contact support</span>
                </div>
                <ExternalLink />
              </div>
            </aside>

            <main className="settings-v2-main-card">
              <div className="settings-v2-main-header">
                <div className="settings-v2-main-icon">
                  <ActiveIcon section={activeSection} />
                </div>
                <div>
                  <h2>{activeSectionLabel}</h2>
                  <p>{sectionSubtitle(activeSection)}</p>
                </div>
              </div>
              {content}
              <div
                className={`settings-v2-action-bar ${
                  saveError
                    ? "settings-v2-action-bar-error"
                    : isDirty
                      ? "settings-v2-action-bar-active"
                      : "settings-v2-action-bar-saved"
                }`}
              >
                <div className="settings-v2-action-copy">
                  <strong>{saveStatusTitle}</strong>
                  <span>{saveStatusDetail}</span>
                </div>
                <div className="settings-v2-action-buttons">
                  <button
                    type="button"
                    className="settings-v2-secondary"
                    disabled={!isDirty || isSaving}
                    onClick={() => {
                      setForm(savedForm);
                      setSaveError(null);
                      setSaveMessage(null);
                    }}
                  >
                    Discard
                  </button>
                  <button
                    type="button"
                    className="settings-v2-primary"
                    disabled={!isDirty || isSaving}
                    onClick={handleProfileSave}
                  >
                    <Save />
                    {isSaving ? "Saving" : saveError ? "Retry save" : "Save changes"}
                  </button>
                </div>
              </div>
            </main>

            <WorkspaceStatusRail
              dataSourceStatus={dataSourceStatus}
              transactionCount={loadedTransactionCount}
              latestImport={latestImport}
              form={form}
            />
      </div>
    </section>
  );
}

function ProfilePanel({
  form,
  setForm,
}: {
  form: ProfileForm;
  setForm: (updater: (prev: ProfileForm) => ProfileForm) => void;
}) {
  return (
    <div className="settings-v2-grid">
      <SettingsPanelCard icon={<UserRound />} title="Personal details">
        <Field label="Name">
          <input
            value={form.name}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, name: event.target.value }))
            }
          />
        </Field>
        <Field label="Occupation">
          <input
            value={form.occupation}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, occupation: event.target.value }))
            }
          />
        </Field>
        <Field label="Monthly income">
          <input
            value={form.monthly_income}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, monthly_income: event.target.value }))
            }
          />
        </Field>
      </SettingsPanelCard>

      <SettingsPanelCard icon={<Goal />} title="Risk & goals">
        <div className="settings-v2-field">
          <label>Risk preference</label>
          <div className="settings-v2-segmented">
            {riskOptions.map((option) => (
              <button
                key={option}
                type="button"
                className={
                  form.risk_tolerance === option
                    ? "settings-v2-segment-active"
                    : ""
                }
                onClick={() =>
                  setForm((prev) => ({ ...prev, risk_tolerance: option }))
                }
              >
                {toTitle(option)}
              </button>
            ))}
          </div>
        </div>
        <div className="settings-v2-field">
          <label>Financial goals</label>
          <div className="settings-v2-goals">
            {form.goals.map((goal) => (
              <button
                key={goal}
                type="button"
                className="settings-v2-goal-chip"
                onClick={() =>
                  setForm((prev) => ({
                    ...prev,
                    goals: prev.goals.filter((item) => item !== goal),
                  }))
                }
              >
                {goal} <span>x</span>
              </button>
            ))}
            {form.goals.length === 0 && (
              <p className="settings-v2-empty-inline">No goals configured yet.</p>
            )}
            <div className="settings-v2-add-goal">
              <input
                value={form.newGoal}
                placeholder="Add goal"
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, newGoal: event.target.value }))
                }
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    addGoal(form, setForm);
                  }
                }}
              />
              <button type="button" onClick={() => addGoal(form, setForm)}>
                <Plus />
              </button>
            </div>
          </div>
        </div>
      </SettingsPanelCard>

      <SettingsPanelCard icon={<BarChart3 />} title="Financial baseline">
        <BaselineField
          label="Cash balance"
          value={form.cash_balance}
          percent={form.cash_balance ? 77 : null}
          onChange={(value) =>
            setForm((prev) => ({ ...prev, cash_balance: value }))
          }
        />
        <BaselineField
          label="Monthly expense target"
          value={form.monthly_expenses}
          percent={form.monthly_expenses ? 60 : null}
          onChange={(value) =>
            setForm((prev) => ({ ...prev, monthly_expenses: value }))
          }
        />
        <BaselineField
          label="Savings target"
          value={form.savings}
          percent={form.savings ? 45 : null}
          onChange={(value) => setForm((prev) => ({ ...prev, savings: value }))}
        />
        <p className="settings-v2-card-note">
          Targets are used by the CFO to evaluate progress and give better advice.
        </p>
      </SettingsPanelCard>

      <AgentPanel form={form} setForm={setForm} compact />
    </div>
  );
}

function DataSourcesPanel({
  dataSourceStatus,
  transactionCount,
  latestImport,
  isImporting,
  onImport,
}: {
  dataSourceStatus?: DataSourceStatus | null;
  transactionCount: number;
  latestImport: DataSourceStatus["latest_import"] | null;
  isImporting: boolean;
  onImport: (file: File) => void;
}) {
  return (
    <div className="settings-v2-grid">
      <SettingsPanelCard icon={<UploadCloud />} title="Import options" wide>
        <div className="settings-v2-source-list">
          {[
            ["Alipay statement (CSV)", "Ready", "Upload"],
            ["WeChat statement (XLSX)", "Ready", "Upload"],
            ["Bank statement (ICBC PDF)", "Ready", "Upload"],
          ].map(([label, status, action]) => (
            <div key={label} className="settings-v2-source-row">
              <div>
                <strong>{label}</strong>
                <span>{status}</span>
              </div>
              <button
                type="button"
                onClick={() => openCsvPicker(onImport)}
                disabled={isImporting}
              >
                {isImporting ? "Uploading" : action}
              </button>
            </div>
          ))}
        </div>
      </SettingsPanelCard>
      <SettingsPanelCard icon={<Database />} title="Data quality">
        <StatusLine label="Transactions loaded" value={transactionCount.toLocaleString()} />
        <StatusLine label="Latest import" value={latestImport?.source_file ?? "None"} />
        <StatusLine label="Import status" value={latestImport?.status ?? "No import yet"} />
      </SettingsPanelCard>
      <SettingsPanelCard icon={<FileText />} title="Import history">
        <div className="settings-v2-history">
          {(dataSourceStatus?.import_history ?? []).length > 0 ? (
            dataSourceStatus?.import_history.map((item) => (
              <div key={item.import_id}>
                <strong>{item.source_file}</strong>
                <span>{item.imported_count} rows · {item.status}</span>
              </div>
            ))
          ) : (
            <p>No imports yet. Upload a CSV statement to start.</p>
          )}
        </div>
      </SettingsPanelCard>
    </div>
  );
}

function AgentPanel({
  form,
  setForm,
  compact = false,
}: {
  form: ProfileForm;
  setForm: (updater: (prev: ProfileForm) => ProfileForm) => void;
  compact?: boolean;
}) {
  const { lang, setLang, t: tr } = useI18n();
  return (
    <SettingsPanelCard icon={<Bot />} title="CFO personalization" wide={!compact}>
      <Field label={tr("settings.uiLanguage")}>
        <select
          value={lang}
          onChange={(event) => setLang(event.target.value as "zh" | "en")}
        >
          <option value="zh">中文</option>
          <option value="en">English</option>
        </select>
      </Field>
      <p className="settings-v2-card-note">{tr("settings.uiLanguage.note")}</p>
      <Field label="Response tone">
        <select
          value={form.responseTone}
          onChange={(event) =>
            setForm((prev) => ({ ...prev, responseTone: event.target.value }))
          }
        >
          <option>Concise</option>
          <option>Balanced</option>
          <option>Comprehensive</option>
        </select>
      </Field>
      <Field label="Preferred language">
        <select
          value={form.language}
          onChange={(event) =>
            setForm((prev) => ({ ...prev, language: event.target.value }))
          }
        >
          <option>English</option>
          <option>Chinese</option>
          <option>Auto</option>
        </select>
      </Field>
      <Field label="Evidence level">
        <select
          value={form.evidenceLevel}
          onChange={(event) =>
            setForm((prev) => ({ ...prev, evidenceLevel: event.target.value }))
          }
        >
          <option>Brief</option>
          <option>Detailed with data</option>
          <option>Audit-heavy</option>
        </select>
      </Field>
      <p className="settings-v2-card-note">
        These preferences shape how the CFO communicates and reasons.
      </p>
    </SettingsPanelCard>
  );
}

function MemoryPanel() {
  return (
    <div className="settings-v2-grid">
      <SettingsPanelCard icon={<Brain />} title="Memory system" wide>
        <StatusLine label="Short-term memory" value="Last 5 turns" />
        <StatusLine label="Session summary" value="Enabled after threshold" />
        <StatusLine label="Shared across agents" value="Enabled" />
        <p className="settings-v2-card-note">
          CFO and specialists share a bounded memory context to avoid duplicated
          context passing and unsupported recall.
        </p>
      </SettingsPanelCard>
    </div>
  );
}

function PrivacyPanel() {
  return (
    <div className="settings-v2-grid">
      <SettingsPanelCard icon={<LockKeyhole />} title="Data handling" wide>
        <StatusLine label="Storage" value="Local Postgres" />
        <StatusLine label="Market data" value="Disabled" />
        <StatusLine label="High-risk audit" value="Required" />
        <StatusLine label="Financial disclaimer" value="Enabled" />
      </SettingsPanelCard>
    </div>
  );
}

function DeveloperPanel({
  apiBaseUrl,
  showDeveloperTools,
}: {
  apiBaseUrl: string;
  showDeveloperTools: boolean;
}) {
  return (
    <div className="settings-v2-grid">
      <SettingsPanelCard icon={<FileText />} title="Developer controls" wide>
        <StatusLine label="Developer pages" value={showDeveloperTools ? "Visible" : "Hidden"} />
        <StatusLine label="API base URL" value={apiBaseUrl} />
        <StatusLine label="Agent runs" value="Available" />
        <StatusLine label="Eval harness" value="Available" />
        <StatusLine label="Replay" value="Available" />
      </SettingsPanelCard>
    </div>
  );
}

function WorkspaceStatusRail({
  dataSourceStatus,
  transactionCount,
  latestImport,
  form,
}: {
  dataSourceStatus?: DataSourceStatus | null;
  transactionCount: number;
  latestImport: DataSourceStatus["latest_import"] | null;
  form: ProfileForm;
}) {
  return (
    <aside className="settings-v2-status-rail">
      <h3>Workspace status</h3>
      <StatusCard icon={<Database />} title="Data Sources">
        <StatusLine label="Alipay statement" value="Ready" tone="good" />
        <StatusLine label="WeChat statement" value="Planned" tone="warn" />
        <StatusLine label="Transactions" value={transactionCount.toLocaleString()} />
        <StatusLine label="Latest import" value={latestImport?.source_file ?? "None"} />
      </StatusCard>
      <StatusCard icon={<Brain />} title="Memory">
        <StatusLine label="Memory system" value="Enabled" tone="good" />
        <StatusLine label="Recent turns" value="No session yet" />
      </StatusCard>
      <StatusCard icon={<Bot />} title="Agent">
        <StatusLine label="Default assistant" value="CFO" tone="good" />
        <StatusLine
          label="Response style"
          value={form.responseTone || "Not configured"}
          tone={form.responseTone ? "good" : undefined}
        />
        <StatusLine label="Market context" value="Disabled" />
      </StatusCard>
      <button className="settings-v2-overview" type="button">
        <BarChart3 />
        View workspace overview
        <ExternalLink />
      </button>
    </aside>
  );
}

function SettingsPanelCard({
  icon,
  title,
  children,
  wide = false,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
  wide?: boolean;
}) {
  return (
    <article className={`settings-v2-panel-card ${wide ? "settings-v2-wide" : ""}`}>
      <div className="settings-v2-panel-title">
        <span>{icon}</span>
        <h3>{title}</h3>
        {title === "Personal details" && (
          <button className="settings-v2-edit-button" type="button">
            <Pencil />
            Edit
          </button>
        )}
      </div>
      {children}
    </article>
  );
}

function StatusCard({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <article className="settings-v2-status-card">
      <div className="settings-v2-status-title">
        <span>{icon}</span>
        <strong>{title}</strong>
        <ChevronRight />
      </div>
      {children}
    </article>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="settings-v2-field">
      <span>{label}</span>
      {children}
    </label>
  );
}

function BaselineField({
  label,
  value,
  percent,
  onChange,
}: {
  label: string;
  value: string;
  percent: number | null;
  onChange: (value: string) => void;
}) {
  return (
    <div className="settings-v2-baseline-row">
      <span>{label}</span>
      <input value={value} onChange={(event) => onChange(event.target.value)} />
      {percent === null ? (
        <strong className="settings-v2-no-data">No data</strong>
      ) : (
        <>
          <div className="settings-v2-progress">
            <div style={{ width: `${percent}%` }} />
          </div>
          <strong>{percent}%</strong>
        </>
      )}
    </div>
  );
}

function StatusLine({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "good" | "warn";
}) {
  return (
    <div className="settings-v2-status-line">
      <span>{label}</span>
      <strong className={tone ? `settings-v2-tone-${tone}` : ""}>{value}</strong>
    </div>
  );
}

function ActiveIcon({ section }: { section: SettingsSection }) {
  const item = navItems.find((nav) => nav.id === section) ?? navItems[0];
  const Icon = item.icon;
  return <Icon />;
}

function buildProfileForm(
  profile: Record<string, any> | null | undefined,
  profileName: string,
  monthlyIncome: number
): ProfileForm {
  return {
    name: profile?.name || (profileName && profileName !== "User" ? profileName : ""),
    occupation: profile?.occupation || "",
    monthly_income:
      profile?.monthly_income != null
        ? formatNumberInput(profile.monthly_income)
        : monthlyIncome > 0
          ? formatNumberInput(monthlyIncome)
          : "",
    monthly_expenses:
      profile?.monthly_expenses != null ? formatNumberInput(profile.monthly_expenses) : "",
    cash_balance:
      profile?.assets?.cash_balance != null
        ? formatNumberInput(profile.assets.cash_balance)
        : "",
    savings:
      profile?.assets?.savings != null ? formatNumberInput(profile.assets.savings) : "",
    risk_tolerance: profile?.risk_tolerance || "moderate",
    goals:
      Array.isArray(profile?.financial_goals) && profile.financial_goals.length > 0
        ? profile.financial_goals
        : [],
    newGoal: "",
    responseTone: TONE_TO_LABEL[profile?.preferences?.response_tone] ?? "Balanced",
    language: LANGUAGE_TO_LABEL[profile?.preferences?.preferred_language] ?? "Auto",
    evidenceLevel: EVIDENCE_TO_LABEL[profile?.preferences?.evidence_level] ?? "Detailed with data",
    notes: profile?.notes || "",
  };
}

const TONE_TO_LABEL: Record<string, string> = {
  concise: "Concise",
  balanced: "Balanced",
  comprehensive: "Comprehensive",
};
const LANGUAGE_TO_LABEL: Record<string, string> = {
  en: "English",
  zh: "Chinese",
  auto: "Auto",
};
const EVIDENCE_TO_LABEL: Record<string, string> = {
  brief: "Brief",
  detailed: "Detailed with data",
  audit_heavy: "Audit-heavy",
};

export function formToPreferences(form: ProfileForm) {
  const tone = Object.entries(TONE_TO_LABEL).find(([, label]) => label === form.responseTone)?.[0] ?? "balanced";
  const language = Object.entries(LANGUAGE_TO_LABEL).find(([, label]) => label === form.language)?.[0] ?? "auto";
  const evidence = Object.entries(EVIDENCE_TO_LABEL).find(([, label]) => label === form.evidenceLevel)?.[0] ?? "detailed";
  return {
    response_tone: tone as "concise" | "balanced" | "comprehensive",
    preferred_language: language as "en" | "zh" | "auto",
    evidence_level: evidence as "brief" | "detailed" | "audit_heavy",
  };
}

function addGoal(
  form: ProfileForm,
  setForm: (updater: (prev: ProfileForm) => ProfileForm) => void
) {
  const goal = form.newGoal.trim();
  if (!goal || form.goals.includes(goal)) return;
  setForm((prev) => ({ ...prev, goals: [...prev.goals, goal], newGoal: "" }));
}

function parseMoney(value: string): number {
  const cleaned = value.replace(/[^\d.-]/g, "");
  const parsed = Number(cleaned);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatNumberInput(value: number): string {
  return value ? String(value) : "";
}

function toTitle(value: string): string {
  return value.slice(0, 1).toUpperCase() + value.slice(1);
}

function sectionTitle(section: SettingsSection): string {
  return {
    profile: "Profile",
    dataSources: "Data Sources",
    agent: "Agent Behavior",
    memory: "Memory",
    privacy: "Privacy & Safety",
    developer: "Developer",
  }[section];
}

function sectionSubtitle(section: SettingsSection): string {
  return {
    profile: "Personalize how the CFO evaluates your financial situation.",
    dataSources: "Connect statements and review import health.",
    agent: "Control how the CFO communicates and delegates work.",
    memory: "Manage what the CFO remembers across conversations.",
    privacy: "Review data handling and safety controls.",
    developer: "Inspect runtime, eval, replay, and API configuration.",
  }[section];
}

function openCsvPicker(onImport: (file: File) => void) {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = ".csv,.xlsx,.pdf";
  input.onchange = (event) => {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (file) onImport(file);
  };
  input.click();
}

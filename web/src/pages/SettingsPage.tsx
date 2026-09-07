import {
  BarChart3,
  Bot,
  Brain,
  ChevronRight,
  CircleHelp,
  Coins,
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
  UserRound,
  WalletCards,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useI18n } from "../i18n";
import {
  fetchCapabilities,
  updateProfile,
  type CapabilityCatalogItem,
  type DataSourceStatus,
  type ProfileUpdatePayload,
} from "../services/financeApi";
import { SubscriptionManager } from "../components/inbox/SubscriptionManager";
import { StatementImportManager } from "../components/statements/StatementImportManager";

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
  initialSection?: SettingsSection;
};

export type SettingsSection =
  | "profile"
  | "dataSources"
  | "costs"
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
  reportingCurrency: string;
  monthlyAiBudget: string;
  notes: string;
};

const navItems = [
  { id: "profile", zh: "个人资料", en: "Profile", icon: UserRound },
  { id: "dataSources", zh: "数据源", en: "Data Sources", icon: Database },
  { id: "costs", zh: "成本报告", en: "Cost Reporting", icon: Coins },
  { id: "agent", zh: "CFO 行为", en: "CFO Behavior", icon: Bot },
  { id: "memory", zh: "记忆", en: "Memory", icon: Brain },
  { id: "privacy", zh: "隐私与安全", en: "Privacy & Safety", icon: ShieldCheck },
  { id: "developer", zh: "开发者", en: "Developer", icon: FileText },
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
  initialSection = "profile",
}: SettingsPageProps) {
  const { lang } = useI18n();
  const [activeSection, setActiveSection] = useState<SettingsSection>(initialSection);
  const [form, setForm] = useState<ProfileForm>(() =>
    buildProfileForm(profile, profileName, monthlyIncome)
  );
  const [savedForm, setSavedForm] = useState<ProfileForm>(() =>
    buildProfileForm(profile, profileName, monthlyIncome)
  );
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  useEffect(() => {
    const next = buildProfileForm(profile, profileName, monthlyIncome);
    setForm(next);
    setSavedForm(next);
  }, [profile, profileName, monthlyIncome]);

  useEffect(() => {
    setActiveSection(initialSection);
  }, [initialSection]);

  useEffect(() => {
    if (!showDeveloperTools && activeSection === "developer") {
      setActiveSection("profile");
    }
  }, [activeSection, showDeveloperTools]);

  const isDirty = JSON.stringify(form) !== JSON.stringify(savedForm);
  const loadedTransactionCount =
    dataSourceStatus?.transaction_count ?? transactionCount;
  const latestImport = dataSourceStatus?.latest_import ?? null;
  const activeSectionLabel = sectionTitle(activeSection, lang);
  const saveStatusTitle = saveError
    ? localize(lang, "无法保存修改", "Could not save changes")
    : isSaving
      ? localize(lang, `正在保存${activeSectionLabel}设置`, `Saving ${activeSectionLabel.toLowerCase()} preferences`)
      : isDirty
        ? localize(lang, `${activeSectionLabel}有未保存修改`, `Unsaved changes in ${activeSectionLabel}`)
        : saveMessage
          ? saveMessage
          : localize(lang, "所有修改均已保存", "All changes saved");
  const saveStatusDetail = saveError
    ? saveError
    : isSaving
      ? localize(lang, "正在将修改应用到财务工作台。", "Applying your edits to the finance workspace.")
      : isDirty
        ? localize(lang, "请确认修改后再保存。", "Review your edits before applying them.")
        : localize(lang, "当前设置已是最新状态。", "Your settings are up to date.");

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
        cost_preferences: {
          reporting_currency: form.reportingCurrency,
          monthly_ai_budget: parseOptionalMoney(form.monthlyAiBudget),
        },
      };
      await updateProfile(userId, payload);
      setSavedForm(form);
      setSaveMessage(localize(lang, "个人资料已保存", "Profile saved"));
      await onProfileSaved?.();
    } catch (error: any) {
      setSaveError(error?.message ?? localize(lang, "个人资料保存失败", "Failed to save profile"));
    } finally {
      setIsSaving(false);
    }
  };

  const content = useMemo(() => {
    if (activeSection === "dataSources") {
      return (
        <DataSourcesPanel
          userId={userId}
          onChanged={onProfileSaved}
          lang={lang}
        />
      );
    }
    if (activeSection === "agent") {
      return <AgentPanel form={form} setForm={setForm} />;
    }
    if (activeSection === "costs") {
      return <CostReportingPanel form={form} setForm={setForm} lang={lang} />;
    }
    if (activeSection === "memory") {
      return <MemoryPanel lang={lang} />;
    }
    if (activeSection === "privacy") {
      return <PrivacyPanel lang={lang} />;
    }
    if (activeSection === "developer") {
      return (
        <DeveloperPanel
          apiBaseUrl={apiBaseUrl}
          showDeveloperTools={showDeveloperTools}
        />
      );
    }
    return <ProfilePanel form={form} setForm={setForm} lang={lang} />;
  }, [
    activeSection,
    apiBaseUrl,
    dataSourceStatus,
    form,
    lang,
    latestImport,
    loadedTransactionCount,
    onProfileSaved,
    showDeveloperTools,
    userId,
  ]);

  return (
    <section className="settings-v2-page">
          <div className="settings-v2-heading">
            <h1>{localize(lang, "设置", "Settings")}</h1>
            <p>{localize(lang, "管理财务工作台、数据、记忆与 CFO 行为。", "Configure your finance workspace, data, memory, and CFO behavior.")}</p>
          </div>

          <div className="settings-v2-layout">
            <aside className="settings-v2-nav-card">
              <nav className="settings-v2-nav">
                {navItems
                  .filter((item) => item.id !== "developer" || showDeveloperTools)
                  .map((item) => {
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
                      <span>{item[lang]}</span>
                      <ChevronRight />
                    </button>
                  );
                  })}
              </nav>

              <div className="settings-v2-help">
                <CircleHelp />
                <div>
                  <strong>{localize(lang, "需要帮助？", "Need help?")}</strong>
                  <span>{localize(lang, "查看文档或联系支持", "View docs or contact support")}</span>
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
                  <p>{sectionSubtitle(activeSection, lang)}</p>
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
                    {localize(lang, "放弃修改", "Discard")}
                  </button>
                  <button
                    type="button"
                    className="settings-v2-primary"
                    disabled={!isDirty || isSaving}
                    onClick={handleProfileSave}
                  >
                    <Save />
                    {isSaving
                      ? localize(lang, "保存中", "Saving")
                      : saveError
                        ? localize(lang, "重试保存", "Retry save")
                        : localize(lang, "保存修改", "Save changes")}
                  </button>
                </div>
              </div>
            </main>

            <WorkspaceStatusRail
              dataSourceStatus={dataSourceStatus}
              transactionCount={loadedTransactionCount}
              latestImport={latestImport}
              form={form}
              lang={lang}
            />
      </div>
    </section>
  );
}

function ProfilePanel({
  form,
  setForm,
  lang,
}: {
  form: ProfileForm;
  setForm: (updater: (prev: ProfileForm) => ProfileForm) => void;
  lang: "zh" | "en";
}) {
  return (
    <div className="settings-v2-grid">
      <SettingsPanelCard icon={<UserRound />} title={localize(lang, "个人信息", "Personal details")} editLabel={localize(lang, "编辑", "Edit")}>
        <Field label={localize(lang, "姓名", "Name")}>
          <input
            value={form.name}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, name: event.target.value }))
            }
          />
        </Field>
        <Field label={localize(lang, "职业", "Occupation")}>
          <input
            value={form.occupation}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, occupation: event.target.value }))
            }
          />
        </Field>
        <Field label={localize(lang, "月收入", "Monthly income")}>
          <input
            value={form.monthly_income}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, monthly_income: event.target.value }))
            }
          />
        </Field>
      </SettingsPanelCard>

      <SettingsPanelCard icon={<Goal />} title={localize(lang, "风险偏好与目标", "Risk & goals")}>
        <div className="settings-v2-field">
          <label>{localize(lang, "风险偏好", "Risk preference")}</label>
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
                {riskLabel(option, lang)}
              </button>
            ))}
          </div>
        </div>
        <div className="settings-v2-field">
          <label>{localize(lang, "财务目标", "Financial goals")}</label>
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
              <p className="settings-v2-empty-inline">{localize(lang, "尚未设置目标", "No goals configured yet.")}</p>
            )}
            <div className="settings-v2-add-goal">
              <input
                value={form.newGoal}
                placeholder={localize(lang, "添加目标", "Add goal")}
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

      <SettingsPanelCard icon={<BarChart3 />} title={localize(lang, "财务基线", "Financial baseline")}>
        <BaselineField
          label={localize(lang, "现金余额", "Cash balance")}
          value={form.cash_balance}
          percent={form.cash_balance ? 77 : null}
          onChange={(value) =>
            setForm((prev) => ({ ...prev, cash_balance: value }))
          }
        />
        <BaselineField
          label={localize(lang, "月支出目标", "Monthly expense target")}
          value={form.monthly_expenses}
          percent={form.monthly_expenses ? 60 : null}
          onChange={(value) =>
            setForm((prev) => ({ ...prev, monthly_expenses: value }))
          }
        />
        <BaselineField
          label={localize(lang, "储蓄目标", "Savings target")}
          value={form.savings}
          percent={form.savings ? 45 : null}
          onChange={(value) => setForm((prev) => ({ ...prev, savings: value }))}
        />
        <p className="settings-v2-card-note">
          {localize(lang, "CFO 会根据这些目标评估进度并提供更准确的建议。", "Targets are used by the CFO to evaluate progress and give better advice.")}
        </p>
      </SettingsPanelCard>

      <AgentPanel form={form} setForm={setForm} compact />
    </div>
  );
}

function DataSourcesPanel({
  userId,
  onChanged,
  lang,
}: {
  userId: string;
  onChanged?: () => Promise<void> | void;
  lang: "zh" | "en";
}) {
  return (
    <div className="settings-v2-grid">
      <div className="settings-v2-wide"><StatementImportManager userId={userId} onChanged={onChanged} /></div>
      <SettingsPanelCard icon={<Database />} title={localize(lang, "财经内容订阅", "Finance content subscriptions")} wide>
        <p className="settings-v2-card-note settings-v2-card-note-leading">
          {localize(
            lang,
            "RSS 内容只会在你请求时刷新；收件箱内容与 CFO 建议保持分离，不会自动加入知识库。",
            "RSS sources are refreshed only when you request it. Inbox content remains separate from CFO advice and is never added to knowledge automatically."
          )}
        </p>
        <SubscriptionManager userId={userId} />
      </SettingsPanelCard>
    </div>
  );
}

function CostReportingPanel({
  form,
  setForm,
  lang,
}: {
  form: ProfileForm;
  setForm: (updater: (prev: ProfileForm) => ProfileForm) => void;
  lang: "zh" | "en";
}) {
  return (
    <div className="settings-v2-grid">
      <SettingsPanelCard icon={<Coins />} title={localize(lang, "报告币种", "Reporting currency")} wide>
        <Field label={localize(lang, "显示币种", "Display currency")}>
          <select
            value={form.reportingCurrency}
            onChange={(event) =>
              setForm((prev) => ({
                ...prev,
                reportingCurrency: event.target.value,
              }))
            }
          >
            <option value="CNY">CNY · Chinese yuan</option>
            <option value="USD">USD · US dollar</option>
            <option value="AUD">AUD · Australian dollar</option>
          </select>
        </Field>
        <p className="settings-v2-card-note">
          FinDesk keeps every provider charge in its native billing currency, then
          derives this reporting view from immutable historical exchange-rate snapshots.
        </p>
      </SettingsPanelCard>
      <SettingsPanelCard icon={<PiggyBank />} title={localize(lang, "AI 成本控制", "AI spending guardrail")} wide>
        <Field label={localize(lang, "每月 AI 预算", "Monthly AI budget")}>
          <div className="settings-v2-money-input">
            <span>{form.reportingCurrency}</span>
            <input
              inputMode="decimal"
              placeholder={localize(lang, "尚未设置", "Not configured")}
              value={form.monthlyAiBudget}
              onChange={(event) =>
                setForm((prev) => ({
                  ...prev,
                  monthlyAiBudget: event.target.value,
                }))
              }
            />
          </div>
        </Field>
        <p className="settings-v2-card-note">
          The budget applies to complete, auditable API costs only. Missing provider
          pricing or exchange rates are reported as coverage gaps, never as zero spend.
        </p>
      </SettingsPanelCard>
      <SettingsPanelCard icon={<Database />} title={localize(lang, "成本数据源", "Cost sources")} wide>
        <StatusLine label="FinDesk Agent Run API" value={localize(lang, "已连接", "Connected")} tone="good" />
        <StatusLine label={localize(lang, "外部项目 API", "External project API usage")} value={localize(lang, "未连接", "Not connected")} />
        <StatusLine label={localize(lang, "AI 订阅", "AI subscriptions")} value={localize(lang, "未连接", "Not connected")} />
        <p className="settings-v2-card-note">
          Provider exports and subscription connectors will appear here only after an
          authoritative source is configured.
        </p>
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
    <SettingsPanelCard icon={<Bot />} title={localize(lang, "CFO 个性化", "CFO personalization")} wide={!compact}>
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
      <Field label={localize(lang, "回复语气", "Response tone")}>
        <select
          value={form.responseTone}
          onChange={(event) =>
            setForm((prev) => ({ ...prev, responseTone: event.target.value }))
          }
        >
          <option value="Concise">{localize(lang, "简洁", "Concise")}</option>
          <option value="Balanced">{localize(lang, "平衡", "Balanced")}</option>
          <option value="Comprehensive">{localize(lang, "详尽", "Comprehensive")}</option>
        </select>
      </Field>
      <Field label={localize(lang, "CFO 回复语言", "Preferred language")}>
        <select
          value={form.language}
          onChange={(event) =>
            setForm((prev) => ({ ...prev, language: event.target.value }))
          }
        >
          <option value="English">{localize(lang, "英语", "English")}</option>
          <option value="Chinese">{localize(lang, "中文", "Chinese")}</option>
          <option value="Auto">{localize(lang, "自动", "Auto")}</option>
        </select>
      </Field>
      <Field label={localize(lang, "证据详细程度", "Evidence level")}>
        <select
          value={form.evidenceLevel}
          onChange={(event) =>
            setForm((prev) => ({ ...prev, evidenceLevel: event.target.value }))
          }
        >
          <option value="Brief">{localize(lang, "简要", "Brief")}</option>
          <option value="Detailed with data">{localize(lang, "包含数据明细", "Detailed with data")}</option>
          <option value="Audit-heavy">{localize(lang, "审计优先", "Audit-heavy")}</option>
        </select>
      </Field>
      <p className="settings-v2-card-note">
        {localize(lang, "这些偏好会影响 CFO 的沟通方式与分析深度。", "These preferences shape how the CFO communicates and reasons.")}
      </p>
    </SettingsPanelCard>
  );
}

function MemoryPanel({ lang }: { lang: "zh" | "en" }) {
  return (
    <div className="settings-v2-grid">
      <SettingsPanelCard icon={<Brain />} title={localize(lang, "记忆系统", "Memory system")} wide>
        <StatusLine label={localize(lang, "短期记忆", "Short-term memory")} value={localize(lang, "最近 5 轮", "Last 5 turns")} />
        <StatusLine label={localize(lang, "会话摘要", "Session summary")} value={localize(lang, "达到阈值后启用", "Enabled after threshold")} />
        <StatusLine label={localize(lang, "Agent 间共享", "Shared across agents")} value={localize(lang, "已启用", "Enabled")} />
        <p className="settings-v2-card-note">
          CFO and specialists share a bounded memory context to avoid duplicated
          context passing and unsupported recall.
        </p>
      </SettingsPanelCard>
    </div>
  );
}

function PrivacyPanel({ lang }: { lang: "zh" | "en" }) {
  return (
    <div className="settings-v2-grid">
      <SettingsPanelCard icon={<LockKeyhole />} title={localize(lang, "数据处理", "Data handling")} wide>
        <StatusLine label={localize(lang, "存储", "Storage")} value={localize(lang, "本地 Postgres", "Local Postgres")} />
        <StatusLine label={localize(lang, "市场数据", "Market data")} value={localize(lang, "已停用", "Disabled")} />
        <StatusLine label={localize(lang, "高风险审计", "High-risk audit")} value={localize(lang, "必须", "Required")} />
        <StatusLine label={localize(lang, "财务免责声明", "Financial disclaimer")} value={localize(lang, "已启用", "Enabled")} />
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
  const [capabilities, setCapabilities] = useState<CapabilityCatalogItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    fetchCapabilities()
      .then((items) => {
        if (!cancelled) setCapabilities(items);
      })
      .catch((caught: Error) => {
        if (!cancelled) setError(caught.message);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="settings-v2-grid">
      <SettingsPanelCard icon={<FileText />} title="Developer controls" wide>
        <StatusLine label="Developer pages" value={showDeveloperTools ? "Visible" : "Hidden"} />
        <StatusLine label="API base URL" value={apiBaseUrl} />
        <p className="settings-v2-card-note">
          Inspect built-in capabilities and optional local connectors. Commands,
          URLs, and credentials are never returned by this endpoint.
        </p>
      </SettingsPanelCard>
      <SettingsPanelCard icon={<Database />} title="Local runtime capabilities" wide>
        {isLoading ? (
          <p className="settings-v2-capability-state">Loading capabilities...</p>
        ) : error ? (
          <p className="settings-v2-capability-state settings-v2-capability-error">
            {error}
          </p>
        ) : capabilities.length === 0 ? (
          <p className="settings-v2-capability-state">No capabilities registered.</p>
        ) : (
          <div className="settings-v2-capability-list">
            {capabilities.map((item) => {
              const state = capabilityState(item);
              return (
                <article
                  className="settings-v2-capability-row"
                  key={item.descriptor.capability_id}
                >
                  <div>
                    <strong>{item.descriptor.title}</strong>
                    <code>{item.descriptor.capability_id}</code>
                    <span>{item.descriptor.description}</span>
                  </div>
                  <div className="settings-v2-capability-meta">
                    <span>{item.descriptor.kind}</span>
                    <span>{item.descriptor.source}</span>
                    <span>{item.descriptor.risk_level} risk</span>
                    <span>{item.descriptor.execution_mode}</span>
                    <strong className={`settings-v2-capability-${state}`}>
                      {state}
                    </strong>
                  </div>
                  {item.status.reason && <p>{item.status.reason}</p>}
                  {item.status.checked_at && (
                    <p>Checked {formatCapabilityCheckedAt(item.status.checked_at)}</p>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </SettingsPanelCard>
    </div>
  );
}

function capabilityState(item: CapabilityCatalogItem) {
  if (!item.status.enabled) return "disabled";
  if (!item.status.available) return "unhealthy";
  return "available";
}

function formatCapabilityCheckedAt(value: string) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function WorkspaceStatusRail({
  dataSourceStatus,
  transactionCount,
  latestImport,
  form,
  lang,
}: {
  dataSourceStatus?: DataSourceStatus | null;
  transactionCount: number;
  latestImport: DataSourceStatus["latest_import"] | null;
  form: ProfileForm;
  lang: "zh" | "en";
}) {
  return (
    <aside className="settings-v2-status-rail">
      <h3>{localize(lang, "工作台状态", "Workspace status")}</h3>
      <StatusCard icon={<Database />} title={localize(lang, "数据源", "Data Sources")}>
        <StatusLine label={localize(lang, "支付宝账单", "Alipay statement")} value={localize(lang, "已就绪", "Ready")} tone="good" />
        <StatusLine label={localize(lang, "微信账单", "WeChat statement")} value={localize(lang, "计划中", "Planned")} tone="warn" />
        <StatusLine label={localize(lang, "交易数量", "Transactions")} value={transactionCount.toLocaleString()} />
        <StatusLine label={localize(lang, "最近导入", "Latest import")} value={latestImport?.source_file ?? localize(lang, "无", "None")} />
      </StatusCard>
      <StatusCard icon={<Brain />} title={localize(lang, "记忆", "Memory")}>
        <StatusLine label={localize(lang, "记忆系统", "Memory system")} value={localize(lang, "已启用", "Enabled")} tone="good" />
        <StatusLine label={localize(lang, "最近对话", "Recent turns")} value={localize(lang, "暂无会话", "No session yet")} />
      </StatusCard>
      <StatusCard icon={<Bot />} title="CFO">
        <StatusLine label={localize(lang, "默认助手", "Default assistant")} value="CFO" tone="good" />
        <StatusLine
          label={localize(lang, "回复风格", "Response style")}
          value={form.responseTone ? preferenceLabel(form.responseTone, lang) : localize(lang, "尚未设置", "Not configured")}
          tone={form.responseTone ? "good" : undefined}
        />
        <StatusLine label={localize(lang, "市场上下文", "Market context")} value={localize(lang, "已停用", "Disabled")} />
      </StatusCard>
      <StatusCard icon={<Coins />} title={localize(lang, "AI 成本", "AI Costs")}>
        <StatusLine
          label={localize(lang, "报告币种", "Reporting currency")}
          value={form.reportingCurrency}
          tone="good"
        />
        <StatusLine
          label={localize(lang, "每月预算", "Monthly budget")}
          value={form.monthlyAiBudget || localize(lang, "尚未设置", "Not configured")}
        />
      </StatusCard>
      <button className="settings-v2-overview" type="button">
        <BarChart3 />
        {localize(lang, "查看工作台概览", "View workspace overview")}
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
  editLabel,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
  wide?: boolean;
  editLabel?: string;
}) {
  return (
    <article className={`settings-v2-panel-card ${wide ? "settings-v2-wide" : ""}`}>
      <div className="settings-v2-panel-title">
        <span>{icon}</span>
        <h3>{title}</h3>
        {editLabel && (
          <button className="settings-v2-edit-button" type="button">
            <Pencil />
            {editLabel}
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
        <strong className="settings-v2-no-data">—</strong>
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
    reportingCurrency: profile?.cost_preferences?.reporting_currency ?? "USD",
    monthlyAiBudget:
      profile?.cost_preferences?.monthly_ai_budget != null
        ? formatNumberInput(profile.cost_preferences.monthly_ai_budget)
        : "",
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

function parseOptionalMoney(value: string): number | null {
  if (!value.trim()) return null;
  return parseMoney(value);
}

function formatNumberInput(value: number | string): string {
  return value ? String(value) : "";
}

function toTitle(value: string): string {
  return value.slice(0, 1).toUpperCase() + value.slice(1);
}

function localize(lang: "zh" | "en", zh: string, en: string): string {
  return lang === "zh" ? zh : en;
}

function riskLabel(value: string, lang: "zh" | "en"): string {
  const labels: Record<string, [string, string]> = {
    conservative: ["保守", "Conservative"],
    moderate: ["稳健", "Moderate"],
    aggressive: ["进取", "Aggressive"],
  };
  const label = labels[value] ?? [value, toTitle(value)];
  return localize(lang, label[0], label[1]);
}

function preferenceLabel(value: string, lang: "zh" | "en"): string {
  const labels: Record<string, string> = {
    Concise: "简洁",
    Balanced: "平衡",
    Comprehensive: "详尽",
    English: "英语",
    Chinese: "中文",
    Auto: "自动",
    Brief: "简要",
    "Detailed with data": "包含数据明细",
    "Audit-heavy": "审计优先",
  };
  return lang === "zh" ? labels[value] ?? value : value;
}

function sectionTitle(section: SettingsSection, lang: "zh" | "en"): string {
  const item = navItems.find((entry) => entry.id === section) ?? navItems[0];
  return item[lang];
}

function sectionSubtitle(section: SettingsSection, lang: "zh" | "en"): string {
  const labels: Record<SettingsSection, [string, string]> = {
    profile: ["设置 CFO 评估你财务状况时使用的个人信息。", "Personalize how the CFO evaluates your financial situation."],
    dataSources: ["连接账单并检查数据导入状态。", "Connect statements and review import health."],
    costs: ["选择报告币种并设置 AI 成本预算。", "Choose a reporting currency and set an AI spending guardrail."],
    agent: ["控制 CFO 的沟通方式和任务处理偏好。", "Control how the CFO communicates and delegates work."],
    memory: ["管理 CFO 在不同会话中保留的记忆。", "Manage what the CFO remembers across conversations."],
    privacy: ["查看数据处理方式和安全控制。", "Review data handling and safety controls."],
    developer: ["检查运行环境、评测、回放和 API 配置。", "Inspect runtime, eval, replay, and API configuration."],
  };
  return localize(lang, labels[section][0], labels[section][1]);
}

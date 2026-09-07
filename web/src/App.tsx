import { useState } from "react";
import {
  Bell,
  LayoutDashboard,
  LineChart,
  LogOut,
  Menu,
  MessagesSquare,
  Settings as SettingsIcon,
  X,
} from "lucide-react";
import { getApiBaseUrl } from "./services/financeApi";
import { useFinanceWorkspaceData } from "./hooks/useFinanceWorkspaceData";

import { AgentTeamPanel } from "./components/AgentTeamPanel";
import { FinanceWorkspacePage } from "./pages/FinanceWorkspacePage";
import { MyOfficePage } from "./pages/MyOfficePage";
import { InvestmentResearchPage } from "./pages/InvestmentResearchPage";
import { FinanceInboxPage } from "./pages/FinanceInboxPage";
import { SettingsPage, type SettingsSection } from "./pages/SettingsPage";
import type { PageId } from "./pages/pageTypes";
import { useI18n } from "./i18n";
import { useAuth } from "./auth";

export default function App() {
  const { user, logout } = useAuth();
  const userId = user.id;
  const { lang, t } = useI18n();
  const l = (zh: string, en: string) => (lang === "zh" ? zh : en);

  const [activePage, setActivePage] = useState<PageId>("workspace");
  const [isNavOpen, setIsNavOpen] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [cfoPrefill, setCfoPrefill] = useState<string | null>(null);
  const [officePrefill, setOfficePrefill] = useState<string | null>(null);
  const [settingsSection, setSettingsSection] = useState<SettingsSection>("profile");

  const {
    profileName,
    profile,
    monthlyIncome,
    txs,
    brief,
    dataSourceStatus,
    loading,
    errMsg,
    isUploading,
    load,
    handleUploadStatement,
    monthlyTrendsData,
    tableTransactions,
    categoryData,
    primaryCurrency,
    budgetStatus,
    duplicateCount,
    topCategory,
  } = useFinanceWorkspaceData(userId);

  const navItems = [
    { id: "workspace" as const, label: t("nav.workspace"), icon: LayoutDashboard },
    { id: "investments" as const, label: t("nav.investments"), icon: LineChart },
    { id: "office" as const, label: t("nav.office"), icon: MessagesSquare },
    { id: "settings" as const, label: t("nav.settings"), icon: SettingsIcon },
  ];

  const onboardingItems = [
    budgetStatus === "risk"
      ? {
          title: l("本周减少弹性支出", "Reduce discretionary spend this week"),
          body: l("支出比例已超过风险阈值，请从最大的弹性支出类目开始检查。", "Your expense ratio is above the risk threshold. Start with the largest flexible category."),
          status: l("高优先级", "High priority"),
        }
      : budgetStatus === "watch"
        ? {
            title: l("设置一条每周支出上限", "Set one weekly spending guardrail"),
            body: l("当前支出偏高但仍可控，可先设置每周上限，再决定是否调整整体预算。", "Spending is elevated but controllable. Use a weekly cap before changing the full budget."),
            status: l("建议", "Recommended"),
          }
        : {
            title: l("保持当前现金流节奏", "Keep the current cash-flow rhythm"),
            body: l("已导入的收支整体稳定，建议先自动化储蓄，再增加弹性支出。", "Loaded income and expenses look stable. Automate savings before adding discretionary spend."),
            status: l("健康", "Healthy"),
          },
    topCategory
      ? {
          title: l(`复核 ${topCategory.category}`, `Review ${topCategory.category}`),
          body: l(`${topCategory.category} 是当前最大支出类目，共 ${topCategory.amount.toLocaleString()} ${topCategory.currency}。`, `${topCategory.category} is currently the largest expense category at ${topCategory.amount.toLocaleString()} ${topCategory.currency}.`),
          status: l("支出复核", "Spending review"),
        }
      : {
          title: l("导入近期交易", "Import recent transactions"),
          body: l("添加账单后即可查看类目复核、异常检查和预算建议。", "Add a statement to unlock category review, anomaly checks, and budget recommendations."),
          status: l("需要数据", "Data needed"),
        },
    duplicateCount > 0
      ? {
          title: l("检查重复交易", "Check duplicate transactions"),
          body: l(`发现 ${duplicateCount} 笔疑似重复交易，请在使用报表前完成复核。`, `${duplicateCount} potential duplicates are flagged and should be reviewed before relying on reports.`),
          status: l("数据质量", "Data quality"),
        }
      : {
          title: l("数据质量良好", "Data quality looks clean"),
          body: l("当前已导入数据中未发现重复交易。", "No duplicate transactions are currently flagged in the loaded dataset."),
          status: l("已验证", "Verified"),
        },
  ];

  const actionItems =
    brief?.has_data && brief.actions.length > 0
      ? brief.actions.map((action) => ({
          title: action.title,
          body: action.rationale,
          status: `Impact ${action.impact} · Effort ${action.effort}`,
        }))
      : onboardingItems;
  const actionSource: "agent" | "onboarding" =
    brief?.has_data && brief.actions.length > 0 ? "agent" : "onboarding";

  return (
    <div className="product-shell">
      <aside className={`product-sidebar ${isNavOpen ? "product-sidebar-open" : ""}`}>
        <div className="product-brand-mark">
          <div className="product-logo">F</div>
          <div className="product-brand-title">FinDesk</div>
          <button
            type="button"
            className="product-nav-close"
            aria-label="Close navigation"
            onClick={() => setIsNavOpen(false)}
          >
            <X />
          </button>
        </div>
        <nav className="product-tabs" aria-label="Primary navigation">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = activePage === item.id;
            return (
              <button
                key={item.id}
                type="button"
                aria-label={item.label}
                aria-current={active ? "page" : undefined}
                title={item.label}
                onClick={() => {
                  if (item.id === "settings") setSettingsSection("profile");
                  setActivePage(item.id);
                  setIsNavOpen(false);
                }}
                className={`product-tab ${active ? "product-tab-active" : ""}`}
              >
                <Icon className="h-4 w-4" />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
        <div className="product-sidebar-foot">
          <span>{l("个人 CFO", "PERSONAL CFO")}</span>
          <p>{l("让每一个财务决策都有据可循。", "Evidence-led financial decisions.")}</p>
        </div>
      </aside>

      {isNavOpen && (
        <button
          type="button"
          className="product-nav-backdrop"
          aria-label="Close navigation"
          onClick={() => setIsNavOpen(false)}
        />
      )}

      <div className="product-app-frame">
        <header className="product-utility-bar">
          <button
            type="button"
            className="product-nav-trigger"
            aria-label="Open navigation"
            aria-expanded={isNavOpen}
            onClick={() => setIsNavOpen(true)}
          >
            <Menu />
          </button>
          <div className="product-utility-context">
            <span>{navItems.find((item) => item.id === activePage)?.label ?? "FinDesk"}</span>
          </div>
          <div className="product-topbar-actions">
            <Bell className="product-bell" />
            <div className="product-avatar" title={user.email}>
              {user.email.slice(0, 2).toUpperCase()}
            </div>
            <button
              type="button"
              className="product-logout"
              onClick={() => void logout()}
              aria-label={l("退出登录", "Sign out")}
              title={l("退出登录", "Sign out")}
            >
              <LogOut />
            </button>
          </div>
        </header>

        <div
          className={`product-content${
            isSidebarOpen && activePage === "workspace" ? " product-content-with-chat" : ""
          }`}
        >
        {activePage === "workspace" ? (
          <FinanceWorkspacePage
            userId={userId}
            actionSource={actionSource}
            brief={brief}
            dataSourceStatus={dataSourceStatus}
            latestImportAt={dataSourceStatus?.latest_import?.created_at ?? null}
            loading={loading}
            errMsg={errMsg}
            isUploading={isUploading}
            primaryCurrency={primaryCurrency}
            budgetStatus={budgetStatus}
            duplicateCount={duplicateCount}
            monthlyTrendsData={monthlyTrendsData}
            actionItems={actionItems}
            categoryData={categoryData}
            tableTransactions={tableTransactions}
            onReload={load}
            onOpenInbox={() => setActivePage("inbox")}
            onOpenCfo={() => setIsSidebarOpen(true)}
            onAskCfoAbout={(question) => {
              setCfoPrefill(question);
              setIsSidebarOpen(true);
            }}
            onUploadStatement={handleUploadStatement}
          />
        ) : activePage === "investments" ? (
          <InvestmentResearchPage
            userId={userId}
            onAskCfo={(question) => {
              setOfficePrefill(question);
              setActivePage("office");
            }}
          />
        ) : activePage === "office" ? (
          <MyOfficePage
            userId={userId}
            userName={profileName}
            initialPrompt={officePrefill}
            onInitialPromptConsumed={() => setOfficePrefill(null)}
          />
        ) : activePage === "inbox" ? (
          <FinanceInboxPage
            userId={userId}
            onBack={() => setActivePage("workspace")}
            onManageSources={() => {
              setSettingsSection("dataSources");
              setActivePage("settings");
            }}
          />
        ) : (
          <main className="settings-shell">
              {activePage === "settings" && (
              <SettingsPage
                userId={userId}
                profileName={profileName}
                profile={profile}
                apiBaseUrl={getApiBaseUrl()}
                transactionCount={txs.length}
                dataSourceStatus={dataSourceStatus}
                monthlyIncome={monthlyIncome}
                onProfileSaved={load}
                showDeveloperTools={
                  import.meta.env.VITE_SHOW_DEVELOPER_TOOLS === "true"
                }
                initialSection={settingsSection}
              />
              )}
            </main>
        )}
        </div>
      </div>

      {activePage === "workspace" && (
        <AgentTeamPanel
          isOpen={isSidebarOpen}
          onClose={() => setIsSidebarOpen(false)}
          userId={userId}
          hasFinanceData={txs.length > 0}
          topCategory={topCategory?.category}
          brief={brief}
          userName={profileName}
          prefill={cfoPrefill}
          onPrefillConsumed={() => setCfoPrefill(null)}
        />
      )}
    </div>
  );
}

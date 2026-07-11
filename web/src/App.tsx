import { useState } from "react";
import { Bell, LayoutDashboard, MessagesSquare, Settings as SettingsIcon } from "lucide-react";
import { getApiBaseUrl } from "./services/financeApi";
import { useFinanceWorkspaceData } from "./hooks/useFinanceWorkspaceData";

import { AgentTeamPanel } from "./components/AgentTeamPanel";
import { FinanceWorkspacePage } from "./pages/FinanceWorkspacePage";
import { MyOfficePage } from "./pages/MyOfficePage";
import { SettingsPage } from "./pages/SettingsPage";
import type { PageId } from "./pages/pageTypes";
import { useI18n } from "./i18n";

export default function App() {
  // TODO: Replace hardcoded "demo" with auth-based user identification
  const userId = "demo";
  const { t } = useI18n();

  const [activePage, setActivePage] = useState<PageId>("workspace");
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [cfoPrefill, setCfoPrefill] = useState<string | null>(null);

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
    { id: "office" as const, label: t("nav.office"), icon: MessagesSquare },
    { id: "settings" as const, label: t("nav.settings"), icon: SettingsIcon },
  ];

  const onboardingItems = [
    budgetStatus === "risk"
      ? {
          title: "Reduce discretionary spend this week",
          body: "Your expense ratio is above the risk threshold. Start with the largest flexible category.",
          status: "High priority",
        }
      : budgetStatus === "watch"
        ? {
            title: "Set one weekly spending guardrail",
            body: "Spending is elevated but controllable. Use a weekly cap before changing the full budget.",
            status: "Recommended",
          }
        : {
            title: "Keep the current cash-flow rhythm",
            body: "Loaded income and expenses look stable. Automate savings before adding discretionary spend.",
            status: "Healthy",
          },
    topCategory
      ? {
          title: `Review ${topCategory.category}`,
          body: `${topCategory.category} is currently the largest expense category at ${topCategory.amount.toLocaleString()} ${topCategory.currency}.`,
          status: "Spending review",
        }
      : {
          title: "Import recent transactions",
          body: "Add a statement to unlock category review, anomaly checks, and budget recommendations.",
          status: "Data needed",
        },
    duplicateCount > 0
      ? {
          title: "Check duplicate transactions",
          body: `${duplicateCount} potential duplicates are flagged and should be reviewed before relying on reports.`,
          status: "Data quality",
        }
      : {
          title: "Data quality looks clean",
          body: "No duplicate transactions are currently flagged in the loaded dataset.",
          status: "Verified",
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
      <header className="product-topbar">
        <div className="product-topbar-inner">
          <div className="product-brand-mark">
            <div className="product-logo">F</div>
            <div>
              <div className="product-brand-title">FinDesk</div>
            </div>
          </div>
          <nav className="product-tabs">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = activePage === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setActivePage(item.id)}
                className={`product-tab ${active ? "product-tab-active" : ""}`}
              >
                <Icon className="h-4 w-4" />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
          <div className="product-topbar-actions">
            <Bell className="product-bell" />
            <div className="product-avatar">RM</div>
          </div>
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
            onOpenCfo={() => setIsSidebarOpen(true)}
            onAskCfoAbout={(question) => {
              setCfoPrefill(question);
              setIsSidebarOpen(true);
            }}
            onUploadStatement={handleUploadStatement}
          />
        ) : activePage === "office" ? (
          <MyOfficePage userId={userId} userName={profileName} />
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
                showDeveloperTools={false}
              />
              )}
            </main>
        )}
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

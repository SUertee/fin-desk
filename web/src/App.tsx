import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Bell,
  Bot,
  BookOpenText,
  LayoutDashboard,
  LineChart,
  LogOut,
  Mail,
  Menu,
  Settings as SettingsIcon,
  WalletCards,
  X,
} from "lucide-react";

import { useAuth } from "./auth";
import { useFinanceWorkspaceData } from "./hooks/useFinanceWorkspaceData";
import { useI18n } from "./i18n";
import { CashPlanPage } from "./pages/CashPlanPage";
import { FinanceInboxPage } from "./pages/FinanceInboxPage";
import { FinanceWorkspacePage, type WorkspaceAttentionItem } from "./pages/FinanceWorkspacePage";
import { InvestmentResearchPage } from "./pages/InvestmentResearchPage";
import { LedgerPage } from "./pages/LedgerPage";
import { MyOfficePage } from "./pages/MyOfficePage";
import type { PageId } from "./pages/pageTypes";
import { SettingsPage, type SettingsSection } from "./pages/SettingsPage";
import { getApiBaseUrl } from "./services/financeApi";

export default function App() {
  const { user, logout } = useAuth();
  const userId = user.id;
  const { lang, t } = useI18n();
  const l = (zh: string, en: string) => (lang === "zh" ? zh : en);
  const [activePage, setActivePage] = useState<PageId>("workspace");
  const [isNavOpen, setIsNavOpen] = useState(false);
  const [isCfoOpen, setIsCfoOpen] = useState(false);
  const [isAccountMenuOpen, setIsAccountMenuOpen] = useState(false);
  const [isAttentionOpen, setIsAttentionOpen] = useState(false);
  const [attentionItems, setAttentionItems] = useState<WorkspaceAttentionItem[]>([]);
  const [officePrefill, setOfficePrefill] = useState<string | null>(null);
  const [settingsSection, setSettingsSection] = useState<SettingsSection>("profile");

  const {
    profileName,
    profile,
    monthlyIncome,
    txs,
    dataSourceStatus,
    loading,
    errMsg,
    isUploading,
    load,
    handleUploadStatement,
    handleCreateManualTransaction,
    monthlyTrendsData,
    tableTransactions,
    categoryData,
    primaryCurrency,
    duplicateCount,
  } = useFinanceWorkspaceData(userId);

  const navItems = [
    { id: "workspace" as const, label: t("nav.today"), icon: LayoutDashboard },
    { id: "ledger" as const, label: t("nav.ledger"), icon: BookOpenText },
    { id: "cash-plan" as const, label: t("nav.plan"), icon: WalletCards },
  ];

  const currentPageLabel = navItems.find((item) => item.id === activePage)?.label
    ?? (activePage === "investments"
      ? t("nav.investments")
      : activePage === "inbox"
        ? l("财经收件箱", "Finance Inbox")
        : activePage === "settings"
          ? t("nav.settings")
          : "FinDesk");

  const navigate = (page: PageId) => {
    if (page === "settings") setSettingsSection("profile");
    setActivePage(page);
    setIsNavOpen(false);
    setIsAccountMenuOpen(false);
    setIsAttentionOpen(false);
    setIsCfoOpen(false);
  };

  const openCfo = (question?: string) => {
    if (question) setOfficePrefill(question);
    setIsAccountMenuOpen(false);
    setIsAttentionOpen(false);
    setIsCfoOpen(true);
  };

  const selectStatement = () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".csv,.xlsx,.pdf";
    input.onchange = (event) => {
      const file = (event.target as HTMLInputElement).files?.[0];
      if (file) handleUploadStatement(file);
    };
    input.click();
  };

  const runAttentionAction = (item: WorkspaceAttentionItem) => {
    setIsAttentionOpen(false);
    if (item.actionTarget === "cash-plan") navigate("cash-plan");
    else selectStatement();
  };

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setIsAccountMenuOpen(false);
      setIsAttentionOpen(false);
      setIsCfoOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, []);

  return (
    <div className="product-shell">
      <aside className={`product-sidebar ${isNavOpen ? "product-sidebar-open" : ""}`}>
        <div className="product-brand-mark">
          <div className="product-logo">F</div>
          <div className="product-brand-title">FinDesk</div>
          <button type="button" className="product-nav-close" aria-label={l("关闭导航", "Close navigation")} onClick={() => setIsNavOpen(false)}><X /></button>
        </div>

        <nav className="product-tabs" aria-label={l("主要导航", "Primary navigation")}>
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                type="button"
                aria-current={activePage === item.id ? "page" : undefined}
                title={item.label}
                onClick={() => navigate(item.id)}
                className={`product-tab ${activePage === item.id ? "product-tab-active" : ""}`}
              >
                <Icon className="h-4 w-4" />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        <div className="product-sidebar-secondary">
          <span>{l("更多工具", "MORE TOOLS")}</span>
          <button type="button" className={activePage === "investments" ? "active" : ""} onClick={() => navigate("investments")}><LineChart />{t("nav.investments")}</button>
          <button type="button" className={activePage === "inbox" ? "active" : ""} onClick={() => navigate("inbox")}><Mail />{l("财经收件箱", "Finance Inbox")}</button>
        </div>

        <div className="product-sidebar-foot">
          <span>{l("个人 CFO", "PERSONAL CFO")}</span>
          <p>{l("让每一个财务决策都有据可循。", "Evidence-led financial decisions.")}</p>
        </div>
      </aside>

      {isNavOpen && <button type="button" className="product-nav-backdrop" aria-label={l("关闭导航", "Close navigation")} onClick={() => setIsNavOpen(false)} />}

      <div className="product-app-frame">
        <header className="product-utility-bar">
          <button type="button" className="product-nav-trigger" aria-label={l("打开导航", "Open navigation")} aria-expanded={isNavOpen} onClick={() => setIsNavOpen(true)}><Menu /></button>
          <div className="product-utility-context"><span>{currentPageLabel}</span></div>
          <div className="product-topbar-actions">
            <button type="button" className={`product-notification-button ${isAttentionOpen ? "active" : ""}`} aria-label={l("打开需要处理", "Open items needing attention")} aria-expanded={isAttentionOpen} onClick={() => { setIsAttentionOpen((open) => !open); setIsAccountMenuOpen(false); }}><Bell />{attentionItems.length > 0 && <span>{attentionItems.length}</span>}</button>
            <button type="button" className="product-notification-button" aria-label={l("打开财经收件箱", "Open finance inbox")} onClick={() => navigate("inbox")}><Mail /></button>
            <button type="button" className={`product-cfo-trigger ${isCfoOpen ? "active" : ""}`} aria-label={l("打开 CFO", "Open CFO")} aria-expanded={isCfoOpen} onClick={() => { setIsCfoOpen((open) => !open); setIsAttentionOpen(false); setIsAccountMenuOpen(false); }}><Bot /><span>{l("问 CFO", "Ask CFO")}</span></button>
            <div className="product-account">
              <button type="button" className="product-avatar" title={user.email} aria-label={l("打开个人菜单", "Open account menu")} aria-expanded={isAccountMenuOpen} onClick={() => { setIsAccountMenuOpen((open) => !open); setIsAttentionOpen(false); }}>{user.email.slice(0, 2).toUpperCase()}</button>
              {isAccountMenuOpen && (
                <>
                  <button type="button" className="product-account-backdrop" aria-label={l("关闭个人菜单", "Close account menu")} onClick={() => setIsAccountMenuOpen(false)} />
                  <div className="product-account-menu">
                    <div><strong>{profileName || user.email}</strong><span>{user.email}</span></div>
                    <button type="button" onClick={() => navigate("settings")}><SettingsIcon />{t("nav.settings")}</button>
                    <button type="button" onClick={() => void logout()}><LogOut />{l("退出登录", "Sign out")}</button>
                  </div>
                </>
              )}
            </div>
          </div>
        </header>

        {isAttentionOpen && (
          <>
            <button type="button" className="product-attention-backdrop" aria-label={l("关闭需要处理", "Close attention items")} onClick={() => setIsAttentionOpen(false)} />
            <aside className="product-attention-popover" role="dialog" aria-label={l("需要处理", "Needs attention")}>
              <header><div><span>{l("需要处理", "NEEDS ATTENTION")}</span><strong>{attentionItems.length ? l(`${attentionItems.length} 件事情`, `${attentionItems.length} items`) : l("暂时没有事项", "All caught up")}</strong></div><button type="button" aria-label={l("关闭需要处理", "Close attention items")} onClick={() => setIsAttentionOpen(false)}><X /></button></header>
              {attentionItems.length ? <div className="product-attention-list">{attentionItems.map((item) => <article key={item.id} className={`product-attention-item product-attention-${item.tone}`}><span><AlertTriangle /></span><div><strong>{item.title}</strong><p>{item.body}</p><button type="button" onClick={() => runAttentionAction(item)}>{item.actionLabel}</button></div></article>)}</div> : <p className="product-attention-empty">{l("账本和计划会在需要操作时提醒你。", "Ledger and plan updates will appear here when action is needed.")}</p>}
            </aside>
          </>
        )}

        <div className="product-content">
          {activePage === "workspace" ? (
            <FinanceWorkspacePage
              userId={userId}
              dataSourceStatus={dataSourceStatus}
              loading={loading}
              errMsg={errMsg}
              isUploading={isUploading}
              primaryCurrency={primaryCurrency}
              tableTransactions={tableTransactions}
              onReload={load}
              onOpenLedger={() => setActivePage("ledger")}
              onOpenCashPlan={() => setActivePage("cash-plan")}
              onUploadStatement={handleUploadStatement}
              onCreateManualTransaction={handleCreateManualTransaction}
              onAttentionChange={setAttentionItems}
            />
          ) : activePage === "ledger" ? (
            <LedgerPage
              userId={userId}
              primaryCurrency={primaryCurrency}
              monthlyTrendsData={monthlyTrendsData}
              categoryData={categoryData}
              tableTransactions={tableTransactions}
              duplicateCount={duplicateCount}
              latestImportAt={dataSourceStatus?.latest_import?.created_at ?? null}
              isUploading={isUploading}
              onUploadStatement={handleUploadStatement}
              onAskCfoAbout={(question) => {
                openCfo(question);
              }}
            />
          ) : activePage === "cash-plan" ? (
            <CashPlanPage
              userId={userId}
              onAskCfo={(question) => {
                openCfo(question);
              }}
              onOpenSettings={() => {
                setSettingsSection("profile");
                setActivePage("settings");
              }}
            />
          ) : activePage === "investments" ? (
            <InvestmentResearchPage userId={userId} onAskCfo={(question) => openCfo(question)} />
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
              <SettingsPage
                userId={userId}
                profileName={profileName}
                profile={profile}
                apiBaseUrl={getApiBaseUrl()}
                transactionCount={txs.length}
                dataSourceStatus={dataSourceStatus}
                monthlyIncome={monthlyIncome}
                onProfileSaved={load}
                showDeveloperTools={import.meta.env.VITE_SHOW_DEVELOPER_TOOLS === "true"}
                initialSection={settingsSection}
              />
            </main>
          )}
        </div>
      </div>

      {isCfoOpen && (
        <>
          <button type="button" className="cfo-global-backdrop" aria-label={l("关闭 CFO", "Close CFO")} onClick={() => setIsCfoOpen(false)} />
          <aside className="cfo-global-panel" role="dialog" aria-modal="true" aria-label={l("CFO 对话", "CFO conversation")}>
            <div className="cfo-global-head"><div><Bot /><span>{l("个人 CFO", "Personal CFO")}</span></div><button type="button" aria-label={l("关闭 CFO", "Close CFO")} onClick={() => setIsCfoOpen(false)}><X /></button></div>
            <MyOfficePage userId={userId} userName={profileName} initialPrompt={officePrefill} onInitialPromptConsumed={() => setOfficePrefill(null)} />
          </aside>
        </>
      )}
    </div>
  );
}

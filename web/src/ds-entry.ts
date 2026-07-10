// Design-system entry for design-sync (claude.ai/design). Re-exports the
// components that make up the FinDesk surfaces; not imported by the app.
// CSS imports ride the module graph so esbuild emits them into _ds_bundle.css.
import "./index.css";
// Regenerated Tailwind sheet (tailwindcss v4 CLI over current sources) — the
// committed index.css is a stale compile missing utilities newer components
// use (bg-[#172026], bg-green-500, h-2, status tints…). Imported after
// index.css so current definitions win.
import "./ds-tailwind.css";
import "./styles/globals.css";
import "./product.css";

export { Header } from "./components/Header";
export { MetricsCards } from "./components/MetricsCards";
export { MonthlyTrends } from "./components/MonthlyTrends";
export { CategoryPieChart } from "./components/CategoryPieChart";
export { SourceBreakdown } from "./components/SourceBreakdown";
export { TransactionsTable } from "./components/TransactionsTable";
export { CategoryComparison } from "./components/CategoryComparison";
export { IncomeSummary } from "./components/IncomeSummary";
export { OperatingSummary } from "./components/OperatingSummary";
export { AgentResponse } from "./components/AgentResponse";
export { AgentTeamPanel } from "./components/AgentTeamPanel";
export { ImageWithFallback } from "./components/figma/ImageWithFallback";
export { FinanceWorkspacePage } from "./pages/FinanceWorkspacePage";
export { SettingsPage } from "./pages/SettingsPage";

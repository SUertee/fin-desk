import { WalletCards } from "lucide-react";

import { CashPlanPanel } from "../components/CashPlanPanel";
import { useI18n } from "../i18n";

type Props = {
  userId: string;
  onAskCfo: (question: string) => void;
  onOpenSettings: () => void;
};

export function CashPlanPage({ userId, onAskCfo, onOpenSettings }: Props) {
  const { lang } = useI18n();
  return (
    <main className="cash-plan-page">
      <header className="cash-plan-page-head">
        <span><WalletCards /> {lang === "zh" ? "规划" : "PLANNING"}</span>
        <h1>{lang === "zh" ? "现金计划" : "Cash plan"}</h1>
        <p>{lang === "zh" ? "管理工资、房租、债务与计划购买，提前看见余额最低点。" : "Manage income, rent, debts and planned purchases before cash runs low."}</p>
      </header>
      <CashPlanPanel userId={userId} onAskCfo={onAskCfo} onOpenSettings={onOpenSettings} />
    </main>
  );
}

type OperatingSummaryItem = {
  label: string;
  value: string;
  note: string;
  status?: "neutral" | "good" | "watch" | "risk";
};

type OperatingSummaryProps = {
  items: readonly OperatingSummaryItem[];
};

const statusClass = {
  neutral: "border-[#dfe5e3] bg-white",
  good: "border-[#cfe2dc] bg-[#f4faf8]",
  watch: "border-[#e3d6bd] bg-[#fbf8f1]",
  risk: "border-[#e7c7c2] bg-[#fbf4f3]",
};

export function OperatingSummary({ items }: OperatingSummaryProps) {
  return (
    <section className="operating-summary-grid">
      {items.map((item) => (
        <div
          key={item.label}
          className={`operating-summary-card ${statusClass[item.status ?? "neutral"]}`}
        >
          <div className="operating-summary-label">{item.label}</div>
          <div className="operating-summary-value">
            {item.value}
          </div>
          <div className="operating-summary-note">{item.note}</div>
        </div>
      ))}
    </section>
  );
}

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
    <section className="mb-5 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
      {items.map((item) => (
        <div
          key={item.label}
          className={`rounded-xl border px-4 py-4 ${statusClass[item.status ?? "neutral"]}`}
        >
          <div className="text-xs font-medium text-[#697571]">{item.label}</div>
          <div className="mt-2 text-2xl font-semibold tracking-normal text-[#172026]">
            {item.value}
          </div>
          <div className="mt-1 text-xs text-[#697571]">{item.note}</div>
        </div>
      ))}
    </section>
  );
}

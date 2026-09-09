export type TransactionRow = {
  id: string;
  user_id: string;
  date: string;        // "2025-03-01"
  month: string;       // "2025-03"
  description: string;
  counterparty?: string | null;
  amount: number;
  gross_amount?: number;
  currency?: string;
  balance: number | null;
  direction?: string;
  source?: string;
  payment_method?: string;
  status?: string;
  note?: string | null;
  external_id?: string | null;
  merchant_order_id?: string | null;
  source_file?: string | null;
  is_duplicate?: boolean;
  duplicate_reason?: string | null;
  duplicate_of?: string | null;
  type: "debit" | "credit" | string;
  category?: string | null;
  is_anomaly?: boolean | null;
  raw?: unknown;
  created_at?: string;
};

export type AnalysisRunRow = {
  id: string;
  user_id: string;
  created_at: string;
  period_start?: string | null;
  period_end?: string | null;
  monthly_totals?: any; // 你可以后面再细化
  input?: any;
  output?: any;
};

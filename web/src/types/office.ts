/**
 * My Office contracts — mirrors backend/app/models/office.py field-for-field.
 *
 * The evidence projection is the USER layer of trace-observability.md: it
 * never carries latency, usage, cost, model/provider names, confidence
 * values, or raw tool payloads.
 */

export type OfficeSessionStatus = "active" | "archived";

export type OfficeSession = {
  id: string;
  user_id: string;
  title: string;
  status: OfficeSessionStatus;
  last_message_preview: string;
  created_at: string;
  updated_at: string;
};

export type OfficeMessage = {
  id: string;
  role: string;
  content: string;
  request_id?: string | null;
  execution?: TurnExecutionFacts | null;
  created_at: string;
};

export type TurnExecutionFacts = {
  outcome:
    | "direct_response"
    | "clarification"
    | "executed"
    | "blocked"
    | "failed";
  evidence_available: boolean;
  specialist_findings_available: boolean;
  process_available: boolean;
  policy_blocked: boolean;
};

export type EvidenceStepKind = "tool" | "specialist" | "audit";

export type EvidenceStep = {
  label: string;
  kind: EvidenceStepKind;
  done: boolean;
};

export type EvidenceFinding = {
  agent: string;
  title: string;
  evidence: string[];
};

export type DataCoverage = {
  period?: string | null;
  source_counts: Record<string, number>;
  quality_warnings: string[];
};

export type EvidenceAudit = {
  status: string;
  warnings: string[];
};

export type AdvancedDetails = {
  run_id: string;
  tool_names: string[];
};

export type UserEvidenceProjection = {
  request_id: string;
  findings: EvidenceFinding[];
  cited_sources: string[];
  data_coverage: DataCoverage;
  steps: EvidenceStep[];
  audit?: EvidenceAudit | null;
  advanced?: AdvancedDetails | null;
};

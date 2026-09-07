import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent, ReactNode } from "react";
import {
  ChevronDown,
  ChevronRight,
  MessagesSquare,
  Plus,
  Send,
  X,
} from "lucide-react";
import {
  createOfficeSession,
  fetchOfficeEvidence,
  fetchOfficeSessionMessages,
  fetchOfficeSessions,
  sendOfficeChatMessageStream,
} from "../services/officeApi";
import type {
  EvidenceStep,
  OfficeSession,
  TurnExecutionFacts,
  UserEvidenceProjection,
} from "../types/office";
import type { ChatResponse, FinanceAgentData } from "../types/financeAgent";

interface MyOfficePageProps {
  userId: string;
  userName?: string;
  initialPrompt?: string | null;
  onInitialPromptConsumed?: () => void;
}

type ThreadMessage = {
  key: string;
  role: "user" | "cfo";
  content: string;
  createdAt: string | null;
  requestId: string | null;
  execution: TurnExecutionFacts | null;
  data: FinanceAgentData | null;
  steps: EvidenceStep[] | null;
  pending?: boolean;
};

type DrawerFocus = "sources" | "findings";

type DrawerState = { requestId: string; focus: DrawerFocus };

const SUGGESTED_QUESTIONS = [
  "这个月我的支出结构怎么样？",
  "有没有需要注意的重复交易或异常扣费？",
  "我最该先做的一件事是什么？",
];

/** CFO replies arrive as light markdown; render bold inline, keep the rest as text. */
function renderInline(text: string): ReactNode[] {
  return text.split(/\*\*(.+?)\*\*/g).map((part, index) =>
    index % 2 === 1 ? <strong key={index}>{part}</strong> : part
  );
}

function stripMarkdown(text: string): string {
  return text.replace(/[*_`#]/g, "");
}

function formatTime(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

function formatDay(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });
}

const AUDIT_NOTES: Record<string, string> = {
  verified: "审计复核已通过：结论与账本数据一致。",
  needs_review: "审计复核提示部分结论需要人工确认。",
  data_limited: "当前数据覆盖有限，结论以已导入的账本为准。",
};

export function MyOfficePage({
  userId,
  userName,
  initialPrompt,
  onInitialPromptConsumed,
}: MyOfficePageProps) {
  const [sessions, setSessions] = useState<OfficeSession[] | null>(null);
  const [sessionsError, setSessionsError] = useState<string | null>(null);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ThreadMessage[]>([]);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [messagesError, setMessagesError] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [drawer, setDrawer] = useState<DrawerState | null>(null);
  const [evidenceCache, setEvidenceCache] = useState<
    Record<string, UserEvidenceProjection>
  >({});
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);
  const [expandedSteps, setExpandedSteps] = useState<Record<string, boolean>>({});
  const [railOpen, setRailOpen] = useState(false);
  const threadRef = useRef<HTMLDivElement | null>(null);

  const loadSessions = useCallback(async () => {
    setSessionsError(null);
    try {
      const list = await fetchOfficeSessions(userId);
      setSessions(list);
      return list;
    } catch (error: any) {
      setSessions([]);
      setSessionsError(/failed to fetch/i.test(error?.message ?? "") ? "无法连接后端服务" : error?.message ?? "无法加载会话档案");
      return [];
    }
  }, [userId]);

  const loadMessages = useCallback(
    async (sessionId: string) => {
      setMessagesLoading(true);
      setMessagesError(null);
      try {
        const rows = await fetchOfficeSessionMessages(userId, sessionId);
        setMessages(
          rows.map((row) => ({
            key: row.id,
            role: row.role === "user" ? "user" : "cfo",
            content: row.content,
            createdAt: row.created_at,
            requestId: row.request_id ?? null,
            execution: row.execution ?? null,
            data: null,
            steps: null,
          }))
        );
      } catch (error: any) {
        setMessages([]);
        setMessagesError(/failed to fetch/i.test(error?.message ?? "") ? "无法连接后端服务" : error?.message ?? "无法加载会话消息");
      } finally {
        setMessagesLoading(false);
      }
    },
    [userId]
  );

  useEffect(() => {
    let mounted = true;
    (async () => {
      const list = await loadSessions();
      if (!mounted) return;
      const first = list.find((session) => session.status === "active") ?? list[0];
      if (first) {
        setActiveSessionId(first.id);
        await loadMessages(first.id);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [loadSessions, loadMessages]);

  useEffect(() => {
    const node = threadRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages, isSending]);

  useEffect(() => {
    if (!initialPrompt) return;
    setInput(initialPrompt);
    onInitialPromptConsumed?.();
  }, [initialPrompt, onInitialPromptConsumed]);

  const activeSession = useMemo(
    () => sessions?.find((session) => session.id === activeSessionId) ?? null,
    [sessions, activeSessionId]
  );

  const selectSession = useCallback(
    (sessionId: string) => {
      if (sessionId === activeSessionId) return;
      setActiveSessionId(sessionId);
      setDrawer(null);
      setRailOpen(false);
      void loadMessages(sessionId);
    },
    [activeSessionId, loadMessages]
  );

  const startNewConversation = useCallback(() => {
    setActiveSessionId(null);
    setMessages([]);
    setMessagesError(null);
    setDrawer(null);
    setRailOpen(false);
  }, []);

  const sendPrompt = useCallback(
    async (prompt: string) => {
      const trimmed = prompt.trim();
      if (!trimmed || isSending) return;
      setInput("");
      setIsSending(true);

      const sentAt = new Date().toISOString();
      const cfoKey = `live-${Date.now()}`;
      setMessages((prev) => [
        ...prev,
        {
          key: `${cfoKey}-user`,
          role: "user",
          content: trimmed,
          createdAt: sentAt,
          requestId: null,
          execution: null,
          data: null,
          steps: null,
        },
        {
          key: cfoKey,
          role: "cfo",
          content: "",
          createdAt: null,
          requestId: null,
          execution: null,
          data: null,
          steps: null,
          pending: true,
        },
      ]);

      const updateCfo = (updater: (msg: ThreadMessage) => ThreadMessage) => {
        setMessages((prev) =>
          prev.map((msg) => (msg.key === cfoKey ? updater(msg) : msg))
        );
      };

      const finishWith = (response: ChatResponse) => {
        updateCfo((msg) => ({
          ...msg,
          content: response.reply,
          createdAt: new Date().toISOString(),
          requestId: response.request_id ?? null,
          execution: response.execution,
          data: response.data ?? null,
          pending: false,
        }));
      };

      try {
        let sessionId = activeSessionId;
        if (!sessionId) {
          const session = await createOfficeSession(userId);
          sessionId = session.id;
          setActiveSessionId(session.id);
          setSessions((prev) => [session, ...(prev ?? [])]);
        }

        let streamed = "";
        await sendOfficeChatMessageStream(userId, sessionId, trimmed, (event) => {
          if (event.type === "delta") {
            streamed += event.text;
            const content = streamed;
            updateCfo((msg) => ({ ...msg, content }));
          } else if (event.type === "steps") {
            updateCfo((msg) => ({ ...msg, steps: event.steps }));
          } else if (event.type === "done") {
            finishWith(event.response);
          } else if (event.type === "error") {
            throw new Error(event.error);
          }
        });
        void loadSessions();
      } catch (error: any) {
        updateCfo((msg) => ({
          ...msg,
          content: error?.message ?? "请求失败，请确认后端服务已启动。",
          pending: false,
        }));
      } finally {
        setIsSending(false);
      }
    },
    [activeSessionId, isSending, loadSessions, userId]
  );

  const openEvidence = useCallback(
    (requestId: string, focus: DrawerFocus) => {
      setDrawer({ requestId, focus });
      setEvidenceError(null);
      if (evidenceCache[requestId]) return;
      setEvidenceLoading(true);
      fetchOfficeEvidence(requestId)
        .then((projection) => {
          setEvidenceCache((prev) => ({ ...prev, [requestId]: projection }));
        })
        .catch((error: any) => {
          setEvidenceError(/failed to fetch/i.test(error?.message ?? "") ? "无法连接后端服务" : error?.message ?? "无法加载证据");
        })
        .finally(() => setEvidenceLoading(false));
    },
    [evidenceCache]
  );

  const drawerEvidence = drawer ? evidenceCache[drawer.requestId] ?? null : null;

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    void sendPrompt(input);
  };

  const handleComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (
      event.nativeEvent.isComposing ||
      event.key !== "Enter" ||
      event.shiftKey
    ) {
      return;
    }
    event.preventDefault();
    void sendPrompt(input);
  };

  return (
    <main className="office-shell">
      <div className={`office-layout${drawer ? " office-layout-with-drawer" : ""}`}>
        <aside className={`office-rail${railOpen ? " office-rail-open" : ""}`}>
          <div className="office-rail-head">
            <div className="office-rail-title">会话档案</div>
            <button type="button" className="office-mobile-close" aria-label="关闭会话列表" onClick={() => setRailOpen(false)}><X /></button>
            <button
              type="button"
              className="office-new-session"
              onClick={startNewConversation}
            >
              <Plus /> 新对话
            </button>
          </div>
          <div className="office-session-list">
            {sessions === null ? (
              <div className="office-muted">加载会话档案…</div>
            ) : sessionsError ? (
              <div className="office-muted">{sessionsError}</div>
            ) : sessions.length === 0 && !activeSessionId ? (
              <div className="office-muted">
                还没有会话记录。向 CFO 提问即可开始第一次会议。
              </div>
            ) : (
              sessions.map((session) => (
                <button
                  key={session.id}
                  type="button"
                  onClick={() => selectSession(session.id)}
                  className={`office-session-item${
                    session.id === activeSessionId ? " office-session-item-active" : ""
                  }`}
                >
                  <span className="office-session-item-title">
                    {session.title || "未命名会话"}
                  </span>
                  <span className="office-session-item-meta">
                    <span className="office-session-item-preview">
                      {stripMarkdown(session.last_message_preview) || "尚无消息"}
                    </span>
                    <span>{formatDay(session.updated_at)}</span>
                  </span>
                </button>
              ))
            )}
          </div>
        </aside>
        {railOpen && (
          <button
            type="button"
            className="office-rail-backdrop"
            aria-label="收起会话档案"
            onClick={() => setRailOpen(false)}
          />
        )}

        <section className="office-thread-card">
          <header className="office-thread-head">
            <button
              type="button"
              className="office-rail-toggle"
              onClick={() => setRailOpen(true)}
            >
              <MessagesSquare /> 会话档案
            </button>
            <div className="office-thread-head-copy">
              <div className="office-thread-kicker">与 CFO 对话</div>
              <div className="office-thread-title">
                {activeSession?.title || "新会议"}
              </div>
            </div>
          </header>

          <div className="office-messages" ref={threadRef}>
            {messagesLoading ? (
              <div className="office-muted office-thread-empty">加载会话…</div>
            ) : messagesError ? (
              <div className="office-muted office-thread-empty">{messagesError}</div>
            ) : messages.length === 0 ? (
              <div className="office-thread-empty">
                <div className="office-greeting">
                  <strong>{userName ? `你好，${userName}` : "你好"}</strong>
                  <span>
                    直接说出你想了解的财务问题。需要核对账本时，CFO
                    会调用合适的工具和团队，并在回答后附上依据。
                  </span>
                </div>
                <div className="office-suggestions">
                  {SUGGESTED_QUESTIONS.map((question) => (
                    <button
                      key={question}
                      type="button"
                      className="office-suggestion"
                      onClick={() => void sendPrompt(question)}
                    >
                      {question}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((message) =>
                message.role === "user" ? (
                  <UserBubble key={message.key} message={message} userName={userName} />
                ) : (
                  <CfoBubble
                    key={message.key}
                    message={message}
                    evidence={
                      message.requestId
                        ? evidenceCache[message.requestId] ?? null
                        : null
                    }
                    stepsExpanded={!!expandedSteps[message.key]}
                    onToggleSteps={() =>
                      setExpandedSteps((prev) => ({
                        ...prev,
                        [message.key]: !prev[message.key],
                      }))
                    }
                    onOpenEvidence={openEvidence}
                  />
                )
              )
            )}
          </div>

          <form className="office-composer" onSubmit={handleSubmit}>
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleComposerKeyDown}
              placeholder="向 CFO 提问…"
              className="office-input"
              rows={1}
            />
            <button
              type="submit"
              className="office-send"
              disabled={isSending || !input.trim()}
              title="发送"
            >
              <Send />
            </button>
          </form>
        </section>

        {drawer && (
          <>
            <button
              type="button"
              className="office-drawer-backdrop"
              aria-label="关闭引用与执行"
              onClick={() => setDrawer(null)}
            />
            <EvidenceDrawer
              focus={drawer.focus}
              evidence={drawerEvidence}
              loading={evidenceLoading}
              error={evidenceError}
              onClose={() => setDrawer(null)}
            />
          </>
        )}
      </div>
    </main>
  );
}

function UserBubble({
  message,
  userName,
}: {
  message: ThreadMessage;
  userName?: string;
}) {
  return (
    <div className="office-msg office-msg-user">
      <div className="office-msg-body">
        <div className="office-msg-meta">
          <span>{userName || "我"}</span>
          {message.createdAt && <span>{formatTime(message.createdAt)}</span>}
        </div>
        <div className="office-bubble office-bubble-user">{message.content}</div>
      </div>
      <div className="office-avatar office-avatar-user">
        {(userName || "我").slice(0, 1)}
      </div>
    </div>
  );
}

function buildCfoDisplayPolicy(
  message: ThreadMessage,
  evidence: UserEvidenceProjection | null
) {
  const execution = message.execution;
  const executed = execution?.outcome === "executed";
  const showProcess = Boolean(
    execution?.process_available || (message.pending && message.steps?.length)
  );
  const steps = showProcess ? message.steps ?? evidence?.steps ?? null : null;
  const findings = execution?.specialist_findings_available
    ? message.data?.findings ?? evidence?.findings ?? null
    : null;
  const actions = executed ? message.data?.actions ?? null : null;
  const findingCount = findings?.length ?? 0;
  const sourceCount = evidence?.cited_sources.length ?? null;
  const isSettled = Boolean(message.requestId && !message.pending);

  return {
    steps,
    findings,
    actions,
    sourceCount,
    findingCount,
    showJudgementLabel: isSettled && executed,
    showSourcesChip: isSettled && Boolean(execution?.evidence_available),
    showFindingsChip:
      isSettled && Boolean(execution?.specialist_findings_available),
  };
}

function CfoBubble({
  message,
  evidence,
  stepsExpanded,
  onToggleSteps,
  onOpenEvidence,
}: {
  message: ThreadMessage;
  evidence: UserEvidenceProjection | null;
  stepsExpanded: boolean;
  onToggleSteps: () => void;
  onOpenEvidence: (requestId: string, focus: DrawerFocus) => void;
}) {
  const display = buildCfoDisplayPolicy(message, evidence);
  const hasChipRow = display.showSourcesChip || display.showFindingsChip;
  const presentation =
    message.execution?.outcome === "executed" ? "analysis" : "conversation";

  return (
    <div className="office-msg office-msg-cfo">
      <div className="office-avatar office-avatar-cfo">CFO</div>
      <div className="office-msg-body">
        <div className="office-msg-meta">
          <span>CFO</span>
          {message.createdAt && <span>{formatTime(message.createdAt)}</span>}
        </div>

        {display.steps && display.steps.length > 0 && (
          <div className="office-process">
            <button type="button" className="office-process-row" onClick={onToggleSteps}>
              {stepsExpanded ? <ChevronDown /> : <ChevronRight />}
              CFO 已完成 {display.steps.length} 步分析 · 查看过程
            </button>
            {stepsExpanded && (
              <ol className="office-process-steps">
                {display.steps.map((step, index) => (
                  <li
                    key={`${step.label}-${index}`}
                    className={step.done ? "" : "office-process-step-pending"}
                  >
                    {step.label}
                  </li>
                ))}
              </ol>
            )}
          </div>
        )}

        <div
          className={`office-bubble office-bubble-cfo office-bubble-cfo-${presentation}`}
        >
          {display.showJudgementLabel && (
            <div className="office-bubble-eyebrow">CFO 判断</div>
          )}
          {message.pending && !message.content ? (
            <span className="office-muted">CFO 正在分析…</span>
          ) : (
            message.content
              .split(/\n{2,}/)
              .filter(Boolean)
              .map((paragraph, index) => <p key={index}>{renderInline(paragraph)}</p>)
          )}

          {display.findings && display.findings.length > 0 && (
            <div className="office-finding-strip">
              <span className="office-finding-label">团队发现</span>
              {display.findings.slice(0, 2).map((finding) => (
                <div key={finding.title} className="office-finding-line">
                  <span>{finding.title}</span>
                </div>
              ))}
            </div>
          )}

          {display.actions && display.actions.length > 0 && (
            <div className="office-actions">
              <span className="office-action-label">下一步建议</span>
              <ol className="office-action-list">
                {display.actions.map((action) => (
                  <li key={action.title} title={action.rationale}>
                    {action.title}
                  </li>
                ))}
              </ol>
            </div>
          )}

          {hasChipRow && (
            <div className="office-chip-row">
              {display.showSourcesChip && (
                <button
                  type="button"
                  className="office-chip"
                  onClick={() => onOpenEvidence(message.requestId!, "sources")}
                >
                  {display.sourceCount !== null
                    ? `${display.sourceCount} 个引用来源`
                    : "引用来源"}
                </button>
              )}
              {display.showFindingsChip && (
                <button
                  type="button"
                  className="office-chip"
                  onClick={() => onOpenEvidence(message.requestId!, "findings")}
                >
                  {display.findingCount > 0
                    ? `团队发现 · ${display.findingCount}`
                    : "团队发现"}
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function EvidenceDrawer({
  focus,
  evidence,
  loading,
  error,
  onClose,
}: {
  focus: DrawerFocus;
  evidence: UserEvidenceProjection | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
}) {
  const coverage = evidence?.data_coverage ?? null;
  const sourceEntries = coverage ? Object.entries(coverage.source_counts) : [];
  const auditNote = evidence?.audit
    ? AUDIT_NOTES[evidence.audit.status] ?? null
    : null;
  const auditWarnings = evidence?.audit?.warnings ?? [];

  return (
    <aside className="office-drawer" role="dialog" aria-label="引用与执行">
      <header className="office-drawer-head">
        <div className="office-drawer-title">引用与执行</div>
        <button
          type="button"
          className="office-drawer-close"
          onClick={onClose}
          title="关闭"
        >
          <X />
        </button>
      </header>

      {loading ? (
        <div className="office-muted office-drawer-state">加载证据…</div>
      ) : error ? (
        <div className="office-muted office-drawer-state">{error}</div>
      ) : !evidence ? (
        <div className="office-muted office-drawer-state">该回答暂无可展示的证据。</div>
      ) : (
        <div className="office-drawer-body">
          <section
            className={`office-drawer-section${
              focus === "sources" ? " office-drawer-section-active" : ""
            }`}
          >
            <h3>证据来源</h3>
            {evidence.cited_sources.length > 0 ? (
              <ul>
                {evidence.cited_sources.map((source) => (
                  <li key={source}>{source}</li>
                ))}
              </ul>
            ) : (
              <div className="office-muted">该回答暂无证据来源记录。</div>
            )}
          </section>

          <section
            className={`office-drawer-section${
              focus === "findings" ? " office-drawer-section-active" : ""
            }`}
          >
            <h3>团队发现</h3>
            {evidence.findings.length > 0 ? (
              <ul className="office-drawer-findings">
                {evidence.findings.map((finding, index) => (
                  <li key={`${finding.title}-${index}`}>
                    <span className="office-drawer-finding-agent">
                      {finding.agent}
                    </span>
                    <span>{finding.title}</span>
                    {finding.evidence.length > 0 && (
                      <ul>
                        {finding.evidence.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <div className="office-muted">该回答暂无团队发现记录。</div>
            )}
          </section>

          <section className="office-drawer-section">
            <h3>审计说明</h3>
            {auditNote || auditWarnings.length > 0 ? (
              <>
                {auditNote && <p>{auditNote}</p>}
                {auditWarnings.length > 0 && (
                  <ul className="office-drawer-warnings">
                    {auditWarnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                )}
              </>
            ) : (
              <div className="office-muted">该回答暂无审计说明。</div>
            )}
          </section>

          <section className="office-drawer-section">
            <h3>数据覆盖</h3>
            {coverage &&
            (coverage.period ||
              sourceEntries.length > 0 ||
              coverage.quality_warnings.length > 0) ? (
              <>
                {coverage.period && <p>周期：{coverage.period}</p>}
                {sourceEntries.length > 0 && (
                  <ul>
                    {sourceEntries.map(([source, count]) => (
                      <li key={source}>
                        {source}：{count} 笔
                      </li>
                    ))}
                  </ul>
                )}
                {coverage.quality_warnings.length > 0 && (
                  <ul className="office-drawer-warnings">
                    {coverage.quality_warnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                )}
              </>
            ) : (
              <div className="office-muted">该回答暂无数据覆盖记录。</div>
            )}
          </section>
        </div>
      )}
    </aside>
  );
}

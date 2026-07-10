import React, { useMemo, useState } from "react";
import { ArrowUpRight, BadgeDollarSign, PanelRightClose, Send, ShieldCheck, Sparkles, TrendingUp, X } from "lucide-react";
import { sendChatMessage, sendChatMessageStream } from "../services/supabaseApi";
import { AGENTS, type AgentType } from "../types/agents";
import type { ChatResponse } from "../types/financeAgent";
import { AgentResponse } from "./AgentResponse";

import type { WorkspaceBrief } from "../types/financeAgent";

interface AgentTeamPanelProps {
  isOpen: boolean;
  onClose: () => void;
  userId: string;
  hasFinanceData: boolean;
  topCategory?: string;
  brief?: WorkspaceBrief | null;
  userName?: string;
  prefill?: string | null;
  onPrefillConsumed?: () => void;
}

type ChatMessage =
  | { role: "user"; content: string }
  | { role: "assistant"; content: string; response?: ChatResponse };

export function AgentTeamPanel({
  isOpen,
  onClose,
  userId,
  hasFinanceData,
  topCategory,
  brief,
  userName,
  prefill,
  onPrefillConsumed,
}: AgentTeamPanelProps) {
  const [activeAgent, setActiveAgent] = useState<AgentType>("cfo");
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  React.useEffect(() => {
    if (isOpen && prefill) {
      onPrefillConsumed?.();
      void sendPrompt(prefill);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, prefill]);

  const activeMeta = useMemo(
    () => AGENTS.find((agent) => agent.id === activeAgent) ?? AGENTS[0],
    [activeAgent]
  );

  const sendPrompt = async (prompt: string) => {
    if (!prompt || isSending) return;
    setInput("");
    setMessages((prev) => [
      ...prev,
      { role: "user", content: prompt },
      { role: "assistant", content: "" },
    ]);
    setIsSending(true);

    const updateLast = (updater: (msg: ChatMessage) => ChatMessage) => {
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = updater(next[next.length - 1]);
        return next;
      });
    };

    try {
      let streamed = "";
      await sendChatMessageStream(
        userId,
        prompt,
        activeMeta.requestedSpecialist,
        (event) => {
          if (event.type === "delta") {
            streamed += event.text;
            updateLast(() => ({ role: "assistant", content: streamed }));
          } else if (event.type === "done") {
            updateLast(() => ({
              role: "assistant",
              content: event.response.reply,
              response: event.response,
            }));
          } else if (event.type === "error") {
            throw new Error(event.error);
          }
        }
      );
    } catch {
      // Streaming failed — fall back to the non-streaming endpoint.
      try {
        const response = await sendChatMessage(userId, prompt, activeMeta.requestedSpecialist);
        updateLast(() => ({
          role: "assistant",
          content: response.reply,
          response,
        }));
      } catch (error: any) {
        updateLast(() => ({
          role: "assistant",
          content: error?.message ?? "Request failed. Check the server.",
        }));
      }
    } finally {
      setIsSending(false);
    }
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    await sendPrompt(input.trim());
  };

  if (!isOpen) return null;

  return (
    <>
    <aside className="agent-team-panel">
      <div className="agent-team-header">
        <div className="agent-team-header-row">
          <div>
            <div className="agent-team-kicker"><Sparkles /> Ask CFO</div>
            <div className="agent-team-subtitle">Your AI Chief Financial Officer</div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="agent-team-icon-button"
            title="Close Agent Team"
          >
            <X />
          </button>
        </div>
      </div>

      <div className="agent-team-selector">
        <div className="agent-team-grid">
          {AGENTS.map((agent) => (
            <button
              key={agent.id}
              type="button"
              onClick={() => setActiveAgent(agent.id)}
              className={`agent-team-agent-button ${
                activeAgent === agent.id ? "agent-team-agent-button-active" : ""
              }`}
              title={agent.label}
            >
              <div className={`agent-team-badge agent-team-badge-${agent.id}`}>
                {agent.icon}
              </div>
              <div className="agent-team-agent-label">
                {agent.shortLabel}
              </div>
            </button>
          ))}
        </div>
        <div className="agent-team-active-card">
          <div className="agent-team-active-title">{activeMeta.label}</div>
          <div className="agent-team-active-summary">{activeMeta.summary}</div>
        </div>
      </div>

      <div className="agent-team-messages">
        {messages.length === 0 ? (
          hasFinanceData ? (
            <>
            <div className="agent-team-greeting">
              <strong>{userName ? `你好，${userName} 👋` : "你好 👋"}</strong>
              <span>
                {brief?.has_data
                  ? `已基于 ${brief.period?.from ?? ""} ~ ${brief.period?.to ?? ""} 的数据生成 CFO 简报。`
                  : "CFO 简报生成后，这里会显示基于真实数据的要点。"}
              </span>
            </div>
            <div className="agent-team-insight-list">
              {(brief?.summary_cards ?? []).slice(0, 3).map((card) => (
                <button className="agent-team-insight" type="button" key={card.label}>
                  <span
                    className={`agent-team-insight-icon ${
                      card.status === "good"
                        ? "green"
                        : card.status === "risk"
                          ? "coral"
                          : "amber"
                    }`}
                  >
                    {card.status === "risk" ? <ShieldCheck /> : card.status === "good" ? <TrendingUp /> : <BadgeDollarSign />}
                  </span>
                  <span>
                    {card.label}: {card.value}
                    {card.note ? ` — ${card.note}` : ""}
                  </span>
                  <ArrowUpRight />
                </button>
              ))}
            </div>
            <div className="agent-team-suggestions">
              {[
                topCategory ? `为什么${topCategory}支出这么高？` : "这个月我的支出结构怎么样？",
                "上个月和这个月的支出差在哪里？",
                "我最该先做的一件事是什么？",
              ].map((question) => (
                <button
                  key={question}
                  type="button"
                  className="agent-team-suggestion"
                  onClick={() => void sendPrompt(question)}
                >
                  {question}
                </button>
              ))}
            </div>
            </>
          ) : (
            <>
              <div className="agent-team-greeting">
                <strong>Import data to unlock CFO analysis</strong>
                <span>
                  I can review cash flow, spending categories, budget risk, and anomalies
                  after you upload an Alipay, WeChat, or bank CSV statement.
                </span>
              </div>
              <div className="agent-team-insight-list">
                <button className="agent-team-insight" type="button">
                  <span className="agent-team-insight-icon green"><TrendingUp /></span>
                  <span>Start with statement import so the CFO can ground every answer in transactions.</span>
                  <ArrowUpRight />
                </button>
                <button className="agent-team-insight" type="button">
                  <span className="agent-team-insight-icon amber"><BadgeDollarSign /></span>
                  <span>After import, I can identify overspending, subscriptions, and cash buffer risk.</span>
                  <ArrowUpRight />
                </button>
                <button className="agent-team-insight" type="button">
                  <span className="agent-team-insight-icon coral"><ShieldCheck /></span>
                  <span>Audit checks will flag data limits instead of making unsupported claims.</span>
                  <ArrowUpRight />
                </button>
              </div>
              <div className="agent-team-empty">
                Try: “What should I upload first?” or import a statement from the main workspace.
              </div>
            </>
          )
        ) : (
          messages.map((message, index) =>
            message.role === "user" ? (
              <div
                key={index}
                className="agent-team-user-message"
              >
                {message.content}
              </div>
            ) : (
              <AgentResponse
                key={index}
                content={message.content}
                data={message.response?.data}
                requestId={message.response?.request_id}
              />
            )
          )
        )}
        {isSending && <div className="agent-team-sending">Analyzing...</div>}
      </div>

      <div className="agent-team-composer">
        <form onSubmit={handleSubmit} className="agent-team-form">
          <input
            type="text"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder={`Ask ${activeMeta.label}...`}
            className="agent-team-input"
          />
          <button
            type="submit"
            className="agent-team-send"
            disabled={isSending}
            title="Send"
          >
            <Send />
          </button>
          <button
            type="button"
            onClick={onClose}
            className="agent-team-collapse"
            title="Collapse panel"
          >
            <PanelRightClose />
          </button>
        </form>
      </div>
    </aside>
    </>
  );
}

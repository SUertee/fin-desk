import React, { useMemo, useState } from "react";
import { PanelRightClose, Send, X } from "lucide-react";
import { sendChatMessage } from "../services/supabaseApi";
import { AGENTS, type AgentType } from "../types/agents";
import type { ChatResponse } from "../types/financeAgent";
import { AgentResponse } from "./AgentResponse";

interface AgentTeamPanelProps {
  isOpen: boolean;
  onClose: () => void;
  userId: string;
}

type ChatMessage =
  | { role: "user"; content: string }
  | { role: "assistant"; content: string; response?: ChatResponse };

export function AgentTeamPanel({ isOpen, onClose, userId }: AgentTeamPanelProps) {
  const [activeAgent, setActiveAgent] = useState<AgentType>("cfo");
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  const activeMeta = useMemo(
    () => AGENTS.find((agent) => agent.id === activeAgent) ?? AGENTS[0],
    [activeAgent]
  );

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const prompt = input.trim();
    if (!prompt || isSending) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: prompt }]);
    setIsSending(true);

    try {
      const response = await sendChatMessage(userId, `${activeMeta.promptPrefix}${prompt}`);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: response.reply,
          response,
        },
      ]);
    } catch (error: any) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: error?.message ?? "Request failed. Check the server.",
        },
      ]);
    } finally {
      setIsSending(false);
    }
  };

  if (!isOpen) return null;

  return (
    <aside className="fixed right-0 top-0 z-40 flex h-screen w-[430px] flex-col border-l border-[#dfe5e3] bg-[#f7f8f8] shadow-[0_18px_60px_rgba(23,32,38,0.12)]">
      <div className="border-b border-[#dfe5e3] bg-white px-5 py-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-[#172026]">Agent Team</div>
            <div className="mt-1 text-xs text-[#697571]">
              CFO coordinates specialist analysis and audit review.
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-[#697571] transition-colors hover:bg-[#eef2f1] hover:text-[#172026]"
            title="Close Agent Team"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="border-b border-[#dfe5e3] bg-white px-5 py-3">
        <div className="grid grid-cols-5 gap-2">
          {AGENTS.map((agent) => (
            <button
              key={agent.id}
              type="button"
              onClick={() => setActiveAgent(agent.id)}
              className={`rounded-xl border px-2 py-2 text-left transition-colors ${
                activeAgent === agent.id
                  ? "border-[#4b8078] bg-[#eef5f3]"
                  : "border-[#dfe5e3] bg-white hover:bg-[#f7f8f8]"
              }`}
              title={agent.label}
            >
              <div
                className={`mb-1 flex h-7 w-7 items-center justify-center rounded-lg ${agent.badgeClass}`}
              >
                {agent.icon}
              </div>
              <div className="truncate text-[11px] font-medium text-[#24302c]">
                {agent.shortLabel}
              </div>
            </button>
          ))}
        </div>
        <div className="mt-3 rounded-xl border border-[#dfe5e3] bg-[#f8faf9] px-3 py-2">
          <div className="text-xs font-medium text-[#24302c]">{activeMeta.label}</div>
          <div className="mt-0.5 text-xs text-[#697571]">{activeMeta.summary}</div>
        </div>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
        {messages.length === 0 ? (
          <div className="rounded-xl border border-[#dfe5e3] bg-white p-4 text-sm text-[#53615d]">
            Ask the CFO for a monthly health check, or choose a specialist for a narrower review.
          </div>
        ) : (
          messages.map((message, index) =>
            message.role === "user" ? (
              <div
                key={index}
                className="ml-10 rounded-xl bg-[#172026] px-3 py-2 text-sm leading-relaxed text-white"
              >
                {message.content}
              </div>
            ) : (
              <AgentResponse
                key={index}
                content={message.content}
                data={message.response?.data}
              />
            )
          )
        )}
        {isSending && <div className="text-xs text-[#697571]">Analyzing...</div>}
      </div>

      <div className="border-t border-[#dfe5e3] bg-white p-4">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder={`Ask ${activeMeta.label}...`}
            className="min-w-0 flex-1 rounded-xl border border-[#ccd6d3] bg-white px-3 py-2 text-sm text-[#172026] outline-none transition focus:border-[#4b8078] focus:ring-2 focus:ring-[#d9e9e5]"
          />
          <button
            type="submit"
            className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#172026] text-white transition-colors hover:bg-[#24302c] disabled:opacity-60"
            disabled={isSending}
            title="Send"
          >
            <Send className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={onClose}
            className="flex h-10 w-10 items-center justify-center rounded-xl border border-[#dfe5e3] text-[#697571] transition-colors hover:bg-[#f7f8f8]"
            title="Collapse panel"
          >
            <PanelRightClose className="h-4 w-4" />
          </button>
        </form>
      </div>
    </aside>
  );
}

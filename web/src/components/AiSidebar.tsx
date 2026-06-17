import React, { useMemo, useState } from "react";
import { ArrowLeft, Send, Shield, X } from "lucide-react";
import { AGENTS, type AgentType } from "../types/agents";

interface AiSidebarProps {
  isOpen: boolean;
  onClose: () => void;
}


type ChatMessage = { role: "user" | "assistant"; content: string };

export function AiSidebar({ isOpen, onClose }: AiSidebarProps) {
  const [viewMode, setViewMode] = useState<"select" | "chat">("select");
  const [activeAgent, setActiveAgent] = useState<AgentType>("cfo");
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [messagesByAgent, setMessagesByAgent] = useState<
    Record<AgentType, ChatMessage[]>
  >({
    cfo: [],
    quant: [],
    coach: [],
    auditor: [],
  });

  const apiBase = useMemo(
    () =>
      (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
      "http://localhost:18000",
    []
  );

  const activeMeta = useMemo(
    () => AGENTS.find((agent) => agent.id === activeAgent) ?? AGENTS[0],
    [activeAgent]
  );

  const activeMessages = messagesByAgent[activeAgent] ?? [];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const prompt = input.trim();
    if (!prompt || isSending) return;

    setInput("");
    setMessagesByAgent((prev) => ({
      ...prev,
      [activeAgent]: [...prev[activeAgent], { role: "user", content: prompt }],
    }));
    setIsSending(true);

    try {
      // Prepend agent context to the user message
      const contextPrefix = `[${activeMeta.label}] `;
      const response = await fetch(`${apiBase}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: "demo",
          message: contextPrefix + prompt,
        }),
      });

      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || "Chat request failed");
      }

      const data = await response.json();
      const reply = data?.reply ?? "No response.";

      setMessagesByAgent((prev) => ({
        ...prev,
        [activeAgent]: [
          ...prev[activeAgent],
          { role: "assistant", content: reply },
        ],
      }));
    } catch (error: any) {
      setMessagesByAgent((prev) => ({
        ...prev,
        [activeAgent]: [
          ...prev[activeAgent],
          {
            role: "assistant",
            content: `Request failed. ${
              error?.message ?? "Check server."
            }`,
          },
        ],
      }));
    } finally {
      setIsSending(false);
    }
  };

  if (!isOpen) return null;

  return (
    <aside className="fixed right-0 top-0 w-[420px] bg-white border-l border-gray-200 flex flex-col h-screen shadow-lg z-40 transition-transform duration-300">
      <div className="px-5 py-4 border-b border-gray-200 flex items-start justify-between">
        <div>
          <h2 className="text-base text-slate-900">AI Command Center</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Strategic Financial Intelligence
          </p>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 hover:bg-gray-100 rounded-lg transition-colors"
          title="Close AI Panel"
        >
          <X className="w-5 h-5 text-gray-500" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
        {viewMode === "chat" ? (
          <>
            <div className="flex items-center justify-between">
              <button
                type="button"
                onClick={() => setViewMode("select")}
                className="text-xs text-slate-600 hover:text-slate-900 flex items-center gap-1"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                返回选择
              </button>
              <span className="text-xs text-slate-500">{activeMeta.label}</span>
            </div>

            <div className="space-y-3">
              {activeMessages.length === 0 ? (
                <div className="text-xs text-gray-500">
                  这里会显示与 {activeMeta.label} 的对话。
                </div>
              ) : (
                activeMessages.map((message, index) => (
                  <div
                    key={`${message.role}-${index}`}
                    className={`rounded-xl px-3 py-2 text-xs leading-relaxed ${
                      message.role === "user"
                        ? "bg-slate-900 text-white ml-10"
                        : "bg-slate-100 text-slate-800 mr-10"
                    }`}
                  >
                    {message.content}
                  </div>
                ))
              )}
              {isSending && (
                <div className="text-xs text-gray-500">Thinking...</div>
              )}
            </div>
          </>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {AGENTS.map((agent) => (
              <button
                key={agent.id}
                type="button"
                onClick={() => {
                  setActiveAgent(agent.id);
                  setViewMode("chat");
                }}
                className="text-left rounded-xl border border-slate-200 bg-white p-3 hover:shadow-sm transition-shadow"
              >
                <div className="flex items-center gap-2">
                  <div
                    className={`w-7 h-7 rounded-lg flex items-center justify-center ${agent.badgeClass}`}
                  >
                    {agent.icon}
                  </div>
                  <div className="text-xs text-slate-900 font-medium">
                    {agent.label}
                  </div>
                </div>
                <div className="mt-2 text-[11px] text-slate-500">
                  {agent.summary}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="border-t border-gray-200 p-4 bg-gray-50">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={`对 ${activeMeta.label} 提问...`}
            className="flex-1 px-3 py-2 text-xs border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white"
          />
          <button
            type="submit"
            className="px-3 py-2 bg-slate-900 text-white rounded-lg hover:bg-slate-800 transition-colors flex items-center gap-2 disabled:opacity-60"
            disabled={isSending}
          >
            <Send className="w-3.5 h-3.5" />
          </button>
        </form>
        <div className="mt-2 flex items-center gap-2 text-xs text-gray-500">
          <Shield className="w-3 h-3 text-teal-600" />
          <span>All insights verified by Agent D: Auditor</span>
        </div>
      </div>
    </aside>
  );
}

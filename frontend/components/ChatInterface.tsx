"use client";

import { FormEvent, useMemo, useState } from "react";
import MessageList from "./MessageList";
import type { Message } from "../lib/types";

const END_MARKER = "<<END_OF_STREAM>>";

export default function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const apiBase = useMemo(() => process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000", []);

  async function submitMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const text = input.trim();
    if (!text || isLoading) {
      return;
    }

    setError(null);
    setInput("");
    setIsLoading(true);

    const userMessage: Message = {
      role: "user",
      content: text,
      timestamp: new Date().toISOString(),
    };

    const history = [...messages, userMessage];
    setMessages(history);

    const assistantPlaceholder: Message = {
      role: "assistant",
      content: "",
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, assistantPlaceholder]);

    try {
      const response = await fetch(`${apiBase}/api/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          conversation_history: history.map((msg) => ({ role: msg.role, content: msg.content })),
          current_message: text,
          stream: true,
        }),
      });

      if (!response.ok || !response.body) {
        throw new Error("Unable to connect to backend.");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let assistantText = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          break;
        }

        const chunk = decoder.decode(value, { stream: true });
        if (!chunk) {
          continue;
        }

        assistantText += chunk;

        if (assistantText.includes(END_MARKER)) {
          assistantText = assistantText.split(END_MARKER).join("").trimEnd();
        }

        setMessages((prev) => {
          const next = [...prev];
          const idx = next.length - 1;
          if (idx >= 0 && next[idx].role === "assistant") {
            next[idx] = { ...next[idx], content: assistantText };
          }
          return next;
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong while sending your message.");
      setMessages((prev) => {
        const next = [...prev];
        const idx = next.length - 1;
        if (idx >= 0 && next[idx].role === "assistant" && !next[idx].content.trim()) {
          next[idx] = {
            ...next[idx],
            content: "I could not reach the backend. Please verify the API server is running.",
          };
        }
        return next;
      });
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <section className="chat-shell">
      <div className="chat-hero">
        <p className="eyebrow">ET Concierge</p>
        <h1>ET User Profiling Agent</h1>
        <p className="subtitle">Answer a few focused questions and get tailored ET recommendations.</p>
      </div>

      <MessageList messages={messages} isLoading={isLoading} />

      <form onSubmit={submitMessage} className="composer">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Tell me about your goals, risk appetite, or interests"
          className="composer-input"
          aria-label="Message"
        />
        <button
          type="submit"
          disabled={isLoading || input.trim().length === 0}
          className="composer-send"
        >
          Send
        </button>
      </form>

      <div className="status-row">
        <p className="status-pill" aria-live="polite">
          {isLoading ? "Streaming response..." : "Ready"}
        </p>
        {error && <p className="error-text">{error}</p>}
      </div>
    </section>
  );
}

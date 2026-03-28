"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import MessageList from "./MessageList";
import type { Message } from "../lib/types";

const END_MARKER = "<<END_OF_STREAM>>";
const CHAT_STORAGE_KEY = "et-chat-sessions-v1";
const AUTH_STORAGE_KEY = "et-auth-v1";

interface ChatSession {
  id: string;
  title: string;
  updatedAt: string;
  messages: Message[];
}

interface HistorySessionSummary {
  id: string;
  title: string;
  updated_at: string;
  created_at: string;
}

interface HistorySessionDetail {
  id: string;
  title: string;
  messages: Array<{
    role: "user" | "assistant";
    content: string;
    timestamp: string;
  }>;
}

interface AuthResponse {
  access_token: string;
  token_type: string;
  user_id: string;
  email: string;
}

function deriveTitle(messages: Message[]): string {
  const firstUser = messages.find((message) => message.role === "user");
  if (!firstUser) {
    return "New chat";
  }

  const trimmed = firstUser.content.trim();
  if (!trimmed) {
    return "New chat";
  }

  return trimmed.length > 48 ? `${trimmed.slice(0, 48)}...` : trimmed;
}

export default function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "signup">("login");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authFullName, setAuthFullName] = useState("");
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [authUserEmail, setAuthUserEmail] = useState<string | null>(null);
  const [isAuthLoading, setIsAuthLoading] = useState(false);
  const [historyMode, setHistoryMode] = useState<"server" | "local">("local");
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);

  const apiBase = useMemo(() => process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000", []);

  function loadLocalSessions(): ChatSession[] {
    try {
      const raw = window.localStorage.getItem(CHAT_STORAGE_KEY);
      if (!raw) {
        return [];
      }

      const parsed = JSON.parse(raw) as ChatSession[];
      if (!Array.isArray(parsed)) {
        return [];
      }

      return parsed
        .filter((item) => item && typeof item.id === "string" && Array.isArray(item.messages))
        .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());
    } catch {
      window.localStorage.removeItem(CHAT_STORAGE_KEY);
      return [];
    }
  }

  function saveLocalAuth(token: string, email: string): void {
    window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify({ token, email }));
  }

  function clearLocalAuth(): void {
    window.localStorage.removeItem(AUTH_STORAGE_KEY);
  }

  async function refreshServerSessions(token: string): Promise<boolean> {
    try {
      const response = await fetch(`${apiBase}/api/history/sessions`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        throw new Error("Unable to load server history.");
      }

      const payload = (await response.json()) as HistorySessionSummary[];
      setSessions((prev) => {
        const previousMessages = new Map(prev.map((session) => [session.id, session.messages]));
        return payload
          .map((item) => ({
            id: item.id,
            title: item.title,
            updatedAt: item.updated_at,
            messages: previousMessages.get(item.id) ?? [],
          }))
          .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());
      });
      setHistoryMode("server");
      return true;
    } catch {
      setHistoryMode("local");
      return false;
    }
  }

  useEffect(() => {
    const localSessions = loadLocalSessions();
    setSessions(localSessions);
    setActiveSessionId(null);
    setMessages([]);

    try {
      const rawAuth = window.localStorage.getItem(AUTH_STORAGE_KEY);
      if (!rawAuth) {
        return;
      }
      const parsedAuth = JSON.parse(rawAuth) as { token?: string; email?: string };
      if (!parsedAuth?.token || !parsedAuth?.email) {
        clearLocalAuth();
        return;
      }
      setAuthToken(parsedAuth.token);
      setAuthUserEmail(parsedAuth.email);
    } catch {
      clearLocalAuth();
    }
  }, []);

  useEffect(() => {
    if (!authToken) {
      setHistoryMode("local");
      return;
    }

    const sync = async () => {
      const loaded = await refreshServerSessions(authToken);
      if (loaded) {
        setActiveSessionId(null);
        setMessages([]);
      }
    };

    void sync();
  }, [authToken]);

  useEffect(() => {
    if (historyMode !== "local") {
      return;
    }
    window.localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(sessions));
  }, [sessions, historyMode]);

  useEffect(() => {
    if (!activeSessionId) {
      return;
    }

    setSessions((prev) => {
      const exists = prev.some((session) => session.id === activeSessionId);
      if (!exists) {
        return prev;
      }

      const next = prev
        .map((session) =>
          session.id === activeSessionId
            ? {
                ...session,
                messages,
                title: historyMode === "local" ? deriveTitle(messages) : session.title,
                updatedAt: new Date().toISOString(),
              }
            : session,
        )
        .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());

      return next;
    });
  }, [messages, activeSessionId, historyMode]);

  function createSession(seedMessages: Message[] = []): string {
    const sessionId =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

    const session: ChatSession = {
      id: sessionId,
      title: deriveTitle(seedMessages),
      updatedAt: new Date().toISOString(),
      messages: seedMessages,
    };

    setSessions((prev) => [session, ...prev]);
    setActiveSessionId(sessionId);
    return sessionId;
  }

  function startNewChat() {
    setActiveSessionId(null);
    setMessages([]);
    setInput("");
    setError(null);
    setIsSidebarOpen(false);
  }

  async function openSession(sessionId: string) {
    if (authToken && historyMode === "server") {
      try {
        const response = await fetch(`${apiBase}/api/history/sessions/${sessionId}`, {
          headers: {
            Authorization: `Bearer ${authToken}`,
          },
        });
        if (!response.ok) {
          throw new Error("Unable to load chat transcript.");
        }
        const detail = (await response.json()) as HistorySessionDetail;
        const sessionMessages: Message[] = detail.messages.map((item) => ({
          role: item.role,
          content: item.content,
          timestamp: item.timestamp,
        }));

        setSessions((prev) =>
          prev.map((session) =>
            session.id === sessionId ? { ...session, title: detail.title, messages: sessionMessages } : session,
          ),
        );
        setActiveSessionId(sessionId);
        setMessages(sessionMessages);
        setInput("");
        setError(null);
        setIsSidebarOpen(false);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to open selected chat.");
      }
      return;
    }

    const localTarget = sessions.find((session) => session.id === sessionId);
    if (localTarget) {
      setActiveSessionId(localTarget.id);
      setMessages(localTarget.messages);
      setInput("");
      setError(null);
      setIsSidebarOpen(false);
    }
  }

  async function handleRenameSession(sessionId: string) {
    const target = sessions.find((session) => session.id === sessionId);
    if (!target) {
      return;
    }

    const title = window.prompt("Rename chat", target.title)?.trim();
    if (!title) {
      return;
    }

    if (authToken && historyMode === "server") {
      try {
        const response = await fetch(`${apiBase}/api/history/sessions/${sessionId}`, {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${authToken}`,
          },
          body: JSON.stringify({ title }),
        });

        if (!response.ok) {
          throw new Error("Unable to rename chat.");
        }

        const updated = (await response.json()) as HistorySessionSummary;
        setSessions((prev) =>
          prev.map((session) =>
            session.id === sessionId ? { ...session, title: updated.title, updatedAt: updated.updated_at } : session,
          ),
        );
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to rename chat.");
      }
      return;
    }

    setSessions((prev) => prev.map((session) => (session.id === sessionId ? { ...session, title } : session)));
  }

  async function handleArchiveSession(sessionId: string) {
    if (authToken && historyMode === "server") {
      try {
        const response = await fetch(`${apiBase}/api/history/sessions/${sessionId}`, {
          method: "DELETE",
          headers: {
            Authorization: `Bearer ${authToken}`,
          },
        });

        if (!response.ok) {
          throw new Error("Unable to archive chat.");
        }

        if (activeSessionId === sessionId) {
          startNewChat();
        }

        await refreshServerSessions(authToken);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to archive chat.");
      }
      return;
    }

    setSessions((prev) => prev.filter((session) => session.id !== sessionId));
    if (activeSessionId === sessionId) {
      startNewChat();
    }
  }

  async function submitAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const email = authEmail.trim().toLowerCase();
    const password = authPassword.trim();
    if (!email || !password) {
      setError("Email and password are required.");
      return;
    }

    if (authMode === "signup" && password.length < 8) {
      setError("Password must be at least 8 characters for sign up.");
      return;
    }

    setIsAuthLoading(true);
    setError(null);

    try {
      const endpoint = authMode === "signup" ? "/api/auth/signup" : "/api/auth/login";
      const payload =
        authMode === "signup"
          ? { email, password, full_name: authFullName.trim() || null }
          : { email, password };

      const response = await fetch(`${apiBase}${endpoint}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({ detail: "Authentication failed." }));
        const detail = body?.detail;
        if (typeof detail === "string") {
          throw new Error(detail);
        }
        if (Array.isArray(detail) && detail.length > 0) {
          const first = detail[0];
          if (first && typeof first === "object" && typeof first.msg === "string") {
            throw new Error(first.msg);
          }
        }
        throw new Error("Authentication failed.");
      }

      const auth = (await response.json()) as AuthResponse;
      setAuthToken(auth.access_token);
      setAuthUserEmail(auth.email);
      saveLocalAuth(auth.access_token, auth.email);
      setIsAuthModalOpen(false);
      setAuthPassword("");
      setAuthFullName("");
      setMessages([]);
      setActiveSessionId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed.");
    } finally {
      setIsAuthLoading(false);
    }
  }

  function logout() {
    clearLocalAuth();
    setAuthToken(null);
    setAuthUserEmail(null);
    const localSessions = loadLocalSessions();
    setSessions(localSessions);
    setActiveSessionId(null);
    setMessages([]);
    setError(null);
  }

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

    if (!activeSessionId && historyMode === "local") {
      createSession([]);
    }

    const history = [...messages, userMessage];
    setMessages(history);

    const assistantPlaceholder: Message = {
      role: "assistant",
      content: "",
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, assistantPlaceholder]);

    try {
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      if (authToken && historyMode === "server") {
        headers.Authorization = `Bearer ${authToken}`;
      }

      const response = await fetch(`${apiBase}/api/chat`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          conversation_history: history.map((msg) => ({ role: msg.role, content: msg.content })),
          current_message: text,
          session_id: authToken && historyMode === "server" ? activeSessionId : null,
          stream: true,
        }),
      });

      if (!response.ok || !response.body) {
        throw new Error("Unable to connect to backend.");
      }

      const serverSessionId = response.headers.get("x-session-id");
      if (serverSessionId) {
        setActiveSessionId(serverSessionId);
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

      if (authToken && historyMode === "server") {
        await refreshServerSessions(authToken);
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
      <div className={`chat-layout ${isSidebarOpen ? "sidebar-open" : ""}`}>
        <aside className={`history-panel ${isSidebarOpen ? "open" : ""}`}>
          <div className="history-panel-header">
            <p>Chat History</p>
            <button type="button" onClick={startNewChat} className="history-new-chat">
              + New
            </button>
          </div>
          <div className="auth-panel">
            {authToken ? (
              <div className="auth-state">
                <p className="auth-user">Signed in as {authUserEmail}</p>
                <button type="button" className="auth-action" onClick={logout}>
                  Log out
                </button>
              </div>
            ) : (
              <button
                type="button"
                className="auth-action"
                onClick={() => {
                  setAuthMode("login");
                  setIsAuthModalOpen(true);
                }}
              >
                Sign in / Sign up
              </button>
            )}
            <p className="history-mode">History source: {historyMode === "server" ? "Server" : "Local fallback"}</p>
          </div>
          <div className="history-list">
            {sessions.length === 0 && <p className="history-empty">No previous chats yet.</p>}
            {sessions.map((session) => (
              <div key={session.id} className={`history-item ${session.id === activeSessionId ? "active" : ""}`}>
                <button type="button" className="history-open" onClick={() => openSession(session.id)}>
                  <span>{session.title}</span>
                </button>
                <div className="history-item-actions">
                  <button type="button" onClick={() => handleRenameSession(session.id)} className="history-mini-action">
                    Rename
                  </button>
                  <button type="button" onClick={() => handleArchiveSession(session.id)} className="history-mini-action">
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        </aside>

        <div className="chat-main">
          <div className="chat-hero">
            <div className="et-masthead" aria-label="Economic Times inspired masthead">
              <span className="et-badge">ET</span>
              <span className="et-title">The Economic Times Concierge</span>
            </div>
            <div className="chat-topbar">
              <button
                type="button"
                className="history-toggle"
                onClick={() => setIsSidebarOpen((prev) => !prev)}
                aria-label="Toggle chat history"
              >
                <span />
                <span />
                <span />
              </button>
              <p className="eyebrow">ET Concierge</p>
              {!authToken && (
                <button
                  type="button"
                  className="topbar-auth-btn"
                  onClick={() => {
                    setAuthMode("login");
                    setIsAuthModalOpen(true);
                  }}
                >
                  Sign In
                </button>
              )}
              <div className="topbar-meta" aria-live="polite">
                <span className={`meta-chip ${historyMode === "server" ? "server" : "local"}`}>
                  {historyMode === "server" ? "Server history" : "Local history"}
                </span>
                <span className="meta-chip user">{authToken ? authUserEmail : "Guest mode"}</span>
              </div>
            </div>
            <div className="et-sections" aria-hidden="true">
              <span>Markets</span>
              <span>Wealth</span>
              <span>Masterclass</span>
              <span>AI</span>
            </div>
            <h1>ET User Profiling Agent</h1>
            <p className="subtitle">Answer a few focused questions and get tailored ET recommendations.</p>
            {!authToken && (
              <button
                type="button"
                className="auth-cta"
                onClick={() => {
                  setAuthMode("signup");
                  setIsAuthModalOpen(true);
                }}
              >
                Sign in or sign up to sync your chat history
              </button>
            )}
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
        </div>
      </div>

      {isAuthModalOpen && (
        <div className="auth-modal-backdrop" role="dialog" aria-modal="true" aria-label="Authentication">
          <div className="auth-modal">
            <div className="auth-modal-header">
              <h2>{authMode === "signup" ? "Create your account" : "Sign in"}</h2>
              <button
                type="button"
                className="auth-modal-close"
                onClick={() => setIsAuthModalOpen(false)}
                aria-label="Close auth popup"
              >
                x
              </button>
            </div>
            <form onSubmit={submitAuth} className="auth-form">
              <div className="auth-mode-row">
                <button
                  type="button"
                  className={`auth-mode ${authMode === "login" ? "active" : ""}`}
                  onClick={() => setAuthMode("login")}
                >
                  Login
                </button>
                <button
                  type="button"
                  className={`auth-mode ${authMode === "signup" ? "active" : ""}`}
                  onClick={() => setAuthMode("signup")}
                >
                  Sign Up
                </button>
              </div>
              {authMode === "signup" && (
                <input
                  value={authFullName}
                  onChange={(e) => setAuthFullName(e.target.value)}
                  placeholder="Full name"
                  className="auth-input"
                  aria-label="Full name"
                />
              )}
              <input
                value={authEmail}
                onChange={(e) => setAuthEmail(e.target.value)}
                placeholder="Email"
                type="email"
                className="auth-input"
                aria-label="Email"
              />
              <input
                value={authPassword}
                onChange={(e) => setAuthPassword(e.target.value)}
                placeholder="Password"
                type="password"
                className="auth-input"
                aria-label="Password"
              />
              <button
                type="submit"
                className="auth-action"
                disabled={isAuthLoading || authEmail.trim().length === 0 || authPassword.trim().length === 0}
              >
                {isAuthLoading ? "Please wait..." : authMode === "signup" ? "Create account" : "Sign in"}
              </button>
            </form>
          </div>
        </div>
      )}
    </section>
  );
}

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import fc from "fast-check";
import ChatInterface from "./ChatInterface";

function createStreamResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
      controller.close();
    },
  });

  return new Response(stream, {
    status: 200,
    headers: { "Content-Type": "text/plain" },
  });
}

describe("ChatInterface", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
    global.fetch = vi.fn().mockResolvedValue(createStreamResponse(["hello", " world", "\n<<END_OF_STREAM>>\n"]));
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("renders initial empty state", () => {
    render(<ChatInterface />);
    expect(screen.getByText(/Start the conversation/i)).toBeInTheDocument();
  });

  it("keeps composer on new chat after reload while preserving local history", () => {
    window.localStorage.setItem(
      "et-chat-sessions-v1",
      JSON.stringify([
        {
          id: "local-session-1",
          title: "Old local chat",
          updatedAt: "2026-03-28T00:00:00Z",
          messages: [
            { role: "user", content: "past question", timestamp: "2026-03-28T00:00:01Z" },
            { role: "assistant", content: "past answer", timestamp: "2026-03-28T00:00:02Z" },
          ],
        },
      ]),
    );

    render(<ChatInterface />);

    expect(screen.getByText(/Start the conversation/i)).toBeInTheDocument();
    expect(screen.queryByText(/past answer/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Old local chat/i)).toBeInTheDocument();
  });

  it("opens sidebar when hamburger is clicked", () => {
    const { container } = render(<ChatInterface />);
    const toggle = screen.getByRole("button", { name: /toggle chat history/i });
    fireEvent.click(toggle);

    expect(container.querySelector(".chat-layout")?.className).toContain("sidebar-open");
    expect(screen.getByText(/No previous chats yet/i)).toBeInTheDocument();
  });

  it("opens auth popup from hero CTA", () => {
    render(<ChatInterface />);
    fireEvent.click(screen.getByRole("button", { name: /sync your chat history/i }));

    expect(screen.getByRole("dialog", { name: /Authentication/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^sign up$/i })).toBeInTheDocument();
  });

  it("blocks signup with short password before API call", async () => {
    render(<ChatInterface />);

    fireEvent.click(screen.getByRole("button", { name: /sync your chat history/i }));
    fireEvent.click(screen.getByRole("button", { name: /^sign up$/i }));

    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "test@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "short7" } });
    fireEvent.submit(screen.getByRole("button", { name: /create account/i }).closest("form") as HTMLFormElement);

    await screen.findByText(/Password must be at least 8 characters/i);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("surfaces backend 422 validation details in auth error", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          detail: [{ msg: "String should have at least 8 characters" }],
        }),
        {
          status: 422,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    render(<ChatInterface />);

    fireEvent.click(screen.getByRole("button", { name: /sync your chat history/i }));
    fireEvent.click(screen.getByRole("button", { name: /^sign up$/i }));
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "test@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "longenough123" } });
    fireEvent.submit(screen.getByRole("button", { name: /create account/i }).closest("form") as HTMLFormElement);

    await screen.findByText(/at least 8 characters/i);
  });

  it("rejects empty message submission (Property 18)", async () => {
    render(<ChatInterface />);

    const input = screen.getByLabelText("Message");
    const send = screen.getByRole("button", { name: /send/i });

    fireEvent.change(input, { target: { value: "   " } });
    expect(send).toBeDisabled();

    fireEvent.submit(send.closest("form") as HTMLFormElement);
    await waitFor(() => {
      expect(global.fetch).not.toHaveBeenCalled();
    });
  });

  it("sends complete prior history in API request (Property 12)", async () => {
    render(<ChatInterface />);

    const input = screen.getByLabelText("Message");
    const form = screen.getByRole("button", { name: /send/i }).closest("form") as HTMLFormElement;

    fireEvent.change(input, { target: { value: "First" } });
    fireEvent.submit(form);

    await screen.findByText(/hello world/i);

    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      createStreamResponse(["second response", "\n<<END_OF_STREAM>>\n"]),
    );

    fireEvent.change(input, { target: { value: "Second" } });
    fireEvent.submit(form);

    await screen.findByText(/second response/i);

    const secondCall = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[1];
    const payload = JSON.parse(secondCall[1].body as string);

    expect(payload.current_message).toBe("Second");
    expect(payload.conversation_history).toEqual([
      { role: "user", content: "First" },
      { role: "assistant", content: "hello world" },
      { role: "user", content: "Second" },
    ]);
  });

  it("appends streamed response into assistant message (Property 13)", async () => {
    render(<ChatInterface />);

    const input = screen.getByLabelText("Message");
    const form = screen.getByRole("button", { name: /send/i }).closest("form") as HTMLFormElement;

    fireEvent.change(input, { target: { value: "Test" } });
    fireEvent.submit(form);

    await screen.findByText(/hello world/i);
    expect(screen.getByText(/hello world/i)).toBeInTheDocument();
  });

  it("shows user-friendly error when backend fails", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response("", { status: 500 }),
    );

    render(<ChatInterface />);

    const input = screen.getByLabelText("Message");
    const form = screen.getByRole("button", { name: /send/i }).closest("form") as HTMLFormElement;

    fireEvent.change(input, { target: { value: "Failure case" } });
    fireEvent.submit(form);

    await screen.findByText(/Unable to connect to backend/i);
    await screen.findByText(/I could not reach the backend/i);
  });

  it("property-checks empty or whitespace inputs never trigger fetch", async () => {
    render(<ChatInterface />);
    const input = screen.getByLabelText("Message");
    const form = screen.getByRole("button", { name: /send/i }).closest("form") as HTMLFormElement;

    await fc.assert(
      fc.asyncProperty(fc.string(), async (s) => {
        if (s.trim().length > 0) {
          return;
        }

        fireEvent.change(input, { target: { value: s } });
        fireEvent.submit(form);
        await Promise.resolve();
      }),
      { numRuns: 25 },
    );

    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("uses bearer auth and session_id for authenticated server chat", async () => {
    window.localStorage.setItem(
      "et-auth-v1",
      JSON.stringify({ token: "token-123", email: "demo@example.com" }),
    );

    (global.fetch as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(
        new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(createStreamResponse(["auth ok", "\n<<END_OF_STREAM>>\n"]).body, {
          status: 200,
          headers: {
            "Content-Type": "text/plain",
            "X-Session-Id": "server-session-1",
          },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify([
            {
              id: "server-session-1",
              title: "Auth Session",
              updated_at: "2026-03-28T00:00:00Z",
              created_at: "2026-03-28T00:00:00Z",
            },
          ]),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
      );

    render(<ChatInterface />);

    const input = screen.getByLabelText("Message");
    const form = screen.getByRole("button", { name: /send/i }).closest("form") as HTMLFormElement;

    await waitFor(() => {
      expect(screen.getByText(/History source: Server/i)).toBeInTheDocument();
    });

    fireEvent.change(input, { target: { value: "Auth flow message" } });
    fireEvent.submit(form);

    await screen.findByText(/auth ok/i);

    const chatCall = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[1];
    expect(chatCall[0]).toContain("/api/chat");
    expect(chatCall[1].headers.Authorization).toBe("Bearer token-123");

    const payload = JSON.parse(chatCall[1].body as string);
    expect(payload.session_id).toBeNull();
  });

  it("loads server transcript when opening a saved session", async () => {
    window.localStorage.setItem(
      "et-auth-v1",
      JSON.stringify({ token: "token-123", email: "demo@example.com" }),
    );

    (global.fetch as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify([
            {
              id: "session-a",
              title: "My Previous Chat",
              updated_at: "2026-03-28T00:00:00Z",
              created_at: "2026-03-28T00:00:00Z",
            },
          ]),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: "session-a",
            title: "My Previous Chat",
            messages: [
              { role: "user", content: "Earlier question", timestamp: "2026-03-28T00:00:01Z" },
              { role: "assistant", content: "Earlier answer", timestamp: "2026-03-28T00:00:02Z" },
            ],
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
      );

    render(<ChatInterface />);

    await screen.findByText(/My Previous Chat/i);
    fireEvent.click(screen.getByRole("button", { name: /my previous chat/i }));

    await screen.findByText(/Earlier question/i);
    await screen.findByText(/Earlier answer/i);
  });
});

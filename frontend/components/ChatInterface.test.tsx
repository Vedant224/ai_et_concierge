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
    global.fetch = vi.fn().mockResolvedValue(createStreamResponse(["hello", " world", "\n<<END_OF_STREAM>>\n"]));
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("renders initial empty state", () => {
    render(<ChatInterface />);
    expect(screen.getByText(/Start the conversation/i)).toBeInTheDocument();
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
});

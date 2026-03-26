import { render, screen } from "@testing-library/react";
import MessageList from "./MessageList";
import type { Message } from "../lib/types";

describe("MessageList", () => {
  beforeAll(() => {
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      value: vi.fn(),
      writable: true,
    });
  });

  it("renders empty prompt when there are no messages", () => {
    render(<MessageList messages={[]} isLoading={false} />);
    expect(screen.getByText(/Start the conversation/i)).toBeInTheDocument();
  });

  it("renders user and assistant messages", () => {
    const messages: Message[] = [
      { role: "user", content: "Hi", timestamp: new Date().toISOString() },
      { role: "assistant", content: "Hello", timestamp: new Date().toISOString() },
    ];

    render(<MessageList messages={messages} isLoading={false} />);

    expect(screen.getByText("You")).toBeInTheDocument();
    expect(screen.getByText("Assistant")).toBeInTheDocument();
    expect(screen.getByText("Hi")).toBeInTheDocument();
    expect(screen.getByText("Hello")).toBeInTheDocument();
  });

  it("shows loading indicator during streaming", () => {
    render(<MessageList messages={[]} isLoading={true} />);
    expect(screen.getByText(/Streaming response/i)).toBeInTheDocument();
  });
});

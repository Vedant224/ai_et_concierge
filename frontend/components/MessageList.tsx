"use client";

import { useEffect, useRef } from "react";
import type { Message } from "../lib/types";

interface MessageListProps {
  messages: Message[];
  isLoading: boolean;
}

export default function MessageList({ messages, isLoading }: MessageListProps) {
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  return (
    <div className="chat-thread">
      {messages.length === 0 && <p className="thread-empty">Start the conversation with your investment goals.</p>}
      {messages.map((msg, index) => (
        <div
          key={`${msg.role}-${index}`}
          className={msg.role === "user" ? "bubble bubble-user" : "bubble bubble-assistant"}
        >
          <div className="bubble-label">{msg.role === "user" ? "You" : "Assistant"}</div>
          <div className="bubble-content">{msg.content}</div>
        </div>
      ))}
      {isLoading && <div className="thread-loading">Streaming response...</div>}
      <div ref={endRef} />
    </div>
  );
}

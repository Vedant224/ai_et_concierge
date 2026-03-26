export type ChatRole = "user" | "assistant";

export interface Message {
  role: ChatRole;
  content: string;
  timestamp: string;
}

export interface ChatRequest {
  conversation_history: Array<{ role: ChatRole; content: string }>;
  current_message: string;
  stream: boolean;
}

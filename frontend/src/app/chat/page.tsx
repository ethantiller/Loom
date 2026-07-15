"use client";

import { useState } from "react";

import MessageComposer from "../components/MessageComposer";

type ChatMessage = {
  id: string;
  text: string;
};

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  function handleSendMessage(text: string): void {
    setMessages((prevMessages) => [
      ...prevMessages,
      { id: crypto.randomUUID(), text },
    ]);
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Message history area. Content sticks to the bottom and grows upward. */}
      <div className="flex flex-1 flex-col overflow-y-auto">
        <div className="mx-auto mt-auto flex w-full max-w-3xl flex-col gap-3 px-4 py-6">
          {messages.map((message) => (
            <div
              key={message.id}
              className="self-end whitespace-pre-wrap rounded-2xl bg-zinc-700 px-4 py-2 text-sm text-zinc-100"
            >
              {message.text}
            </div>
          ))}
        </div>
      </div>

      <MessageComposer onSendMessage={handleSendMessage} />
    </div>
  );
}

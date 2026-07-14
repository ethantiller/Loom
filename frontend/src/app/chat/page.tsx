"use client";

import { useState } from "react";

import MessageComposer from "../components/MessageComposer";

export default function ChatPage() {
  const [messages, setMessages] = useState<string[]>([]);

  function handleSendMessage(message: string): void {
    setMessages((prevMessages) => [...prevMessages, message]);
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Message history area. Content sticks to the bottom and grows upward. */}
      <div className="flex flex-1 flex-col overflow-y-auto">
        <div className="mx-auto mt-auto flex w-full max-w-3xl flex-col gap-3 px-4 py-6">
          {messages.map((message, index) => (
            <div
              key={index}
              className="self-end whitespace-pre-wrap rounded-2xl bg-zinc-700 px-4 py-2 text-sm text-zinc-100"
            >
              {message}
            </div>
          ))}
        </div>
      </div>

      <MessageComposer onSendMessage={handleSendMessage} />
    </div>
  );
}

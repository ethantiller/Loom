"use client";

import { useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";

/** Upper bound (px) the textarea grows to before it starts scrolling internally. */
const MAX_TEXTAREA_HEIGHT = 200;

interface MessageComposerProps {
  onSendMessage: (message: string) => void;
}

export default function MessageComposer({ onSendMessage }: MessageComposerProps) {
  const [value, setValue] = useState<string>("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Grow the textarea to fit its content, capped at MAX_TEXTAREA_HEIGHT.
  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, MAX_TEXTAREA_HEIGHT)}px`;
  }, [value]);

  // Shift+Enter inserts a newline (the textarea default); a bare Enter sends.
  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>): void {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSend();
    }
  }

  function handleSend(): void {
    const message = value.trim();
    if (!message) {
      return;
    }
    onSendMessage(message);
    setValue("");
  }

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-6">
      <div className="flex items-end gap-2 rounded-2xl border border-zinc-700/60 bg-zinc-900 px-4 py-3 shadow-lg focus-within:border-zinc-600">
        <button className="cursor-pointer hover:scale-110 ease-in duration-100 rounded-full pr-2 text-zinc-400 transition-colors hover:bg-zinc-800/60 hover:text-zinc-200">
          +
        </button>
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
          placeholder="Send a message..."
          aria-label="Message"
          className="max-h-[200px] flex-1 resize-none bg-transparent text-sm text-zinc-200 placeholder:text-zinc-500 focus:outline-none"
        />
      </div>
    </div>
  );
}

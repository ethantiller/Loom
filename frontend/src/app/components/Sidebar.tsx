"use client";

import { useState } from "react";

type NavItem = {
  label: string;
  icon: React.ReactNode;
};

const navItems: NavItem[] = [
  {
    label: "Home",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
        <path d="M3 10.5 12 3l9 7.5" />
        <path d="M5 9.5V21h14V9.5" />
        <path d="M9.5 21v-6h5v6" />
      </svg>
    ),
  },
  {
    label: "Chat",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
        <path d="M21 15a2 2 0 0 1-2 2H8l-4 4V5a2 2 0 0 1 2-2h13a2 2 0 0 1 2 2z" />
      </svg>
    ),
  },
  {
    label: "Projects",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
        <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
      </svg>
    ),
  },
];

const chats: string[] = [
  "Weekend trip planning",
  "Landing page copy",
  "Bug in auth flow",
  "Dinner recipe ideas",
  "Q3 roadmap draft",
  "Interview prep notes",
  "Book recommendations",
];

export default function Sidebar() {
  const [active, setActive] = useState<string>("Home");
  const [isOpen, setIsOpen] = useState<boolean>(true);

  function handleOpenClose(): void {
    setIsOpen(!isOpen);
  }

  const sidebarWidth: string = isOpen ? "w-60" : "w-16";

  return (
    <div className={`flex ${sidebarWidth} shrink-0 flex-col overflow-hidden whitespace-nowrap border-r border-zinc-700/60 bg-zinc-900 transition-[width] duration-200 ease-in-out`}>
      {/* Toggle */}
      <div className={`flex items-center py-4 ${isOpen ? "px-3" : "justify-center px-2"}`}>
        {isOpen && (
          <p className="text-lg font-bold text-zinc-100">Loom</p>
        )}
        <button
          onClick={handleOpenClose}
          aria-label={isOpen ? "Collapse sidebar" : "Expand sidebar"}
          title={isOpen ? "Collapse sidebar" : "Expand sidebar"}
          className={`cursor-pointer flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-zinc-400 transition-colors hover:bg-zinc-800/60 hover:text-zinc-200 ${
            isOpen ? "ml-auto" : ""
          }`}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
            <rect x="3" y="4" width="18" height="16" rx="2" />
            <path d="M9 4v16" />
          </svg>
        </button>
      </div>

      {/* Nav */}
      <nav className="space-y-1 px-3">
        {navItems.map((item) => {
          const isActive = item.label === active;
          return (
            <button
              key={item.label}
              onClick={() => setActive(item.label)}
              title={!isOpen ? item.label : undefined}
              aria-label={item.label}
              className={`cursor-pointer flex w-full items-center gap-3 rounded-lg py-2 text-sm font-medium transition-colors ${
                isOpen ? "px-3" : "justify-center px-0"
              } ${
                isActive
                  ? "bg-zinc-800 text-zinc-100"
                  : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200"
              }`}
            >
              {item.icon}
              {isOpen && item.label}
            </button>
          );
        })}
      </nav>

      {/* Chats */}
      {isOpen && (
        <div className="mt-6 flex-1 overflow-y-auto px-3">
          <p className="px-3 pb-2 text-xs font-medium uppercase tracking-wide text-zinc-500">
            Chats
          </p>
          <div className="space-y-1">
            {chats.map((chat) => (
              <button
                key={chat}
                className="cursor-pointer flex w-full items-center rounded-lg px-3 py-2 text-left text-sm text-zinc-400 transition-colors hover:bg-zinc-800/60 hover:text-zinc-200"
              >
                <span className="truncate">{chat}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Spacer keeps footer pinned when collapsed */}
      {!isOpen && <div className="flex-1" />}

      {/* Footer */}
      <div className="border-t border-zinc-700/60 px-3 py-4">
        <div className={`flex items-center gap-3 rounded-lg py-2 ${isOpen ? "px-3" : "justify-center px-0"}`}>
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-zinc-700 text-sm font-medium text-zinc-200">
            E
          </div>
          {isOpen && (
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-zinc-200">Ethan</p>
              <p className="truncate text-xs text-zinc-500">0 Projects</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

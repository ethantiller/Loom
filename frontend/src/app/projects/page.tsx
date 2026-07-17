"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";

const API_BASE = "http://localhost:8000";

interface Project {
  id: string;
  name: string;
  created_at: string;
  document_count: number;
}

export default function ProjectsPage() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [newName, setNewName] = useState("");
  const [isCreating, setIsCreating] = useState(false);

  const fetchProjects = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/projects`);
      if (!res.ok) throw new Error(res.statusText);
      setProjects(await res.json());
      setError(null);
    } catch {
      setError("Cannot reach Loom backend — make sure the server is running on port 8000.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setIsCreating(true);
    try {
      const res = await fetch(`${API_BASE}/projects`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newName.trim() }),
      });
      if (!res.ok) throw new Error(await res.text());
      const project: Project = await res.json();
      setShowModal(false);
      setNewName("");
      router.push(`/projects/${project.id}`);
    } catch (err: any) {
      alert(err.message || "Failed to create project.");
    } finally {
      setIsCreating(false);
    }
  };

  const formatDate = (s: string) =>
    new Date(s).toLocaleDateString(undefined, {
      year: "numeric", month: "short", day: "numeric",
    });

  return (
    <div className="flex flex-1 flex-col overflow-y-auto px-8 py-10">
      {/* Header row */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-zinc-100">Projects</h1>
          <p className="text-sm text-zinc-400 mt-0.5">
            Each project bundles files, embeddings, and a knowledge graph together.
          </p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="cursor-pointer flex items-center gap-2 rounded-xl bg-cyan-500 px-4 py-2 text-sm font-semibold text-zinc-950 shadow-lg shadow-cyan-500/20 transition-all hover:bg-cyan-400 active:scale-95"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
          New Project
        </button>
      </div>

      {error && (
        <div className="mb-6 rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-300">
          {error}
        </div>
      )}

      {isLoading ? (
        <div className="flex flex-1 items-center justify-center">
          <div className="flex flex-col items-center gap-3 text-zinc-500">
            <svg className="animate-spin h-8 w-8 text-cyan-500" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <p className="text-sm">Loading projects…</p>
          </div>
        </div>
      ) : projects.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-5 text-center">
          <div className="flex h-20 w-20 items-center justify-center rounded-3xl border border-dashed border-zinc-700 bg-zinc-900/60 text-zinc-600">
            <svg className="h-10 w-10" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.2} d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
            </svg>
          </div>
          <div>
            <p className="text-lg font-semibold text-zinc-200">No projects yet</p>
            <p className="text-sm text-zinc-500 mt-1 max-w-xs">
              Create your first project to start ingesting documents and exploring their knowledge graph.
            </p>
          </div>
          <button
            onClick={() => setShowModal(true)}
            className="cursor-pointer rounded-xl bg-cyan-500 px-5 py-2.5 text-sm font-semibold text-zinc-950 shadow-lg shadow-cyan-500/20 hover:bg-cyan-400"
          >
            Create a project
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((p) => (
            <button
              key={p.id}
              onClick={() => router.push(`/projects/${p.id}`)}
              className="cursor-pointer group relative flex flex-col gap-3 rounded-2xl border border-zinc-700/60 bg-zinc-900/50 p-5 text-left shadow-md transition-all hover:border-cyan-500/40 hover:bg-zinc-800/60 hover:shadow-cyan-500/5 active:scale-[0.98]"
            >
              {/* Icon */}
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/10 text-cyan-400 transition-colors group-hover:bg-cyan-500/20">
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
                </svg>
              </div>

              {/* Name + meta */}
              <div className="min-w-0">
                <p className="truncate text-base font-semibold text-zinc-100 group-hover:text-white">
                  {p.name}
                </p>
                <p className="mt-0.5 text-xs text-zinc-500">
                  {formatDate(p.created_at)}
                </p>
              </div>

              {/* Footer */}
              <div className="flex items-center justify-between border-t border-zinc-800/80 pt-3 mt-auto">
                <span className="text-xs text-zinc-500">
                  {p.document_count} {p.document_count === 1 ? "file" : "files"}
                </span>
                <svg className="h-4 w-4 text-zinc-600 transition-colors group-hover:text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </svg>
              </div>
            </button>
          ))}
        </div>
      )}

      {/* New Project Modal */}
      {showModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={() => setShowModal(false)}
        >
          <div
            className="relative w-full max-w-md rounded-2xl border border-zinc-700/60 bg-zinc-900 p-6 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-lg font-bold text-zinc-100 mb-1">New Project</h2>
            <p className="text-xs text-zinc-400 mb-5">Give your project a descriptive name. You can upload files after creating it.</p>

            <label className="block text-xs font-semibold text-zinc-400 mb-1.5 uppercase tracking-wide">
              Project Name
            </label>
            <input
              autoFocus
              type="text"
              placeholder="e.g. Q4 Research, Loom Docs…"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              className="w-full rounded-xl border border-zinc-700 bg-zinc-800 px-4 py-2.5 text-sm text-zinc-100 placeholder-zinc-500 focus:border-cyan-500 focus:outline-none"
            />

            <div className="flex gap-3 mt-5 justify-end">
              <button
                onClick={() => setShowModal(false)}
                className="cursor-pointer rounded-xl border border-zinc-700 bg-zinc-800 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-700"
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                disabled={isCreating || !newName.trim()}
                className="cursor-pointer rounded-xl bg-cyan-500 px-5 py-2 text-sm font-semibold text-zinc-950 shadow-lg shadow-cyan-500/20 hover:bg-cyan-400 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isCreating ? "Creating…" : "Create Project"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

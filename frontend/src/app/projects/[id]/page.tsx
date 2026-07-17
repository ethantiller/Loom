"use client";

import React, { useEffect, useState, useCallback, useRef } from "react";
import { use } from "react";
import GraphVisualizer from "../../components/GraphVisualizer";

const API_BASE = "http://localhost:8000";
const ACCEPTED_TYPES = ".pdf,.txt,.md";
const POLL_INTERVAL_MS = 3000;

interface ProjectDoc {
  id: string;
  title: string;
  source_path: string;
  created_at: string | null;
  chunk_count: number;
  file_type: string;
}

interface Project {
  id: string;
  name: string;
  created_at: string;
  documents: ProjectDoc[];
}

interface DocContent {
  id: string;
  title: string;
  file_type: string;
  text: string;
  chunk_count: number;
}

interface GraphNode {
  id: string;
  label: string;
  type: "document" | "entity";
  entity_type?: string;
  doc_id?: string;
  metadata?: { source_path?: string; created_at?: string; file_type?: string };
}

interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  type: "relationship" | "mention";
}

// Each pending upload tracks the doc IDs returned by the server
// so completion can be detected reliably by ID, not by title matching.
interface PendingUpload {
  name: string;
  status: "uploading" | "processing" | "completed" | "failed";
  docIds: string[];       // preassigned IDs returned from /ingest
}

const FILE_TYPE_ICON: Record<string, React.JSX.Element> = {
  pdf: (
    <svg className="h-4 w-4 text-rose-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
    </svg>
  ),
  txt: (
    <svg className="h-4 w-4 text-zinc-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
    </svg>
  ),
  md: (
    <svg className="h-4 w-4 text-violet-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
    </svg>
  ),
};

export default function ProjectDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id: projectId } = use(params);

  const [project, setProject] = useState<Project | null>(null);
  const [graphData, setGraphData] = useState<{ nodes: GraphNode[]; edges: GraphEdge[] }>({ nodes: [], edges: [] });
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [docContent, setDocContent] = useState<DocContent | null>(null);
  const [selectedGraphNode, setSelectedGraphNode] = useState<GraphNode | null>(null);
  const [isLoadingProject, setIsLoadingProject] = useState(true);
  const [isLoadingGraph, setIsLoadingGraph] = useState(true);
  const [isLoadingContent, setIsLoadingContent] = useState(false);
  const [pendingUploads, setPendingUploads] = useState<PendingUpload[]>([]);
  const [isDragActive, setIsDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Stable ref to the latest pendingUploads so the interval can read it
  // without being recreated on every state change.
  const pendingUploadsRef = useRef<PendingUpload[]>([]);
  pendingUploadsRef.current = pendingUploads;

  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Data fetchers ──────────────────────────────────────────────────────────
  const fetchProject = useCallback(async (): Promise<Project | null> => {
    const res = await fetch(`${API_BASE}/projects/${projectId}`);
    if (!res.ok) return null;
    const data: Project = await res.json();
    setProject(data);
    setIsLoadingProject(false);
    return data;
  }, [projectId]);

  const fetchGraph = useCallback(async () => {
    const res = await fetch(`${API_BASE}/projects/${projectId}/graph/data`);
    if (!res.ok) return;
    setGraphData(await res.json());
    setIsLoadingGraph(false);
  }, [projectId]);

  // Initial load
  useEffect(() => {
    fetchProject();
    fetchGraph();
  }, [fetchProject, fetchGraph]);

  // ── Polling ────────────────────────────────────────────────────────────────
  // Start a single stable interval when component mounts; stop it on unmount.
  // The interval checks pendingUploadsRef (a ref, not state) so it never needs
  // to be recreated on every render.
  useEffect(() => {
    const tick = async () => {
      const processing = pendingUploadsRef.current.filter((u) => u.status === "processing");
      if (processing.length === 0) return;

      const project = await fetchProject();
      if (!project) return;

      const presentDocIds = new Set(project.documents.map((d) => d.id));

      // Check which processing uploads have their doc IDs in the project now
      let anyCompleted = false;
      setPendingUploads((prev) =>
        prev.map((u) => {
          if (
            u.status === "processing" &&
            u.docIds.length > 0 &&
            u.docIds.some((id) => presentDocIds.has(id))
          ) {
            anyCompleted = true;
            return { ...u, status: "completed" as const };
          }
          return u;
        })
      );

      // Only refetch the graph when at least one new doc was just detected
      if (anyCompleted) {
        fetchGraph();
      }
    };

    pollIntervalRef.current = setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]); // Only re-mount if project changes, NOT on pendingUploads changes

  // Auto-clear completed uploads after 4 s
  useEffect(() => {
    const hasCompleted = pendingUploads.some((u) => u.status === "completed");
    if (!hasCompleted) return;
    const t = setTimeout(() => {
      setPendingUploads((prev) => prev.filter((u) => u.status !== "completed"));
    }, 4000);
    return () => clearTimeout(t);
  }, [pendingUploads]);

  // ── Load document content when a file is selected ─────────────────────────
  useEffect(() => {
    if (!selectedDocId) { setDocContent(null); return; }
    setIsLoadingContent(true);
    fetch(`${API_BASE}/projects/${projectId}/documents/${selectedDocId}/content`)
      .then((r) => r.json())
      .then(setDocContent)
      .catch(() => setDocContent(null))
      .finally(() => setIsLoadingContent(false));
  }, [selectedDocId, projectId]);

  // ── Upload handler ─────────────────────────────────────────────────────────
  const handleUpload = async (files: FileList | File[]) => {
    const fileArray = Array.from(files);
    if (fileArray.length === 0) return;

    // Optimistically add uploading entries (docIds unknown yet)
    const newPending: PendingUpload[] = fileArray.map((f) => ({
      name: f.name,
      status: "uploading",
      docIds: [],
    }));
    setPendingUploads((prev) => [...prev, ...newPending]);

    const formData = new FormData();
    fileArray.forEach((f) => formData.append("files", f));

    try {
      const res = await fetch(`${API_BASE}/projects/${projectId}/ingest`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Upload failed" }));
        throw new Error(err.detail || "Upload failed");
      }

      // Server returns the preassigned doc IDs — store them so the
      // poll can match by ID rather than by fragile title comparison.
      const result: { doc_ids: string[] } = await res.json();
      const returnedIds: string[] = result.doc_ids ?? [];

      // Distribute IDs across the file uploads (one ID per file in order)
      setPendingUploads((prev) =>
        prev.map((u, _i) => {
          const matchIdx = newPending.findIndex((n) => n.name === u.name && u.status === "uploading");
          if (matchIdx === -1) return u;
          return {
            ...u,
            status: "processing" as const,
            docIds: returnedIds.slice(matchIdx, matchIdx + 1),
          };
        })
      );
    } catch (err: any) {
      setPendingUploads((prev) =>
        prev.map((u) =>
          newPending.some((n) => n.name === u.name) ? { ...u, status: "failed" as const } : u
        )
      );
      alert(err.message || "Upload failed");
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragActive(false);
    if (e.dataTransfer.files.length > 0) handleUpload(e.dataTransfer.files);
  };

  const getStatusDot = (status: string) => {
    if (status === "uploading") return <span className="inline-block h-1.5 w-1.5 rounded-full bg-zinc-400 animate-pulse" />;
    if (status === "processing") return <span className="inline-block h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse" />;
    if (status === "completed") return <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-400" />;
    return <span className="inline-block h-1.5 w-1.5 rounded-full bg-rose-400" />;
  };

  if (isLoadingProject) {
    return (
      <div className="flex flex-1 items-center justify-center text-zinc-500">
        <svg className="animate-spin h-6 w-6 text-cyan-500" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      </div>
    );
  }

  if (!project) {
    return <div className="flex flex-1 items-center justify-center text-zinc-400">Project not found.</div>;
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Top bar */}
      <div className="flex items-center gap-3 border-b border-zinc-800 px-5 py-3 shrink-0">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-cyan-500/10 text-cyan-400">
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
          </svg>
        </div>
        <div className="flex-1 min-w-0">
          <h1 className="text-base font-bold text-zinc-100 truncate">{project.name}</h1>
          <p className="text-[11px] text-zinc-500">{project.documents.length} file{project.documents.length !== 1 ? "s" : ""}</p>
        </div>

        {/* Upload button */}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={ACCEPTED_TYPES}
          className="hidden"
          onChange={(e) => { if (e.target.files) handleUpload(e.target.files); e.target.value = ""; }}
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          className="cursor-pointer flex items-center gap-1.5 rounded-lg bg-zinc-800 border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-700 hover:text-zinc-100 transition-colors"
        >
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 16V4m0 0l-4 4m4-4l4 4M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2" />
          </svg>
          Upload Files
        </button>
      </div>

      {/* Pending uploads strip */}
      {pendingUploads.length > 0 && (
        <div className="flex gap-3 flex-wrap border-b border-zinc-800/60 bg-zinc-900/60 px-5 py-2 shrink-0">
          {pendingUploads.map((u, i) => (
            <div key={i} className="flex items-center gap-1.5 rounded-md bg-zinc-800/80 px-2.5 py-1 text-[11px] text-zinc-300">
              {getStatusDot(u.status)}
              <span className="max-w-[140px] truncate">{u.name}</span>
              <span className="text-zinc-500">
                {u.status === "uploading" ? "uploading…" :
                 u.status === "processing" ? "extracting knowledge graph…" :
                 u.status === "completed" ? "done ✓" : "failed"}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Main split pane */}
      <div
        className="flex flex-1 overflow-hidden"
        onDragOver={(e) => { e.preventDefault(); setIsDragActive(true); }}
        onDragLeave={() => setIsDragActive(false)}
        onDrop={handleDrop}
      >
        {/* ── Left pane: file list ──────────────────────────────────────── */}
        <div className="flex w-64 shrink-0 flex-col border-r border-zinc-800 bg-zinc-900/40 overflow-hidden">
          <div className="px-4 pt-4 pb-2 shrink-0">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Files</p>
          </div>

          <div className="flex-1 overflow-y-auto">
            {project.documents.length === 0 ? (
              <div className="flex flex-col items-center justify-center gap-3 py-12 px-4 text-center">
                <div className={`flex h-12 w-12 items-center justify-center rounded-2xl border-2 border-dashed transition-colors ${isDragActive ? "border-cyan-500 text-cyan-400" : "border-zinc-700 text-zinc-600"}`}>
                  <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 16V4m0 0l-4 4m4-4l4 4" />
                  </svg>
                </div>
                <p className="text-xs text-zinc-500">Drop files here or use Upload Files</p>
              </div>
            ) : (
              <div className="space-y-0.5 px-2 pb-4">
                {project.documents.map((doc) => {
                  const isSelected = selectedDocId === doc.id;
                  return (
                    <button
                      key={doc.id}
                      onClick={() => {
                        setSelectedDocId(isSelected ? null : doc.id);
                        setSelectedGraphNode(null);
                      }}
                      className={`cursor-pointer flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-xs transition-colors ${
                        isSelected
                          ? "bg-cyan-500/10 text-cyan-300 border border-cyan-500/20"
                          : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200"
                      }`}
                    >
                      {FILE_TYPE_ICON[doc.file_type] || FILE_TYPE_ICON.txt}
                      <span className="flex-1 truncate font-medium">{doc.title}</span>
                      <span className="text-zinc-600 shrink-0">{doc.chunk_count}c</span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* ── Right pane ────────────────────────────────────────────────── */}
        <div className="flex flex-1 flex-col overflow-hidden relative">
          {selectedDocId && docContent ? (
            /* Document viewer */
            <div className="flex flex-1 flex-col overflow-hidden">
              <div className="flex items-center gap-2 border-b border-zinc-800 px-5 py-2.5 shrink-0 bg-zinc-900/40">
                <button
                  onClick={() => setSelectedDocId(null)}
                  className="cursor-pointer rounded-md px-2 py-1 text-xs text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800"
                >
                  ← Back to graph
                </button>
                <span className="text-xs text-zinc-600">|</span>
                <p className="text-xs font-medium text-zinc-300 truncate">{docContent.title}</p>
                <span className={`ml-auto text-[10px] px-1.5 py-0.5 rounded font-medium uppercase tracking-wide ${
                  docContent.file_type === "pdf" ? "bg-rose-900/30 text-rose-400" :
                  docContent.file_type === "md" ? "bg-violet-900/30 text-violet-400" :
                  "bg-zinc-800 text-zinc-400"
                }`}>
                  {docContent.file_type}
                </span>
              </div>
              {isLoadingContent ? (
                <div className="flex flex-1 items-center justify-center text-zinc-500">
                  <svg className="animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                </div>
              ) : (
                <div className="flex-1 overflow-y-auto px-8 py-6">
                  <pre className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-zinc-300">
                    {docContent.text}
                  </pre>
                </div>
              )}
            </div>
          ) : (
            /* Graph view */
            <div className="flex flex-1 flex-col overflow-hidden relative">
              {isLoadingGraph && (
                <div className="absolute inset-0 z-10 flex items-center justify-center bg-zinc-900/60 backdrop-blur-sm">
                  <svg className="animate-spin h-6 w-6 text-cyan-500" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                </div>
              )}

              {graphData.nodes.length === 0 && !isLoadingGraph ? (
                <div className="flex flex-1 flex-col items-center justify-center text-center gap-4 px-6">
                  <div className="flex h-16 w-16 items-center justify-center rounded-2xl border border-dashed border-zinc-700 text-zinc-600">
                    <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" />
                      <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" /><line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
                    </svg>
                  </div>
                  <div>
                    <p className="text-base font-semibold text-zinc-300">Graph is empty</p>
                    <p className="text-sm text-zinc-500 mt-1 max-w-sm">
                      Upload files and wait for extraction to complete. Entities and relationships will appear here.
                    </p>
                  </div>
                </div>
              ) : (
                <GraphVisualizer
                  nodes={graphData.nodes}
                  edges={graphData.edges}
                  onNodeSelect={(node) => {
                    setSelectedGraphNode(node);
                    if (node?.type === "document" && node.doc_id) {
                      setSelectedDocId(node.doc_id);
                    }
                  }}
                  selectedNode={selectedGraphNode}
                />
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

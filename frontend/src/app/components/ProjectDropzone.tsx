/**
 * Presentational drop area for creating a project. Purely visual for now —
 * no drag/drop or upload wiring is attached.
 */

const ProjectIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="h-6 w-6">
    <path d="M12 16V4" />
    <path d="m6 10 6-6 6 6" />
    <path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
  </svg>
);

export default function ProjectDropzone() {
  return (
    <div className="flex w-[85%] max-w-3xl flex-col items-center gap-4 rounded-3xl border border-dashed border-zinc-600/70 bg-zinc-900/40 px-8 py-14 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-zinc-800 text-zinc-400">
        <ProjectIcon />
      </div>

      <div className="space-y-1">
        <p className="text-base font-medium text-zinc-200">
          Create a new project
        </p>
        <p className="text-sm text-zinc-500">
          Drag and drop files here, or use the button below to upload.
        </p>
      </div>

      <button
        type="button"
        className="cursor-pointer rounded-full bg-zinc-100 px-5 py-2 text-sm font-medium text-zinc-900 transition-colors hover:bg-white"
      >
        Upload files
      </button>
    </div>
  );
}

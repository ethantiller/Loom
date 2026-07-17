"use client";

import React, { useRef, useState } from "react";

const ProjectIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="h-6 w-6">
    <path d="M12 16V4" />
    <path d="m6 10 6-6 6 6" />
    <path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
  </svg>
);

interface ProjectDropzoneProps {
  onFilesSelected: (files: FileList) => void;
  isUploading?: boolean;
}

export default function ProjectDropzone({ onFilesSelected, isUploading = false }: ProjectDropzoneProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragActive, setIsDragActive] = useState(false);

  const handleButtonClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      onFilesSelected(e.target.files);
    }
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setIsDragActive(true);
    } else if (e.type === "dragleave") {
      setIsDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      onFilesSelected(e.dataTransfer.files);
    }
  };

  return (
    <div
      onDragEnter={handleDrag}
      onDragOver={handleDrag}
      onDragLeave={handleDrag}
      onDrop={handleDrop}
      className={`flex w-[85%] max-w-3xl flex-col items-center gap-4 rounded-3xl border border-dashed px-8 py-14 text-center transition-all ${
        isDragActive
          ? "border-emerald-500 bg-emerald-950/10 shadow-[0_0_15px_rgba(16,185,129,0.1)]"
          : "border-zinc-600/70 bg-zinc-900/40"
      }`}
    >
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".txt,.pdf"
        className="hidden"
        onChange={handleFileChange}
        disabled={isUploading}
      />

      <div className={`flex h-12 w-12 items-center justify-center rounded-full bg-zinc-800 text-zinc-400 transition-colors ${
        isDragActive ? "bg-emerald-900/30 text-emerald-400" : ""
      }`}>
        <ProjectIcon />
      </div>

      <div className="space-y-1">
        <p className="text-base font-medium text-zinc-200">
          Create a new project / Ingest files
        </p>
        <p className="text-sm text-zinc-500">
          Drag and drop PDF or TXT files here, or use the button below to upload.
        </p>
      </div>

      <button
        type="button"
        onClick={handleButtonClick}
        disabled={isUploading}
        className="cursor-pointer rounded-full bg-zinc-100 px-5 py-2 text-sm font-medium text-zinc-900 transition-colors hover:bg-white disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {isUploading ? "Uploading..." : "Upload files"}
      </button>
    </div>
  );
}

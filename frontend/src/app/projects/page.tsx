import ProjectDropzone from "../components/ProjectDropzone";

export default function ProjectsPage() {
  return (
    <div className="flex flex-1 flex-col items-center overflow-y-auto px-6 pt-[18vh]">
      <ProjectDropzone />

      <p className="mt-8 text-sm text-zinc-500">You have no projects.</p>
    </div>
  );
}

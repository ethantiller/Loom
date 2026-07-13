import Image from "next/image";
import Sidebar from "./components/Sidebar";

export default function Home() {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex flex-1 items-center justify-center bg-zinc-800 px-6">
        <main className="flex w-full max-w-sm flex-col items-center gap-7 text-center">
          <div>
            <p className="text-3xl font-semibold text-zinc-300">
              Welcome back, <span className="font-medium text-zinc-300">Ethan</span>
            </p>
          </div>
        </main>
      </div>
    </div>
  );
}

import Image from "next/image";
import Sidebar from "./components/Sidebar";

export default function Home() {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex flex-1 items-center justify-center bg-zinc-800 px-6">
        <main className="flex w-full max-w-sm flex-col items-center gap-7 text-center">
          <div>
            <Image
              className="invert"
              src="/loom-logo.png"
              alt="Loom logo"
              width={400}
              height={400}
              priority
            />
          </div>
        </main>
      </div>
    </div>
  );
}

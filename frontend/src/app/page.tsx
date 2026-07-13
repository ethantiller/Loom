import Image from "next/image";

export default function Home() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-black px-6">
      <main className="flex w-full max-w-sm flex-col items-center gap-7 text-center">
        <Image
          className="invert"
          src="/loom-logo.png"
          alt="Loom logo"
          width={400}
          height={400}
          priority
        />

        <p className="text-sm leading-relaxed text-zinc-400 sm:text-base sm:leading-7">
          A <b className="font-semibold text-zinc-100">hybrid RAG system</b> that combines{" "}
          <b className="font-semibold text-zinc-100">vector retrieval</b> with{" "}
          <b className="font-semibold text-zinc-100">knowledge-graph traversal</b>, using an
          agentic loop that decides when to search, traverse, or answer. Built for multi-hop
          questions that plain RAG can't reach.
        </p>

        <hr className="w-full border-zinc-800" />

        <a
          href="/"
          className="inline-flex h-11 items-center justify-center rounded-full bg-zinc-100 px-8 text-sm font-medium tracking-wide text-zinc-900 transition-all hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-500 focus-visible:ring-offset-2 focus-visible:ring-offset-black"
        >
          Get started
        </a>
      </main>
    </div>
  );
}
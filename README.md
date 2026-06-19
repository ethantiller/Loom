# Loom

A hybrid RAG system that combines vector retrieval with knowledge-graph traversal, using an agentic loop that decides when to search, traverse, or answer — built to handle multi-hop questions that plain RAG can't reach.

This README is the single source of truth for "what is this project and why does it look the way it does." If you're picking up a ticket and something is unclear, the answer is almost certainly in here before it's worth asking.

## Table of contents

- [What this is](#what-this-is)
- [Why GraphRAG (the actual problem)](#why-graphrag-the-actual-problem)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Repository structure](#repository-structure)
- [Getting started](#getting-started)
- [Build plan & ticket tracking](#build-plan--ticket-tracking)
- [Evaluation & definition of done](#evaluation--definition-of-done)
- [Design decisions & FAQ](#design-decisions--faq)
- [Stretch goals](#stretch-goals)
- [Picking up a ticket](#picking-up-a-ticket)

---

## What this is

Loom ingests a set of documents, builds both a **vector index** (for semantic similarity) and a **knowledge graph** (entities + relationships extracted by an LLM) from them, and answers questions by combining the two: vector search finds semantically relevant chunks, graph traversal pulls in facts that are *structurally* connected but wouldn't surface from similarity search alone. An agentic controller decides, per query, whether it needs to search again, expand the graph further, or has enough to answer.

It's a portfolio project, which means two things in practice:
- It needs to actually demonstrate the multi-hop advantage, not just exist. See [Evaluation](#evaluation--definition-of-done).
- Some "production" concerns are intentionally deferred (entity resolution quality, scale beyond a few hundred docs, etc.) — these are documented as known gaps, not accidents. See [Design decisions](#design-decisions--faq).

## Why GraphRAG (the actual problem)

Standard RAG retrieves chunks that are semantically close to the query embedding. That works fine for "what is X" questions. It breaks down for multi-hop questions like:

> "What country did the founder of the company that acquired [Company X] grow up in?"

No single chunk is semantically close to that question — the answer is assembled from facts scattered across multiple documents, connected by entities, not by wording. A knowledge graph captures those entity-to-entity connections explicitly, so traversal can recover a path that vector similarity would never surface. That gap — and closing it — is the whole point of this project.

## Architecture

```
                ┌─────────────┐
 Raw Docs  ───▶ │  Ingestion   │  (load → chunk)
                └─────┬───────┘
                      │ chunks
          ┌───────────┴─────────────┐
          ▼                         ▼
   ┌─────────────┐           ┌──────────────┐
   │  Embedder    │           │  Extractor    │
   │ chunk → vec  │           │ chunk → triples│
   └─────┬───────┘           └──────┬───────┘
         ▼                          ▼
  ┌─────────────┐           ┌───────────────┐
  │  pgvector    │           │  Graph store   │
  │ (Postgres)   │           │ Postgres rows  │
  └─────┬───────┘           │ + NetworkX in   │
        │                    │   memory        │
        │                    └───────┬───────┘
        └────────────┬───────────────┘
                      ▼
            ┌──────────────────┐
   Query ─▶ │ Hybrid Retriever  │  vector search → seed entities → graph expansion
            │  + Agent loop     │  (decides: expand more? search again? answer?)
            └─────────┬─────────┘
                      ▼
              ┌─────────────────┐
              │ Answer Generator │  LLM call over assembled chunks + triples
              └─────────┬────────┘
                        ▼
                  Response + citations
```

**Stages, in order of data flow:**

1. **Ingestion** — load raw docs, chunk them (`ingestion/`).
2. **Embedding** — chunks → vectors, stored in pgvector (`embeddings/`).
3. **Extraction** — chunks → (entity, relation, entity) triples via LLM, stored in Postgres + hydrated into NetworkX (`extraction/`, `graph/`).
4. **Retrieval** — a query triggers vector search for seed chunks, maps them to graph entities, and expands N hops to pull in connected facts (`retrieval/`).
5. **Agent loop** — decides, per query, whether to search again, expand further, or answer now (`retrieval/agent.py`).
6. **Generation** — final LLM call over the assembled context, with citations (`generation/`).

## Tech stack

| Stage | Choice | Why |
|---|---|---|
| Storage | Postgres + pgvector, single instance | One database to operate, not two. |
| Graph engine | NetworkX, in-memory, hydrated from Postgres tables | Fits comfortably in memory at this scale; no Neo4j ops overhead. See FAQ. |
| Embeddings | Local — `sentence-transformers`, `BAAI/bge-small-en-v1.5` | Free, no rate limits, good enough at this scale. API budget goes to reasoning, not embeddings. |
| Extraction LLM | Claude, Haiku-tier, tool-use for structured output | Cheap/fast model for a high-volume, low-reasoning task. |
| Generation / agent LLM | Claude, Sonnet-tier, tool-use | Higher reasoning quality where it actually matters. |
| Orchestration | Hand-rolled ReAct loop (no LangGraph/LlamaIndex) | We're demonstrating that we can build control flow, not just call a framework. |
| Serving | FastAPI + Uvicorn | — |
| Deployment | Cloud Run (API) + Cloud SQL Postgres (with `vector` extension) | No AlloyDB/Neo4j footprint for a demo-scale graph. |
| Frontend | Next.js — **stretch only** | Nice for a demo recording; not core to the ML story. |

## Repository structure

```
loom/
├── app/
│   ├── main.py                  # FastAPI app instance, router registration, startup hooks
│   ├── config.py                # Settings via pydantic-settings (DB url, API keys, model names)
│   ├── db/
│   │   ├── models.py            # SQLAlchemy: Document, Chunk, Entity, Relationship, ChunkEntity
│   │   ├── session.py           # Engine + session factory
│   │   └── migrations/          # Alembic
│   ├── ingestion/
│   │   ├── loaders.py           # File → raw text (pdf/txt/html)
│   │   ├── chunker.py           # Raw text → Chunk objects
│   │   └── pipeline.py          # Orchestrates load → chunk → embed → extract → persist
│   ├── extraction/
│   │   ├── schemas.py           # Pydantic: Entity, Relationship, ExtractionResult
│   │   ├── prompts.py           # Extraction tool-use prompt/schema
│   │   └── extractor.py         # Calls LLM, validates, returns ExtractionResult
│   ├── embeddings/
│   │   └── embedder.py          # Wraps sentence-transformers, batch + single encode
│   ├── graph/
│   │   ├── store.py              # Postgres upsert/read for entities + relationships
│   │   ├── builder.py            # DB rows → nx.MultiDiGraph
│   │   └── traversal.py          # Seed selection, n-hop expansion, subgraph → text
│   ├── retrieval/
│   │   ├── vector_search.py      # pgvector cosine search SQL
│   │   ├── hybrid_retriever.py   # Combines vector search + graph expansion
│   │   └── agent.py              # ReAct controller: expand / search / answer
│   ├── generation/
│   │   ├── prompts.py            # Answer-generation prompt
│   │   └── generator.py          # Final LLM call, returns answer + citations
│   ├── api/
│   │   ├── routes_ingest.py      # POST /ingest
│   │   ├── routes_query.py       # POST /query
│   │   └── routes_graph.py       # GET /graph/{query_id} — debug/viz endpoint
│   └── eval/
│       ├── dataset.py            # Curated multi-hop QA test set
│       ├── metrics.py            # Retrieval recall@k, answer correctness
│       └── run_eval.py           # Runs pipeline over eval set, prints report
├── scripts/seed_corpus.py        # Fetch/prepare sample corpus
├── tests/
└── frontend/                     # stretch
```

## Getting started

**Prerequisites:** Python 3.11+, Docker, an Anthropic API key. GCP project only needed for deployment (Phase 5).

```bash
# 1. Clone & install
git clone <repo-url> loom && cd loom
pip install -r requirements.txt   # or: poetry install

# 2. Local Postgres with pgvector
docker compose up -d

# 3. Configure environment
cp .env.example .env
# fill in: DATABASE_URL, ANTHROPIC_API_KEY, EMBEDDING_MODEL

# 4. Run migrations
alembic upgrade head

# 5. Seed a sample corpus
python scripts/seed_corpus.py

# 6. Run the API
uvicorn app.main:app --reload

# 7. Try a query
curl -X POST localhost:8000/query -H "Content-Type: application/json" \
  -d '{"question": "..."}'

# 8. Run the eval harness
python -m app.eval.run_eval
```

## Build plan & ticket tracking

Work is broken into tickets, tracked as GitHub Issues in this repo, titled `[GRAG-#] Title`. Each issue carries a Description, Acceptance Criteria, Dependencies, and an Effort estimate (**S** ≈ 0.5 day, **M** ≈ 1 day, **L** ≈ 1.5–2 days). **Respect the dependency order** — a ticket's "Dependencies" field lists what has to land first; don't start GRAG-14 before GRAG-7 and GRAG-13 are done, for example.

| Phase | Tickets | Unlocks |
|---|---|---|
| 0 — Foundations | GRAG-1, GRAG-2 | Repo scaffolding, DB schema/migrations |
| 1 — Ingestion & vector pipeline | GRAG-3 → GRAG-7 | Documents in, chunked, embedded, vector-searchable |
| 2 — Knowledge graph extraction | GRAG-8 → GRAG-13 | Entities/relationships extracted, stored, traversable |
| 3 — Retrieval & generation | GRAG-14 → GRAG-16 | Hybrid retrieval, agent loop, answer generation |
| 4 — API & serving | GRAG-17, GRAG-18 | `/ingest` and `/query` endpoints |
| 5 — Data, eval & deploy | GRAG-19 → GRAG-22 | Real corpus, eval results, Cloud Run deployment, this README |
| 6 — Stretch | GRAG-23 → GRAG-27 | Frontend, graph viz, observability, chunking/entity-resolution upgrades |

Core path (Phases 0–5) is ~14–18 days of effort. Stretch tickets are explicitly optional — cut them first if you're behind schedule, in the order they're numbered.

## Evaluation & definition of done

The project's actual thesis — hybrid retrieval beats vector-only on multi-hop questions — has to be measured, not assumed. `app/eval/run_eval.py` runs both retrieval modes against a hand-curated multi-hop QA set (GRAG-19) and reports:

- **Recall@k** — did retrieval surface the chunks/entities actually needed to answer?
- **Answer correctness** — exact/fuzzy match or LLM-as-judge against gold answers.

**Definition of done for the core build:** hybrid retrieval measurably outperforms vector-only retrieval on the multi-hop subset of the eval set. If it doesn't, the first thing to check is corpus connectivity (GRAG-19) — a weakly-connected corpus makes graph traversal look pointless regardless of how correct the implementation is.

## Design decisions & FAQ

**Why NetworkX instead of Neo4j?**
At this scale (dozens to low-hundreds of docs) the whole graph fits in memory. NetworkX gives Python-native traversal with zero extra infrastructure. Neo4j is the right call at real scale, but it's a second database to deploy and operate for no scale-driven reason here. Nodes/edges persist as plain Postgres tables; the in-memory graph is rebuilt from them (`graph/builder.py`).

**Why local embeddings instead of an embedding API?**
Open models (bge-small) are competitive at this scale, free, and don't rate-limit ingestion. API budget is reserved for the two places it buys real quality: extraction and generation/agent reasoning.

**Why a hand-rolled ReAct loop instead of LangGraph or LlamaIndex?**
Building the control flow ourselves is the stronger signal for the "agentic AI" part of this project. It costs roughly a day more than wiring up a framework — that's the trade we're making on purpose.

**Why Haiku for extraction but Sonnet for generation/the agent?**
Extraction is high-volume and low-reasoning (pull triples out of a chunk) — a cheap, fast model is fine. Generation and the agent's step-by-step decisions need more reasoning quality, so they get the better model.

**Why fixed-size chunking instead of semantic chunking?**
Fixed-size with overlap (~300–500 tokens, ~15% overlap) is simple and fast to ship. Semantic/recursive chunking is a real improvement but it's an optimization — see GRAG-26 if there's time left.

**How good is entity resolution, really?**
Deliberately naive for v1: normalized-string dedup (lowercase + strip). It will under-merge aliases ("OpenAI" vs "Open AI"). This is a known, documented gap, not a bug — see GRAG-27 for the embedding-based upgrade if it becomes worth the time.

**Why does the corpus matter so much?**
The whole premise only demonstrates value if entities actually connect across documents. An unrelated pile of PDFs will make graph traversal look like dead weight next to plain vector search, because there's nothing to traverse. GRAG-19 exists specifically to guard against this.

## Picking up a ticket

1. Check the issue's **Dependencies** field — don't start if a dependency isn't merged yet.
2. Treat the **Acceptance Criteria** as a literal checklist; a ticket isn't done until all of them pass.
3. If something in the architecture or trade-offs isn't clear, check [Design decisions & FAQ](#design-decisions--faq) before asking — most "why is this built this way" questions are answered there.
4. If you hit a design question that *isn't* covered above, that's worth raising — it probably means the FAQ needs a new entry.

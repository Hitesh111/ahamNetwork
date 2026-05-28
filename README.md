# ahamNetwork — Evolutionary Gossip Engine

Population-based cognitive architecture where intelligence emerges from
interacting populations of AI micro-agents.

```bash
# quick start (local mutations only, no LLM needed)
pip install httpx pyyaml
python3 -m gossip_engine.main --domain domains/palindrome.py --rounds 50

# interactive shell
python3 -m gossip_engine.main --domain domains/palindrome.py --interactive

# structured problem studio
python3 -m gossip_engine.main --interactive
python3 -m gossip_engine.main --studio

# with an LLM
export GOSSIP_LLM_PROVIDER=openai
export GOSSIP_OPENAI_KEY=sk-...
python3 -m gossip_engine.main --domain domains/palindrome.py --rounds 100
```

**Status**: Phase 0–2 MVP complete.
- `--interactive` with no `--domain` launches the structured problem studio.
- The studio forces a schema: title, statement, input/output kinds, examples, constraints, and optional retrieval sources.
- Retrieval sources can be local files, URLs, or web search queries, which are folded into the generated domain as RAG context.
- [PLAN.md](./PLAN.md) — roadmap
- [IMPLEMENTATION.md](./IMPLEMENTATION.md) — architecture
- [MEMORY_ARCHITECTURE.md](./MEMORY_ARCHITECTURE.md) — memory substrate design

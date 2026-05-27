# ahamNetwork — Evolutionary Gossip Engine

Population-based cognitive architecture where intelligence emerges from
interacting populations of AI micro-agents.

```bash
# quick start (local mutations only, no LLM needed)
pip install httpx pyyaml
python3 -m gossip_engine.main --domain domains/palindrome.py --rounds 50

# with an LLM
export GOSSIP_LLM_PROVIDER=openai
export GOSSIP_OPENAI_KEY=sk-...
python3 -m gossip_engine.main --domain domains/palindrome.py --rounds 100
```

**Status**: Phase 0–1 MVP complete.
- [PLAN.md](./PLAN.md) — roadmap
- [IMPLEMENTATION.md](./IMPLEMENTATION.md) — architecture
- [MEMORY_ARCHITECTURE.md](./MEMORY_ARCHITECTURE.md) — memory substrate design

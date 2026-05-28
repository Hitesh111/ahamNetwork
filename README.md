# ahamNetwork — Evolutionary Gossip Engine

Population-based cognitive architecture where intelligence emerges from
interacting populations of AI micro-agents.

## Quick Start

```bash
# install deps
pip install httpx pyyaml

# run a domain with AST-only mutations (no LLM needed)
python3 -m gossip_engine.main --domain domains/palindrome.py --rounds 50
```

## Step-by-Step Usage

### 1. Pick a Domain

Domains define the problem to solve. Built-in domains:

| File | Problem | Solution pattern |
|------|---------|-----------------|
| `domains/palindrome.py` | Check if string is palindrome | `x == x[::-1]` |
| `domains/fizzbuzz.py` | Classic FizzBuzz | modulo + string concat |
| `domains/is_even.py` | Check if number is even | modulo 2 |
| `domains/is_prime.py` | Check if number is prime | divisor loop |
| `domains/valid_parens.py` | Validate balanced brackets | stack-based |
| `domains/max_of_two.py` | Return max of list of 2 nums | comparison |

Each domain provides test cases, a fitness function, and a `solve()`
signature that agents evolve towards.

### 2. Run Without an LLM (AST-Only Mode)

```bash
python3 -m gossip_engine.main --domain domains/fizzbuzz.py --rounds 100
```

The mutation engine uses 12 AST operators (injections, guard insertion,
boolean flips, operator swaps, etc.) to evolve solutions. This is fast
but limited to simple pattern-matching problems.

### 3. Run With Ollama (Local LLM)

```bash
# install ollama and pull a model
ollama pull deepseek-coder:1.3b

# run with the LLM
GOSSIP_LLM_PROVIDER=local \
GOSSIP_LOCAL_MODEL=deepseek-coder:1.3b \
python3 -m gossip_engine.main --domain domains/valid_parens.py --rounds 200
```

Recommended model: `deepseek-coder:1.3b` (7-13s per call, solves
palindrome + fizzbuzz in round 1, struggles with algorithmic reasoning).

### 4. Run With OpenAI

```bash
export GOSSIP_LLM_PROVIDER=openai
export GOSSIP_OPENAI_KEY=sk-...
python3 -m gossip_engine.main --domain domains/valid_parens.py --rounds 100
```

### 5. Use the Shell Script

```bash
# run with defaults (AST-only)
./run.sh domains/fizzbuzz.py --rounds 100

# run with Ollama
./run.sh domains/palindrome.py --rounds 200 --provider local --model deepseek-coder:1.3b

# run AST-only explicitly
./run.sh domains/is_prime.py --rounds 50 --no-llm

# see all options
./run.sh --help
```

### 6. Interactive Shell

```bash
# interactive REPL with a domain
python3 -m gossip_engine.main --domain domains/palindrome.py --interactive

# problem studio (create custom domains interactively)
python3 -m gossip_engine.main --interactive
```

### 7. Create a Custom Domain

Create a `.py` file with:

```python
# domains/your_problem.py

PROMPT = "Describe what solve() should do in plain English."

TEST_CASES = [
    (input_value, expected_output),
    (input_value, expected_output),
    # ...
]

# Optional: behavioral descriptor for MAP-Elites archive
def behavioral_descriptor(code: str) -> tuple[float, float]:
    return (min(len(code), 500) / 500.0, 0.5)

# Optional: solved detector
def is_solved(code: str, trust: float) -> bool:
    return trust > 0.9 and fitness(code)[0]

# This is the test harness injected into the sandbox
test_code = \"\"\"
if solve(input) != expected: raise AssertionError()
# ...
\"\"\"
```

## Understanding the Output

During a run, the log shows per-round metrics:

```
Round   10 | pop=  4 | archive=  5 | best=0.850 | occupancy=0.25 | fail=0.30| cb=1| ws=3
```

| Metric | Meaning |
|--------|---------|
| `pop` | Current agent population size |
| `archive` | Number of filled MAP-Elites archive cells |
| `best` | Highest trust score in the archive |
| `occupancy` | Fraction of archive cells that are filled |
| `fail` | Failure rate (failed evaluations / total) |
| `cb` | Codebook entries (L4 shared concept vocabulary) |
| `ws` | Global workspace slots filled (L5 emergent consensus) |

Additional activity logs:

```
L5 promoted 3 artifacts (attention: 0.450)  — workspace cycle
Codebook evolution: {'merged': 1}            — codebook maintenance
Critic: focus=explore_new_niches div=0.27... — step-back reasoning
Problem solved at round 5!                   — domain solved
```

## Architecture Overview

```
                    ┌─────────────────────────┐
                    │  L5 Global Workspace     │  ← attention-weighted promotion
                    │  (7 slots, broadcast)   │
                    └──────────┬──────────────┘
                               │
    ┌──────────────┐    ┌──────┴───────┐    ┌──────────────┐
    │  L3 Lineage  │    │  Population   │    │  L2 Episodic │
    │  DAG (SQLite)│◄──►│  of Agents   │◄──►│  Artifact    │
    │  (ancestry)  │    │  (swarm)     │    │  Store       │
    └──────────────┘    └──────┬───────┘    └──────────────┘
                               │
                    ┌──────────┴──────────────┐
                    │  L4 Codebook             │
                    │  (concept vocabulary)    │
                    └─────────────────────────┘
```

Each agent cycle: **mutate** → **evaluate** (sandbox) → **score** →
**archive** → **gossip** → **lineage record** → **codebook encode**.

Background processes:
- Population growth/shrink (every 5-10 rounds)
- L5 workspace promotion (every 5 rounds)
- L4 codebook evolution MINT/MERGE/SPLIT/RETIRE (every 20 rounds)
- L6 step-back critic analysis (every 15 rounds)

## Environment Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `GOSSIP_LLM_PROVIDER` | LLM backend | `local`, `openai`, `gemini` |
| `GOSSIP_LOCAL_MODEL` | Ollama model | `deepseek-coder:1.3b` |
| `GOSSIP_LOCAL_BASE_URL` | Ollama URL | `http://localhost:11434` |
| `GOSSIP_OPENAI_KEY` | OpenAI API key | `sk-...` |
| `GOSSIP_GEMINI_KEY` | Google API key | `...` |

## All CLI Flags

```
python3 -m gossip_engine.main [OPTIONS]

  --domain PATH     Domain .py file
  --rounds N        Number of evolutionary rounds (default: 100)
  --provider NAME   LLM provider override
  --model NAME      LLM model override
  --no-llm          Force AST-only mutations
  --parallel        Run agents in parallel
  --interactive     Launch interactive shell
  --studio          Launch problem studio
  --seed N          Random seed
  --log LEVEL       Log level (DEBUG/INFO/WARNING)

  -h, --help        Show help
```

## Memory Persistence

Checkpoints are saved to `checkpoints/` by default:

| File | Contents |
|------|----------|
| `artifacts.sqlite3` | L2 episodic store (all artifacts) |
| `lineage.sqlite3` | L3 lineage DAG |
| `codebook.sqlite3` | L4 codebook entries |
| `workspace.sqlite3` | L5 promotion history |
| `checkpoint.json` | Runtime state for resume |

The system resumes from where it left off when restarted with the same
checkpoint directory.

## Files

| File | Purpose |
|------|---------|
| `gossip_engine/agent/` | Agent model, factory, state machine |
| `gossip_engine/evolution/` | Mutation engine, recombination, MAP-Elites archive |
| `gossip_engine/gossip/` | Gossip protocol (fanout=3, rumor mill) |
| `gossip_engine/grounding/` | Sandbox, scorer, validator, execution cache |
| `gossip_engine/llm/` | LLM backends (Ollama, OpenAI, Gemini) |
| `gossip_engine/memory/` | L1-L5 memory layers |
| `gossip_engine/critic/` | Step-back reasoning critic |
| `gossip_engine/population/` | Population manager (growth/shrink) |
| `gossip_engine/orchestrator.py` | Main loop wiring all phases |
| `gossip_engine/config.py` | Configuration loading |
| `setup.sh` | Install deps and pull Ollama model |
| `run.sh` | Convenience runner |

## Project Status

- ✅ **Phase 1** — Population, sandbox, domains, config
- ✅ **Phase 2** — Gossip protocol, AST recombination, state machine
- ✅ **Phase 3** — Archive reconciliation, credit assignment
- ✅ **Phase 4** — L4 CodebookStore (concept vocabulary)
- ✅ **Phase 5** — L5 GlobalWorkspace (attention-weighted consensus)
- ✅ **Phase 6** — Step-back critic (dual-loop reasoning)
- ⬜ **Phase 7** — Fractal scaling (agents spawn sub-swarms)

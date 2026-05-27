SYSTEM PLAN — GOSSIP ENGINE
============================
Architecture & implementation roadmap | May 2026

Prerequisite: MEMORY_ARCHITECTURE.md defines the 5-layer memory
substrate this plan builds on.

PHILOSOPHY
----------
Build vertically, not horizontally. Each phase produces a working
(if minimal) system that can be exercised end-to-end. Only add
distribution, scale, or sophistication when the current phase
reveals why it's needed.

The plan is ordered by dependency, not by glory. Phase 1 is the
dullest and most important.

CRITICAL DESIGN PRINCIPLE: POPULATION EVOLVES WITH PROBLEM
-----------------------------------------------------------
Population size is NOT a config parameter. It is an evolved
property of the problem — just like the solutions themselves.
The system starts with a minimal viable population (2-3 agents)
and grows only when the problem demands it. Growth follows an
exponential trajectory (N → ~1.5-2N → ~1.5-2(1.5N)...) triggered
by measurable signals. Shrinkage happens when the problem is
solved or plateaus.

The exact starting number doesn't matter. What matters:
  - Start small enough that easy problems are solved cheaply
  - Grow multiplicatively when stuck, not additively
  - Let problem complexity determine the equilibrium size
  - The population curve itself becomes a diagnostic signal
    (steep curve = hard problem, flat curve = easy problem)

Fixed population sizes assume the designer knows complexity
upfront. That contradicts the evolutionary nature of the system.


USER INTERACTION MODEL
-----------------------
The system has two fundamentally different interaction modes
that map to different interfaces:

MODE 1 — PROBLEM DEFINITION (CLI / Python API)
  The user defines:
    - Task specification
    - Test harness / fitness function
    - Behavioral descriptor dimensions (for MAP-Elites)
    - Domain-specific sandbox rules

  This is inherently CODE. A web form would be painful and
  restrictive. The interface is a Python config module or
  YAML file that defines the problem domain, validation
  logic, and scoring function.

  Example:
    # domains/sort_design.py
    def fitness(code: str) -> tuple[float, list[float]]:
        score = run_tests(code)
        behavior = [time_complexity(code), space_complexity(code)]
        return (score, behavior)

MODE 2 — MONITORING & ANALYSIS (Web GUI, Phase 4+)
  Once running, the user wants to watch:
    - Population growth curve (diagnostic: steep = hard problem)
    - MAP-Elites archive heatmap
    - Lineage DAG (who evolved from whom)
    - Agent cognitive state distribution
    - Trust scores over generations

  This is VISUAL. CLI tables cannot compete with real-time
  graphs for understanding emergent behavior.

PHASED APPROACH
  Phase 1-3 (MVP): CLI only.
    Problem definition via Python config. Monitoring via
    structured logs + terminal charts (ASCII archive heatmap,
    lineage stats, population curve). Faster to build, and
    the hardest part is the evolutionary substrate, not the UI.

  Phase 4+ (Maturity): Web dashboard added.
    FastAPI backend reads the same checkpoint DB that the
    CLI writes. Streamlit or lightweight SPA for real-time
    lineage viz, archive browsing, agent inspection. The DB
    is the API — CLI and web are just readers.

  Key invariant: The system NEVER depends on the UI. The
  checkpoint files and DB are the public interface. CLI and
  web dashboard are interchangeable consumers. This keeps
  the evolutionary core decoupled from presentation.


LLM PROVIDER CONFIGURATION
----------------------------
Agents need LLM backends for mutation and reasoning. Users
bring their own API keys. No keys ship with the system.

Supported providers:
  - OpenAI  (GPT-4o, GPT-4o-mini, o3)
  - Google  (Gemini 1.5 Pro, Gemini 2.0 Flash)
  - DeepSeek (DeepSeek-V3, DeepSeek-R1)
  - xAI     (Grok-2, Grok-3)
  - Local   (Ollama / LM Studio — no key needed)

Configuration mechanism:
  Two methods, both optional — the system validates at startup:

  Method A — .env file (recommended for CLI):
    GOSSIP_LLM_PROVIDER=openai
    GOSSIP_OPENAI_KEY=sk-...
    GOSSIP_OPENAI_MODEL=gpt-4o-mini
    GOSSIP_GEMINI_KEY=AIza...
    GOSSIP_DEEPSEEK_KEY=sk-...
    GOSSIP_GROK_KEY=xai-...
    GOSSIP_LOCAL_BASE_URL=http://localhost:11434/v1

  Method B — config file (YAML/TOML):
    llm:
      provider: openai
      openai:
        key: sk-...
        model: gpt-4o-mini
      gemini:
        key: AIza...
        model: gemini-2.0-flash

Validation at startup:
  - Check that at least one provider has a key configured
  - Make a test inference call (cheap, short prompt)
  - If test fails: print error with the exact provider that failed
  - If no valid provider: exit immediately (don't waste compute)

Multi-provider fallback:
  Optional. If enabled and the primary provider returns a 5xx
  error, fall through to the next configured provider. Failures
  are logged per-agent for debugging. This prevents a single
  API outage from killing the entire evolutionary run.

Local models:
  The system prefers local models when available (no cost, no
  latency). If GOSSIP_LOCAL_BASE_URL is set, it becomes the
  default provider regardless of GOSSIP_LLM_PROVIDER. Remote
  providers are fallbacks. This lets users iterate cheaply
  during development and switch to stronger models for
  production runs.


PHASE 0 — MEMORY SUBSTRATE (DONE)
----------------------------------
5-layer memory architecture defined in MEMORY_ARCHITECTURE.md.
Implementation is deferred to phases below — each phase
will implement the layers it needs as it goes.

L1: Agent-local (need from Phase 1)
L2: Episodic store (need from Phase 3)
L3: Lineage DAG (need from Phase 3)
L4: Codebook (need from Phase 4)
L5: Global workspace (need from Phase 5)


PHASE 1 — SINGLE-PROCESS EVOLUTIONARY SUBSTRATE
-------------------------------------------------
Goal: Prove the core hypothesis — an evolving population of LLM-
augmented agents produces better solutions than static prompting.

What we build:
  - Agent model (internal structure)
  - Population manager (spawn, cull, tick)
  - Sandboxed reality grounding (code execution)
  - MAP-Elites archive (selection)

Components:

1a. AGENT MODEL
  Each agent is a struct with:
    - LLM backend handle (API client or local model)
    - Cognitive state (SATTVA/RAJAS/TAMAS — see Phase 2 for full
      dynamics; start with random assignment or fixed)
    - L1 working memory (dict with TTL)
    - Genome: the current artifact/solution the agent holds
    - Trust score (initialized to 0.5)
    - Niche assignment (MAP-Eliles grid cell)
    - Agent ID (UUID)

  Agent lifecycle:
    1. Receive input (task description or problem instance)
    2. Mutate genome based on cognitive state
    3. Execute mutated genome in sandbox
    4. Receive validation results
    5. Update trust score based on results
    6. Contribute to MAP-Elites archive
    7. Optionally produce output

  NOT yet implemented:
    - Gossip (Phase 2)
    - Recombination (Phase 2)
    - Codebook (Phase 4)
    - Recurrent thinking cycles (Phase 2)

1b. REALITY GROUNDING — SANDBOX
  Subprocess-based Python execution.
  - Restricted globals (no imports, no filesystem, no network)
  - Timeout per execution (configurable, default 5s)
  - Stdout capture + return code
  - Preloaded test harness per problem domain
  - Result: (passed: bool, output: str, error: str | None, runtime_ms: int)

  Risk: sandboxing is a constant tax. Every execution domain needs
  a bespoke validator. The plan only works for domains with cheap,
  automated ground truth (code generation, math, games, constraint
  satisfaction, circuit design, etc.)

1c. POPULATION MANAGER (SINGLE-PROCESS)
  Simple round-robin loop:
    - For each agent in population:
        - Tick agent (mutate -> execute -> evaluate)
        - Insert result into MAP-Elites archive
    - After N ticks: check growth/shrink signals
    - After M ticks: cull weakest agents from oversubscribed niches

  INITIAL POPULATION: 2-3 agents. Minimal viable size. The
  population itself evolves from here — its growth curve is an
  emergent property of problem difficulty.

  Growth signals (check every N=10 rounds):
    - STAGNATION: no archive improvement in 10 rounds
    - HIGH FAILURE: >50% of artifacts invalid in a window
    - SHALLOW LINEAGE: best artifacts <5 mutations from seed
      (means search space barely explored)
    - ARCHIVE SATURATION: all niches filled but max trust < 0.5

  Growth formula (multiplicative, not additive):
    next = floor(current * (1.5 + random(0, 0.5)))
    This gives ~1.5x-2x growth per signal.
    Example trajectory: 2 → 4 → 8 → 16 → 32 → 64 → 128...
    The multiplier varies so growth isn't perfectly predictable.

  Shrink signals (check every M=20 rounds):
    - PLATEAU: no archive improvement for 20+ rounds → trim 20%
    - SOLVED: target fitness achieved → cull to 2-3 verification agents
    - NICHE COLLAPSE: multiple agents in same niche, identical scores
      → merge agents, cull extras

  Key constraint: spawn lazily. Don't add agents unless a growth
  signal fires. Small populations on easy problems, large
  populations on hard problems, automatically.

  The population trajectory itself becomes a useful signal:
    - Steep exponential curve → problem is hard, search space vast
    - Flat line → problem is easy or solved
    - Step function (grow, plateau, grow, plateau) → problem has
      multiple difficulty regimes, system is climbing them

1d. MAP-ELITES ARCHIVE
  Grid over behavioral dimensions (problem-specific).
  - Each cell stores: (artifact, trust_score, agent_id, age)
  - Archive operations:
    - insert(artifact, score, niche_coords) -> replaces if score
      is higher than current occupant
    - get_random_cell() -> for selection
    - get_best_cell(niche_coords) -> for exploitation
    - get_empty_cells() -> for exploration
    - novelty_score(artifact) -> distance to nearest occupied cell

  Selection strategy:
    - 70% from archive (tournament: pick random cell, then highest
      trust score within cell)
    - 20% random mutation of archive elites
    - 10% immigrant injection (randomly generated genomes)

Output: Verified that the evolutionary loop produces artifacts
with increasing trust scores over generations.

Risks:
  - LLM cost per mutation ($0.01-0.10 per tick × agents × rounds.
    Starts cheap at 3-8 agents, grows only when needed.
    Worst case: 100 agents × 1000 rounds = $500-1000)
  - Sandbox too slow for meaningful generation counts
  - MAP-Elites dimensions poorly chosen → archive doesn't reflect
    meaningful diversity

  Gate question: Do mutated solutions improve over the population
  baseline, or does mutation mostly produce garbage?

Deliverable: Working script that evolves code solutions for a
simple problem domain (e.g., string manipulation, numeric
optimization) and logs trust scores over generations.

Estimated complexity: 3-5 days for a solo engineer.


PHASE 2 — GOSSIP + RECOMBINATION + COGNITIVE STATES
------------------------------------------------------
Goal: Add decentralized communication and between-agent evolution.

Components:

2a. GOSSIP PROTOCOL (IN-PROCESS)
  No network yet. Agents are in the same process, but the protocol
  is designed as if they weren't.

  Each agent maintains:
    - Neighbor table: list of peer IDs, dynamically updated
      (start: random subset, update: successful collaborators get
      higher weight)
    - Rumor mill: priority queue of (artifact, trust_score,
      origin_agent, hop_count, timestamp)
    - Outgoing message queue

  Gossip round per tick:
    1. Select best item from rumor mill (highest trust × novelty)
    2. Serialize: (artifact_code, lineage_hash, trust_score,
       niche_coords, cognitive_state)
    3. Send to k=3 random neighbors (or highest-weight neighbors
       with 70/30 exploration-exploitation split)
    4. Receive from neighbors, merge into rumor mill (dedup by
       artifact hash)

  Implementation trick: serialize artifact as string + codebook
  indices (even though codebook doesn't exist yet, reserve the
  field). For Phase 2, just use embeddings from a frozen sentence
  transformer.

2b. RECOMBINATION
  Crossover at structural boundaries, NOT arbitrary text.

  Implementation strategy:
    - Parse genomes into AST (Python's `ast` module)
    - Define legal recombination points: function boundaries,
      class boundaries, loop bodies, conditional branches
    - Recombination:
      1. Pick two parent artifacts from agent's local archive or
         from different MAP-Elites cells (diversity constraint)
      2. Parse both to AST
      3. Identify compatible recombination points (same AST node
         type at both parents)
      4. Swap subtrees at a random compatible point
      5. Unparse to source code
      6. Validate by parsing again (syntax check)
      7. Execute in sandbox

  Recombination is triggered probabilistically. RAJAS agents
  recombine more (30% chance per tick). SATTVA agents rarely
  recombine (5%).

2c. COGNITIVE STATE MACHINE (GUNAS)
  Three states with transition rules:

  SATTVA (stable, integrative):
    - Mutation rate: 0.05
    - Recombination rate: 0.05
    - Message emission: low (polishing own work)
    - Trust threshold for accepting foreign artifacts: high
    - Default for high-trust agents

  RAJAS (exploratory, aggressive):
    - Mutation rate: 0.30
    - Recombination rate: 0.30
    - Message emission: high (broadcast everything)
    - Trust threshold: low (try anything)
    - Default for low-trust agents trying to improve

  TAMAS (failure/recovery):
    - Triggered when trust score drops below 0.2
    - Agent may: reset genome to random, self-mutate heavily,
      isolate (stop gossipping), or request culling
    - After TAMAS recovery period: transition to RAJAS

  Transitions:
    - SATTVA -> RAJAS: stagnation (no trust improvement in N ticks)
    - RAJAS -> SATTVA: sustained success (trust > 0.8 for M ticks)
    - Any -> TAMAS: trust < 0.2 or catastrophic validation failure
    - TAMAS -> RAJAS: after recovery period (5-10 ticks)

  The state machine is the system's meta-parameter for balancing
  explore vs. exploit at the agent level.

Risks:
  - Gossip without trust-weighted filtering → memetic pollution
  - AST recombination produces mostly invalid or worse code
  - Cognitive state transitions oscillate too rapidly or get stuck

Deliverable: System where agents exchange solutions and
recombine them, with observable state transitions. Demonstrate
that recombined solutions sometimes outperform either parent.

Estimated complexity: 5-7 days.


PHASE 3 — LINEAGE + EPISODIC MEMORY INTEGRATION
-------------------------------------------------
Goal: Implement L2 (episodic store) and L3 (lineage DAG) from
the memory architecture. Without this, evolution has no history.

3a. EPISODIC STORE
  SQLite-based artifact repository (single-process).
  Each artifact row:
    - content_hash (SHA256 of code)
    - agent_id
    - trust_score (at insertion)
    - validation_results (JSON blob)
    - niche_coords (JSON array)
    - timestamp
    - parent_hash (optional, for lineage linking)
  Vector index via sqlite-vec or simple in-memory HNSW.

3b. LINEAGE DAG
  SQLite adjacency table:
    node_id | artifact_hash | parent_ids | mutation_type |
    agent_id | trust_score | niche_coords | timestamp

  Queries:
    - get_ancestors(hash, depth) — recursive CTE
    - get_descendants(hash, depth) — recursive CTE
    - get_lineage_stats(hash) — depth, branches, avg trust

3c. ARCHIVE RECONCILIATION
  MAP-Elites archive persists to SQLite. On restart, archive is
  reloaded. Selection bases on historical lineage data, not just
  current snapshot.

3d. CREDIT ASSIGNMENT (BASIC)
  When a high-trust artifact is produced, propagate trust bonus
  back through its lineage:
    - Each ancestor gets +0.05 trust (capped at 0.95)
    - Lineage depth increases mean higher bonus (deeper lineages
      have more accumulated evidence)
  This is the Hebbian learning rule from the agent-as-neuron model.

Deliverable: System with persistent evolutionary memory.
Lineages can be traced. Trust propagates through ancestry.

Estimated complexity: 2-3 days.


PHASE 4 — CODEBOOK (SHARED CONCEPT VOCABULARY)
------------------------------------------------
Goal: Implement L4. Agents communicate via shared concept
indices instead of raw text.

4a. CODEBOOK SERVER
  In-process Raft-like replicated log (or single-leader for MVP).
  Codebook entries:
    - index (auto-incrementing integer)
    - centroid_embedding (768-dim float vector)
    - human_label (optional debug string)
    - parent_index (for lineage tracking of concepts)
    - birth_timestamp
    - usage_count

4b. ENCODE / DECODE
  encode: artifact embedding -> nearest codebook index (cosine
  similarity or L2). If distance > threshold, trigger MINT.
  decode: codebook index -> centroid embedding.

4c. CODEBOOK EVOLUTION
  Background process runs every N gossip rounds:
    - Cluster all artifact embeddings that entered the archive
      since last evolution round
    - For each cluster: find nearest codebook entry
    - If cluster-to-codebook distance > threshold: MINT new code
    - If two codes are co-activated >90%: MERGE them
    - If a code's cluster purity < threshold: SPLIT
    - Codes with usage_count == 0 for 100 rounds: RETIRE

4d. GOSSIP UPGRADE
  Gossip messages now transmit codebook index sequences instead of
  raw text. Artifact bodies transmitted separately (once per
  artifact, cached by hash).

Deliverable: Agents communicating via shared concept vocabulary.
Codebook shows emergent structure (concepts cluster in meaningful
ways). Gossip bandwidth reduced.

Risks:
  - Codebook doesn't converge to meaningful concepts
  - MINT creates too many entries (noise)
  - encode/decode loss destroys information needed for
    recombination

Estimated complexity: 5-7 days.


PHASE 5 — GLOBAL WORKSPACE + POPULATION SELF-MANAGEMENT
----------------------------------------------------------
Goal: Implement L5 and dynamic population management.

5a. GLOBAL WORKSPACE
  In-process event bus with subscriptions.
  Activation thresholds:
    - Novelty > 3σ from niche mean
    - Trust > 1.5× previous niche max
    - Contradiction between high-trust artifacts
  Broadcast: all agents receive event, each decides relevance.

5b. DYNAMIC POPULATION (EVOLVED SIZE)
  Population size is a feedback-driven emergent property, not a
  config knob. The population manager monitors four signals and
  applies exponential backoff growth or proportional shrinkage.

  Growth signals (checked every 10 rounds):
    - STAGNATION: no archive improvement in 10 rounds → problem
      is harder than current population can crack → grow
    - HIGH FAILURE RATE: >50% of artifacts produce invalid sandbox
      results → need more diversity to find correct approaches → grow
    - SHALLOW LINEAGE: best artifacts in archive are <5 mutations
      from initial seed → search space barely scratched → grow
    - ARCHIVE SATURATION: all MAP-Elites cells occupied but max
      trust across all cells < 0.5 → stuck in local optimum,
      need more agents to escape → grow

  Growth formula (multiplicative):
    next = floor(current * (1.5 + random(0, 0.5)))
    Creates ~1.5x-2x growth per signal.
    Example trajectory: 2 → 4 → 8 → 16 → 32 → 64 → 128...
    New agents start in RAJAS (exploration) state by default.

  Shrink signals:
    - PLATEAU: no improvement for 20+ rounds → cull lowest-trust
      20% of agents. Don't grow. Let the population contract
      until improvement resumes.
    - PROBLEM SOLVED: target fitness achieved → cull to minimal
      verification population (2-3 agents in SATTVA state).
      Preserve the archive and lineage — the solution is in
      the archive, not in the agents.
    - NICHE COLLAPSE: multiple agents producing identical scores
      in the same niche → merge their lineages, cull extras.
    - COMPUTE PRESSURE: total sandbox execution time exceeds
      budget → cull lowest-trust across all niches.

  No hard min/max. The system should be able to run 2 agents on
  "sort 3 numbers" and 500 agents on "design a novel hash
  function" without reconfiguration.

5c. ADVERSARIAL MEMETICS DEFENSE
  Mechanisms to prevent "ideas that spread" from outcompeting
  "ideas that are true":
    - Trust discount for artifacts that arrive via long gossip
      chains (each hop reduces weight by 0.1)
    - Grounding requirement: artifacts must be validated by at
      least 2 agents before trust score counts
    - Contradiction detection: if two high-trust artifacts in the
      same niche conflict, promote to global workspace for
      arbitration
    - Lineage penalty: agents that consistently produce artifacts
      descendant from low-trust lineages have their own trust
      score decay faster

Deliverable: Self-regulating population that maintains diversity
under evolutionary pressure. Global workspace catches anomalies.
Memetic defenses prevent truth-from-spreadability collapse.

Risks:
  - Global workspace becomes too noisy (false positives)
  - Population management parameters are fragile
  - Memetic defenses are either too weak (nonsense spreads) or
    too strong (innovation suppressed)

Estimated complexity: 3-5 days.


PHASE 6 — DISTRIBUTED RUNTIME
-------------------------------
Goal: Multiple machines. This is where the distributed systems
problems actually appear.

6a. NETWORK LAYER
  gRPC or NATS-based agent communication.
  Each agent runs as a lightweight process binding to a gossip
  port. Agent discovery via rendezvous hash ring (consistent
  hashing over agent IDs).

6b. DISTRIBUTED GOSSIP
  Epidemic broadcast (push-gossip) with fanout k=3.
  Anti-entropy: periodic pull from random peers to detect
  missed messages.
  Failure detection: phi-accrual (Cassandra-style).

6c. DISTRIBUTED LINEAGE DAG
  CRDT-based DAG merge on partition recovery.
  Each node stores its subgraph; queries that cross node
  boundaries are forwarded (gossip-mediated retrieval from
  the memory architecture spec).

6d. DISTRIBUTED CODEBOOK
  Raft consensus group for codebook writes.
  Read replicas on each node for fast local access.

6e. DISTRIBUTED SANDBOX
  Sandbox workers on separate machines, job queue (NATS or
  RabbitMQ) for artifact execution. Workers register their
  availability; agents submit execution tasks.

Deliverable: Multi-node system. Agents on different machines
discover each other, gossip, and evolve together.

Risks:
  - Network latency breaks the gossip cycle timing assumptions
  - CRDT merge conflicts in lineage DAG produce inconsistent
    evolutionary histories
  - Sandbox workers become the bottleneck (all evolution depends
    on reality grounding)

Estimated complexity: 2-4 weeks.


PHASE 7 — ADVANCED FEATURES
-----------------------------
Non-essential but valuable:

7a. AGENT-AS-NEURON RECURRENT ARCHITECTURE
  Agents run for K timesteps before readout, exchanging
  activation vectors (not just artifacts). This is the full
  neural connectivity model from the original vision.

7b. CONTINUOUS CODEBOOK EMBEDDINGS
  Replace discrete codebook indices with differentiable
  communication (DIAL-style). Only useful if the system is
  trained end-to-end, not just evolved.

7c. PARADIGM SHIFT DETECTION
  Statistical monitoring of the codebook evolution rate.
  A burst of MINT operations signals a paradigm shift.
  System can detect when it's in a period of conceptual
  revolution vs. normal science (Kuhnian dynamics).

7d. MULTI-DOMAIN TRANSFER
  Run the gossip engine on two unrelated problem domains
  simultaneously. Monitor for cross-domain analogies
  (agents recombining solutions from different domains).
  This is the Dunbar-style breakthrough mechanism.

7e. INTERACTIVE VISUALIZATION
  Real-time lineage graph, codebook evolution, MAP-Elites
  archive heatmap, agent state distribution. Essential for
  debugging but not for the core hypothesis.

Estimated complexity: per feature, 1-2 weeks.


DEPENDENCY GRAPH
-----------------
Phase 1 ──> Phase 2 ──> Phase 3 ──> Phase 4 ──> Phase 5 ──> Phase 6
  │                        │                                      │
  └────────────────────────┴──────────────────────────────────────┘
                                   │
                                   v
                              Phase 7

Phases 1-3 form the critical path for the MVP hypothesis test.
Phase 4 (codebook) can be deferred if Phase 2 gossip shows that
plain-text + embedding communication is sufficient for useful
recombination.

Phase 6 (distributed) should only begin AFTER Phases 1-5 have
demonstrated that the substrate produces genuinely useful
emergent behavior in a single process. Premature distribution
would obscure whether the core idea works while paying all the
complexity cost.


OPEN QUESTIONS (TO DECIDE BEFORE PHASE 1)
-------------------------------------------
1. LLM provider / cost model
   - OpenAI API: $0.01-0.10 per mutation call
   - Local model (via Ollama/LM Studio): slower but free
   - Recommendation: start with a cheap model (GPT-4o-mini or
     Llama 3 8B via Ollama) for Phase 1, upgrade if the
     hypothesis holds

2. Problem domain for Phase 1
   - Code generation (string manipulation, sorting, etc.)
   - Mathematical optimization
   - Constraint satisfaction (puzzles, scheduling)
   - Recommendation: code generation because:
     a) AST-based recombination is natural
     b) Sandbox implementation is straightforward
     c) Prior art exists (FunSearch) for comparison

3. How much structure do agents share vs. own?
   - Do all agents share the same system prompt? (probably yes
     for Phase 1, differentiated by cognitive state in Phase 2)
   - Do agents have persistent memory between ticks? (yes — L1)

4. What constitutes a "generation"?
   - Every agent ticks once per generation
   - Or agents tick independently and generation is a global
     counter incremented after all agents have ticked?
   - Recommendation: independent ticking with a global round
     counter for logging/analysis

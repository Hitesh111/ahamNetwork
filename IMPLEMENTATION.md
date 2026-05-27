IMPLEMENTATION — GOSSIP ENGINE
===============================
System architecture, data flow, and component interaction | May 2026


TABLE OF CONTENTS
-----------------
1. System-Level Architecture Graph
2. Agent Internals
3. The Main Loop (Tick Cycle)
4. Data Flow Through the System
5. Component Interaction Matrix
6. File/Module Map
7. Configuration
8. Entry Point Flow


1. SYSTEM-LEVEL ARCHITECTURE GRAPH
------------------------------------

The system has 9 major subsystems. Below shows how they connect.
Arrows indicate data flow direction. Dotted lines indicate
asynchronous/eventual communication.

                              +------------------+
                              |   PROBLEM DOMAIN |
                              |   (task spec,    |
                              |    test harness, |
                              |    fitness func) |
                              +--------+---------+
                                       ^
                                       | feedback: complexity signals
                                       | (stagnation, failure rate,
                                       |  shallow lineage, archive sat)
                                       |
     +------------------+     +--------+---------+     +------------------+
     |   LLM BACKEND    |<--->|     ORCHESTRATOR  |<--->|   CONFIG / CLI   |
     |   (API / local)  |     |   (main loop)     |     |   (entry point)  |
     +------------------+     +--------+---------+     +------------------+
                                       |
                  +--------------------+--------------------+
                  |                    |                    |
                  v                    v                    v
     +------------------+   +------------------+   +------------------+
     |   AGENT POOL     |   | POPULATION MGR   |   | GLOBAL WORKSPACE |
      |   (starts at 2-3,|   | (monitors growth |   | (anomaly/break-  |
      |    grows on      |<---|  signals, spawns |   |  through events)  |
      |    demand,       |   |  multiplicatively,|   +------------------+
     |    shrinks on    |   |  culls on        |
     |    plateau/solve)|   |  plateau/solve)  |
     +------------------+   +------------------+
        ||||||| (gossip, not hierarchical)
        |||||||
     +------------------+
     |   GOSSIP LAYER   |
     |   (neighbor mgmt,|
     |    rumor mill,   |
     |    message relay)|
     +------------------+
                  |
                  v
     +-------------------------------+
     |        EVOLUTION ENGINE       |
     |  +---------+  +------------+  |
     |  | MAP-    |  | RECOMBINA- |  |
     |  | ELITES  |  | TION ENGINE|  |
     |  | ARCHIVE |  | (AST       |  |
     |  | (niche  |  |  crossover)|  |
     |  |  grid)  |  +------------+  |
     |  +---------+                  |
     |  +---------+  +------------+  |
     |  | MUTATION|  | LINEAGE    |  |
     |  | ENGINE  |  | ANALYZER   |  |
     |  | (7 types|  | (credit    |  |
     |  |  of     |  |  assign,   |  |
     |  |  mutate)|  |  pattern   |  |
     |  +---------+  |  mining)   |  |
     |               +------------+  |
     +-------------------------------+
                  |
                  v
     +-------------------------------+
     |         MEMORY LAYER          |
     |  +---------+  +------------+  |
     |  | L1:    |  | L2:        |  |
     |  | AGENT  |  | EPISODIC   |  |
     |  | LOCAL  |  | STORE      |  |
     |  | (TTL)  |  | (SQLite +  |  |
     |  +---------+  |  vectors)  |  |
     |               +------------+  |
     |  +---------+  +------------+  |
     |  | L3:    |  | L4:        |  |
     |  | LINEAGE|  | CODEBOOK   |  |
     |  | DAG    |  | (concept   |  |
     |  | (graph)|  |  vocab)    |  |
     |  +---------+  +------------+  |
     +-------------------------------+
                  |
                  v
     +-------------------------------+
     |      REALITY GROUNDING        |
     |  +---------+  +------------+  |
     |  | EXEC    |  | VALIDATOR  |  |
     |  | SANDBOX |  | (test      |  |
     |  | (sub-   |  |  harness,  |  |
     |  | process)|  |  assertion)|  |
     |  +---------+  +------------+  |
     |  +---------+  +------------+  |
     |  | SCORER  |  | CACHE      |  |
     |  | (trust, |  | (dedup     |  |
     |  |  novelty|  |  execs)    |  |
     |  |  score) |  |            |  |
     |  +---------+  +------------+  |
     +-------------------------------+


2. AGENT INTERNALS
--------------------

Every agent is an independent cognitive unit. Here is its internal
structure and the loop it runs each tick.

     +----------------------------------------------------+
     |                    AGENT                            |
     |                                                     |
     |  +------------------+   +------------------------+  |
     |  |  L1 WORKING      |   |  GENOME                |  |
     |  |  MEMORY          |   |  (current artifact     |  |
     |  |  - context       |   |   + lineage_hash)      |  |
     |  |  - local beliefs |   +------------------------+  |
     |  |  - peer trust    |                              |
     |  |    estimates     |   +------------------------+  |
     |  +------------------+   |  COGNITIVE STATE       |  |
     |                          |  SATTVA | RAJAS | TAMAS|  |
     |  +------------------+   +------------------------+  |
     |  |  RUMOR MILL      |                              |
     |  |  (incoming       |   +------------------------+  |
     |  |   gossip queue,  |   |  NEIGHBOR TABLE        |  |
     |  |   prioritized    |   |  (weighted peer list,  |  |
     |  |   by trust)      |   |   Hebbian-updated)     |  |
     |  +------------------+   +------------------------+  |
     +----------------------------------------------------+
                           |
     AGENT TICK (called by orchestrator each round):
                           |
       1. RECEIVE: ingest incoming gossip messages into
          rumor mill. Sample k neighbors for new messages.
                           |
       2. SELECT: choose what to work on this tick.
          - 70%: mutate own genome
          - 20%: recombine own genome with a rumor mill item
          - 10%: explore (generate random genome or immigrant)
                           |
       3. MUTATE / RECOMBINE: apply evolution operator
          based on cognitive state (rate varies by state).
                           |
       4. EXECUTE: send resulting artifact to reality
          grounding sandbox. Get validation result.
                           |
       5. EVALUATE: compute trust update based on
          validation + novelty (distance to MAP-Elites
          archive).
                           |
       6. ARCHIVE: submit artifact to MAP-Elites (inserts
          if it improves the niche). Submit to lineage DAG.
                           |
       7. GOSSIP OUT: select best item from rumor mill
          or own new best artifact. Send to k neighbors.
                           |
       8. STATE TRANSITION: check if cognitive state
          should change based on recent trust trajectory.
                           |
       9. FORGET: expire old L1 entries per TTL.


3. THE MAIN LOOP (TICK CYCLE)
-------------------------------

The orchestrator runs the system. Below is the top-level loop.

     +--------------------------------------------------------------------+
     |                   ORCHESTRATOR MAIN LOOP                            |
     |                                                                     |
     |  while running:                                                     |
     |                                                                     |
     |  1. INPUT PHASE                                                     |
     |     Read problem instance from queue or CLI.                        |
     |     If no tasks pending and all agents idle: sleep or exit.         |
     |                                                                     |
     |  2. DISPATCH PHASE                                                  |
     |     For each active agent (in parallel where possible):             |
     |       agent.tick()                                                  |
     |     (In single-process MVP: sequential round-robin)                 |
     |                                                                     |
     |  3. GROUNDING PHASE                                                 |
     |     Execute all sandbox jobs from this tick.                        |
     |     Collect validation results.                                     |
     |     Dedup by artifact hash (same code submitted by multiple         |
     |     agents only runs once per tick).                                |
     |                                                                     |
     |  4. ARCHIVE PHASE                                                   |
     |     MAP-Elites: insert all validated artifacts.                     |
     |     Lineage DAG: record all mutation/recombination events.          |
     |     Episodic store: persist artifacts with scores.                  |
     |                                                                     |
     |  5. POPULATION MANAGEMENT PHASE                                     |
     |     Check growth signals (every 10 rounds):                         |
     |       - Stagnation: no archive improvement in 10 rounds             |
     |       - High failure: >50% artifacts invalid in window             |
     |       - Shallow lineage: best <5 mutations from seed               |
     |       - Archive saturation: all cells filled but max trust < 0.5   |
     |     If ANY growth signal fires:                                     |
     |       next = floor(current * (1.5 + random(0, 0.5)))               |
     |       Spawn new agents in RAJAS state.                             |
     |     Check shrink signals (every 20 rounds):                        |
     |       - Plateau: no improvement for 20+ rounds -> trim 20%         |
     |              - Solved: target fitness reached -> cull to 2-3                    |
     |       - Niche collapse: duplicate agents in same cell -> merge     |
     |       - Compute pressure: over budget -> cull lowest-trust         |
     |                                                                     |
     |  6. CODEBOOK PHASE (if L4 active)                                   |
     |     Sample recent artifacts.                                        |
     |     Cluster embeddings.                                             |
     |     Mint/merge/split/retire codes.                                  |
     |                                                                     |
     |  7. WORKSPACE PHASE (if L5 active)                                  |
     |     Check for anomaly/breakthrough/contradiction.                   |
     |     If triggered: broadcast event to all agents.                    |
     |                                                                     |
     |  8. FORGETTING PHASE                                                |
     |     L2: compact/prune/archive old artifacts.                        |
     |     L3: freeze dead branches, compress.                             |
     |                                                                     |
     |  9. LOGGING / CHECKPOINT PHASE                                      |
     |     Write round summary (scores, diversity, population stats).      |
     |     Periodically checkpoint archive + lineage to disk.              |
     |                                                                     |
     |  10. ROUND COUNTER INCREMENT                                        |
     |                                                                     |
     +--------------------------------------------------------------------+


4. DATA FLOW THROUGH THE SYSTEM
----------------------------------

Below traces a single artifact through all stages.

     +--------+     +------+     +---------+     +---------+
     | AGENT  +---->| LLM  |---->| SANDBOX |---->| SCORER  |
     | (has   |     | call |     | (exec   |     | (compute|
     | genome)|     |(mut-)|     |  test   |     | trust + |
     +--------+     |ation)|     | harness)|     | novelty)|
                    +------+     +---------+     +----+----+
                                                      |
                                                      v
                                          +-----------+-----------+
                                          |                       |
                                          v                       v
                                   +-----------+         +-------------+
                                   | MAP-ELITES |         | LINEAGE DAG |
                                   | ARCHIVE    |         | (record     |
                                   | (insert if |         |  parent,    |
                                   |  improves  |         |  mutation,  |
                                   |  niche)    |         |  score)     |
                                   +-----+-----+         +------+------+
                                         |                       |
                                         v                       v
                                   +-----------+         +-------------+
                                   | EPISODIC  |         | TRUST       |
                                   | STORE     |         | PROPAGATION |
                                   | (persist) |         | (backprop   |
                                   +-----------+         |  to lineage)|
                                                         +------+------+
                                                                |
                                                                v
                                                          +-----------+
                                                          | AGENT'S   |
                                                          | RUMOR     |
                                                          | MILL      |
                                                          | (top item |
                                                          |  selected |
                                                          |  next     |
                                                          |  tick for |
                                                          |  gossip   |
                                                          |  out)     |
                                                          +-----------+
                                                                |
                                                                v
                                                          +-----------+
                                                          | K NEIGH-  |
                                                          | BORS      |
                                                          | (gossip   |
                                                          |  receive  |
                                                          |  into     |
                                                          |  their    |
                                                          |  rumor    |
                                                          |  mills)   |
                                                          +-----------+


5. COMPONENT INTERACTION MATRIX
----------------------------------

Each row shows who talks to whom and what they exchange.

     FROM \ TO          | ORCHESTRATOR | AGENT POOL | GOSSIP   | EVOLUTION | MEMORY   | GROUNDING | WORKSPACE
    --------------------+--------------+------------+----------+-----------+----------+-----------+----------
     ORCHESTRATOR       |      —       | tick()     | —        | archive() | store()  | execute() | check()
                        |              | spawn()    |          | get_best()| query()  |           |
                        |              | cull()     |          |           |          |           |
    --------------------+--------------+------------+----------+-----------+----------+-----------+----------
     AGENT POOL         | return       |     —      | send()   | mutate()  | read()   | submit()  | publish()
                        | artifact     |            | receive()| recombine()| write() |           |
                        | + score      |            |          |           | forget() |           |
    --------------------+--------------+------------+----------+-----------+----------+-----------+----------
     GOSSIP             | —            | deliver()  |    —     | —         | —        | —         | —
                        |              |            |          |           |          |           |
    --------------------+--------------+------------+----------+-----------+----------+-----------+----------
     EVOLUTION          | metrics()    | select()   | —        |     —     | read()   | —         | —
                        |              | parent()   |          |           | write()  |           |
    --------------------+--------------+------------+----------+-----------+----------+-----------+----------
     MEMORY             | —            | —          | —        | query()   |    —     | cache()   | —
                        |              |            |          | lineage() |          |           |
    --------------------+--------------+------------+----------+-----------+----------+-----------+----------
     GROUNDING          | results()    | notify()   | —        | —         | store()  |     —     | —
                        |              |            |          |           |          |           |
    --------------------+--------------+------------+----------+-----------+----------+-----------+----------
     WORKSPACE          | broadcast()  | receive()  | —        | —         | archive()| —         | —
                        |              |            |          |           |          |           |


6. FILE / MODULE MAP
----------------------

Project structure for implementation. Each module maps to one
subsystem from the architecture graph.

    gossip_engine/
    ├── __init__.py
    ├── main.py                    # Entry point, orchestrator loop
    ├── config.py                  # All configuration (pydantic-settings)
    │
    ├── agent/
    │   ├── __init__.py
    │   ├── model.py               # Agent dataclass, Genome type
    │   ├── tick.py                # agent.tick() — the per-agent loop
    │   ├── state_machine.py       # SATTVA / RAJAS / TAMAS transitions
    │   └── factory.py             # spawn_agent(), random_agent()
    │
    ├── gossip/
    │   ├── __init__.py
    │   ├── protocol.py            # GossipMessage type, serialize/deserialize
    │   ├── neighbor_table.py      # Peer weights, Hebbian updates
    │   ├── rumor_mill.py          # Priority queue with dedup
    │   └── network.py             # Send/receive (in-process or gRPC)
    │
    ├── evolution/
    │   ├── __init__.py
    │   ├── mutation.py            # 7 mutation types (refactor, substitute,
    │   │                          #   inject, ablate, crossover_prep, etc.)
    │   ├── recombination.py       # AST-based structural crossover
    │   ├── selection.py           # MAP-Elites: tournament, novelty,
    │   │                          #   diversity-based selection
    │   └── archive.py             # MAP-Elites grid, insert, query
    │
    ├── grounding/
    │   ├── __init__.py
    │   ├── sandbox.py             # Subprocess execution, timeout, restrictions
    │   ├── validator.py           # Test harness integration, assertion checking
    │   ├── scorer.py              # Trust score + novelty score computation
    │   └── cache.py               # Execution result cache by artifact hash
    │
    ├── memory/
    │   ├── __init__.py
    │   ├── l1_agent_local.py      # Agent-local KV with TTL
    │   ├── l2_episodic.py         # SQLite artifact store + vector index
    │   ├── l3_lineage.py          # SQLite graph DAG, recursive CTE queries
    │   ├── l4_codebook.py         # Codebook server, encode/decode, evolution
    │   ├── l5_workspace.py        # Global workspace broadcast bus
    │   └── forgetting.py          # Compaction, archival, pruning policies
    │
    ├── population/
    │   ├── __init__.py
    │   ├── manager.py             # Spawn/cull decisions, compute allocation
    │   ├── metrics.py             # Archive occupancy, stagnation, diversity
    │   └── immigrants.py          # Immigrant injection, random genomes
    │
    ├── trust/
    │   ├── __init__.py
    │   ├── scoring.py             # Trust computation functions
    │   ├── propagation.py         # Lineage-based credit assignment,
    │   │                          #   Hebbian peer trust updates
    │   ├── decay.py               # Trust decay over time, hop penalty
    │   └── defense.py             # Anti-memetic-pollution mechanisms
    │
    ├── llm/
    │   ├── __init__.py
    │   ├── backend.py             # Abstract LLM interface
    │   ├── openai_backend.py      # OpenAI / compatible API
    │   └── local_backend.py       # Ollama / LM Studio
    │
    ├── lineage/
    │   ├── __init__.py
    │   ├── graph.py               # DAG operations
    │   ├── analyzer.py            # Pattern mining over lineage
    │   └── credit.py              # Credit assignment rules
    │
    ├── checkpoint/
    │   ├── __init__.py
    │   ├── save.py                # Serialize full state
    │   └── load.py                # Deserialize and resume
    │
    └── utils/
        ├── __init__.py
        ├── log.py                 # Structured logging
        ├── ids.py                 # UUID, content hashing
        └── display.py             # Terminal display helpers


7. CONFIGURATION
------------------

All system parameters in one place. Environment-variable overridable.

    # System
    ROUNDS: int = 1000                      # Max rounds to run
    PARALLEL: bool = False                  # Tick agents in parallel
    CHECKPOINT_INTERVAL: int = 50           # Rounds between saves

    # Population (size evolves with problem complexity)
    INITIAL_POPULATION: int = 2             # Minimal viable size
    INITIAL_POPULATION_JITTER: int = 1      # Optional +0/1 for variety
    GROWTH_CHECK_INTERVAL: int = 10         # Check growth signals every N rounds
    SHRINK_CHECK_INTERVAL: int = 20         # Check shrink signals every N rounds
    GROWTH_STAGNATION_ROUNDS: int = 10      # No archive improvement -> grow
    GROWTH_HIGH_FAILURE_RATE: float = 0.5   # >50% invalid artifacts -> grow
    GROWTH_SHALLOW_LINEAGE_DEPTH: int = 5   # Best <5 mutations from seed -> grow
    GROWTH_ARCHIVE_SATURATION_TRUST: float = 0.5
    SHRINK_PLATEAU_ROUNDS: int = 20         # No improvement for 20 rounds -> trim
    SHRINK_TRIM_FRACTION: float = 0.2       # Cull lowest-trust 20%
    SHRINK_VERIFICATION_POP: int = 3        # Target size when problem solved

    # Agent defaults
    DEFAULT_COGNITIVE_STATE: str = "RAJAS"  # RAJAS, SATTVA, or TAMAS
    TRUST_INIT: float = 0.5
    TRUST_MAX: float = 1.0
    TRUST_MIN: float = 0.0
    NEIGHBOR_FANOUT: int = 3               # Gossip peers per tick
    RUMOR_MILL_SIZE: int = 20

    # Mutation rates (overridden by cognitive state)
    MUTATION_RATE_SATTVA: float = 0.05
    MUTATION_RATE_RAJAS: float = 0.30
    MUTATION_RATE_TAMAS: float = 0.50

    # Recombination rates
    RECOMBINATION_RATE_SATTVA: float = 0.05
    RECOMBINATION_RATE_RAJAS: float = 0.30
    RECOMBINATION_RATE_TAMAS: float = 0.10

    # MAP-Elites
    ARCHIVE_DIMENSIONS: int = 2             # Behavioral descriptor dimensions
    ARCHIVE_RESOLUTION: int = 10            # Cells per dimension
    SELECTION_EPSILON: float = 0.3          # 30% random exploration in selection

    # Sandbox
    EXECUTION_TIMEOUT_MS: int = 5000
    MAX_OUTPUT_SIZE: int = 65536            # Truncate stdout
    CACHE_MAX_SIZE: int = 10000

    # LLM
    LLM_PROVIDER: str = "local"             # openai | gemini | deepseek | grok | local
    LLM_MODEL: str = ""                     # Override default model per provider
    LLM_TEMPERATURE: float = 0.8
    LLM_MAX_TOKENS: int = 1024
    LLM_FALLBACK_ENABLED: bool = False      # Try next provider on 5xx error

    # API keys (loaded from environment or .env file)
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_MODEL: str = "deepseek-chat"
    GROK_API_KEY: str = ""
    GROK_MODEL: str = "grok-2-latest"
    LOCAL_BASE_URL: str = "http://localhost:11434/v1"
    LOCAL_MODEL: str = "llama3"

    # Memory
    L1_TTL_DEFAULT: int = 100               # Rounds before L1 expiry
    L2_COMPACTION_INTERVAL: int = 50        # Rounds between compactions
    L2_ARCHIVE_THRESHOLD: float = 0.1       # Trust below this -> archive
    L2_DELETE_THRESHOLD: float = 0.01       # Trust below this -> delete
    L3_FREEZE_DEPTH: int = 50              # Branches deeper than this freeze
    L4_ENABLED: bool = False               # Codebook (enable in Phase 4)
    L5_ENABLED: bool = False               # Workspace (enable in Phase 5)

    # Trust
    TRUST_HOP_DECAY: float = 0.9            # Per-hop gossip trust discount
    TRUST_PROPAGATION_FACTOR: float = 0.05  # Credit backprop per ancestor
    TRUST_DECAY_PER_ROUND: float = 0.001    # Passive decay
    CONTRADICTION_THRESHOLD: float = 0.7    # Trigger workspace if conflict

    # Workspace
    WORKSPACE_NOVELTY_SIGMA: float = 3.0    # Std devs above mean to trigger
    WORKSPACE_TRUST_MULTIPLIER: float = 1.5 # Max trust exceedance to trigger
    WORKSPACE_BROADCAST_TTL: int = 3        # Rounds workspace stays active


8. ENTRY POINT FLOW
---------------------

    main.py
    │
    ├── 1. Load config from env/file
    │
    ├── 2. Initialize subsystems:
    │     ├── LLM backend
    │     ├── Reality grounding (sandbox pool)
    │     ├── Memory layer (SQLite connection)
    │     ├── MAP-Elites archive
    │     ├── Population manager
    │     ├── Checkpoint system (load if resuming)
    │     └── Global workspace (if enabled)
    │
    ├── 3. Spawn initial agent population (2-3 agents, minimal start)
    │
    ├── 4. Enter main loop (see §3 above)
    │
    ├── 5. On completion:
    │     ├── Print summary stats
    │     ├── Save checkpoint
    │     ├── Export lineage graph
    │     └── Shutdown subsystems

Two modes:
  - INTERACTIVE: one problem instance, run until solved or rounds
    exhausted. Print best artifact at end.
  - BATCH: queue of problem instances, run sequentially. Log
    results to file for analysis.


APPENDIX: KEY TYPE DEFINITIONS (PSEUDOCODE)
---------------------------------------------

    Agent:
      id: UUID
      genome: str                          # Source code or solution text
      lineage_hash: str                    # Hash of parent artifact
      cognitive_state: SATTVA | RAJAS | TAMAS
      trust_score: float                   # [0, 1]
      l1_memory: dict[str, Any]            # TTL-indexed KV
      rumor_mill: PriorityQueue[RumorItem]
      neighbor_table: dict[UUID, float]    # peer_id -> weight
      niche_coords: tuple[int, ...]        # MAP-Elites grid cell

    RumorItem:
      artifact_code: str
      lineage_hash: str
      trust_score: float
      niche_coords: tuple
      hop_count: int
      timestamp: float

    GossipMessage:
      sender_id: UUID
      rumor: RumorItem
      cognitive_state: str                 # For sender state inference

    Artifact:
      content_hash: str                    # SHA256 of code
      code: str
      agent_id: UUID
      lineage_hash: str
      trust_score: float
      novelty_score: float
      niche_coords: tuple
      validation_result: ValidationResult
      timestamp: float

    ValidationResult:
      passed: bool
      output: str
      error: str | None
      runtime_ms: int
      test_results: list[bool]

    LineageNode:
      node_id: str
      artifact_hash: str
      parent_ids: list[str]
      mutation_type: str
      agent_id: UUID
      trust_score: float
      niche_coords: tuple
      timestamp: float

    CodebookEntry:
      index: int
      centroid: list[float]                # 768-dim embedding
      label: str
      parent_index: int | None
      birth_timestamp: float
      usage_count: int
      citations: list[str]                 # Artifact hashes that support
                                           # this concept

    WorkspaceEvent:
      event_id: str
      event_type: ANOMALY | BREAKTHROUGH | CONTRADICTION | CRISIS
      source_agent_id: UUID
      artifact_hash: str
      description: str
      magnitude: float
      timestamp: float

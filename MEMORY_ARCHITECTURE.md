MEMORY ARCHITECTURE — GOSSIP ENGINE
====================================
Synthesis of design proposals | May 2026


MEMORY IS THE SUBSTRATE, NOT A FEATURE
---------------------------------------
Memory in this system is not storage. It is the medium through which
evolutionary pressure shapes future cognition. Every read is selection.
Every write is mutation. Forgetting is regularization.

The architecture defines five layers with distinct lifetimes, consistency
models, and access patterns. They form a gradient from ephemeral-individual
to persistent-collective, NOT a strict hierarchy — agents can access any
layer directly depending on context and privilege.


LAYER 1 — AGENT-LOCAL WORKING MEMORY
-------------------------------------
Purpose:   Active thinking state, diversity preservation.
Lifetime:  Single thinking cycle to a few gossip rounds.
Consistency: None. Only the owning agent accesses it.
Storage:   In-process KV store with TTL expiry. 10-200 KB effective
           semantic state per agent. Not a context window — structured
           data structures (beliefs, trust estimates, active subtasks,
           recent messages, local hypothesis queue).

What lives here:
  - Recent context (last N inputs/outputs)
  - Local beliefs (current hypotheses the agent is exploring)
  - Trust estimates for known peers (scalar per peer, Hebbian-updated)
  - Active subtask state
  - Short-term hypotheses being evaluated
  - Codebook index references for currently active concepts
  - Local lineage references (parent artifact hashes)

Key property:
  This memory can die with the agent. That is a feature, not a bug.
  Diversity depends on agents maintaining divergent local states.
  If this layer were globally synced, all agents would collapse into
  one mind and novelty would die.

Forgetting:
  Aggressive. TTL-based expiry (configurable per agent cognitive state:
  RAJAS agents expire faster, SATTVA agents retain longer). No
  persistence across restarts by default.

Interface:
  read(key) -> value
  write(key, value, ttl=default)
  expire(prefix_pattern)
  get_active_concepts() -> List[codebook_index]


LAYER 2 — EPISODIC SHARED MEMORY ("THE ARTIFACT STORE")
--------------------------------------------------------
Purpose:   Civilization memory. Accumulated validated artifacts,
           trajectories, and failures. What the population knows.
Lifetime:  Hours to days. Survives agent death. Periodically summarized.
Consistency: Eventual. CRDT-based append-only log with timestamp
             vectors. Network-partition tolerant. Conflicting writes
             resolved by last-writer-wins per artifact key.

Storage:   Content-addressed blob store + vector index.
           - Blobs: S3-compatible, local filesystem, or IPFS
           - Index: HNSW vector index (Qdrant-style) over embedding
           - SQLite metadata table for structured queries
           Each artifact has: content_hash, parent_hash, agent_id,
           timestamp, niche_bucket, trust_score, validation_results,
           mutation_type, lineage_depth.

What lives here:
  - Successful task trajectories (full execution traces)
  - Validated code artifacts (output of reality grounding)
  - Failed attempts with error signatures (anti-pattern library)
  - Tool-use sequences that worked
  - Gossip snapshots (periodic, for replay and analysis)
  - Intermediate discoveries that had high novelty scores
  - Checkpoints of population state

Key property:
  This is the population's shared experience base. It is NOT the
  lineage graph (Layer 3) — it stores *outcomes*, not *evolution*.
  Think: scientific paper repository, not phylogenetic tree.

Retrieval protocol:
  Agents retrieve by:
    1. Semantic similarity (embedding query -> nearest neighbors)
    2. Lineage depth (ancestors/descendants of a known artifact)
    3. Niche bucket (all artifacts in a MAP-Elites behavioral niche)
    4. Trust threshold (artifacts with trust_score > N)
    5. Recency (most recent artifacts matching query)
  Retrieval is gossip-mediated by default — an agent queries its
  peers for artifacts matching a vector, and peers check their local
  cache of this layer before forwarding.

Forgetting:
  - TTL-based archival (configurable per niche — high-novelty niches
    retain longer, saturated niches expire faster)
  - Compression: periodically cluster similar artifacts, replace
    cluster with prototype + membership list
  - Pruning: artifacts with trust_score near zero AND age > threshold
    are deleted (not archived — genuinely forgotten)
  - Archival: artifacts below recency/novelty thresholds but above
    trust threshold are moved to cold storage (S3 glacier, etc.)

Interface:
  store(artifact: Artifact) -> content_hash
  retrieve(query: RetrievalQuery) -> List[Artifact]
  retrieve_by_hash(content_hash) -> Artifact
  retrieve_lineage(artifact_hash, direction=ANCESTORS|DESCENDANTS, depth=10) -> List[Artifact]
  get_niche_inventory(niche_id) -> List[Artifact]
  summarize_niche(niche_id) -> Summary
  compact(compaction_policy) -> None


LAYER 3 — LINEAGE DAG ("THE EVOLUTIONARY GENOME")
--------------------------------------------------
Purpose:   Track the ancestry, mutation, and selection history of
           every artifact ever produced. The system's phylogenetic tree.
Lifetime:  Permanent. Immutable. Append-only.
Consistency: Strong. Linearizable writes within a partition. CRDT
             merge across partitions with conflict-free replicated
             data types for the DAG structure.

Storage:   Graph database or custom DAG store.
           - Option A: SQLite with adjacency table + node table
           - Option B: DuckDB with recursive CTE support
           - Option C: Purpose-built append-only DAG log (like Git
             but with richer node types)
           Each node in the DAG:
             - artifact_hash (link to Layer 2)
             - parent_hashes[] (1 for mutation, 2 for recombination)
             - agent_id who produced it
             - mutation_type (mutate, recombine, reset, inject, ablate)
             - mutation_params (specific perturbation applied)
             - trust_score at creation time
             - lineage_depth (integer, from root)
             - niche_bucket at creation time
           Each edge:
             - type: "parent_of" | "recombined_from" | "forked_from"
             - weight: trust contribution (for credit assignment)

What lives here:
  - Every mutation event (who mutated what, how)
  - Every recombination event (which two artifacts combined)
  - Fork events (when an agent produced a sibling artifact)
  - Selection events (which artifacts survived culling)
  - Trust propagation history (which artifacts contributed to
    downstream success)
  - Lineage death events (branches that were culled)

Key property:
  This is your most unique component. Standard RAG systems don't
  have this. It enables:
    - Credit assignment ("which ancestor contributed to this success?")
    - Evolutionary pattern mining ("which mutation strategies produce
      the deepest lineages?")
    - Lineage replay ("what if we branched from this ancestor instead?")
    - Trust backpropagation (lineage-based Hebbian credit assignment)

Retrieval protocol:
  Queries are structural, not semantic:
    - "Find all descendants of artifact X within depth D"
    - "Find the common ancestor of artifacts A and B"
    - "Which lineages survived more than N generations?"
    - "Which mutation types cluster in high-trust lineages?"
    - "Find the most recent fork point before artifact X"

Write amplification concern:
  With 50 agents × 10 artifacts/round × 1000 rounds = 500,000 nodes.
  This is manageable in isolation, but retrieval latency degrades.
  Mitigations:
    - Lineage summarization: mark lineage branches as "frozen" (no
      longer producing descendants). Frozen branches are compressed
      to aggregate stats (depth, max_trust, niche trajectory) and
      individual nodes evicted to cold storage.
    - Depth-limited traversal: queries specify max depth.
    - Partition by niche: each niche's lineage subgraph is stored
      separately; cross-niche queries are rare and expensive.

Forgetting:
  Nodes are never deleted — this layer is the immutable record.
  But they can be:
    - Frozen (no more incoming edges)
    - Compressed (aggregated into summary nodes)
    - Archived (moved to cold storage, hash remains for integrity)
  The root nodes (initial seeded artifacts) are always retained.

Interface:
  record_mutation(parent_hash, artifact_hash, agent_id, mutation_type, params) -> node_id
  record_recombination(parent_hash_a, parent_hash_b, artifact_hash, ...) -> node_id
  get_ancestors(artifact_hash, depth=N) -> List[DAGNode]
  get_descendants(artifact_hash, depth=N) -> List[DAGNode]
  find_common_ancestor(hash_a, hash_b) -> DAGNode
  get_lineage_stats(artifact_hash) -> LineageStats
  get_surviving_lineages(min_depth=N, min_trust=T) -> List[LineageSummary]
  freeze_branch(artifact_hash) -> None
  compress_branch(artifact_hash) -> CompressedSummary


LAYER 4 — CODEBOOK ("SHARED CONCEPT VOCABULARY")
-------------------------------------------------
Purpose:   Shared semantic vocabulary that all agents use to
           communicate and think. Prevents semantic drift.
           Collective conceptual memory of the population.
Lifetime:  Persistent. Evolves via mint/retire/split/merge operations.
Consistency: Strong. Raft/Paxos replicated log or single authoritative
             server with local read caches. Two agents using the same
             codebook index MUST mean the same thing.

Storage:   Replicated state machine backed by write-ahead log.
           - Codebook entries: (index, embedding_vector, human_label,
             description, parent_index, birth_timestamp, usage_count,
             validation_citations[])
           - Index is an integer 0..N (VQ-VAE style)
           - Embedding is the centroid of all artifact embeddings
             that activated this code

What lives here:
  - Concept index → embedding mapping
  - Concept index → human-readable label (optional, for debugging)
  - Concept birth/death lineage (which concept split into which)
  - Usage statistics (how often referenced, by which agents/niches)
  - Validation grounding (links to Layer 2 artifacts that justify
    the concept's existence)

Evolution operations:
  MINT:   Create new code when an agent discovers a concept not
          covered by existing codes. Requires: at least 3 validation
          artifacts from different contexts that support the new
          concept. Prevents noise entries.
  RETIRE: Mark a code as unused when usage_count stays at 0 for
          N gossip rounds. Codes are soft-deleted — existing
          references remain readable but no new references allowed.
  SPLIT:  When a code's cluster purity drops below threshold,
          split into k sub-codes. Child codes inherit the lineage
          of the parent.
  MERGE:  When two codes are co-activated >90% of the time over
          a window, merge them. Combined code inherits both lineages.

Key property:
  The codebook is the bridge between communication and memory.
  When an agent gossips, it sends codebook indices (not text).
  When it reads the lineage DAG, it indexes by codebook vectors.
  When it queries episodic memory, the query is a codebook vector.
  This means: memory and communication share ONE representation.
  No translation layer needed.

Consistency model detail:
  - Reads: local cache, async refresh from leader. Stale reads are
    acceptable for most operations (agent will still produce useful
    output with a slightly outdated codebook).
  - Writes (MINT/RETIRE/SPLIT/MERGE): must go through the Raft
    leader. Latency-tolerant because these are rare operations
    (O(tens) per hour, not per second).
  - Cache invalidation: leader broadcasts version vector; peers
    invalidate local cache entries with stale versions.

Interface (client side):
  encode(embedding_vector) -> codebook_index
  decode(codebook_index) -> embedding_vector
  lookup(codebook_index) -> CodebookEntry
  mint(embedding, label, citations) -> codebook_index
  retire(codebook_index) -> None
  split(codebook_index, k) -> List[codebook_index]
  merge(indices_a, indices_b) -> codebook_index
  search(query_embedding, top_k=5) -> List[(index, distance)]


LAYER 5 — GLOBAL WORKSPACE / ATTENTION FIELD
---------------------------------------------
Purpose:   Temporary shared attention field for high-signal events.
           Anomalies, breakthroughs, contradictions, crises, or
           paradigm shifts become globally visible across the
           population. Sparse, expensive, time-limited.

Lifetime:  Seconds to minutes. Ephemeral by design — no long-term
           storage in this layer itself (though the event is
           archived to Layers 2 and 3 afterward).

Consistency: Strong within the broadcast event. All active agents
             that subscribe must see the same workspace content
             for the broadcast window.

Storage:   In-memory distributed broadcast bus (Redis Streams or
           NATS JetStream). NOT persistent — snapshot to Layer 2
           on close.

When it activates:
  - Anomaly threshold: an artifact's novelty score exceeds N
    standard deviations from the niche mean
  - Contradiction: two high-trust artifacts in the same niche
    have mutually exclusive validation results
  - Breakthrough: an artifact's trust_score exceeds the previous
    niche maximum by >50%
  - Crisis: niche population drops below minimum threshold
    (indicates memetic extinction event)
  - Paradigm shift: a newly minted codebook entry is referenced
    >10% of all gossip messages within a window (indicates a
    new concept is rapidly spreading)

What happens during activation:
  1. Trigger agent broadcasts the event to the workspace
  2. All active agents receive it within a bounded latency
  3. Each agent independently evaluates relevance
  4. Agents may: adopt the new idea, challenge it, fork from
     it, or ignore it
  5. After the broadcast window, the workspace closes
  6. The event and aggregate response are archived to Layer 2
     and recorded in Layer 3

Key design constraint:
  This must be SPARSE. If >1% of all events trigger global
  broadcast, the threshold is too low. Gossip is the default
  communication channel. Workspace is the exception.

Interface:
  broadcast(event: WorkspaceEvent) -> event_id
  subscribe(event_filter) -> Stream[WorkspaceEvent]
  archive_event(event_id) -> artifact_hash (in Layer 2)
  get_active_workspace() -> List[WorkspaceEvent]


CROSS-CUTTING: MEMORY GRADIENTS
--------------------------------
Instead of "local vs global," memory accessibility varies by
distance — both semantic and network distance.

- Network distance: number of gossip hops from the querying agent
  to the memory's origin. Nearby agents share more memory state
  via gossip. Distant agents share less.

- Semantic distance: distance in codebook space between the query
  and the memory. Closer concepts are more accessible (lower
  retrieval threshold). Distant concepts require higher signal
  strength to be retrieved.

- Trust distance: memories from high-trust agents are more
  accessible than those from low-trust agents, regardless of
  network or semantic distance.

This gradient creates emergent structure:
  - Cognitive regions: clusters of nearby agents share local
    memory, creating specialized sub-populations
  - Specialization zones: different regions of the network
    converge on different niche vocabularies
  - Memetic niches: ideas propagate within a gradient boundary
    before crossing to other regions
  - Emergent cultures: sustained gradient-bounded memory
    differences produce distinct "cultures" in the agent
    population

Implementation:
  Each Layer 2 and Layer 3 query includes a distance budget
  parameter. The agent's gossip peers forward the query up to
  TTL hops. Responses are weighted by inverse distance.
  Layer 4 (codebook) is not gradient-accessible — it must
  be consistent.


CROSS-CUTTING: FORGETTING PROTOCOL
-----------------------------------
Every layer except Layer 3 has explicit forgetting.

Layer 1: TTL expiry (configurable per agent state).
Layer 2: Clustering + prototype compression. Threshold-based
         archival and deletion.
Layer 3: Freezing + compression. Nodes never deleted but
         aggregated into summary forms.
Layer 4: Retirement of unused codes. Soft-delete with lineage
         preservation.
Layer 5: Ephemeral by construction. Archive on close.

The forgetting protocol is a background process that runs
periodically (every N gossip rounds or when resource pressure
exceeds threshold). It is governed by a configurable policy
that can be tuned per niche or per agent cognitive state
(SATTVA niches should forget slower, RAJAS faster).


CROSS-CUTTING: RETRIEVAL PROTOCOL
-----------------------------------
Agents do not query a central index. Retrieval is gossip-mediated.

The protocol:
  1. Agent constructs a retrieval query (embedding vector or
     codebook index, plus distance budget and trust threshold)
  2. Agent samples k peers from its neighbor set
  3. Each peer checks its local cache of Layer 2/3/4
  4. If found: return result + hop_count
  5. If not found and TTL > 0: forward to their peers, TTL - 1
  6. Results accumulate back to the querying agent
  7. Agent selects best result(s) by trust_score / distance

This is a Kademlia-style DHT lookup over the memory layers.
It preserves epistemic locality (agents don't see everything)
while enabling any memory to be reachable within bounded hops.


CROSS-CUTTING: CONSISTENCY GUARANTEES
--------------------------------------
Layer | Consistency          | Justification
------|----------------------|------------------------------------------
L1    | None                 | Only owning agent reads/writes
L2    | Eventual (CRDT)      | Partition-tolerant artifact store
L3    | Strong (per partition)| Lineage integrity requires linearizability
L4    | Strong (Raft)        | Codebook ambiguity breaks communication
L5    | Strong (broadcast)   | Workspace must be same for all observers

L2 and L3 are partitioned by niche. Cross-niche queries are
eventually consistent; intra-niche queries are strongly consistent.
This is a pragmatic compromise between CAP constraints.


MERGE SUMMARY
--------------
This architecture merges:

From my original design:
  - 3 layers simplified to 5 with better separation
  - Codebook as the bridge between memory and communication
  - Consistency model breakdown per layer
  - Write amplification mitigation

From ChatGPT:
  - Memory gradients (distance-based accessibility)
  - Forgetting as a first-class mechanism
  - Global workspace layer
  - Episodic/shared memory separation from lineage

Resolved tensions:
  - Memory is NOT communication: wrong. Codebook is both.
  - Memory IS storage: wrong. Memory is evolutionary pressure.
  - Forgetting is failure: wrong. Forgetting is regularization.
  - All memory must be consistent: wrong. Only codebook needs strong consistency.

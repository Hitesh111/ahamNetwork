from __future__ import annotations
import importlib.util
import logging
import random
import time
from pathlib import Path

from .agent.factory import create_immigrant_agent
from .agent.model import Agent
from .agent.state_machine import CognitiveState
from .checkpoint.save import save_checkpoint
from .config import Config
from .evolution.archive import MAPElitesArchive
from .evolution.mutation import MutationEngine
from .grounding.sandbox import Sandbox
from .grounding.scorer import Scorer
from .grounding.validator import evaluate_solution
from .grounding.cache import ExecutionCache
from .llm.backend import create_backend
from .memory.l2_episodic import ArtifactRecord, ArtifactStore
from .memory.l3_lineage import LineageStore
from .population.manager import PopulationManager
from .utils.ids import content_hash
from .utils.log import setup_logging

logger = logging.getLogger("gossip_engine")


class Orchestrator:
    def __init__(self, config: Config):
        self.cfg = config
        self.provider = config.resolve_llm_provider()
        self.model = config.resolve_llm_model(self.provider)
        self.logger = setup_logging(config.log_level)
        self.llm = create_backend(self.provider, config) if self.provider else None
        self.mutation_engine = MutationEngine(self.llm, "")
        self.sandbox = Sandbox(
            timeout_ms=config.execution_timeout_ms,
            max_output=config.max_output_size,
        )
        self.scorer = Scorer(
            trust_init=config.trust_init,
            trust_max=config.trust_max,
            trust_min=config.trust_min,
        )
        self.archive = MAPElitesArchive(
            dimensions=config.archive_dimensions,
            resolution=config.archive_resolution,
        )
        self.exec_cache = ExecutionCache(max_size=config.cache_max_size)
        self.population = PopulationManager(config)
        self.generation = 0

        checkpoint_dir = Path(self.cfg.checkpoint_dir)
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path = checkpoint_dir / "checkpoint.json"
        self.artifact_store = ArtifactStore(checkpoint_dir / "artifacts.sqlite3")
        self.lineage_store = LineageStore(checkpoint_dir / "lineage.sqlite3")

        self._domain_module = None
        self._domain_fitness = None
        self._domain_descriptor = None
        self._domain_test_cases = None
        self._domain_test = ""
        self._domain_prompt = ""
        self._domain_solved = None

    def load_domain(self, module_path: str):
        spec = importlib.util.spec_from_file_location("domain", module_path)
        if spec is None or spec.loader is None:
            raise ValueError(f"Unable to load domain module: {module_path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self._domain_module = mod
        self._domain_fitness = getattr(mod, "fitness", None)
        self._domain_descriptor = getattr(mod, "behavioral_descriptor", None)
        self._domain_test_cases = getattr(mod, "TEST_CASES", None)
        self._domain_test = getattr(mod, "test_code", "")
        self._domain_prompt = getattr(mod, "PROMPT", "")
        self._domain_solved = getattr(mod, "is_solved", None)
        self.mutation_engine.domain_prompt = self._domain_prompt
        logger.info(f"Loaded domain: {module_path}")

    def _default_behavior(self, code: str) -> tuple[float, ...]:
        h = content_hash(code)
        dims = max(1, self.cfg.archive_dimensions)
        behavior = [
            (int(h[i : i + 2], 16) % 100) / 100.0
            for i in range(0, min(dims * 2, len(h)), 2)
        ]
        while len(behavior) < dims:
            behavior.append(0.0)
        return tuple(behavior[:dims])

    def _normalize_behavior(self, behavior: tuple[float, ...] | list[float]) -> tuple[float, ...]:
        values = [float(v) for v in behavior]
        if len(values) < self.cfg.archive_dimensions:
            values.extend([0.0] * (self.cfg.archive_dimensions - len(values)))
        return tuple(values[: self.cfg.archive_dimensions])

    def _evaluate_genome(self, genome: str) -> tuple[bool, float, tuple[float, ...], float, str, str | None]:
        cached = self.exec_cache.get(genome)
        if cached:
            return cached

        if self._domain_test_cases is not None:
            if self._domain_descriptor:
                behavior_fn = lambda code, score, passed, total: self._normalize_behavior(self._domain_descriptor(code))
            else:
                behavior_fn = lambda code, score, passed, total: self._default_behavior(code)
            result = evaluate_solution(
                genome,
                self._domain_test_cases,
                sandbox=self.sandbox,
                behavior_fn=behavior_fn,
            )
            output = (
                result.passed,
                result.score,
                result.behavior,
                result.runtime_ms,
                result.output,
                result.error,
            )
            self.exec_cache.put(genome, output)
            return output

        if self._domain_fitness:
            passed, score, behavior = self._domain_fitness(genome)
            output = (
                bool(passed),
                float(score),
                self._normalize_behavior(behavior),
                0.0,
                "",
                None,
            )
            self.exec_cache.put(genome, output)
            return output

        sandbox_result = self.sandbox.execute(genome, self._domain_test)
        score = 1.0 if sandbox_result.passed else 0.0
        result = (
            sandbox_result.passed,
            score,
            self._default_behavior(genome),
            sandbox_result.runtime_ms,
            sandbox_result.output,
            sandbox_result.error,
        )
        self.exec_cache.put(genome, result)
        return result

    def _all_embeddings(self) -> list[list[float]]:
        return [list(entry.coords) for entry in self.archive._cells.values()]

    def _record_result(
        self,
        agent: Agent,
        parent_hash: str,
        mutation_type: str,
        passed: bool,
        score: float,
        behavior: tuple[float, ...],
        runtime_ms: float,
        output: str,
        error: str | None,
    ) -> float:
        artifact_hash = content_hash(agent.genome)
        novelty = self.scorer.compute_novelty(list(behavior), self._all_embeddings())
        old_trust = agent._prev_trust
        trust = self.scorer.compute_trust(
            passed=passed,
            runtime_ms=runtime_ms,
            novelty_score=novelty,
            trust_decay=self.cfg.trust_decay_per_round * agent.age,
            quality_score=score,
        )

        agent.trust_score = trust
        agent.age += 1
        agent._prev_trust = trust
        agent.niche_coords = self.archive._discretize(behavior)
        agent.state_machine.transition(trust, trust - old_trust)
        agent.lineage_hash = artifact_hash

        inserted = self.archive.insert(
            genome=agent.genome,
            trust_score=trust,
            novelty_score=novelty,
            agent_id=agent.id,
            lineage_hash=parent_hash,
            behavior=behavior,
            artifact_hash=artifact_hash,
        )

        lineage_depth = 0
        if parent_hash:
            parent_node = self.lineage_store.get_node(parent_hash)
            lineage_depth = parent_node.lineage_depth + 1 if parent_node else 1

        lineage_node = self.lineage_store.get_node(artifact_hash)
        if lineage_node is None:
            self.lineage_store.record_mutation(
                parent_hash=parent_hash,
                artifact_hash=artifact_hash,
                agent_id=agent.id,
                mutation_type=mutation_type,
                params={
                    "score": score,
                    "passed": passed,
                    "runtime_ms": runtime_ms,
                    "inserted": inserted,
                },
                trust_score=trust,
                niche_bucket=agent.niche_coords,
            )
            lineage_node = self.lineage_store.get_node(artifact_hash)
        if lineage_node:
            lineage_depth = lineage_node.lineage_depth

        self.artifact_store.store(
            ArtifactRecord(
                artifact_hash=artifact_hash,
                content=agent.genome,
                agent_id=agent.id,
                trust_score=trust,
                validation_results={
                    "passed": passed,
                    "score": score,
                    "runtime_ms": runtime_ms,
                    "output": output,
                    "error": error,
                },
                niche_coords=agent.niche_coords,
                parent_hash=parent_hash,
                lineage_depth=lineage_depth,
                mutation_type=mutation_type,
                novelty_score=novelty,
                behavior=behavior,
            )
        )

        self.population.record_failure(passed)
        return trust

    def _tick_agent(self, agent: Agent) -> float:
        parent_hash = ""
        mutation_type = "seed"
        mr = agent.state_machine.mutation_rate

        if agent.genome and random.random() < mr:
            parent_hash = content_hash(agent.genome)
            agent.genome = self.mutation_engine.mutate(
                agent.genome,
                mutation_rate=mr,
            )
            mutation_type = "mutate"
        elif not agent.genome and self._domain_prompt:
            if self.mutation_engine.llm_available:
                immigrant = create_immigrant_agent(self._domain_prompt, self.llm)
                agent.genome = immigrant.genome
                mutation_type = "immigrant"
            else:
                agent.genome = "def solve(x): return x"
                mutation_type = "seed"

        passed, score, behavior, runtime_ms, output, error = self._evaluate_genome(agent.genome)
        return self._record_result(
            agent=agent,
            parent_hash=parent_hash,
            mutation_type=mutation_type,
            passed=passed,
            score=score,
            behavior=behavior,
            runtime_ms=runtime_ms,
            output=output,
            error=error,
        )

    def _seed_population(self):
        for index, agent in enumerate(self.population.agents):
            if self._domain_prompt and self.llm:
                try:
                    immigrant = create_immigrant_agent(self._domain_prompt, self.llm)
                    agent.genome = immigrant.genome
                except Exception:
                    agent.genome = "def solve(x): return x"
            elif self._domain_prompt and not self.llm and index == 0 and getattr(self.mutation_engine, "_fallback_templates", None):
                agent.genome = self.mutation_engine._fallback_templates[0]
            elif not agent.genome:
                agent.genome = "def solve(x): return x"

    def run(self, rounds: int | None = None) -> dict:
        target_rounds = self.cfg.rounds if rounds is None else self.generation + rounds
        if not self.population.agents:
            self.population.initialize()
            self._seed_population()

        solved = False
        completed_rounds = self.generation
        start_time = time.time()

        for round_index in range(self.generation, target_rounds):
            completed_rounds = round_index + 1
            self.generation = completed_rounds

            for agent in self.population.agents:
                if agent.cognitive_state == CognitiveState.TAMAS:
                    continue
                self._tick_agent(agent)

            if completed_rounds % self.cfg.growth_check_interval == 0:
                growth_signals = self.population.check_growth_signals(
                    self.archive,
                    self.lineage_store,
                )
                if growth_signals:
                    self.population.grow(growth_signals, self.llm, self._domain_prompt)

            if completed_rounds % self.cfg.shrink_check_interval == 0:
                shrink_signals = self.population.check_shrink_signals(self.archive, solved)
                if shrink_signals:
                    self.population.shrink(shrink_signals)

            if completed_rounds % 10 == 0:
                elite = self.archive.get_elite()
                metrics = self.population.get_metrics()
                logger.info(
                    f"Round {completed_rounds:4d} | pop={metrics['size']:3d} "
                    f"| archive={self.archive.num_cells():3d} "
                    f"| best={(elite.trust_score if elite else 0.0):.3f} "
                    f"| occupancy={self.archive.occupancy():.2f} "
                    f"| fail={metrics['failure_rate']:.2f}"
                )

            elite = self.archive.get_elite()
            if self._domain_solved and elite:
                try:
                    if self._domain_solved(elite.genome, elite.trust_score):
                        logger.info(f"Problem solved at round {completed_rounds}!")
                        solved = True
                        break
                except Exception as exc:
                    logger.debug("Domain solved check failed: %s", exc)

            if self.cfg.checkpoint_interval and completed_rounds % self.cfg.checkpoint_interval == 0:
                save_checkpoint(self.checkpoint_path, self, completed_rounds, solved)

        elapsed = time.time() - start_time
        elite = self.archive.get_elite()

        save_checkpoint(self.checkpoint_path, self, completed_rounds, solved)

        return {
            "rounds": completed_rounds,
            "elapsed_seconds": elapsed,
            "population_size": self.population.size,
            "archive_cells": self.archive.num_cells(),
            "archive_occupancy": self.archive.occupancy(),
            "max_trust": self.archive.max_trust(),
            "best_genome": elite.genome if elite else "",
            "solved": solved,
        }

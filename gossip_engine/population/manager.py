from __future__ import annotations
import random
import logging
from ..agent.model import Agent
from ..agent.factory import create_agent, create_immigrant_agent
from ..agent.state_machine import CognitiveState

logger = logging.getLogger("gossip_engine.population")

MAX_GROWTH_MULTIPLIER = 1.5
ABS_MAX_POPULATION = 500


class PopulationManager:
    def __init__(self, config):
        self.cfg = config
        self.agents: list[Agent] = []
        self.generation = 0
        self._rounds_since_improvement = 0
        self._prev_best_trust = 0.0
        self._failure_window: list[bool] = []
        self._consecutive_growth_rounds = 0

    def initialize(self):
        n = self.cfg.initial_population + random.randint(0, self.cfg.initial_population_jitter)
        rates = dict(
            mr_s=self.cfg.mutation_rate_sattva,
            mr_r=self.cfg.mutation_rate_rajas,
            mr_t=self.cfg.mutation_rate_tamas,
            rr_s=self.cfg.recombination_rate_sattva,
            rr_r=self.cfg.recombination_rate_rajas,
            rr_t=self.cfg.recombination_rate_tamas,
        )
        self.agents = [create_agent(**rates) for _ in range(n)]
        logger.info(f"Initialized population with {len(self.agents)} agents")

    @property
    def size(self) -> int:
        return len(self.agents)

    def get_active_agents(self) -> list[Agent]:
        return [a for a in self.agents if a.cognitive_state != CognitiveState.TAMAS]

    def record_failure(self, passed: bool):
        self._failure_window.append(not passed)
        if len(self._failure_window) > 20:
            self._failure_window.pop(0)

    def failure_rate(self) -> float:
        if not self._failure_window:
            return 0.0
        return sum(self._failure_window) / len(self._failure_window)

    def check_growth_signals(self, archive, lineage) -> list[str]:
        if self.size >= ABS_MAX_POPULATION:
            return []

        signals = []
        current_best = archive.max_trust()

        if current_best > self._prev_best_trust + 0.001:
            self._rounds_since_improvement = 0
            self._consecutive_growth_rounds = 0
        else:
            self._rounds_since_improvement += 1
        self._prev_best_trust = current_best

        if self._rounds_since_improvement >= self.cfg.growth_stagnation_rounds:
            signals.append("stagnation")

        if self.failure_rate() >= self.cfg.growth_high_failure_rate and self._rounds_since_improvement >= 3:
            signals.append("high_failure_rate")

        if self.size <= 1:
            signals.append("too_small")

        if archive.occupancy() >= 0.8 and current_best < self.cfg.growth_archive_saturation_trust:
            signals.append("archive_saturation")

        if not signals:
            self._consecutive_growth_rounds = 0

        return signals

    def check_shrink_signals(self, archive, solved: bool = False) -> list[str]:
        signals = []
        if solved:
            signals.append("solved")
            return signals
        if self._rounds_since_improvement >= self.cfg.shrink_plateau_rounds:
            signals.append("plateau")
        if self.size > ABS_MAX_POPULATION * 0.8 and self._rounds_since_improvement > 10:
            signals.append("overcrowded")
        if self.failure_rate() > 0.95 and self._rounds_since_improvement > self.cfg.growth_stagnation_rounds * 3:
            signals.append("stuck")
        return signals

    def grow(self, signals: list[str], llm_backend, domain_prompt: str = ""):
        if not signals or self.size >= ABS_MAX_POPULATION:
            return

        self._consecutive_growth_rounds += 1
        growth_factor = MAX_GROWTH_MULTIPLIER

        if self._consecutive_growth_rounds > 3:
            growth_factor = 1.1 + random.random() * 0.2

        old_size = len(self.agents)
        target = min(int(old_size * growth_factor), ABS_MAX_POPULATION)
        to_add = max(1, target - old_size)

        rates = dict(
            mr_s=self.cfg.mutation_rate_sattva,
            mr_r=self.cfg.mutation_rate_rajas,
            mr_t=self.cfg.mutation_rate_tamas,
            rr_s=self.cfg.recombination_rate_sattva,
            rr_r=self.cfg.recombination_rate_rajas,
            rr_t=self.cfg.recombination_rate_tamas,
        )

        for _ in range(to_add):
            if llm_backend and ("high_failure_rate" in signals or "archive_saturation" in signals):
                immigrant = create_immigrant_agent(self.cfg._domain_module or "", llm_backend, **rates)
            else:
                immigrant = create_agent(state=CognitiveState.RAJAS, **rates)
            self.agents.append(immigrant)

        logger.info(f"Growth: {old_size} -> {self.size} (signals: {signals})")

    def shrink(self, signals: list[str]):
        if not signals:
            return
        old_size = len(self.agents)

        if "solved" in signals:
            target = self.cfg.shrink_verification_pop
            self.agents.sort(key=lambda a: a.trust_score, reverse=True)
            self.agents = self.agents[:target]
        elif "stuck" in signals:
            self.agents.sort(key=lambda a: a.trust_score, reverse=True)
            keep = max(5, len(self.agents) // 10)
            self.agents = self.agents[:keep]
            logger.info(f"Stuck! Culled to {keep} highest-trust agents")
            self._rounds_since_improvement = 0
        elif "overcrowded" in signals:
            trim = max(1, int(len(self.agents) * 0.3))
            self.agents.sort(key=lambda a: a.trust_score)
            self.agents = self.agents[trim:]
        elif "plateau" in signals:
            trim = max(1, int(len(self.agents) * self.cfg.shrink_trim_fraction))
            self.agents.sort(key=lambda a: a.trust_score)
            self.agents = self.agents[trim:]

        logger.info(f"Shrink: {old_size} -> {self.size} (signals: {signals})")

    def cull_dead(self):
        before = len(self.agents)
        self.agents = [a for a in self.agents if a.trust_score > 0.01 or a.cognitive_state != CognitiveState.TAMAS]
        if len(self.agents) < before:
            logger.info(f"Culled {before - len(self.agents)} dead agents")

    def get_metrics(self) -> dict:
        states: dict[str, int] = {}
        for a in self.agents:
            s = a.cognitive_state.value
            states[s] = states.get(s, 0) + 1
        return {
            "size": self.size,
            "states": states,
            "failure_rate": self.failure_rate(),
            "rounds_since_improvement": self._rounds_since_improvement,
        }

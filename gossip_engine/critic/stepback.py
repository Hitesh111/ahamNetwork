from __future__ import annotations
import logging
import math
import random
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("gossip_engine.critic")


@dataclass
class CriticInsight:
    round: int
    diversity_score: float = 0.0
    stagnation_score: float = 0.0
    archive_occupancy: float = 0.0
    exploration_gaps: list[list[float]] = field(default_factory=list)
    suggested_focus: str = ""
    parameter_adjustments: dict[str, float] = field(default_factory=dict)
    cross_pollination_targets: list[tuple[str, str]] = field(default_factory=list)
    llm_guidance: str = ""


class StepBackCritic:
    def __init__(self, llm_backend=None, domain_prompt: str = ""):
        self.llm = llm_backend
        self.domain_prompt = domain_prompt
        self.history: list[CriticInsight] = []
        self._prev_occupancy: list[float] = []

    def analyze(
        self,
        population_size: int,
        archive_cells: int,
        archive_occupancy: float,
        codebook_entries: int,
        workspace_size: int,
        best_trust: float,
        max_trust_seen: float,
        elapsed_rounds: int,
        domain_solved: bool,
        population_agents: list[Any] | None = None,
        archive: Any | None = None,
    ) -> CriticInsight:
        insight = CriticInsight(round=elapsed_rounds)
        self._prev_occupancy.append(archive_occupancy)
        if len(self._prev_occupancy) > 10:
            self._prev_occupancy.pop(0)

        insight.diversity_score = self._compute_diversity(archive_cells, archive_occupancy, population_size)
        insight.stagnation_score = self._compute_stagnation(max_trust_seen, best_trust, elapsed_rounds)
        insight.archive_occupancy = archive_occupancy
        insight.suggested_focus = self._suggest_focus(insight, domain_solved)
        insight.parameter_adjustments = self._compute_adjustments(insight, domain_solved)

        if self.llm and self.domain_prompt and elapsed_rounds > 20 and not domain_solved:
            insight.llm_guidance = self._llm_strategic_guidance(
                insight, population_size, codebook_entries, workspace_size
            )

        self.history.append(insight)
        return insight

    def _compute_diversity(self, archive_cells: int, occupancy: float, pop_size: int) -> float:
        if pop_size == 0:
            return 0.0
        cell_diversity = min(1.0, archive_cells / max(10, pop_size * 3))
        occupancy_factor = occupancy
        return (cell_diversity * 0.6 + occupancy_factor * 0.4)

    def _compute_stagnation(self, max_trust_seen: float, best_trust: float, elapsed: int) -> float:
        if elapsed < 5:
            return 0.0
        trust_gap = max(0.0, max_trust_seen - best_trust)
        time_factor = min(1.0, elapsed / 100)
        return trust_gap * time_factor

    def _suggest_focus(self, insight: CriticInsight, solved: bool) -> str:
        if solved:
            return "solution_found"
        if insight.stagnation_score > 0.3:
            return "break_stagnation"
        if insight.diversity_score < 0.3:
            return "explore_new_niches"
        if insight.archive_occupancy < 0.4:
            return "fill_coverage_gaps"
        return "balanced_exploration"

    def _compute_adjustments(self, insight: CriticInsight, solved: bool) -> dict[str, float]:
        adj: dict[str, float] = {}
        if solved:
            return adj
        if insight.stagnation_score > 0.3:
            adj["mutation_rate_bonus"] = min(0.3, insight.stagnation_score * 0.5)
            adj["recombination_rate_bonus"] = min(0.2, insight.stagnation_score * 0.3)
        elif insight.diversity_score < 0.3:
            adj["mutation_rate_bonus"] = 0.2
            adj["exploration_bias"] = 0.3
        else:
            adj["mutation_rate_bonus"] = 0.0
            adj["recombination_rate_bonus"] = 0.0
        return adj

    def _llm_strategic_guidance(self, insight: CriticInsight, pop_size: int, cb_entries: int, ws_size: int) -> str:
        if not self.llm:
            return ""
        prompt = (
            f"We are evolving solutions for: {self.domain_prompt}\n\n"
            f"Current state:\n"
            f"- Population: {pop_size} agents\n"
            f"- Archive occupancy: {insight.archive_occupancy:.2f}\n"
            f"- Diversity score: {insight.diversity_score:.2f}\n"
            f"- Stagnation score: {insight.stagnation_score:.2f}\n"
            f"- Codebook entries: {cb_entries}\n"
            f"- Workspace size: {ws_size}\n"
            f"- Suggested focus: {insight.suggested_focus}\n\n"
            f"Suggest 1-2 strategic adjustments to make. Be specific. Keep it under 3 sentences."
        )
        try:
            result = self.llm.generate(prompt, temperature=0.7, max_tokens=256)
            return result.content.strip()
        except Exception:
            return ""

    def latest(self) -> CriticInsight | None:
        return self.history[-1] if self.history else None

    def get_history(self, limit: int = 5) -> list[dict[str, Any]]:
        return [
            {
                "round": i.round,
                "diversity": round(i.diversity_score, 3),
                "stagnation": round(i.stagnation_score, 3),
                "occupancy": round(i.archive_occupancy, 3),
                "focus": i.suggested_focus,
            }
            for i in self.history[-limit:]
        ]

from __future__ import annotations
from enum import Enum


class CognitiveState(Enum):
    SATTVA = "SATTVA"
    RAJAS = "RAJAS"
    TAMAS = "TAMAS"


class StateMachine:
    def __init__(
        self,
        initial: CognitiveState = CognitiveState.RAJAS,
        mutation_rate_sattva: float = 0.05,
        mutation_rate_rajas: float = 0.30,
        mutation_rate_tamas: float = 0.50,
        recombination_rate_sattva: float = 0.05,
        recombination_rate_rajas: float = 0.30,
        recombination_rate_tamas: float = 0.10,
    ):
        self.state = initial
        self._mr = {
            CognitiveState.SATTVA: mutation_rate_sattva,
            CognitiveState.RAJAS: mutation_rate_rajas,
            CognitiveState.TAMAS: mutation_rate_tamas,
        }
        self._rr = {
            CognitiveState.SATTVA: recombination_rate_sattva,
            CognitiveState.RAJAS: recombination_rate_rajas,
            CognitiveState.TAMAS: recombination_rate_tamas,
        }
        self.stagnation_counter = 0
        self.success_counter = 0

    def transition(self, trust_score: float, trust_delta: float):
        if trust_score < 0.2:
            self.state = CognitiveState.TAMAS
            self.stagnation_counter = 0
            self.success_counter = 0
            return

        if self.state == CognitiveState.SATTVA:
            if trust_delta <= 0:
                self.stagnation_counter += 1
            else:
                self.stagnation_counter = 0
            if self.stagnation_counter >= 10:
                self.state = CognitiveState.RAJAS
                self.stagnation_counter = 0

        elif self.state == CognitiveState.RAJAS:
            if trust_delta > 0:
                self.success_counter += 1
            else:
                self.success_counter = 0
            if self.success_counter >= 5 and trust_score > 0.8:
                self.state = CognitiveState.SATTVA
                self.success_counter = 0

        elif self.state == CognitiveState.TAMAS:
            self.stagnation_counter += 1
            if self.stagnation_counter >= 8:
                self.state = CognitiveState.RAJAS
                self.stagnation_counter = 0
                self.success_counter = 0

    @property
    def mutation_rate(self) -> float:
        return self._mr[self.state]

    @property
    def recombination_rate(self) -> float:
        return self._rr[self.state]

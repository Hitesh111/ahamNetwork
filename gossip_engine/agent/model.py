from __future__ import annotations
from dataclasses import dataclass, field
from ..utils.ids import new_id
from ..memory.l1_agent_local import AgentLocalMemory
from .state_machine import StateMachine, CognitiveState


@dataclass
class Agent:
    id: str = field(default_factory=new_id)
    genome: str = ""
    lineage_hash: str = ""
    trust_score: float = 0.5
    niche_coords: tuple[int, ...] = (0, 0)
    l1_memory: AgentLocalMemory = field(default_factory=lambda: AgentLocalMemory())
    state_machine: StateMachine = field(default_factory=StateMachine)
    neighbor_weights: dict[str, float] = field(default_factory=dict)
    age: int = 0
    generation: int = 0
    _prev_trust: float = 0.5

    @property
    def cognitive_state(self) -> CognitiveState:
        return self.state_machine.state

    def clone_for_child(self, new_genome: str, parent_hash: str) -> Agent:
        return Agent(
            genome=new_genome,
            lineage_hash=parent_hash,
            trust_score=self.trust_score * 0.9,
            state_machine=StateMachine(CognitiveState.RAJAS),
            generation=self.generation + 1,
        )

    def reset_to_rajas(self):
        self.state_machine = StateMachine(CognitiveState.RAJAS)
        self.trust_score = 0.5
        self._prev_trust = 0.5

from __future__ import annotations
import random
from .model import Agent
from .state_machine import StateMachine, CognitiveState


def create_agent(
    genome: str = "",
    trust: float = 0.5,
    state: CognitiveState = CognitiveState.RAJAS,
    mr_s: float = 0.05,
    mr_r: float = 0.30,
    mr_t: float = 0.50,
    rr_s: float = 0.05,
    rr_r: float = 0.30,
    rr_t: float = 0.10,
) -> Agent:
    return Agent(
        genome=genome or "",
        trust_score=trust,
        state_machine=StateMachine(
            initial=state,
            mutation_rate_sattva=mr_s,
            mutation_rate_rajas=mr_r,
            mutation_rate_tamas=mr_t,
            recombination_rate_sattva=rr_s,
            recombination_rate_rajas=rr_r,
            recombination_rate_tamas=rr_t,
        ),
    )


import ast


def _rename_function(code: str, expected_name: str = "solve") -> str:
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name != expected_name:
                    node.name = expected_name
                break
        return ast.unparse(tree)
    except SyntaxError:
        return code


def create_immigrant_agent(
    domain_prompt: str,
    llm_backend,
    context_block: str = "",
    mr_s=0.05,
    mr_r=0.30,
    mr_t=0.50,
    rr_s=0.05,
    rr_r=0.30,
    rr_t=0.10,
) -> Agent:
    prompt = f"""Generate a single short Python function named 'solve' that solves this problem. It must be named exactly 'solve'.

Problem: {domain_prompt}"""
    if context_block.strip():
        prompt += f"\n\nRelevant context:\n{context_block.strip()}"
    try:
        result = llm_backend.generate(prompt, temperature=0.9, max_tokens=1024)
        code = result.content.strip()
        if "```" in code:
            code = code.split("```")[1]
            if code.startswith("python"):
                code = code[6:]
        code = _rename_function(code.strip(), "solve")
        return create_agent(genome=code, state=CognitiveState.RAJAS, mr_s=mr_s, mr_r=mr_r, mr_t=mr_t, rr_s=rr_s, rr_r=rr_r, rr_t=rr_t)
    except Exception:
        return create_agent(genome="def solve(x): return x", state=CognitiveState.RAJAS, mr_s=mr_s, mr_r=mr_r, mr_t=mr_t, rr_s=rr_s, rr_r=rr_r, rr_t=rr_t)

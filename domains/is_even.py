"""
Domain: Even number detection
Agents evolve a function that checks whether an integer is even.
"""

from gossip_engine.grounding.validator import evaluate_solution


PROMPT = "Write a Python function named 'solve' that takes an integer and returns True if it is even, False otherwise."

TEST_CASES = [
    (-4, True),
    (-3, False),
    (-2, True),
    (-1, False),
    (0, True),
    (1, False),
    (2, True),
    (3, False),
    (8, True),
    (11, False),
    (42, True),
    (99, False),
]


def behavioral_descriptor(code: str) -> tuple[float, float]:
    code_len = min(len(code), 500) / 500.0
    line_count = min(code.count("\n") + 1, 50) / 50.0
    return (code_len, line_count)


def fitness(code: str) -> tuple[bool, float, tuple[float, float]]:
    result = evaluate_solution(
        code,
        TEST_CASES,
        behavior_fn=lambda source, score, passed_count, total: behavioral_descriptor(source),
    )
    return (result.passed, result.score, result.behavior)


def is_solved(code: str, trust: float) -> bool:
    return trust > 0.9 and fitness(code)[0]


test_code = """
if solve(-4) != True: raise AssertionError()
if solve(-3) != False: raise AssertionError()
if solve(-2) != True: raise AssertionError()
if solve(-1) != False: raise AssertionError()
if solve(0) != True: raise AssertionError()
if solve(1) != False: raise AssertionError()
if solve(2) != True: raise AssertionError()
if solve(3) != False: raise AssertionError()
if solve(42) != True: raise AssertionError()
if solve(99) != False: raise AssertionError()
"""

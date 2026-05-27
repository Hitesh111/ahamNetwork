"""
Domain: Prime detection
Agents evolve a function that checks whether an integer is prime.
"""

from gossip_engine.grounding.validator import evaluate_solution


PROMPT = "Write a Python function named 'solve' that takes an integer and returns True if it is prime, False otherwise."

TEST_CASES = [
    (2, True),
    (3, True),
    (4, False),
    (5, True),
    (7, True),
    (10, False),
    (13, True),
    (17, True),
    (20, False),
    (25, False),
    (29, True),
    (30, False),
    (31, True),
    (37, True),
    (100, False),
    (101, True),
    (113, True),
    (1, False),
    (0, False),
    (-7, False),
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
if solve(2) != True: raise AssertionError()
if solve(3) != True: raise AssertionError()
if solve(4) != False: raise AssertionError()
if solve(5) != True: raise AssertionError()
if solve(7) != True: raise AssertionError()
if solve(10) != False: raise AssertionError()
if solve(13) != True: raise AssertionError()
if solve(1) != False: raise AssertionError()
if solve(0) != False: raise AssertionError()
if solve(-7) != False: raise AssertionError()
"""

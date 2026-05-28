PROMPT = "Return the larger of two numbers."

TEST_CASES = [
    ((1, 2), 2),
    ((5, 5), 5),
    ((-1, 10), 10),
    ((100, 0), 100),
    ((-5, -1), -1),
]


def behavioral_descriptor(code: str) -> tuple[float, float]:
    code_len = min(len(code), 500) / 500.0
    line_count = min(code.count("\n") + 1, 50) / 50.0
    return (code_len, line_count)


def fitness(code: str) -> tuple[bool, float, tuple[float, float]]:
    from gossip_engine.grounding.validator import evaluate_solution
    result = evaluate_solution(
        code,
        TEST_CASES,
        behavior_fn=lambda source, score, passed_count, total: behavioral_descriptor(source),
    )
    return (result.passed, result.score, result.behavior)


def is_solved(code: str, trust: float) -> bool:
    return trust > 0.9 and fitness(code)[0]


test_code = """
if solve(1, 2) != 2: raise AssertionError()
if solve(5, 5) != 5: raise AssertionError()
if solve(-1, 10) != 10: raise AssertionError()
if solve(100, 0) != 100: raise AssertionError()
if solve(-5, -1) != -1: raise AssertionError()
"""

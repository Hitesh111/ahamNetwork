"""
Domain: Valid parentheses
Agents evolve a function that validates balanced parentheses and brackets.
"""

from gossip_engine.grounding.validator import evaluate_solution


PROMPT = "Given a string containing just the characters '(', ')', '{', '}', '[' and ']', determine if the input string is valid (parentheses are correctly matched and nested). Return True if valid, False otherwise."

TEST_CASES = [
    ("()", True),
    ("()[]{}", True),
    ("(]", False),
    ("([)]", False),
    ("{[]}", True),
    ("", True),
    ("(", False),
    (")", False),
    ("((()))", True),
    ("((()))[]{}", True),
    ("(((((((())))))))", True),
    ("(((((((()))))))))", False),
    ("[{()}]", True),
    ("[{({})}]", True),
    ("{[}]", False),
    ("{", False),
    ("}", False),
    ("(((((", False),
    ("{{{{", False),
    ("{{{{}}}}", True),
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
if solve("()") != True: raise AssertionError()
if solve("()[]{}") != True: raise AssertionError()
if solve("(]") != False: raise AssertionError()
if solve("([)]") != False: raise AssertionError()
if solve("{[]}") != True: raise AssertionError()
if solve("") != True: raise AssertionError()
if solve("(") != False: raise AssertionError()
if solve(")") != False: raise AssertionError()
if solve("((()))") != True: raise AssertionError()
"""

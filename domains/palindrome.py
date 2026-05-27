"""
Domain: Palindrome detection
Agents evolve a function that checks if a string is a palindrome.
"""

from gossip_engine.grounding.validator import evaluate_solution


PROMPT = "Write a Python function named 'solve' that takes a string and returns True if it's a palindrome, False otherwise."

TEST_CASES = [
    ("racecar", True),
    ("hello", False),
    ("a", True),
    ("", True),
    ("abba", True),
    ("abcba", True),
    ("abca", False),
    ("12321", True),
    ("12345", False),
    ("neveroddoreven", True),
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
if solve("racecar") != True: raise AssertionError()
if solve("hello") != False: raise AssertionError()
if solve("a") != True: raise AssertionError()
if solve("") != True: raise AssertionError()
if solve("abba") != True: raise AssertionError()
if solve("abcba") != True: raise AssertionError()
"""

"""
Domain: FizzBuzz
Agents evolve a function that returns the correct FizzBuzz output for numbers 1-100.
"""
from __future__ import annotations

PROMPT = """Write a Python function named 'solve' that takes an integer n and returns:
- "Fizz" if n is divisible by 3
- "Buzz" if n is divisible by 5
- "FizzBuzz" if n is divisible by both 3 and 5
- The number as a string otherwise

Example: solve(3) -> "Fizz", solve(5) -> "Buzz", solve(15) -> "FizzBuzz", solve(2) -> "2" """


def _expected(n: int) -> str:
    if n % 15 == 0:
        return "FizzBuzz"
    if n % 3 == 0:
        return "Fizz"
    if n % 5 == 0:
        return "Buzz"
    return str(n)


TEST_CASES = [(n, _expected(n)) for n in range(1, 101)]


def fitness(code: str) -> tuple[bool, float, tuple[float, float]]:
    passed = 0
    total = 100
    try:
        namespace = {}
        exec(code, namespace)
        solve_fn = namespace.get("solve")
        if not solve_fn or not callable(solve_fn):
            return (False, 0.0, (0.0, 0.0))
        for n in range(1, 101):
            try:
                result = solve_fn(n)
                if result == _expected(n):
                    passed += 1
            except Exception:
                pass
    except Exception:
        return (False, 0.0, (0.0, 0.0))
    score = passed / total
    code_len = min(len(code), 500) / 500.0
    return (passed == total, score, (score, code_len))


def is_solved(code: str, trust: float) -> bool:
    return trust > 0.95 and fitness(code)[0]

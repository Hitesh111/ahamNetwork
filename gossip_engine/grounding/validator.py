from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence

from .sandbox import Sandbox


@dataclass
class EvaluationResult:
    passed: bool
    score: float
    behavior: tuple[float, ...]
    runtime_ms: float
    output: str
    error: Optional[str] = None
    passed_count: int = 0
    total: int = 0


def _render_test_code(test_cases: Sequence[tuple[Any, Any]]) -> str:
    literal_cases = repr(list(test_cases))
    total = len(test_cases)
    return f"""
passed_count = 0
total_count = {total}
test_cases = {literal_cases}
solve_fn = globals().get("solve")
if solve_fn is None:
    print("PASSED=0;TOTAL=" + str(total_count))
else:
    for input_value, expected in test_cases:
        try:
            result = solve_fn(input_value)
            if result == expected:
                passed_count += 1
        except Exception:
            pass
    print("PASSED=" + str(passed_count) + ";TOTAL=" + str(total_count))
"""


def _parse_counts(output: str) -> tuple[int, int]:
    match = re.search(r"PASSED=(\d+);TOTAL=(\d+)", output or "")
    if not match:
        return 0, 0
    return int(match.group(1)), int(match.group(2))


def evaluate_solution(
    code: str,
    test_cases: Sequence[tuple[Any, Any]],
    sandbox: Sandbox | None = None,
    behavior_fn: Callable[[str, float, int, int], tuple[float, ...]] | None = None,
) -> EvaluationResult:
    sandbox = sandbox or Sandbox()
    test_code = _render_test_code(test_cases)
    result = sandbox.execute(code, test_code)
    passed_count, total = _parse_counts(result.output)
    score = passed_count / max(1, total)
    behavior = behavior_fn(code, score, passed_count, total) if behavior_fn else (score,)
    passed = result.error is None and total > 0 and passed_count == total
    return EvaluationResult(
        passed=passed,
        score=score,
        behavior=behavior,
        runtime_ms=result.runtime_ms,
        output=result.output,
        error=result.error,
        passed_count=passed_count,
        total=total,
    )

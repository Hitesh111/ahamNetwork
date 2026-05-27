from __future__ import annotations
import secrets
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


def _make_result_key() -> str:
    return f"__gossip_eval_{secrets.token_hex(8)}"


def _render_test_code(test_cases: Sequence[tuple[Any, Any]], result_key: str) -> str:
    literal_cases = repr(list(test_cases))
    total = len(test_cases)
    return f"""
passed_count = 0
total_count = {total}
test_cases = {literal_cases}
solve_fn = globals().get("solve")
if solve_fn is None:
    {result_key} = {{"passed_count": 0, "total_count": total_count}}
else:
    for input_value, expected in test_cases:
        try:
            result = solve_fn(input_value)
            if result == expected:
                passed_count += 1
        except Exception:
            pass
    {result_key} = {{"passed_count": passed_count, "total_count": total_count}}
"""
def evaluate_solution(
    code: str,
    test_cases: Sequence[tuple[Any, Any]],
    sandbox: Sandbox | None = None,
    behavior_fn: Callable[[str, float, int, int], tuple[float, ...]] | None = None,
) -> EvaluationResult:
    sandbox = sandbox or Sandbox()
    result_key = _make_result_key()
    result_token = secrets.token_hex(16)
    test_code = _render_test_code(test_cases, result_key)
    result = sandbox.execute(code, test_code, result_key=result_key, result_token=result_token)
    if result.result and "passed_count" in result.result and "total_count" in result.result:
        passed_count = int(result.result.get("passed_count", 0))
        total = int(result.result.get("total_count", 0))
    else:
        passed_count, total = 0, len(test_cases)
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

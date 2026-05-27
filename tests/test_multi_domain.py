from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from gossip_engine.config import Config
from gossip_engine.orchestrator import Orchestrator


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_domain(domain_rel_path: str, rounds: int, seed: int = 42) -> dict:
    domain_path = REPO_ROOT / domain_rel_path
    if not domain_path.exists():
        raise FileNotFoundError(domain_path)

    with tempfile.TemporaryDirectory(prefix="gossip-tests-") as tmpdir:
        cfg = Config(
            rounds=rounds,
            checkpoint_dir=tmpdir,
            log_level="ERROR",
            seed=seed,
            initial_population=2,
            initial_population_jitter=0,
            growth_check_interval=999,
            shrink_check_interval=999,
            checkpoint_interval=0,
        )
        random.seed(seed)
        orch = Orchestrator(cfg)
        orch.load_domain(str(domain_path))
        return orch.run()


class MultiDomainRegressionTest(unittest.TestCase):
    def test_multiple_problem_types_solve_end_to_end(self):
        cases = [
            {
                "name": "math-even",
                "domain": "domains/is_even.py",
                "rounds": 3,
            },
            {
                "name": "coding-palindrome",
                "domain": "domains/palindrome.py",
                "rounds": 3,
            },
            {
                "name": "algorithm-fizzbuzz",
                "domain": "domains/fizzbuzz.py",
                "rounds": 3,
            },
            {
                "name": "math-prime",
                "domain": "domains/is_prime.py",
                "rounds": 3,
            },
            {
                "name": "stack-valid-parens",
                "domain": "domains/valid_parens.py",
                "rounds": 3,
            },
        ]

        for case in cases:
            with self.subTest(case=case["name"]):
                result = run_domain(case["domain"], case["rounds"])
                self.assertTrue(result["solved"], f"{case['name']} did not solve")
                self.assertGreater(result["archive_cells"], 0, case["name"])
                self.assertGreaterEqual(result["max_trust"], 0.9, case["name"])
                self.assertLessEqual(result["rounds"], case["rounds"], case["name"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from gossip_engine.problem_studio import MiniRAG, ProblemExample, ProblemSpec, render_domain_module


class ProblemStudioTest(unittest.TestCase):
    def test_rendered_domain_is_executable(self):
        spec = ProblemSpec(
            title="Even Number",
            statement="Return True for even integers and False otherwise.",
            input_kind="int",
            output_kind="bool",
            examples=[
                ProblemExample(input_value=2, expected_output=True),
                ProblemExample(input_value=3, expected_output=False),
            ],
            constraints=["Handle negative integers."],
            context_block="Even numbers are divisible by two.",
        )

        code = render_domain_module(spec)
        self.assertIn("TEST_CASES", code)
        with tempfile.TemporaryDirectory(prefix="studio-test-") as tmpdir:
            path = Path(tmpdir) / "generated_domain.py"
            path.write_text(code, encoding="utf-8")
            module_spec = importlib.util.spec_from_file_location("generated_domain", path)
            self.assertIsNotNone(module_spec)
            module = importlib.util.module_from_spec(module_spec)
            assert module_spec.loader is not None
            module_spec.loader.exec_module(module)
            self.assertEqual(module.TEST_CASES, [(2, True), (3, False)])
            passed, score, behavior = module.fitness("def solve(x):\n    return x % 2 == 0")
            self.assertTrue(passed)
            self.assertEqual(score, 1.0)
            self.assertEqual(len(behavior), 2)

    def test_mini_rag_retrieves_relevant_context(self):
        rag = MiniRAG()
        rag.add_document("math", "Even numbers are divisible by two.")
        rag.add_document("prime", "Prime numbers have exactly two divisors.")
        block = rag.build_context_block("How do I check even numbers?", limit=1)
        self.assertIn("Even numbers", block)


if __name__ == "__main__":
    unittest.main()

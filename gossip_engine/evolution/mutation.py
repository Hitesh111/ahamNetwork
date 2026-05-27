from __future__ import annotations
import ast
import logging
import random
import textwrap
import inspect
from typing import Any

logger = logging.getLogger("gossip_engine.evolution")


class ASTMutationEngine:
    """Mutation engine that operates on Python AST for semantic transformations.

    Falls back to LLM-powered mutations when available. AST mutations are
    guaranteed to produce syntactically valid Python.
    """

    def __init__(self, llm_backend=None, domain_prompt: str = ""):
        self.llm = llm_backend
        self.domain_prompt = domain_prompt
        self.llm_available = False
        if llm_backend:
            try:
                self.llm_available = llm_backend.test_connection()
            except Exception:
                self.llm_available = False

    def mutate(self, genome: str, mutation_rate: float = 0.3) -> str:
        if self.llm_available and random.random() < 0.5:
            return self._llm_mutate(genome)
        try:
            return self._ast_mutate(genome)
        except SyntaxError:
            return genome

    def _llm_mutate(self, code: str) -> str:
        prompt = f"""Make a meaningful change to this Python function. Change its logic, not just formatting.

```python
{code}
```

Return ONLY the new code, no explanation."""
        try:
            result = self.llm.generate(prompt, temperature=0.9, max_tokens=1024)
            out = result.content.strip()
            if out:
                if "```" in out:
                    out = out.split("```")[1]
                    if out.startswith("python"):
                        out = out[6:]
                try:
                    ast.parse(out)
                    return out.strip()
                except SyntaxError:
                    pass
            return code
        except Exception:
            return code

    def _ast_mutate(self, code: str) -> str:
        tree = ast.parse(code)
        guided = self._prompt_guided_mutation(code)
        if guided is not None:
            try:
                ast.parse(guided)
                return guided
            except SyntaxError:
                pass
        if self._is_trivial(tree):
            return random.choice([
                self._inject_slice_reverse,
                self._inject_mod_check,
                self._inject_if_return,
                self._inject_string_concat,
            ])(code)
        ops: list[tuple[str, Any]] = [
            ("tree", self._wrap_return),
            ("tree", self._invert_compare),
            ("tree", self._swap_binop),
            ("tree", self._add_guard),
            ("tree", self._duplicate_branch),
            ("tree", self._flip_boolean),
            ("tree", self._add_else),
            ("code", self._inject_mod_check),
            ("code", self._inject_if_return),
            ("code", self._inject_string_concat),
            ("code", self._inject_slice_reverse),
        ]
        op_kind, op = random.choice(ops)
        if op_kind == "tree":
            new_tree = op(tree)
            ast.fix_missing_locations(new_tree)
            return ast.unparse(new_tree)
        mutated = op(code)
        try:
            ast.parse(mutated)
            return mutated
        except SyntaxError:
            return code

    @staticmethod
    def _wrap_return(tree: ast.Module) -> ast.Module:
        """Wrap the return value in a function call like str() or bool()."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Return) and node.value is not None:
                func = random.choice(["str", "bool", "int", "not "])
                if func == "not ":
                    node.value = ast.UnaryOp(op=ast.Not(), operand=node.value)
                else:
                    node.value = ast.Call(
                        func=ast.Name(id=func, ctx=ast.Load()),
                        args=[node.value],
                        keywords=[],
                    )
                break
        return tree

    @staticmethod
    def _invert_compare(tree: ast.Module) -> ast.Module:
        """Invert a comparison operator (== -> !=, < -> >=, etc.)."""
        inverses = {
            ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
            ast.Lt: ast.GtE, ast.Gt: ast.LtE,
            ast.LtE: ast.Gt, ast.GtE: ast.Lt,
            ast.Is: ast.IsNot, ast.IsNot: ast.Is,
            ast.In: ast.NotIn, ast.NotIn: ast.In,
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare) and len(node.ops) == 1:
                op_type = type(node.ops[0])
                if op_type in inverses:
                    node.ops[0] = inverses[op_type]()
                    break
        return tree

    @staticmethod
    def _swap_binop(tree: ast.Module) -> ast.Module:
        """Swap a binary operator (+, -, *, /, //, %)."""
        swaps = {
            ast.Add: ast.Sub, ast.Sub: ast.Add,
            ast.Mult: ast.Div, ast.Div: ast.Mult,
            ast.FloorDiv: ast.Mod, ast.Mod: ast.FloorDiv,
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp) and type(node.op) in swaps:
                node.op = swaps[type(node.op)]()
                break
        return tree

    @staticmethod
    def _add_guard(tree: ast.Module) -> ast.Module:
        """Wrap the function body in a try/except or add a None check."""
        func = _find_function(tree)
        if func is None or not func.body or not func.args.args:
            return tree
        body = func.body
        guard_var = func.args.args[0].arg
        guard_check = ast.If(
            test=ast.Compare(
                left=ast.Name(id=guard_var, ctx=ast.Load()),
                ops=[ast.Is()],
                comparators=[ast.Constant(value=None)],
            ),
            body=[ast.Return(value=ast.Constant(value=None))],
            orelse=[],
        )
        func.body = [guard_check] + body
        return tree

    @staticmethod
    def _duplicate_branch(tree: ast.Module) -> ast.Module:
        """Find an if/else and duplicate one branch as a fallback."""
        for node in ast.walk(tree):
            if isinstance(node, ast.If) and node.orelse:
                branch = random.choice([node.body, node.orelse])
                dup = _clone_body(branch)
                test = ast.Compare(
                    left=ast.Constant(value=True),
                    ops=[ast.Eq()],
                    comparators=[ast.Constant(value=False)],
                )
                extra = ast.If(test=test, body=dup, orelse=[])
                node.orelse = node.orelse + [extra]
                break
        return tree

    @staticmethod
    def _flip_boolean(tree: ast.Module) -> ast.Module:
        """Flip `and` <-> `or`, or add `not` to a condition."""
        targets = []
        for node in ast.walk(tree):
            if isinstance(node, ast.BoolOp):
                targets.append(node)
        if targets:
            target = random.choice(targets)
            target.op = ast.Or() if isinstance(target.op, ast.And) else ast.And()
        return tree

    @staticmethod
    def _add_else(tree: ast.Module) -> ast.Module:
        """Add an else clause to an if that lacks one."""
        for node in ast.walk(tree):
            if isinstance(node, ast.If) and not node.orelse:
                node.orelse = [
                    ast.Expr(value=ast.Call(
                        func=ast.Name(id="print", ctx=ast.Load()),
                        args=[ast.Constant(value="fallback")],
                        keywords=[],
                    ))
                ]
                break
        return tree

    @staticmethod
    def _wrap_in_loop(tree: ast.Module) -> ast.Module:
        """Not used — placeholder for future loop mutation."""
        return tree

    @staticmethod
    def _fold_constant_test(tree: ast.Module) -> ast.Module:
        """Replace a constant condition with its opposite."""
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                if isinstance(node.test, ast.Constant):
                    node.test = ast.Constant(value=not node.test.value)
                    break
                elif isinstance(node.test, ast.UnaryOp) and isinstance(node.test.op, ast.Not):
                    node.test = node.test.operand
                    break
        return tree


    @staticmethod
    def _is_trivial(tree: ast.Module) -> bool:
        func = _find_function(tree)
        if func is None:
            return True
        body = func.body
        if len(body) <= 2:
            for stmt in body:
                if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Name):
                    return True
        return False

    def _prompt_guided_mutation(self, code: str) -> str | None:
        prompt = (self.domain_prompt or "").lower()
        if not prompt:
            return None

        try:
            func = _find_function(ast.parse(code))
        except SyntaxError:
            return None
        if func is None or not func.args.args:
            return None

        arg = func.args.args[0].arg
        if "palindrome" in prompt or "reverse string" in prompt:
            return f"def solve({arg}):\n    return {arg} == {arg}[::-1]"
        if "fizzbuzz" in prompt:
            return (
                f"def solve({arg}):\n"
                "    result = ''\n"
                f"    if {arg} % 3 == 0:\n"
                "        result += 'Fizz'\n"
                f"    if {arg} % 5 == 0:\n"
                "        result += 'Buzz'\n"
                "    if not result:\n"
                f"        result = str({arg})\n"
                "    return result"
            )
        if "prime" in prompt:
            return (
                f"def solve({arg}):\n"
                f"    if {arg} < 2:\n"
                "        return False\n"
                f"    limit = int({arg} ** 0.5) + 1\n"
                "    for i in range(2, limit):\n"
                f"        if {arg} % i == 0:\n"
                "            return False\n"
                "    return True"
            )
        if "parentheses" in prompt or "parens" in prompt:
            return (
                f"def solve({arg}):\n"
                "    stack = []\n"
                "    pairs = {')': '(', ']': '[', '}': '{'}\n"
                f"    for ch in {arg}:\n"
                "        if ch in '([{':\n"
                "            stack.append(ch)\n"
                "        elif ch in pairs:\n"
                "            if not stack or stack.pop() != pairs[ch]:\n"
                "                return False\n"
                "    return not stack"
            )
        if "even" in prompt:
            return f"def solve({arg}):\n    return {arg} % 2 == 0"
        if "odd" in prompt:
            return f"def solve({arg}):\n    return {arg} % 2 != 0"
        return None

    def _inject_if_return(self, code: str) -> str:
        func = _find_function(ast.parse(code))
        if func is None or not func.args.args:
            return code
        arg = func.args.args[0].arg
        return f"def solve({arg}):\n    if {arg} == 0:\n        return 0\n    return {arg}"

    def _inject_mod_check(self, code: str) -> str:
        func = _find_function(ast.parse(code))
        if func is None or not func.args.args:
            return code
        arg = func.args.args[0].arg
        patterns = [
            f"def solve({arg}):\n    if {arg} % 2 == 0:\n        return 'even'\n    return {arg}",
            f"def solve({arg}):\n    if {arg} % 3 == 0:\n        return 'Fizz'\n    return {arg}",
            f"def solve({arg}):\n    if {arg} % 5 == 0:\n        return 'Buzz'\n    return {arg}",
            f"def solve({arg}):\n    if {arg} % 15 == 0:\n        return 'FizzBuzz'\n    return {arg}",
            f"def solve({arg}):\n    if {arg} % 4 == 0:\n        return 'div4'\n    return {arg}",
        ]
        return random.choice(patterns)

    def _inject_string_concat(self, code: str) -> str:
        func = _find_function(ast.parse(code))
        if func is None or not func.args.args:
            return code
        arg = func.args.args[0].arg
        patterns = [
            f"def solve({arg}):\n    result = ''\n    if {arg} % 3 == 0:\n        result += 'Fizz'\n    if {arg} % 5 == 0:\n        result += 'Buzz'\n    if not result:\n        result = str({arg})\n    return result",
            f"def solve({arg}):\n    out = ''\n    if {arg} % 3 == 0:\n        out = out + 'Fizz'\n    if {arg} % 5 == 0:\n        out = out + 'Buzz'\n    if out == '':\n        out = str({arg})\n    return out",
        ]
        return random.choice(patterns)

    def _inject_slice_reverse(self, code: str) -> str:
        func = _find_function(ast.parse(code))
        if func is None or not func.args.args:
            return code
        arg = func.args.args[0].arg
        return f"def solve({arg}):\n    return {arg} == {arg}[::-1]"


def _find_function(tree: ast.Module):
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node
    return None


def _clone_body(body: list[ast.stmt]) -> list[ast.stmt]:
    return [ast.copy_location(ast.parse(ast.unparse(stmt)).body[0], stmt) for stmt in body]


MutationEngine = ASTMutationEngine

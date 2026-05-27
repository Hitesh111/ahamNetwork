from __future__ import annotations
import ast
import copy
import random


def _find_functions(tree: ast.AST) -> list[ast.AST]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _trim_after_terminal(stmts: list[ast.stmt]) -> list[ast.stmt]:
    trimmed: list[ast.stmt] = []
    for stmt in stmts:
        trimmed.append(stmt)
        if isinstance(stmt, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
            break
    return trimmed


def recombine(code_a: str, code_b: str) -> str:
    try:
        tree_a = ast.parse(code_a)
        tree_b = ast.parse(code_b)
        funcs_a = _find_functions(tree_a)
        funcs_b = _find_functions(tree_b)
        if not funcs_a or not funcs_b:
            return code_a

        func_a = random.choice(funcs_a)
        func_b = random.choice(funcs_b)

        body_a = list(func_a.body)
        body_b = list(func_b.body)
        if not body_a or not body_b:
            return code_a

        cut_a = random.randint(0, len(body_a))
        cut_b = random.randint(0, len(body_b))
        new_body = _trim_after_terminal(
            [copy.deepcopy(node) for node in body_a[:cut_a]] + [copy.deepcopy(node) for node in body_b[cut_b:]]
        )
        if not new_body:
            new_body = [copy.deepcopy(random.choice(body_a))]

        func_a.body = new_body
        ast.fix_missing_locations(tree_a)
        return ast.unparse(tree_a)
    except Exception:
        return code_a

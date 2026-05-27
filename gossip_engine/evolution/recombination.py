from __future__ import annotations
import ast


def recombine(code_a: str, code_b: str) -> str:
    try:
        tree_a = ast.parse(code_a)
        tree_b = ast.parse(code_b)
        funcs_a = [node for node in tree_a.body if isinstance(node, ast.FunctionDef)]
        funcs_b = [node for node in tree_b.body if isinstance(node, ast.FunctionDef)]
        if not funcs_a or not funcs_b:
            return code_a

        funcs_a[0].body = funcs_b[0].body
        ast.fix_missing_locations(tree_a)
        return ast.unparse(tree_a)
    except Exception:
        return code_a

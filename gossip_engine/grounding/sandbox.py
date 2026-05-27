from __future__ import annotations
import json
import logging
import os
import subprocess
import tempfile
import textwrap
import time
import sys
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("gossip_engine.grounding")


SAFE_BUILTINS = {
    "__build_class__": __build_class__,
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "callable": callable,
    "bytes": bytes,
    "bytearray": bytearray,
    "classmethod": classmethod,
    "chr": chr,
    "complex": complex,
    "divmod": divmod,
    "dict": dict,
    "enumerate": enumerate,
    "Exception": Exception,
    "float": float,
    "format": format,
    "frozenset": frozenset,
    "hash": hash,
    "int": int,
    "id": id,
    "globals": globals,
    "isinstance": isinstance,
    "issubclass": issubclass,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "object": object,
    "locals": locals,
    "pow": pow,
    "print": print,
    "range": range,
    "repr": repr,
    "reversed": reversed,
    "round": round,
    "set": set,
    "slice": slice,
    "sorted": sorted,
    "str": str,
    "staticmethod": staticmethod,
    "sum": sum,
    "super": super,
    "tuple": tuple,
    "type": type,
    "ord": ord,
    "zip": zip,
    "True": True,
    "False": False,
    "None": None,
    "ValueError": ValueError,
    "TypeError": TypeError,
    "IndexError": IndexError,
    "KeyError": KeyError,
    "NameError": NameError,
    "AssertionError": AssertionError,
    "RuntimeError": RuntimeError,
    "ArithmeticError": ArithmeticError,
    "ZeroDivisionError": ZeroDivisionError,
    "StopIteration": StopIteration,
}


@dataclass
class SandboxResult:
    passed: bool
    output: str
    error: Optional[str]
    runtime_ms: float


class Sandbox:
    def __init__(self, timeout_ms: int = 5000, max_output: int = 65536):
        self.timeout_ms = timeout_ms
        self.max_output = max_output

    def _build_script(self, code: str, test_code: str = "") -> str:
        payload = json.dumps({"code": code, "test_code": test_code})
        return textwrap.dedent(
            f"""
            import json

            PAYLOAD = json.loads({payload!r})
            SAFE_BUILTINS = {{"__build_class__": __build_class__, "abs": abs, "all": all,
            "any": any, "bool": bool, "callable": callable, "bytes": bytes,
            "bytearray": bytearray, "classmethod": classmethod, "chr": chr,
            "complex": complex, "divmod": divmod, "dict": dict, "enumerate": enumerate,
            "Exception": Exception, "float": float, "format": format, "frozenset": frozenset,
            "hash": hash, "id": id, "globals": globals, "int": int, "isinstance": isinstance,
            "issubclass": issubclass, "len": len, "list": list, "map": map,
            "max": max, "min": min, "object": object, "locals": locals, "ord": ord, "pow": pow,
            "print": print, "range": range, "repr": repr, "reversed": reversed,
            "round": round, "set": set, "slice": slice, "sorted": sorted, "str": str,
            "staticmethod": staticmethod, "sum": sum, "super": super, "tuple": tuple,
            "type": type, "zip": zip, "True": True, "False": False, "None": None,
            "ValueError": ValueError, "TypeError": TypeError, "IndexError": IndexError,
            "KeyError": KeyError, "NameError": NameError, "AssertionError": AssertionError, "RuntimeError": RuntimeError,
            "ArithmeticError": ArithmeticError, "ZeroDivisionError": ZeroDivisionError,
            "StopIteration": StopIteration}}

            _env = {{"__builtins__": SAFE_BUILTINS, "__name__": "__main__"}}
            exec(PAYLOAD["code"], _env, _env)
            if PAYLOAD["test_code"]:
                exec(PAYLOAD["test_code"], _env, _env)
            """
        ).strip()

    def execute(self, code: str, test_code: str = "") -> SandboxResult:
        script = self._build_script(code, test_code)
        start = time.time()
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(script)
                f.flush()
                tmp_path = f.name

            proc = subprocess.run(
                [sys.executable or "python3", "-I", "-B", tmp_path],
                capture_output=True,
                text=True,
                timeout=self.timeout_ms / 1000,
                env={},
            )
            runtime = (time.time() - start) * 1000
            if proc.returncode != 0:
                return SandboxResult(
                    passed=False,
                    output=proc.stdout[:self.max_output],
                    error=proc.stderr[:self.max_output],
                    runtime_ms=runtime,
                )
            return SandboxResult(
                passed=True,
                output=proc.stdout[:self.max_output],
                error=None,
                runtime_ms=runtime,
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(
                passed=False,
                output="",
                error="TIMEOUT",
                runtime_ms=self.timeout_ms,
            )
        except Exception as e:
            return SandboxResult(
                passed=False,
                output="",
                error=str(e),
                runtime_ms=(time.time() - start) * 1000,
            )
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    logger.debug("Failed to remove temp sandbox file: %s", tmp_path)

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
from typing import Any, Optional

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
    result: Optional[dict[str, Any]] = None


class Sandbox:
    def __init__(self, timeout_ms: int = 5000, max_output: int = 65536):
        self.timeout_ms = timeout_ms
        self.max_output = max_output

    @staticmethod
    def _browser_source() -> str:
        return """
from urllib.request import Request, urlopen
from urllib.parse import urlparse, quote
from html.parser import HTMLParser
import json, re, time

_BROWSE_RATE_LIMIT = 1.0
_BROWSE_LAST = 0.0

class _TextExtract(HTMLParser):
    def __init__(self):
        super().__init__()
        self._t = []
        self._skip = False
    def handle_starttag(self, tag, attrs):
        if tag in ("script","style","noscript"): self._skip = True
    def handle_endtag(self, tag):
        if tag in ("script","style","noscript"): self._skip = False
    def handle_data(self, data):
        if not self._skip:
            s = data.strip()
            if s: self._t.append(s)
    @property
    def text(self): return " ".join(self._t)

def browse(url, limit=50000):
    global _BROWSE_LAST
    now = time.time()
    if now - _BROWSE_LAST < _BROWSE_RATE_LIMIT:
        time.sleep(_BROWSE_RATE_LIMIT - (now - _BROWSE_LAST))
    _BROWSE_LAST = time.time()
    parsed = urlparse(url)
    if not parsed.scheme:
        url = "https://" + url
        parsed = urlparse(url)
    if parsed.scheme not in ("http","https"):
        return {"url":url,"status":0,"content":"","error":"Only http/https"}
    try:
        req = Request(url, headers={"User-Agent":"Mozilla/5.0 (compatible; GossipEngine/1.0)"})
        with urlopen(req, timeout=15) as r:
            raw = r.read(limit+10000)
            ct = r.headers.get("Content-Type","")
            fu = r.url
        if "application/json" in ct:
            content = json.dumps(json.loads(raw), indent=2)
        else:
            p = _TextExtract()
            p.feed(raw.decode("utf-8","replace"))
            content = p.text[:limit]
        return {"url":fu,"status":200,"content":content,"error":None}
    except Exception as e:
        return {"url":url,"status":0,"content":"","error":str(e)}

def search(query, num=5):
    global _BROWSE_LAST
    now = time.time()
    if now - _BROWSE_LAST < _BROWSE_RATE_LIMIT:
        time.sleep(_BROWSE_RATE_LIMIT - (now - _BROWSE_LAST))
    _BROWSE_LAST = time.time()
    try:
        url = f"https://html.duckduckgo.com/html/?q={quote(query)}"
        req = Request(url, headers={"User-Agent":"Mozilla/5.0 (compatible; GossipEngine/1.0)"})
        with urlopen(req, timeout=15) as r:
            html = r.read(50000).decode("utf-8","replace")
    except Exception as e:
        return [{"title":f"Search error: {e}","url":"","snippet":""}]
    results=[]
    for m in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL):
        href=m.group(1); title=re.sub(r"<[^>]+>","",m.group(2)).strip(); snippet=re.sub(r"<[^>]+>","",m.group(3)).strip()
        results.append({"title":title,"url":href,"snippet":snippet})
        if len(results)>=num: break
    return results if results else [{"title":f"No results for: {query}","url":"","snippet":""}]
"""

    def _build_script(self, code: str, test_code: str = "", result_key: str = "", result_token: str = "") -> str:
        payload = json.dumps({
            "code": code,
            "test_code": test_code,
            "result_key": result_key,
            "result_token": result_token,
        })
        browser_code = self._browser_source()
        return (
            f"import json\n{browser_code}\n"
            f"PAYLOAD = json.loads({payload!r})\n"
            f"SAFE_BUILTINS = {{'__build_class__': __build_class__, 'abs': abs, 'all': all, "
            f"'any': any, 'bool': bool, 'callable': callable, 'bytes': bytes, "
            f"'bytearray': bytearray, 'classmethod': classmethod, 'chr': chr, "
            f"'complex': complex, 'divmod': divmod, 'dict': dict, 'enumerate': enumerate, "
            f"'Exception': Exception, 'float': float, 'format': format, 'frozenset': frozenset, "
            f"'hash': hash, 'id': id, 'globals': globals, 'int': int, 'isinstance': isinstance, "
            f"'issubclass': issubclass, 'len': len, 'list': list, 'map': map, "
            f"'max': max, 'min': min, 'object': object, 'locals': locals, 'ord': ord, 'pow': pow, "
            f"'print': print, 'range': range, 'repr': repr, 'reversed': reversed, "
            f"'round': round, 'set': set, 'slice': slice, 'sorted': sorted, 'str': str, "
            f"'staticmethod': staticmethod, 'sum': sum, 'super': super, 'tuple': tuple, "
            f"'type': type, 'zip': zip, 'True': True, 'False': False, 'None': None, "
            f"'ValueError': ValueError, 'TypeError': TypeError, 'IndexError': IndexError, "
            f"'KeyError': KeyError, 'NameError': NameError, 'AssertionError': AssertionError, "
            f"'RuntimeError': RuntimeError, 'ArithmeticError': ArithmeticError, "
            f"'ZeroDivisionError': ZeroDivisionError, 'StopIteration': StopIteration, "
            f"'browse': browse, 'search': search}}\n"
            f"_env = {{'__builtins__': SAFE_BUILTINS, '__name__': '__main__'}}\n"
            f"exec(PAYLOAD['code'], _env, _env)\n"
            f"if PAYLOAD['test_code']:\n"
            f"    exec(PAYLOAD['test_code'], _env, _env)\n"
            f"if PAYLOAD.get('result_key') and PAYLOAD.get('result_token'):\n"
            f"    _payload = _env.get(PAYLOAD['result_key'])\n"
            f"    print(json.dumps({{'token': PAYLOAD['result_token'], 'result': _payload}}, sort_keys=True))\n"
        )

    def execute(self, code: str, test_code: str = "", result_key: str = "", result_token: str = "") -> SandboxResult:
        script = self._build_script(code, test_code, result_key=result_key, result_token=result_token)
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
            result_payload: dict[str, Any] | None = None
            if result_key and result_token and proc.stdout:
                for line in reversed([line for line in proc.stdout.splitlines() if line.strip()]):
                    try:
                        parsed = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(parsed, dict) and parsed.get("token") == result_token:
                        maybe_result = parsed.get("result")
                        if isinstance(maybe_result, dict):
                            result_payload = maybe_result
                        break
            if proc.returncode != 0:
                return SandboxResult(
                    passed=False,
                    output=proc.stdout[:self.max_output],
                    error=proc.stderr[:self.max_output],
                    runtime_ms=runtime,
                    result=result_payload,
                )
            return SandboxResult(
                passed=True,
                output=proc.stdout[:self.max_output],
                error=None,
                runtime_ms=runtime,
                result=result_payload,
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(
                passed=False,
                output="",
                error="TIMEOUT",
                runtime_ms=self.timeout_ms,
                result=None,
            )
        except Exception as e:
            return SandboxResult(
                passed=False,
                output="",
                error=str(e),
                runtime_ms=(time.time() - start) * 1000,
                result=None,
            )
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    logger.debug("Failed to remove temp sandbox file: %s", tmp_path)

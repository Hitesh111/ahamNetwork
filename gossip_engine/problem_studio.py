from __future__ import annotations

import ast
import json
import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import Config
from .grounding.browser import browse, search
from .utils.display import format_kv, shorten

_WORD_RE = re.compile(r"[A-Za-z0-9_]+")


@dataclass
class ProblemExample:
    input_value: Any
    expected_output: Any


@dataclass
class ProblemSource:
    kind: str
    value: str
    label: str = ""
    text: str = ""


@dataclass
class ProblemSpec:
    title: str
    statement: str
    input_kind: str
    output_kind: str
    examples: list[ProblemExample] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    sources: list[ProblemSource] = field(default_factory=list)
    context_block: str = ""

    @property
    def slug(self) -> str:
        value = self.title.lower().strip()
        value = re.sub(r"[^a-z0-9]+", "-", value)
        value = value.strip("-")
        return value or "problem"

    def to_manifest(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "statement": self.statement,
            "input_kind": self.input_kind,
            "output_kind": self.output_kind,
            "constraints": list(self.constraints),
            "examples": [
                {"input": item.input_value, "output": item.expected_output}
                for item in self.examples
            ],
            "sources": [
                {"kind": source.kind, "value": source.value, "label": source.label}
                for source in self.sources
            ],
            "context_block": self.context_block,
        }


class MiniRAG:
    def __init__(self):
        self._chunks: list[dict[str, str]] = []

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {token.lower() for token in _WORD_RE.findall(text)}

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 1200, overlap: int = 200) -> list[str]:
        cleaned = text.strip()
        if not cleaned:
            return []
        if len(cleaned) <= chunk_size:
            return [cleaned]
        chunks: list[str] = []
        start = 0
        while start < len(cleaned):
            end = min(len(cleaned), start + chunk_size)
            chunks.append(cleaned[start:end].strip())
            if end >= len(cleaned):
                break
            start = max(end - overlap, start + 1)
        return [chunk for chunk in chunks if chunk]

    def add_document(self, source: str, text: str):
        for index, chunk in enumerate(self._chunk_text(text)):
            self._chunks.append(
                {
                    "source": source,
                    "chunk": chunk,
                    "label": f"{source}#{index + 1}",
                }
            )

    def retrieve(self, query: str, limit: int = 5) -> list[dict[str, str]]:
        if not self._chunks:
            return []
        query_tokens = self._tokenize(query)
        scored: list[tuple[float, dict[str, str]]] = []
        for item in self._chunks:
            chunk_tokens = self._tokenize(item["chunk"])
            if not chunk_tokens:
                continue
            overlap = len(query_tokens & chunk_tokens)
            density = overlap / max(1, len(chunk_tokens))
            source_boost = 0.15 if item["source"].lower() in query.lower() else 0.0
            score = overlap + density + source_boost
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [item for _, item in scored[: max(1, limit)]]

    def build_context_block(self, query: str, limit: int = 5, max_chars: int = 4000) -> str:
        hits = self.retrieve(query, limit=limit)
        if not hits:
            return ""
        parts: list[str] = []
        total = 0
        for hit in hits:
            block = f"[{hit['label']}]\n{hit['chunk'].strip()}"
            if total + len(block) > max_chars:
                block = block[: max(0, max_chars - total)].rstrip()
            if block:
                parts.append(block)
                total += len(block)
            if total >= max_chars:
                break
        return "\n\n".join(parts)


def _prompt_text(label: str, default: str = "", required: bool = False) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        try:
            value = input(f"{label}{suffix}: ").strip()
        except EOFError:
            value = ""
        if value:
            return value
        if default:
            return default
        if not required:
            return ""
        print("This field is required.")


def _prompt_yes_no(label: str, default: bool = False) -> bool:
    default_text = "Y/n" if default else "y/N"
    while True:
        try:
            value = input(f"{label} ({default_text}): ").strip().lower()
        except EOFError:
            value = ""
        if not value:
            return default
        if value in {"y", "yes", "1", "true"}:
            return True
        if value in {"n", "no", "0", "false"}:
            return False
        print("Please answer y or n.")


def _prompt_choice(label: str, options: list[str], default_index: int = 0) -> str:
    for index, option in enumerate(options, start=1):
        marker = " (default)" if index - 1 == default_index else ""
        print(f"  {index}. {option}{marker}")
    while True:
        try:
            raw = input(f"{label} [1-{len(options)}]: ").strip()
        except EOFError:
            raw = ""
        if not raw:
            return options[default_index]
        if raw.isdigit():
            choice = int(raw)
            if 1 <= choice <= len(options):
                return options[choice - 1]
        print("Choose one of the numbered options.")


def _parse_literal(value: str) -> Any:
    raw = value.strip()
    if not raw:
        return ""
    try:
        return json.loads(raw)
    except Exception:
        pass
    try:
        return ast.literal_eval(raw)
    except Exception:
        return raw


def _prompt_json_object(label: str) -> dict[str, Any] | None:
    while True:
        try:
            raw = input(f"{label}: ").strip()
        except EOFError:
            raw = ""
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except Exception:
            try:
                parsed = ast.literal_eval(raw)
            except Exception:
                print("Enter valid JSON, for example: {\"input\": 2, \"output\": true}")
                continue
        if isinstance(parsed, dict):
            return parsed
        print("Enter an object with named fields.")


def _read_source(spec: ProblemSource) -> str:
    if spec.kind == "file":
        path = Path(spec.value)
        if not path.exists():
            raise FileNotFoundError(path)
        return path.read_text(encoding="utf-8", errors="replace")
    if spec.kind == "url":
        result = browse(spec.value)
        if result.get("error"):
            return f"URL fetch error for {spec.value}: {result['error']}"
        return result.get("content") or ""
    if spec.kind == "search":
        hits = search(spec.value, num=3)
        parts = []
        for hit in hits:
            title = hit.get("title", "").strip()
            snippet = hit.get("snippet", "").strip()
            url = hit.get("url", "").strip()
            if title or snippet or url:
                parts.append(
                    "\n".join(part for part in [title, snippet, url] if part)
                )
        if hits and hits[0].get("url"):
            try:
                fetched = browse(hits[0]["url"])
                if fetched.get("content"):
                    parts.append(fetched["content"])
            except Exception:
                pass
        return "\n\n".join(parts)
    if spec.kind == "text":
        return spec.value
    return spec.value


def collect_problem_spec(config: Config) -> ProblemSpec | None:
    print("=== Problem Studio ===")
    print("assistant: Define the problem in a structured way. I will turn it into a domain and run the solver.")
    print("assistant: Keep the answer schema tight. Examples must be JSON objects with input/output fields.")
    print()

    title = _prompt_text("assistant: Problem title", required=True)
    statement = _prompt_text("assistant: One-sentence problem statement", required=True)
    input_kind = _prompt_choice(
        "assistant: Input kind",
        ["int", "string", "list", "dict", "json", "custom"],
        default_index=1,
    )
    if input_kind == "custom":
        input_kind = _prompt_text("assistant: Describe the input shape", required=True)
    output_kind = _prompt_choice(
        "assistant: Output kind",
        ["bool", "int", "string", "list", "dict", "custom"],
        default_index=0,
    )
    if output_kind == "custom":
        output_kind = _prompt_text("assistant: Describe the output shape", required=True)

    examples: list[ProblemExample] = []
    print("assistant: Add examples as JSON objects, e.g. {\"input\": 2, \"output\": true}")
    while True:
        example = _prompt_json_object("user example")
        if example is None:
            if examples:
                break
            print("assistant: You need at least one example to make the problem executable.")
            continue
        if "input" not in example or "output" not in example:
            print("assistant: Example must contain 'input' and 'output'.")
            continue
        examples.append(
            ProblemExample(
                input_value=example["input"],
                expected_output=example["output"],
            )
        )
        if not _prompt_yes_no("assistant: Add another example", default=False):
            break

    constraints: list[str] = []
    print("assistant: Add constraints as a JSON array of strings, or [] if none.")
    while True:
        try:
            raw = input("user constraints: ").strip()
        except EOFError:
            raw = ""
        if not raw:
            break
        try:
            parsed = json.loads(raw)
        except Exception:
            try:
                parsed = ast.literal_eval(raw)
            except Exception:
                print("assistant: Enter a JSON array, for example: [\"handle negatives\", \"use O(n)\"]")
                continue
        if isinstance(parsed, list) and all(isinstance(item, str) for item in parsed):
            constraints = [item.strip() for item in parsed if item.strip()]
            break
        print("assistant: Constraints must be a list of strings.")

    sources: list[ProblemSource] = []
    if _prompt_yes_no("assistant: Add retrieval sources for RAG", default=False):
        print("assistant: Add sources as JSON objects like {\"kind\": \"file\", \"value\": \"docs/spec.md\"}")
        print("assistant: Supported kinds: file, url, search, text")
        while True:
            source_raw = _prompt_json_object("user source")
            if source_raw is None:
                break
            kind = str(source_raw.get("kind", "")).strip().lower()
            value = str(source_raw.get("value", "")).strip()
            if not kind or not value:
                print("assistant: Source needs 'kind' and 'value'.")
                continue
            if kind not in {"file", "url", "search", "text"}:
                print("assistant: Kind must be file, url, search, or text.")
                continue
            label = str(source_raw.get("label", "")).strip()
            sources.append(ProblemSource(kind=kind, value=value, label=label))
            if not _prompt_yes_no("assistant: Add another source", default=False):
                break

    spec = ProblemSpec(
        title=title,
        statement=statement,
        input_kind=input_kind,
        output_kind=output_kind,
        examples=examples,
        constraints=constraints,
        sources=sources,
    )
    spec.context_block = build_context_block(spec)

    print()
    print("assistant: Structured spec preview")
    print(format_kv(
        {
            "title": spec.title,
            "statement": shorten(spec.statement, 120),
            "input_kind": spec.input_kind,
            "output_kind": spec.output_kind,
            "examples": len(spec.examples),
            "constraints": len(spec.constraints),
            "sources": len(spec.sources),
        }
    ))
    if spec.context_block:
        print()
        print("assistant: Retrieved context")
        print(spec.context_block[:2000])

    if not _prompt_yes_no("assistant: Materialize and solve this problem", default=True):
        return None
    return spec


def build_context_block(spec: ProblemSpec, limit: int = 5) -> str:
    rag = MiniRAG()
    for source in spec.sources:
        try:
            rag.add_document(
                source.label or f"{source.kind}:{source.value}",
                _read_source(source),
            )
        except Exception as exc:
            rag.add_document(
                source.label or f"{source.kind}:{source.value}",
                f"Source load error for {source.kind}:{source.value}: {exc}",
            )
    query_parts = [spec.title, spec.statement, spec.input_kind, spec.output_kind]
    query_parts.extend(spec.constraints)
    for example in spec.examples[:5]:
        query_parts.append(repr(example.input_value))
        query_parts.append(repr(example.expected_output))
    query = " ".join(query_parts)
    return rag.build_context_block(query, limit=limit)


def render_domain_module(spec: ProblemSpec) -> str:
    prompt_lines = [
        f"Title: {spec.title}",
        f"Problem: {spec.statement}",
        f"Input kind: {spec.input_kind}",
        f"Output kind: {spec.output_kind}",
    ]
    if spec.constraints:
        prompt_lines.append("Constraints:")
        prompt_lines.extend(f"- {item}" for item in spec.constraints)
    if spec.context_block:
        prompt_lines.append("Relevant context:")
        prompt_lines.append(spec.context_block)
    prompt_text = "\n".join(prompt_lines).strip()

    test_cases = [(item.input_value, item.expected_output) for item in spec.examples]
    test_code_lines = [
        f"if solve({repr(item.input_value)}) != {repr(item.expected_output)}: raise AssertionError()"
        for item in spec.examples
    ]
    test_code_block = textwrap.indent("\n".join(test_code_lines) or "pass", "    ")

    module = f'''"""
Generated domain: {spec.title}
Created by the structured problem studio.
"""

from gossip_engine.grounding.validator import evaluate_solution


PROMPT = {prompt_text!r}
CONTEXT = {spec.context_block!r}
PROBLEM_SPEC = {spec.to_manifest()!r}
TEST_CASES = {test_cases!r}


def behavioral_descriptor(code: str) -> tuple[float, float]:
    code_len = min(len(code), 500) / 500.0
    line_count = min(code.count("\\n") + 1, 50) / 50.0
    return (code_len, line_count)


def fitness(code: str) -> tuple[bool, float, tuple[float, float]]:
    result = evaluate_solution(
        code,
        TEST_CASES,
        behavior_fn=lambda source, score, passed_count, total: behavioral_descriptor(source),
    )
    return (result.passed, result.score, result.behavior)


def is_solved(code: str, trust: float) -> bool:
    return trust > 0.9 and fitness(code)[0]


test_code = """
{test_code_block}
"""
'''
    return textwrap.dedent(module).lstrip()


def write_domain_module(spec: ProblemSpec, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    domain_path = output_dir / f"{spec.slug}.py"
    spec_path = output_dir / f"{spec.slug}.json"
    domain_path.write_text(render_domain_module(spec), encoding="utf-8")
    spec_path.write_text(
        json.dumps(spec.to_manifest(), indent=2, sort_keys=True, default=repr),
        encoding="utf-8",
    )
    return domain_path


def run_problem_studio(config: Config) -> str | None:
    spec = collect_problem_spec(config)
    if spec is None:
        print("assistant: Studio cancelled.")
        return None
    output_dir = Path(config.checkpoint_dir) / "problem_studio"
    domain_path = write_domain_module(spec, output_dir)
    print()
    print("assistant: Problem materialized")
    print(format_kv(
        {
            "domain_path": str(domain_path),
            "spec_path": str(domain_path.with_suffix(".json")),
            "prompt_chars": len(spec.statement),
            "context_chars": len(spec.context_block),
        }
    ))
    return str(domain_path)

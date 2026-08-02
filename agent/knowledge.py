"""Deterministic lightweight retrieval over selected curated project knowledge."""

from __future__ import annotations

import json
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = PROJECT_ROOT / "data/runtime_knowledge_manifest.json"


def manifest_sources(path: Path = DEFAULT_MANIFEST) -> tuple[Path, ...]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return tuple(PROJECT_ROOT / value for value in data.get("retrieval_sources", []))


class KnowledgeRetriever:
    def __init__(self, config: dict, sources=None):
        self.max_snippets = int(config.get("max_snippets", 5))
        self.max_chars = int(config.get("max_chars_per_snippet", 900))
        self.sections = []
        sources = manifest_sources() if sources is None else sources
        for path in sources:
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if path.suffix.casefold() == ".json":
                try:
                    value = json.loads(text)
                    if isinstance(value, dict):
                        chunks = [f"{key}: {json.dumps(item, ensure_ascii=False)}" for key, item in value.items()]
                    elif isinstance(value, list):
                        chunks = [json.dumps(item, ensure_ascii=False) for item in value]
                    else:
                        chunks = [str(value)]
                except json.JSONDecodeError:
                    chunks = [text]
            else:
                chunks = re.split(r"\n\s*\n|(?=^#{1,3}\s)", text, flags=re.MULTILINE)
            for index, chunk in enumerate(chunks):
                clean = chunk.strip()
                if clean:
                    self.sections.append((path, index, clean))

    def search(self, query: str) -> list[dict]:
        terms = {term for term in re.findall(r"[a-z0-9_]+", query.casefold()) if len(term) > 2}
        scored = []
        for path, index, text in self.sections:
            lowered = text.casefold()
            score = sum(lowered.count(term) for term in terms)
            if score:
                scored.append((score, path, index, text))
        scored.sort(key=lambda item: (-item[0], str(item[1]), item[2]))
        return [
            {"source": str(path), "section": index, "score": score, "text": text[: self.max_chars]}
            for score, path, index, text in scored[: self.max_snippets]
        ]

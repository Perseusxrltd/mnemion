"""Pinned tokenizer offsets or explicitly labelled conservative byte budgets."""

from __future__ import annotations

import bisect
import hashlib
import os
import threading
from pathlib import Path

from .model_config import TokenizerSpec


class EmbeddingTokenizer:
    def __init__(self, specification: TokenizerSpec, cache_dir: Path, *, offline=False):
        self.specification = specification
        self.cache_dir = cache_dir
        self.offline = offline
        self._tokenizer = None
        self._lock = threading.Lock()

    @property
    def unit(self) -> str:
        return "utf8_bytes" if self.specification.kind == "utf8" else "model_tokens"

    def prepare(self) -> None:
        if self.specification.kind == "utf8" or self._tokenizer is not None:
            return
        with self._lock:
            if self._tokenizer is not None:
                return
            from tokenizers import Tokenizer

            spec = self.specification
            if spec.kind == "file":
                value = os.environ.get(spec.file_env or "")
                if not value:
                    raise ValueError("The configured private tokenizer file is unavailable")
                path = Path(value)
            else:
                from huggingface_hub import hf_hub_download

                path = Path(
                    hf_hub_download(
                        repo_id=spec.repository,
                        revision=spec.revision,
                        filename="tokenizer.json",
                        cache_dir=str(self.cache_dir),
                        local_files_only=self.offline,
                        token=False,
                    )
                )
            if not path.is_file() or path.stat().st_size > 32 * 1024 * 1024:
                raise ValueError("Tokenizer file is missing or exceeds 32 MiB")
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != spec.sha256:
                raise ValueError("Tokenizer checksum failed")
            tokenizer = Tokenizer.from_file(str(path))
            tokenizer.no_padding()
            tokenizer.no_truncation()
            self._tokenizer = tokenizer

    def count(self, text: str) -> int:
        if self.specification.kind == "utf8":
            return len(text.encode("utf-8"))
        self.prepare()
        return len(self._tokenizer.encode(text, add_special_tokens=False).ids)

    def spans(self, text: str, size: int, overlap: int) -> list[tuple[int, int]]:
        if not text or not 0 <= overlap < size:
            raise ValueError("A nonempty document and valid chunk budgets are required")
        if self.specification.kind == "utf8":
            positions = [0]
            for character in text:
                positions.append(positions[-1] + len(character.encode("utf-8")))
            spans, start = [], 0
            while start < len(text):
                end = bisect.bisect_right(positions, positions[start] + size) - 1
                if end <= start:
                    raise ValueError("Chunk budget cannot fit one Unicode character")
                spans.append((start, end))
                if len(spans) > 512:
                    raise ValueError("Document exceeds the 512 chunk indexing limit")
                if end == len(text):
                    break
                start = max(start + 1, bisect.bisect_left(positions, positions[end] - overlap))
            return spans
        self.prepare()
        offsets = self._tokenizer.encode(text, add_special_tokens=False).offsets
        if not offsets:
            raise ValueError("Document has no encodable tokens")
        spans = []
        for index in range(0, len(offsets), size - overlap):
            stop = min(index + size, len(offsets))
            start = offsets[index][0] if index else 0
            end = len(text) if stop == len(offsets) else offsets[stop - 1][1]
            if end > start and (not spans or spans[-1] != (start, end)):
                spans.append((start, end))
            if len(spans) > 512:
                raise ValueError("Document exceeds the 512 chunk indexing limit")
            if stop == len(offsets):
                break
        if not spans:
            raise ValueError("Tokenizer returned no usable source spans")
        return spans

"""One tokenizer vocabulary for full source spans and model inference.

FastEmbed's pinned runtime configures truncation and padding for inference.
Source counting/chunking must temporarily disable both. A shared lock covers
every encoding and the entire inference iterator, including exceptional exits.
"""

from contextlib import contextmanager
import threading


class SharedModelTokenizer:
    def __init__(self, tokenizer):
        self._tokenizer = tokenizer
        self._lock = threading.RLock()

    @contextmanager
    def inference(self):
        with self._lock:
            yield

    def encode(self, text: str, *, add_special_tokens: bool = True):
        with self._lock:
            tokenizer = self._tokenizer
            truncation, padding = tokenizer.truncation, tokenizer.padding
            try:
                tokenizer.no_truncation()
                tokenizer.no_padding()
                return tokenizer.encode(text, add_special_tokens=add_special_tokens)
            finally:
                if truncation is not None:
                    tokenizer.enable_truncation(**truncation)
                if padding is not None:
                    tokenizer.enable_padding(**padding)

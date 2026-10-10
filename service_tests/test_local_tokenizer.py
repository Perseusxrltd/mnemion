from concurrent.futures import ThreadPoolExecutor
import threading

import pytest
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import Whitespace

from mnemion.service.local_tokenizer import SharedModelTokenizer


def test_full_unicode_source_offsets_preserve_model_truncation_and_padding():
    raw = Tokenizer(WordLevel({"[UNK]": 0, "[PAD]": 1, "café": 2, "été": 3}, unk_token="[UNK]"))
    raw.pre_tokenizer = Whitespace()
    raw.enable_truncation(max_length=3, direction="left")
    raw.enable_padding(pad_id=1, pad_token="[PAD]", direction="left", length=5)
    before = raw.to_str()
    shared = SharedModelTokenizer(raw)
    text = "café été café été café été"
    encoded = shared.encode(text, add_special_tokens=False)
    assert encoded.ids == [2, 3, 2, 3, 2, 3]
    assert encoded.offsets == [(0, 4), (5, 8), (9, 13), (14, 17), (18, 22), (23, 26)]
    assert raw.to_str() == before
    with shared.inference():
        assert raw.encode(text).ids == [1, 1, 3, 2, 3]
    with pytest.raises(TypeError):
        shared.encode(None)
    assert raw.to_str() == before


def test_source_counting_cannot_change_tokenizer_during_a_lazy_inference():
    raw = Tokenizer(WordLevel({"[UNK]": 0, "word": 1}, unk_token="[UNK]"))
    raw.pre_tokenizer = Whitespace()
    raw.enable_truncation(max_length=2)
    shared = SharedModelTokenizer(raw)
    text = "word " * 9
    started = threading.Event()

    def count():
        started.set()
        return len(shared.encode(text).ids)

    with ThreadPoolExecutor(max_workers=1) as pool:
        with shared.inference():
            pending = pool.submit(count)
            assert started.wait(1)
            assert not pending.done()
            assert len(raw.encode(text).ids) == 2
        assert pending.result(timeout=2) == 9
    assert len(raw.encode(text).ids) == 2

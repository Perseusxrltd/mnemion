"""Locale-aware entity detection pattern loading."""

from __future__ import annotations

from dataclasses import dataclass

from .config import MnemionConfig


@dataclass(frozen=True)
class LocalePatterns:
    person_verbs: tuple[str, ...]
    project_verbs: tuple[str, ...]


_LOCALE_PATTERNS = {
    "en": LocalePatterns(person_verbs=(), project_verbs=()),
    "pt-br": LocalePatterns(
        person_verbs=(
            r"\b{name}\s+disse\b",
            r"\b{name}\s+perguntou\b",
            r"\b{name}\s+respondeu\b",
        ),
        project_verbs=(
            r"\bconstruindo\s+{name}\b",
            r"\blanç(?:ando|ou)\s+{name}\b",
        ),
    ),
}


def get_entity_languages(languages=None) -> tuple[str, ...]:
    if languages is None:
        return tuple(MnemionConfig().entity_languages)
    if isinstance(languages, str):
        parts = [part.strip().lower() for part in languages.split(",")]
    else:
        parts = [str(part).strip().lower() for part in languages]
    values = tuple(part for part in parts if part)
    return values or ("en",)


def get_locale_patterns(languages=None) -> LocalePatterns:
    person = []
    project = []
    for lang in get_entity_languages(languages):
        patterns = _LOCALE_PATTERNS.get(lang)
        if not patterns:
            continue
        person.extend(patterns.person_verbs)
        project.extend(patterns.project_verbs)
    return LocalePatterns(person_verbs=tuple(person), project_verbs=tuple(project))

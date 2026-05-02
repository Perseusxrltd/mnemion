from mnemion.entity_patterns import get_entity_languages, get_locale_patterns


def test_entity_languages_default_to_english(monkeypatch):
    monkeypatch.delenv("MNEMION_ENTITY_LANGUAGES", raising=False)

    assert get_entity_languages() == ("en",)


def test_entity_languages_env_override(monkeypatch):
    monkeypatch.setenv("MNEMION_ENTITY_LANGUAGES", "en,pt-br")

    assert get_entity_languages() == ("en", "pt-br")
    patterns = get_locale_patterns()
    assert any("disse" in pattern for pattern in patterns.person_verbs)

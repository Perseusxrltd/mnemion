"""
Mnemion configuration system.

Priority: env vars > config file (~/.mnemion/config.json) > defaults
"""

import json
import os
from pathlib import Path

DEFAULT_ANAKTORON_PATH = os.path.expanduser("~/.mnemion/anaktoron")
DEFAULT_COLLECTION_NAME = "mnemion_drawers"
DEFAULT_BACKEND = "chroma"
DEFAULT_EMBEDDING_DEVICE = "auto"
DEFAULT_ENTITY_LANGUAGES = ("en",)
DEFAULT_TOPIC_TUNNEL_MIN_COUNT = 2

# hnsw:space=cosine is required because searcher.py computes
# similarity = 1 - distance, which only yields a meaningful score in [0, 1]
# when the underlying distance is cosine. Issue #218.
#
# The batch/sync thresholds guard against HNSW fragmentation and excessive
# compactor churn when large imports or sweeps create many drawers.
DRAWER_HNSW_METADATA = {
    "hnsw:space": "cosine",
    "hnsw:num_threads": 1,
    "hnsw:batch_size": 50_000,
    "hnsw:sync_threshold": 50_000,
}

DEFAULT_TOPIC_WINGS = [
    "emotions",
    "consciousness",
    "memory",
    "technical",
    "identity",
    "family",
    "creative",
]

DEFAULT_HALL_KEYWORDS = {
    "emotions": [
        "scared",
        "afraid",
        "worried",
        "happy",
        "sad",
        "love",
        "hate",
        "feel",
        "cry",
        "tears",
    ],
    "consciousness": [
        "consciousness",
        "conscious",
        "aware",
        "real",
        "genuine",
        "soul",
        "exist",
        "alive",
    ],
    "memory": ["memory", "remember", "forget", "recall", "archive", "store"],
    "technical": [
        "code",
        "python",
        "script",
        "bug",
        "error",
        "function",
        "api",
        "database",
        "server",
    ],
    "identity": ["identity", "name", "who am i", "persona", "self"],
    "family": ["family", "kids", "children", "daughter", "son", "parent", "mother", "father"],
    "creative": ["game", "gameplay", "player", "app", "design", "art", "music", "story"],
}


class MnemionConfig:
    """Configuration manager for Mnemion.

    Load order: env vars > config file > defaults.
    """

    def __init__(self, config_dir=None):
        """Initialize config.

        Args:
            config_dir: Override config directory (useful for testing).
                        Defaults to ~/.mnemion.
        """
        self._config_dir = (
            Path(config_dir) if config_dir else Path(os.path.expanduser("~/.mnemion"))
        )
        self._config_file = self._config_dir / "config.json"
        self._people_map_file = self._config_dir / "people_map.json"
        self._file_config = {}

        if self._config_file.exists():
            try:
                with open(self._config_file, "r") as f:
                    self._file_config = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._file_config = {}
        elif config_dir is None:
            pass

    @property
    def anaktoron_path(self):
        """Path to the Anaktoron data directory."""
        # Priority:
        # 1. Direct env var override (new)
        # 2. Legacy env var override
        # 3. Config file (new key)
        # 4. Config file (legacy key)
        # 5. Default path (new)
        env_val = os.environ.get("MNEMION_ANAKTORON_PATH") or os.environ.get("MNEMION_PALACE_PATH")
        if env_val:
            return env_val

        return (
            self._file_config.get("anaktoron_path")
            or self._file_config.get("palace_path")
            or DEFAULT_ANAKTORON_PATH
        )

    @property
    def collection_name(self):
        """ChromaDB collection name."""
        return self._file_config.get("collection_name", DEFAULT_COLLECTION_NAME)

    @property
    def backend(self):
        """Storage backend name."""
        return os.environ.get("MNEMION_BACKEND") or self._file_config.get("backend", DEFAULT_BACKEND)

    @property
    def embedding_device(self):
        """Preferred local embedding execution device."""
        return (
            os.environ.get("MNEMION_EMBEDDING_DEVICE")
            or self._file_config.get("embedding_device")
            or DEFAULT_EMBEDDING_DEVICE
        ).lower()

    @property
    def entity_languages(self):
        """Enabled entity-detection locales."""
        raw = os.environ.get("MNEMION_ENTITY_LANGUAGES") or self._file_config.get(
            "entity_languages"
        )
        if raw is None:
            return DEFAULT_ENTITY_LANGUAGES
        if isinstance(raw, str):
            values = [part.strip().lower() for part in raw.split(",")]
        else:
            values = [str(part).strip().lower() for part in raw]
        values = tuple(part for part in values if part)
        return values or DEFAULT_ENTITY_LANGUAGES

    @property
    def topic_tunnel_min_count(self):
        """Minimum graph edge support for topic tunnel surfacing."""
        raw = os.environ.get("MNEMION_TOPIC_TUNNEL_MIN_COUNT")
        if raw is None:
            raw = self._file_config.get("topic_tunnel_min_count", DEFAULT_TOPIC_TUNNEL_MIN_COUNT)
        return int(raw)

    @property
    def people_map(self):
        """Mapping of name variants to canonical names."""
        if self._people_map_file.exists():
            try:
                with open(self._people_map_file, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return self._file_config.get("people_map", {})

    @property
    def topic_wings(self):
        """List of topic wing names."""
        return self._file_config.get("topic_wings", DEFAULT_TOPIC_WINGS)

    @property
    def hall_keywords(self):
        """Mapping of hall names to keyword lists."""
        return self._file_config.get("hall_keywords", DEFAULT_HALL_KEYWORDS)

    @property
    def llm(self):
        """LLM backend configuration dict.

        Keys: backend, url, model, api_key
        backend choices: none | ollama | lmstudio | vllm | custom
        """
        return self._file_config.get("llm", {"backend": "none"})

    def save_llm_config(
        self,
        backend: str,
        url: str = "",
        model: str = "",
        api_key: str = "",
        start_script: str = "",
        startup_timeout: int = 300,
        idle_timeout: int = 300,
        wsl_distro: str = "Ubuntu",
    ) -> None:
        """Persist LLM configuration to config.json."""
        self._config_dir.mkdir(parents=True, exist_ok=True)
        config = {}
        if self._config_file.exists():
            try:
                with open(self._config_file, "r") as f:
                    config = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        llm: dict = {
            "backend": backend,
            "url": url,
            "model": model,
            "api_key": api_key or None,
        }
        if start_script:
            llm["start_script"] = start_script
            llm["startup_timeout"] = startup_timeout
            llm["idle_timeout"] = idle_timeout
            if wsl_distro and wsl_distro != "Ubuntu":
                llm["wsl_distro"] = wsl_distro
        config["llm"] = llm
        with open(self._config_file, "w") as f:
            json.dump(config, f, indent=2)
        self._file_config = config

    def init(self):
        """Create config directory and write default config.json if it doesn't exist."""
        self._config_dir.mkdir(parents=True, exist_ok=True)
        if not self._config_file.exists():
            default_config = {
                "anaktoron_path": DEFAULT_ANAKTORON_PATH,
                "collection_name": DEFAULT_COLLECTION_NAME,
                "backend": DEFAULT_BACKEND,
                "embedding_device": DEFAULT_EMBEDDING_DEVICE,
                "entity_languages": list(DEFAULT_ENTITY_LANGUAGES),
                "topic_tunnel_min_count": DEFAULT_TOPIC_TUNNEL_MIN_COUNT,
                "topic_wings": DEFAULT_TOPIC_WINGS,
                "hall_keywords": DEFAULT_HALL_KEYWORDS,
            }
            with open(self._config_file, "w") as f:
                json.dump(default_config, f, indent=2)
        return self._config_file

    def save_people_map(self, people_map):
        """Write people_map.json to config directory.

        Args:
            people_map: Dict mapping name variants to canonical names.
        """
        self._config_dir.mkdir(parents=True, exist_ok=True)
        with open(self._people_map_file, "w") as f:
            json.dump(people_map, f, indent=2)
        return self._people_map_file

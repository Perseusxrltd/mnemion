"""
Mnemion configuration system.

Priority: env vars > config file (~/.mnemion/config.json) > defaults
"""

import json
import os
from pathlib import Path

DEFAULT_PALACE_PATH = os.path.expanduser("~/.mnemion/palace")
DEFAULT_COLLECTION_NAME = "mnemion_drawers"

# hnsw:space=cosine is required because searcher.py computes
# similarity = 1 - distance, which only yields a meaningful score in [0, 1]
# when the underlying distance is cosine. Issue #218.
DRAWER_HNSW_METADATA = {"hnsw:space": "cosine"}

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
    "memory": ["memory", "remember", "forget", "recall", "archive", "palace", "store"],
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


class MempalaceConfig:
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

    @property
    def palace_path(self):
        """Path to the memory palace data directory."""
        # Check new env var first, then legacy mempalace env vars for backward compat
        env_val = (
            os.environ.get("MNEMION_PALACE_PATH")
            or os.environ.get("MEMPALACE_PALACE_PATH")
            or os.environ.get("MEMPAL_PALACE_PATH")
        )
        if env_val:
            return env_val
        return self._file_config.get("palace_path", DEFAULT_PALACE_PATH)

    @property
    def collection_name(self):
        """ChromaDB collection name."""
        return self._file_config.get("collection_name", DEFAULT_COLLECTION_NAME)

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
        startup_timeout: int = 90,
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
                "palace_path": DEFAULT_PALACE_PATH,
                "collection_name": DEFAULT_COLLECTION_NAME,
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

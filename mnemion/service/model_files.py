"""Retrieve pinned inference files without repeatedly listing a remote repository."""

from pathlib import Path, PurePosixPath


def pinned_model_directory(configuration, cache_dir, *, offline=False):
    from huggingface_hub import _CACHED_NO_EXIST, hf_hub_download, try_to_load_from_cache
    from huggingface_hub.errors import EntryNotFoundError, LocalEntryNotFoundError

    model_file = configuration["model_file"]
    relative = PurePosixPath(model_file)
    if (
        not relative.parts
        or relative.is_absolute()
        or ".." in relative.parts
        or str(relative) != model_file
        or "\\" in model_file
    ):
        raise ValueError("Use a relative model file inside the pinned repository")
    # These are the files consumed by the pinned FastEmbed text runtime. Optional
    # files retain its normal missing-file behavior; no unrelated JSON or model
    # weights are downloaded. Every load still verifies model/tokenizer hashes.
    required = (model_file, "tokenizer.json", "tokenizer_config.json")
    optional = ("config.json", "special_tokens_map.json")
    common = {
        "repo_id": configuration["repository"],
        "revision": configuration["revision"],
        "cache_dir": str(cache_dir),
    }
    directory = None
    for filename in (*required, *optional):
        location = try_to_load_from_cache(filename=filename, **common)
        if location is _CACHED_NO_EXIST:
            if filename in optional:
                continue
            raise LocalEntryNotFoundError("A required pinned model file is unavailable.")
        if not isinstance(location, str) or not Path(location).is_file():
            if offline:
                if filename in optional:
                    continue
                raise LocalEntryNotFoundError(
                    "A required pinned model file is not cached; prepare this model online first."
                )
            try:
                location = hf_hub_download(filename=filename, token=False, **common)
            except EntryNotFoundError:
                if filename in optional:
                    continue
                raise
        root = Path(location).absolute()
        for _ in PurePosixPath(filename).parts:
            root = root.parent
        if directory is not None and root != directory:
            raise RuntimeError("Pinned model files must belong to the same snapshot")
        directory = root
    if directory is None:
        raise RuntimeError("The pinned model snapshot is empty")
    return directory

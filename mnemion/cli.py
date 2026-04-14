#!/usr/bin/env python3
"""
Mnemion — Give your AI a memory. No API key required.

Two ways to ingest:
  Projects:      mnemion mine ~/projects/my_app          (code, docs, notes)
  Conversations: mnemion mine ~/chats/ --mode convos     (Claude, ChatGPT, Slack)

Same Anaktoron. Same search. Different ingest strategies.

Commands:
    mnemion init <dir>                  Detect rooms from folder structure
    mnemion split <dir>                 Split concatenated mega-files into per-session files
    mnemion mine <dir>                  Mine project files (default)
    mnemion mine <dir> --mode convos    Mine conversation exports
    mnemion restore <file.json>         Import a JSON export into the Anaktoron (new machine setup)
    mnemion restore <file.json> --merge Add to an existing Anaktoron without wiping it
    mnemion search "query"              Find anything, exact words
    mnemion wake-up                     Show L0 + L1 wake-up context
    mnemion wake-up --wing my_app       Wake-up for a specific project
    mnemion status                      Show what's been filed
    mnemion llm setup                   Configure LLM backend (ollama/lmstudio/vllm/custom/none)
    mnemion llm status                  Show current LLM config and ping the endpoint
    mnemion llm test                    Send a test prompt to verify the backend
    mnemion llm start                   Start the LLM server (requires start_script in config)
    mnemion llm stop                    Stop the LLM server
    mnemion librarian                   Run daily background tidy-up (contradiction scan + re-classification + KG)
    mnemion librarian --status          Show librarian state and pending count

Examples:
    mnemion init ~/projects/my_app
    mnemion mine ~/projects/my_app
    mnemion mine ~/chats/claude-sessions --mode convos
    mnemion search "why did we switch to GraphQL"
    mnemion search "pricing discussion" --wing my_app --room costs
"""

import os
import sys
import argparse
from pathlib import Path

from .config import MnemionConfig


def cmd_init(args):
    import json
    from pathlib import Path
    from .entity_detector import scan_for_detection, detect_entities, confirm_entities
    from .room_detector_local import detect_rooms_local

    # Pass 1: auto-detect people and projects from file content
    print(f"\n  Scanning for entities in: {args.dir}")
    files = scan_for_detection(args.dir)
    if files:
        print(f"  Reading {len(files)} files...")
        detected = detect_entities(files)
        total = len(detected["people"]) + len(detected["projects"]) + len(detected["uncertain"])
        if total > 0:
            confirmed = confirm_entities(detected, yes=getattr(args, "yes", False))
            # Save confirmed entities to <project>/entities.json for the miner
            if confirmed["people"] or confirmed["projects"]:
                entities_path = Path(args.dir).expanduser().resolve() / "entities.json"
                with open(entities_path, "w") as f:
                    json.dump(confirmed, f, indent=2)
                print(f"  Entities saved: {entities_path}")
        else:
            print("  No entities detected — proceeding with directory-based rooms.")

    # Pass 2: detect rooms from folder structure
    detect_rooms_local(project_dir=args.dir, yes=getattr(args, "yes", False))
    MnemionConfig().init()


def cmd_mine(args):
    anaktoron_path = (
        os.path.expanduser(args.palace) if args.palace else MnemionConfig().anaktoron_path
    )
    include_ignored = []
    for raw in args.include_ignored or []:
        include_ignored.extend(part.strip() for part in raw.split(",") if part.strip())

    if args.mode == "convos":
        from .convo_miner import mine_convos

        mine_convos(
            convo_dir=args.dir,
            palace_path=anaktoron_path,
            wing=args.wing,
            agent=args.agent,
            limit=args.limit,
            dry_run=args.dry_run,
            extract_mode=args.extract,
        )
    else:
        from .miner import mine

        mine(
            project_dir=args.dir,
            palace_path=anaktoron_path,
            wing_override=args.wing,
            agent=args.agent,
            limit=args.limit,
            dry_run=args.dry_run,
            respect_gitignore=not args.no_gitignore,
            include_ignored=include_ignored,
        )


def cmd_search(args):
    from .hybrid_searcher import HybridSearcher
    from .config import MnemionConfig

    anaktoron_path = (
        os.path.expanduser(args.palace) if args.palace else MnemionConfig().anaktoron_path
    )

    try:
        hs = HybridSearcher(palace_path=anaktoron_path)
        hits = hs.search(
            query=args.query,
            wing=args.wing,
            room=args.room,
            n_results=args.results,
            min_similarity=0.0,
        )

        if not hits:
            print("No results found.")
            return

        print(f"\nFound {len(hits)} results for '{args.query}'\n" + "=" * 50)
        for i, hit in enumerate(hits, 1):
            w = hit.get("wing", "unknown")
            r = hit.get("room", "unknown")
            t = hit.get("type", "vector")
            print(f"\n[{i}] {w}/{r}  (source: {t})")
            print(f"ID: {hit['id']}")
            print("-" * 50)
            print(f"{hit.get('text', '')}\n")

    except Exception as e:
        print(f"Search failed: {e}")
        sys.exit(1)


def cmd_wakeup(args):
    """Show L0 (identity) + L1 (essential story) — the wake-up context."""
    from .layers import MemoryStack

    anaktoron_path = (
        os.path.expanduser(args.palace) if args.palace else MnemionConfig().anaktoron_path
    )
    stack = MemoryStack(palace_path=anaktoron_path)

    text = stack.wake_up(wing=args.wing)
    tokens = len(text) // 4
    print(f"Wake-up text (~{tokens} tokens):")
    print("=" * 50)
    print(text)


def cmd_split(args):
    """Split concatenated transcript mega-files into per-session files."""
    from .split_mega_files import main as split_main
    import sys

    # Rebuild argv for split_mega_files argparse.
    # Expand ~ and resolve to absolute path so split_mega_files sees a real path.
    argv = ["--source", str(Path(args.dir).expanduser().resolve())]
    if args.output_dir:
        argv += ["--output-dir", args.output_dir]
    if args.dry_run:
        argv.append("--dry-run")
    if args.min_sessions != 2:
        argv += ["--min-sessions", str(args.min_sessions)]

    old_argv = sys.argv
    sys.argv = ["mnemion split"] + argv
    try:
        split_main()
    finally:
        sys.argv = old_argv


def cmd_status(args):
    from .miner import status

    anaktoron_path = (
        os.path.expanduser(args.palace) if args.palace else MnemionConfig().anaktoron_path
    )
    status(palace_path=anaktoron_path)


def cmd_repair(args):
    """Rebuild Anaktoron vector index from SQLite metadata."""
    import chromadb
    import shutil

    cfg = MnemionConfig()
    anaktoron_path = os.path.expanduser(args.palace) if args.palace else cfg.anaktoron_path
    col_name = cfg.collection_name

    if not os.path.isdir(anaktoron_path):
        print(f"\n  No Anaktoron found at {anaktoron_path}")
        return

    print(f"\n{'=' * 55}")
    print("  Mnemion Repair")
    print(f"{'=' * 55}\n")
    print(f"  Anaktoron: {anaktoron_path}")
    print(f"  Collection: {col_name}")

    # Try to read existing drawers
    try:
        client = chromadb.PersistentClient(path=anaktoron_path)
        col = client.get_collection(col_name)
        total = col.count()
        print(f"  Drawers found: {total}")
    except Exception as e:
        print(f"  Error reading Anaktoron: {e}")
        print("  Cannot recover — Anaktoron may need to be re-mined from source files.")
        return

    if total == 0:
        print("  Nothing to repair.")
        return

    # Extract all drawers in batches
    print("\n  Extracting drawers...")
    batch_size = 5000
    all_ids = []
    all_docs = []
    all_metas = []
    offset = 0
    while offset < total:
        batch = col.get(limit=batch_size, offset=offset, include=["documents", "metadatas"])
        all_ids.extend(batch["ids"])
        all_docs.extend(batch["documents"])
        all_metas.extend(batch["metadatas"])
        offset += batch_size
    print(f"  Extracted {len(all_ids)} drawers")

    # Backup and rebuild
    backup_path = anaktoron_path + ".backup"
    if os.path.exists(backup_path):
        shutil.rmtree(backup_path)
    print(f"  Backing up to {backup_path}...")
    shutil.copytree(anaktoron_path, backup_path)

    print("  Rebuilding collection...")
    client.delete_collection(col_name)
    new_col = client.create_collection(col_name)

    filed = 0
    for i in range(0, len(all_ids), batch_size):
        batch_ids = all_ids[i : i + batch_size]
        batch_docs = all_docs[i : i + batch_size]
        batch_metas = all_metas[i : i + batch_size]
        new_col.add(documents=batch_docs, ids=batch_ids, metadatas=batch_metas)
        filed += len(batch_ids)
        print(f"  Re-filed {filed}/{len(all_ids)} drawers...")

    print(f"\n  Repair complete. {filed} drawers rebuilt.")
    print(f"  Backup saved at {backup_path}")
    print(f"\n{'=' * 55}\n")


def _count_json_objects(filepath):
    """Fast byte scan to count top-level objects in the export.

    Each drawer has exactly one top-level ``"id":`` key. Keys inside
    JSON string values are escaped (``\\\"``), so searching for the
    literal byte sequence ``b'"id":'`` reliably counts only top-level
    drawer entries.
    """
    count = 0
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            count += chunk.count(b'"id":')
    return count


def _stream_json_array(filepath, read_size=524288):
    """Yield objects from a top-level JSON array one at a time.

    Uses ``json.JSONDecoder.raw_decode()`` with a rolling file buffer so
    only a single object (plus a small read-ahead) is in memory at once —
    regardless of how large the overall file is.
    """
    import json

    decoder = json.JSONDecoder()
    buf = ""

    with open(filepath, "r", encoding="utf-8") as f:
        # Advance to the opening bracket
        while "[" not in buf:
            chunk = f.read(read_size)
            if not chunk:
                return
            buf += chunk
        buf = buf[buf.index("[") + 1 :]

        while True:
            # Drop separators between elements
            buf = buf.lstrip(" \t\r\n,")

            # Refill when the buffer is running low
            if len(buf) < read_size // 4:
                chunk = f.read(read_size)
                if chunk:
                    buf += chunk

            # End of array or empty file
            if not buf or buf[0] == "]":
                break

            # Decode one object; read more if it is incomplete
            while True:
                try:
                    obj, end = decoder.raw_decode(buf)
                    yield obj
                    buf = buf[end:]
                    break
                except json.JSONDecodeError:
                    chunk = f.read(read_size)
                    if not chunk:
                        return  # Truncated file
                    buf += chunk


def cmd_restore(args):
    """Import a JSON export (archive/drawers_export.json) into the local Anaktoron."""
    import gc
    import chromadb
    from pathlib import Path
    from .config import MnemionConfig, DRAWER_HNSW_METADATA

    cfg = MnemionConfig()
    anaktoron_path = os.path.expanduser(args.palace) if args.palace else cfg.anaktoron_path
    col_name = cfg.collection_name
    json_file = args.file
    batch_size = args.batch_size

    if not os.path.isfile(json_file):
        print(f"\n  File not found: {json_file}\n", flush=True)
        sys.exit(1)

    file_mb = os.path.getsize(json_file) / 1_048_576
    print(f"\n{'=' * 55}", flush=True)
    print("  Mnemion Restore", flush=True)
    print(f"{'=' * 55}\n", flush=True)
    print(f"  Source:     {json_file} ({file_mb:.1f} MB)", flush=True)
    print(f"  Anaktoron: {anaktoron_path}", flush=True)
    print(f"  Collection: {col_name}", flush=True)
    print(f"  Batch size: {batch_size}", flush=True)

    # Fast pre-count (byte scan, no JSON parsing) so we can show %
    print("  Counting drawers ...", end=" ", flush=True)
    total = _count_json_objects(json_file)
    print(f"{total}", flush=True)

    Path(anaktoron_path).mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=anaktoron_path)

    try:
        col = client.get_or_create_collection(col_name, metadata=DRAWER_HNSW_METADATA)
    except Exception as e:
        print(f"  Error opening Anaktoron: {e}\n", flush=True)
        sys.exit(1)

    existing = col.count()
    if existing > 0 and not args.merge and not args.replace:
        print(f"\n  Anaktoron already has {existing} drawers.")
        print("  Use --merge to add to an existing Anaktoron, or --replace to overwrite.\n")
        sys.exit(1)

    if args.replace and existing > 0:
        print(f"\n  Replacing {existing} existing drawers...", flush=True)
        client.delete_collection(col_name)
        col = client.create_collection(col_name, metadata=DRAWER_HNSW_METADATA)

    print("  Streaming restore started ...\n", flush=True)

    filed = 0
    skipped = 0
    batch = []

    def _flush(b):
        nonlocal filed, skipped
        ids = [d["id"] for d in b]
        docs = [d["content"] for d in b]
        clean_metas = [
            {
                k: v
                for k, v in (d.get("meta") or {}).items()
                if isinstance(v, (str, int, float, bool))
            }
            for d in b
        ]
        try:
            col.upsert(ids=ids, documents=docs, metadatas=clean_metas)
            filed += len(b)
            pct = filed * 100 // total if total else 0
            print(f"  [{pct:3d}%] {filed}/{total}", flush=True)
        except Exception as e:
            print(f"  Error at {filed}: {e}", flush=True)
            skipped += len(b)
        finally:
            del ids, docs, clean_metas
            gc.collect()

    for drawer in _stream_json_array(json_file):
        batch.append(drawer)
        if len(batch) >= batch_size:
            _flush(batch)
            batch = []

    if batch:
        _flush(batch)

    print(
        f"\n  Done. {filed} drawers restored" + (f", {skipped} skipped." if skipped else "."),
        flush=True,
    )
    if filed > 0:
        print("  Run 'mnemion status' to verify.\n", flush=True)
    print(f"{'=' * 55}\n", flush=True)


def cmd_llm(args):
    """LLM backend management: setup, status, test."""
    from .config import MnemionConfig
    from .llm_backend import get_backend, BACKEND_DEFAULTS, BACKEND_LABELS, NullBackend

    config = MnemionConfig()

    if args.llm_action == "status":
        llm_cfg = config.llm
        backend_name = llm_cfg.get("backend", "none")
        print(f"\n  LLM backend: {backend_name}")
        backend = get_backend(config)
        print(f"  Details:     {backend.info()}")
        if isinstance(backend, NullBackend):
            print("  Status:      disabled — contradiction detection off")
            print("\n  Run 'mnemion llm setup' to configure a backend.\n")
        else:
            print("  Pinging...", end=" ", flush=True)
            if backend.ping():
                print("OK")
            else:
                print("UNREACHABLE")
                start_script = llm_cfg.get("start_script", "")
                if start_script:
                    print("  Auto-start available — run: mnemion llm start\n")
                else:
                    print(f"  Check that {llm_cfg.get('url', '?')} is running.\n")

    elif args.llm_action == "start":
        from .llm_backend import ManagedBackend

        backend = get_backend(config)
        if isinstance(backend, NullBackend):
            print("\n  No LLM configured. Run: mnemion llm setup\n")
            return
        if not isinstance(backend, ManagedBackend):
            print(f"\n  {backend.info()}")
            print("  No start_script configured — start this backend manually.")
            print("  To enable auto-start, run: mnemion llm setup\n")
            return
        if backend.ping():
            print(f"\n  Already running: {backend.info()}\n")
            return
        print(f"\n  Starting {backend.info()} ...")
        print(f"  (startup timeout: {backend.startup_timeout}s)", flush=True)
        if backend.ensure_running():
            print("  Server ready.\n")
        else:
            print("  Startup timed out. Check the start_script and try again.\n")

    elif args.llm_action == "stop":
        from .llm_backend import ManagedBackend

        backend = get_backend(config)
        if isinstance(backend, NullBackend) or not isinstance(backend, ManagedBackend):
            print("\n  No managed LLM configured — nothing to stop.\n")
            return
        if not backend.ping():
            print("\n  Already stopped.\n")
            return
        backend.stop()
        print(f"\n  Stopped {backend.info()}\n")

    elif args.llm_action == "test":
        backend = get_backend(config)
        if isinstance(backend, NullBackend):
            print("\n  No LLM configured. Run: mnemion llm setup\n")
            return
        print(f"\n  Testing {backend.info()} ...")
        messages = [
            {"role": "system", "content": "You are a helpful assistant. Be brief."},
            {"role": "user", "content": "Say exactly: MNEMION_OK"},
        ]
        result = backend.chat(messages, max_tokens=20)
        if result:
            print(f"  Response: {result}")
            print("  Test PASSED\n")
        else:
            print("  Test FAILED — no response. Check the backend is running.\n")

    elif args.llm_action == "setup":
        _cmd_llm_setup(config, BACKEND_DEFAULTS, BACKEND_LABELS)

    else:
        print("\n  Usage: mnemion llm <setup|status|test|start|stop>\n")


def _cmd_llm_setup(config, BACKEND_DEFAULTS, BACKEND_LABELS):
    """Interactive LLM backend wizard."""
    from .llm_backend import get_backend

    print("\n  Mnemion — LLM Backend Setup")
    print("  " + "-" * 45)
    print("  The LLM backend powers contradiction detection.")
    print("  It runs in the background and is optional.\n")

    ordered = ["none", "ollama", "lmstudio", "vllm", "custom"]
    for i, key in enumerate(ordered, 1):
        marker = "  "
        if config.llm.get("backend", "none") == key:
            marker = "* "  # mark current
        print(f"  {marker}{i}. {BACKEND_LABELS[key]}")

    print()
    raw = input("  Choose [1-5] (Enter = keep current): ").strip()
    if not raw:
        print("  No change.\n")
        return

    try:
        idx = int(raw) - 1
        backend_name = ordered[idx]
    except (ValueError, IndexError):
        print("  Invalid choice.\n")
        return

    if backend_name == "none":
        config.save_llm_config("none")
        print("  LLM disabled. Contradiction detection will be skipped.\n")
        return

    defaults = BACKEND_DEFAULTS.get(backend_name, {})
    current_llm = config.llm
    default_url = current_llm.get("url") or defaults.get("url", "")
    default_model = current_llm.get("model") or defaults.get("model", "")

    print()
    url_prompt = f"  Base URL [{default_url}]: "
    url = input(url_prompt).strip() or default_url

    model_hint = "(leave blank for LM Studio auto-select)" if backend_name == "lmstudio" else ""
    model_prompt = f"  Model name [{default_model}] {model_hint}: "
    model = input(model_prompt).strip() or default_model

    api_key = ""
    if backend_name == "custom":
        api_key = input("  API key (leave blank if none): ").strip()

    # Auto-start / lifecycle config (vllm and custom only)
    start_script = ""
    startup_timeout = 90
    idle_timeout = 300
    if backend_name in ("vllm", "custom"):
        print()
        print("  -- Auto-start / lifecycle (optional) --")
        print("  Set a start_script to let Mnemion launch the server automatically")
        print("  when contradiction detection needs it, and stop it when idle.")
        print("  Examples:")
        print("    wsl:///home/user/run_vllm.sh    (WSL on Windows)")
        print("    /home/user/run_vllm.sh          (Linux / macOS)")
        default_script = current_llm.get("start_script", "")
        start_script = (
            input(f"  Start script [{default_script or 'blank = disabled'}]: ").strip()
            or default_script
        )
        if start_script:
            default_startup = current_llm.get("startup_timeout", 90)
            raw = input(f"  Startup timeout seconds [{default_startup}]: ").strip()
            startup_timeout = int(raw) if raw.isdigit() else default_startup

            default_idle_min = current_llm.get("idle_timeout", 300) // 60
            raw = input(f"  Auto-stop after idle minutes [{default_idle_min}]: ").strip()
            idle_timeout = (int(raw) * 60) if raw.isdigit() else (default_idle_min * 60)

    # Test before saving
    print("\n  Testing connection...", end=" ", flush=True)
    config.save_llm_config(
        backend_name,
        url=url,
        model=model,
        api_key=api_key,
        start_script=start_script,
        startup_timeout=startup_timeout,
        idle_timeout=idle_timeout,
    )
    backend = get_backend(config)

    if backend.ping():
        print("OK")
        result = backend.chat(
            [{"role": "user", "content": "Reply with exactly: OK"}], max_tokens=10
        )
        if result:
            print(f"  Model response: {result.strip()[:80]}")
        print("\n  Saved to ~/.mnemion/config.json")
        print(f"  Backend: {backend_name}  url={url}  model={model}\n")
    else:
        print("UNREACHABLE")
        print(f"  Could not reach {url}")
        print("  Config saved anyway — fix the URL or start your LLM server, then re-run setup.\n")


def cmd_librarian(args):
    """Daily background Anaktoron tidy-up via local LLM."""
    import json
    from .librarian import run_librarian, show_status

    if getattr(args, "status", False):
        show_status()
        return

    stats = run_librarian(
        limit=getattr(args, "limit", 50),
        wing=getattr(args, "wing", None),
        dry_run=getattr(args, "dry_run", False),
    )
    print(json.dumps(stats, indent=2))


def cmd_hook(args):
    """Run hook logic: reads JSON from stdin, outputs JSON to stdout."""
    from .hooks_cli import run_hook

    run_hook(hook_name=args.hook, harness=args.harness)


def cmd_instructions(args):
    """Output skill instructions to stdout."""
    from .instructions_cli import run_instructions

    run_instructions(name=args.name)


def cmd_compress(args):
    """Compress drawers in a wing using AAAK Dialect."""
    import chromadb
    from .dialect import Dialect

    cfg = MnemionConfig()
    anaktoron_path = os.path.expanduser(args.palace) if args.palace else cfg.anaktoron_path
    col_name = cfg.collection_name

    # Load dialect (with optional entity config)
    config_path = args.config
    if not config_path:
        for candidate in ["entities.json", os.path.join(anaktoron_path, "entities.json")]:
            if os.path.exists(candidate):
                config_path = candidate
                break

    if config_path and os.path.exists(config_path):
        dialect = Dialect.from_config(config_path)
        print(f"  Loaded entity config: {config_path}")
    else:
        dialect = Dialect()

    # Connect to Anaktoron
    try:
        client = chromadb.PersistentClient(path=anaktoron_path)
        col = client.get_collection(col_name)
    except Exception:
        print(f"\n  No Anaktoron found at {anaktoron_path}")
        print("  Run: mnemion init <dir> then mnemion mine <dir>")
        sys.exit(1)

    # Query drawers in batches to avoid SQLite variable limit (~999)
    where = {"wing": args.wing} if args.wing else None
    _BATCH = 500
    docs, metas, ids = [], [], []
    offset = 0
    while True:
        try:
            kwargs = {"include": ["documents", "metadatas"], "limit": _BATCH, "offset": offset}
            if where:
                kwargs["where"] = where
            batch = col.get(**kwargs)
        except Exception as e:
            if not docs:
                print(f"\n  Error reading drawers: {e}")
                sys.exit(1)
            break
        batch_docs = batch.get("documents", [])
        if not batch_docs:
            break
        docs.extend(batch_docs)
        metas.extend(batch.get("metadatas", []))
        ids.extend(batch.get("ids", []))
        offset += len(batch_docs)
        if len(batch_docs) < _BATCH:
            break

    if not docs:
        wing_label = f" in wing '{args.wing}'" if args.wing else ""
        print(f"\n  No drawers found{wing_label}.")
        return

    print(
        f"\n  Compressing {len(docs)} drawers"
        + (f" in wing '{args.wing}'" if args.wing else "")
        + "..."
    )
    print()

    total_original = 0
    total_compressed = 0
    compressed_entries = []

    for doc, meta, doc_id in zip(docs, metas, ids):
        compressed = dialect.compress(doc, metadata=meta)
        stats = dialect.compression_stats(doc, compressed)

        total_original += stats["original_chars"]
        total_compressed += stats["compressed_chars"]

        compressed_entries.append((doc_id, compressed, meta, stats))

        if args.dry_run:
            wing_name = meta.get("wing", "?")
            room_name = meta.get("room", "?")
            source = Path(meta.get("source_file", "?")).name
            print(f"  [{wing_name}/{room_name}] {source}")
            print(
                f"    {stats['original_tokens']}t -> {stats['compressed_tokens']}t ({stats['ratio']:.1f}x)"
            )
            print(f"    {compressed}")
            print()

    # Store compressed versions (unless dry-run)
    if not args.dry_run:
        try:
            comp_col = client.get_or_create_collection("mnemion_compressed")
            for doc_id, compressed, meta, stats in compressed_entries:
                comp_meta = dict(meta)
                comp_meta["compression_ratio"] = round(stats["ratio"], 1)
                comp_meta["original_tokens"] = stats["original_tokens"]
                comp_col.upsert(
                    ids=[doc_id],
                    documents=[compressed],
                    metadatas=[comp_meta],
                )
            print(
                f"  Stored {len(compressed_entries)} compressed drawers in 'mnemion_compressed' collection."
            )
        except Exception as e:
            print(f"  Error storing compressed drawers: {e}")
            sys.exit(1)

    # Summary
    ratio = total_original / max(total_compressed, 1)
    orig_tokens = Dialect.count_tokens("x" * total_original)
    comp_tokens = Dialect.count_tokens("x" * total_compressed)
    print(f"  Total: {orig_tokens:,}t -> {comp_tokens:,}t ({ratio:.1f}x compression)")
    if args.dry_run:
        print("  (dry run -- nothing stored)")


def main():
    parser = argparse.ArgumentParser(
        description="Mnemion — Give your AI a memory. No API key required.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--palace",  # kept for backward compat; controls anaktoron_path
        default=None,
        help="Where the Anaktoron lives (default: from ~/.mnemion/config.json or ~/.mnemion/anaktoron)",
    )

    sub = parser.add_subparsers(dest="command")

    # init
    p_init = sub.add_parser("init", help="Detect rooms from your folder structure")
    p_init.add_argument("dir", help="Project directory to set up")
    p_init.add_argument(
        "--yes", action="store_true", help="Auto-accept all detected entities (non-interactive)"
    )

    # mine
    p_mine = sub.add_parser("mine", help="Mine files into the Anaktoron")
    p_mine.add_argument("dir", help="Directory to mine")
    p_mine.add_argument(
        "--mode",
        choices=["projects", "convos"],
        default="projects",
        help="Ingest mode: 'projects' for code/docs (default), 'convos' for chat exports",
    )
    p_mine.add_argument("--wing", default=None, help="Wing name (default: directory name)")
    p_mine.add_argument(
        "--no-gitignore",
        action="store_true",
        help="Don't respect .gitignore files when scanning project files",
    )
    p_mine.add_argument(
        "--include-ignored",
        action="append",
        default=[],
        help="Always scan these project-relative paths even if ignored; repeat or pass comma-separated paths",
    )
    p_mine.add_argument(
        "--agent",
        default="mnemion",
        help="Your name — recorded on every drawer (default: mnemion)",
    )
    p_mine.add_argument("--limit", type=int, default=0, help="Max files to process (0 = all)")
    p_mine.add_argument(
        "--dry-run", action="store_true", help="Show what would be filed without filing"
    )
    p_mine.add_argument(
        "--extract",
        choices=["exchange", "general"],
        default="exchange",
        help="Extraction strategy for convos mode: 'exchange' (default) or 'general' (5 memory types)",
    )

    # search
    p_search = sub.add_parser("search", help="Find anything, exact words")
    p_search.add_argument("query", help="What to search for")
    p_search.add_argument("--wing", default=None, help="Limit to one project")
    p_search.add_argument("--room", default=None, help="Limit to one room")
    p_search.add_argument("--results", type=int, default=5, help="Number of results")

    # compress
    p_compress = sub.add_parser(
        "compress", help="Compress drawers using AAAK Dialect (~30x reduction)"
    )
    p_compress.add_argument("--wing", default=None, help="Wing to compress (default: all wings)")
    p_compress.add_argument(
        "--dry-run", action="store_true", help="Preview compression without storing"
    )
    p_compress.add_argument(
        "--config", default=None, help="Entity config JSON (e.g. entities.json)"
    )

    # wake-up
    p_wakeup = sub.add_parser("wake-up", help="Show L0 + L1 wake-up context (~600-900 tokens)")
    p_wakeup.add_argument("--wing", default=None, help="Wake-up for a specific project/wing")

    # split
    p_split = sub.add_parser(
        "split",
        help="Split concatenated transcript mega-files into per-session files (run before mine)",
    )
    p_split.add_argument("dir", help="Directory containing transcript files")
    p_split.add_argument(
        "--output-dir",
        default=None,
        help="Write split files here (default: same directory as source files)",
    )
    p_split.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be split without writing files",
    )
    p_split.add_argument(
        "--min-sessions",
        type=int,
        default=2,
        help="Only split files containing at least N sessions (default: 2)",
    )

    # hook
    p_hook = sub.add_parser(
        "hook",
        help="Run hook logic (reads JSON from stdin, outputs JSON to stdout)",
    )
    hook_sub = p_hook.add_subparsers(dest="hook_action")
    p_hook_run = hook_sub.add_parser("run", help="Execute a hook")
    p_hook_run.add_argument(
        "--hook",
        required=True,
        choices=["session-start", "stop", "precompact"],
        help="Hook name to run",
    )
    p_hook_run.add_argument(
        "--harness",
        required=True,
        choices=["claude-code", "codex"],
        help="Harness type (determines stdin JSON format)",
    )

    # instructions
    p_instructions = sub.add_parser(
        "instructions",
        help="Output skill instructions to stdout",
    )
    instructions_sub = p_instructions.add_subparsers(dest="instructions_name")
    for instr_name in ["init", "search", "mine", "help", "status"]:
        instructions_sub.add_parser(instr_name, help=f"Output {instr_name} instructions")

    # llm
    p_llm = sub.add_parser(
        "llm",
        help="Configure LLM backend for contradiction detection (ollama, lmstudio, vllm, custom, none)",
    )
    llm_sub = p_llm.add_subparsers(dest="llm_action")
    llm_sub.add_parser("setup", help="Interactive wizard to choose and configure a backend")
    llm_sub.add_parser("status", help="Show current backend config and ping the endpoint")
    llm_sub.add_parser("test", help="Send a test prompt and verify the backend responds")
    llm_sub.add_parser("start", help="Start the LLM server (auto-start must be configured)")
    llm_sub.add_parser("stop", help="Stop the LLM server")

    # restore
    p_restore = sub.add_parser(
        "restore",
        help="Import a JSON export (archive/drawers_export.json) into the local Anaktoron",
    )
    p_restore.add_argument(
        "file", help="Path to the JSON export file (e.g. archive/drawers_export.json)"
    )
    p_restore.add_argument(
        "--merge",
        action="store_true",
        help="Add imported drawers to an existing Anaktoron (default: abort if Anaktoron not empty)",
    )
    p_restore.add_argument(
        "--replace",
        action="store_true",
        help="Wipe the existing Anaktoron and restore from the export",
    )
    p_restore.add_argument(
        "--batch-size",
        type=int,
        default=50,
        dest="batch_size",
        help="Drawers per ChromaDB write batch (default: 50). Reduce if restore is killed by OOM.",
    )

    # repair
    sub.add_parser(
        "repair",
        help="Rebuild Anaktoron vector index from stored data (fixes segfaults after corruption)",
    )

    # librarian
    p_librarian = sub.add_parser(
        "librarian",
        help="Background tidy-up: contradiction scan, room re-classification, KG extraction",
    )
    p_librarian.add_argument(
        "--limit", type=int, default=50, help="Max drawers to process per run (default: 50)"
    )
    p_librarian.add_argument("--wing", default=None, help="Limit to one wing")
    p_librarian.add_argument(
        "--dry-run", action="store_true", help="Preview what would be done without writing"
    )
    p_librarian.add_argument(
        "--status", action="store_true", help="Show librarian state and pending count"
    )

    # status
    sub.add_parser("status", help="Show what's been filed")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Handle two-level subcommands
    if args.command == "llm":
        if not getattr(args, "llm_action", None):
            p_llm.print_help()
            return
        cmd_llm(args)
        return

    if args.command == "hook":
        if not getattr(args, "hook_action", None):
            p_hook.print_help()
            return
        cmd_hook(args)
        return

    if args.command == "instructions":
        name = getattr(args, "instructions_name", None)
        if not name:
            p_instructions.print_help()
            return
        args.name = name
        cmd_instructions(args)
        return

    dispatch = {
        "init": cmd_init,
        "mine": cmd_mine,
        "restore": cmd_restore,
        "split": cmd_split,
        "search": cmd_search,
        "compress": cmd_compress,
        "wake-up": cmd_wakeup,
        "repair": cmd_repair,
        "status": cmd_status,
        "llm": cmd_llm,
        "librarian": cmd_librarian,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()

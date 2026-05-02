"""Manifest and git-author entity discovery for init."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .corpus_origin import CorpusOriginResult

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.9 fallback
    tomllib = None


@dataclass(frozen=True)
class DetectedProject:
    name: str
    source: str
    confidence: float = 0.95


@dataclass(frozen=True)
class DetectedPerson:
    name: str
    source: str
    confidence: float = 0.8
    frequency: int = 1


def _manifest_projects(root: Path) -> list[DetectedProject]:
    projects: list[DetectedProject] = []
    pyproject = root / "pyproject.toml"
    if pyproject.is_file() and tomllib is not None:
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            name = (data.get("project") or {}).get("name") or (data.get("tool") or {}).get(
                "poetry", {}
            ).get("name")
            if name:
                projects.append(DetectedProject(str(name), "pyproject.toml"))
        except (OSError, tomllib.TOMLDecodeError):
            pass
    elif pyproject.is_file():
        name = _parse_toml_section_name(pyproject, {"project", "tool.poetry"})
        if name:
            projects.append(DetectedProject(name, "pyproject.toml"))

    package = root / "package.json"
    if package.is_file():
        try:
            name = json.loads(package.read_text(encoding="utf-8")).get("name")
            if name:
                projects.append(DetectedProject(str(name), "package.json"))
        except (OSError, json.JSONDecodeError):
            pass

    cargo = root / "Cargo.toml"
    if cargo.is_file() and tomllib is not None:
        try:
            name = (tomllib.loads(cargo.read_text(encoding="utf-8")).get("package") or {}).get(
                "name"
            )
            if name:
                projects.append(DetectedProject(str(name), "Cargo.toml"))
        except (OSError, tomllib.TOMLDecodeError):
            pass
    elif cargo.is_file():
        name = _parse_toml_section_name(cargo, {"package"})
        if name:
            projects.append(DetectedProject(name, "Cargo.toml"))

    gomod = root / "go.mod"
    if gomod.is_file():
        try:
            first = gomod.read_text(encoding="utf-8").splitlines()[0]
            if first.startswith("module "):
                projects.append(DetectedProject(first.split()[-1].split("/")[-1], "go.mod"))
        except (OSError, IndexError):
            pass
    return _dedupe_projects(projects)


def _parse_toml_section_name(path: Path, sections: set[str]) -> str | None:
    current = None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line.strip("[]").strip()
            continue
        if current in sections and line.startswith("name") and "=" in line:
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
            return value or None
    return None


def _dedupe_projects(projects: Iterable[DetectedProject]) -> list[DetectedProject]:
    seen = set()
    result = []
    for project in projects:
        key = project.name.lower()
        if key not in seen:
            seen.add(key)
            result.append(project)
    return result


def _git_people(root: Path) -> list[DetectedPerson]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "log", "--format=%aN"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return []
    if proc.returncode != 0:
        return []

    counts: dict[str, int] = {}
    for raw in proc.stdout.splitlines():
        name = raw.strip()
        if not name or re.search(r"\b(bot|github-actions|dependabot)\b", name, re.I):
            continue
        counts[name] = counts.get(name, 0) + 1

    return [
        DetectedPerson(name=name, source="git", confidence=0.7, frequency=count)
        for name, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)
    ]


def scan(root: str | Path) -> tuple[list[DetectedProject], list[DetectedPerson]]:
    path = Path(root).expanduser().resolve()
    return _manifest_projects(path), _git_people(path)


def _entity(name: str, entity_type: str, confidence: float, frequency: int, signal: str) -> dict:
    return {
        "name": name,
        "type": entity_type,
        "confidence": round(confidence, 2),
        "frequency": frequency,
        "signals": [signal],
    }


def reclassify_agent_personas(detected: dict, persona_names: Iterable[str]) -> dict:
    personas = {name.lower() for name in persona_names}
    result = {
        "people": [],
        "projects": list(detected.get("projects", [])),
        "uncertain": list(detected.get("uncertain", [])),
        "agent_personas": list(detected.get("agent_personas", [])),
    }
    for entity in detected.get("people", []):
        if entity["name"].lower() in personas:
            persona = dict(entity)
            persona["type"] = "agent_persona"
            persona["signals"] = list(persona.get("signals", [])) + ["AI dialogue origin"]
            result["agent_personas"].append(persona)
        else:
            result["people"].append(entity)
    return result


def to_detected_dict(projects: list[DetectedProject], people: list[DetectedPerson]) -> dict:
    return {
        "people": [
            _entity(person.name, "person", person.confidence, person.frequency, person.source)
            for person in people[:15]
        ],
        "projects": [
            _entity(project.name, "project", project.confidence, 1, project.source)
            for project in projects[:10]
        ],
        "uncertain": [],
        "agent_personas": [],
    }


def discover_entities(
    root: str | Path,
    corpus_origin: CorpusOriginResult | None = None,
    max_files: int = 10,
) -> dict:
    projects, people = scan(root)
    detected = to_detected_dict(projects, people)

    try:
        from .entity_detector import detect_entities, scan_for_detection

        regex_detected = detect_entities(scan_for_detection(str(root), max_files=max_files))
        detected["people"].extend(regex_detected.get("people", []))
        detected["projects"].extend(regex_detected.get("projects", []))
        detected["uncertain"].extend(regex_detected.get("uncertain", []))
    except Exception:
        pass

    if corpus_origin:
        detected = reclassify_agent_personas(detected, corpus_origin.agent_persona_names)

    return detected

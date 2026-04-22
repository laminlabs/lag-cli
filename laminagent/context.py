from __future__ import annotations

from pathlib import Path
from typing import Any

import lamindb as ln


def get_local_skill(
    *, topic: str, run_uid: str, skills_root: str | None = None, limit: int = 3
) -> dict[str, Any]:
    root = Path(skills_root or "~/work/repos/scientific-agent-skills").expanduser()
    if not root.exists():
        return {
            "run_uid": run_uid,
            "matches": [],
            "message": f"Skills root not found: {root}",
        }

    matches: list[dict[str, str]] = []
    topic_lower = topic.lower()
    for skill_file in root.rglob("SKILL.md"):
        if len(matches) >= limit:
            break
        rel = str(skill_file.relative_to(root))
        if topic_lower in rel.lower():
            content = skill_file.read_text(encoding="utf-8")
            matches.append({"path": str(skill_file), "content": content[:8000]})
            continue
        content = skill_file.read_text(encoding="utf-8")
        if topic_lower in content.lower():
            matches.append({"path": str(skill_file), "content": content[:8000]})

    return {
        "run_uid": run_uid,
        "matches": matches,
        "message": f"Found {len(matches)} local skill matches for '{topic}'.",
    }


def get_lamindb_skill(*, query: str, run_uid: str, limit: int = 5) -> dict[str, Any]:
    """Best-effort direct lookup from laminlabs/biomed-skills."""
    original_slug: str | None = None
    warnings: list[str] = []
    try:
        original_slug = str(ln.setup.settings.instance.slug)
    except Exception as exc:
        original_slug = None
        warnings.append(f"Could not read current LaminDB instance before lookup: {exc}")

    try:
        ln.connect("laminlabs/biomed-skills")
    except Exception as exc:
        return {
            "run_uid": run_uid,
            "query": query,
            "results": [],
            "message": f"Could not connect to laminlabs/biomed-skills: {exc}",
        }

    query_lower = query.lower()
    results: list[dict[str, str]] = []

    try:
        transforms = ln.Transform.filter().all()
        for transform in transforms:
            name = str(getattr(transform, "name", "") or "")
            desc = str(getattr(transform, "description", "") or "")
            haystack = f"{name}\n{desc}".lower()
            if query_lower in haystack:
                results.append(
                    {
                        "type": "transform",
                        "uid": str(transform.uid),
                        "name": name,
                        "description": desc[:1000],
                    }
                )
                if len(results) >= limit:
                    break
    except Exception as exc:
        warnings.append(f"Transform lookup failed: {exc}")

    try:
        if len(results) < limit:
            artifacts = ln.Artifact.filter().all()
            for artifact in artifacts:
                desc = str(getattr(artifact, "description", "") or "")
                key = str(getattr(artifact, "key", "") or "")
                haystack = f"{key}\n{desc}".lower()
                if query_lower in haystack:
                    results.append(
                        {
                            "type": "artifact",
                            "uid": str(artifact.uid),
                            "key": key,
                            "description": desc[:1000],
                        }
                    )
                    if len(results) >= limit:
                        break
    except Exception as exc:
        warnings.append(f"Artifact lookup failed: {exc}")

    payload = {
        "run_uid": run_uid,
        "query": query,
        "results": results,
        "message": f"Found {len(results)} LaminDB matches for '{query}'.",
        "warnings": warnings,
    }
    if original_slug:
        try:
            ln.connect(original_slug)
        except Exception as exc:
            warnings.append(
                f"Could not reconnect to original instance {original_slug}: {exc}"
            )
    return payload

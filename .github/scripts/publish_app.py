#!/usr/bin/env python3
"""Validate an IIXII Store app-submission issue and update catalog/registry.json."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

SECTION_RE = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)
APP_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+$")
GITHUB_REPO_RE = re.compile(
    r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?/?$"
)


def parse_sections(body: str) -> dict[str, str]:
    matches = list(SECTION_RE.finditer(body))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        value = body[start:end].strip()
        if value == "_No response_":
            value = ""
        sections[match.group(1).strip().lower()] = value
    return sections


def require(sections: dict[str, str], label: str) -> str:
    value = sections.get(label.lower(), "").strip()
    if not value:
        raise ValueError(f"Missing required issue field: {label}")
    return value


def validate_https_url(value: str, field: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"{field} must be a complete HTTPS URL: {value}")
    return value


def parse_screenshots(raw: str) -> list[str]:
    screenshots: list[str] = []
    for line in raw.splitlines():
        value = re.sub(r"^[-*]\s+", "", line.strip())
        if not value:
            continue
        validate_https_url(value, "Screenshot URL")
        if value not in screenshots:
            screenshots.append(value)
    return screenshots


def load_registry(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": 1, "generated_at": "", "apps": []}

    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {"schema_version": 1, "generated_at": "", "apps": data}
    if not isinstance(data, dict) or not isinstance(data.get("apps"), list):
        raise ValueError("catalog/registry.json must contain an apps array.")
    if int(data.get("schema_version", 1)) != 1:
        raise ValueError("Only catalogue schema_version 1 is supported.")
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue-body", required=True, type=Path)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--issue-number", required=True)
    args = parser.parse_args()

    sections = parse_sections(args.issue_body.read_text(encoding="utf-8"))

    app_name = require(sections, "App name")
    app_id = require(sections, "App ID").lower()
    package_name = require(sections, "Android package name")
    source = require(sections, "GitHub source repository").rstrip("/")
    description = require(sections, "Description")
    icon_url = validate_https_url(require(sections, "Icon URL"), "Icon URL")
    screenshots = parse_screenshots(sections.get("screenshot urls", ""))

    if not APP_ID_RE.fullmatch(app_id):
        raise ValueError(
            "App ID must be lowercase and may contain only letters, numbers, dots, underscores, and hyphens."
        )
    if not PACKAGE_RE.fullmatch(package_name):
        raise ValueError("Android package name is invalid.")
    if not GITHUB_REPO_RE.fullmatch(source):
        raise ValueError("GitHub source repository must be a normal https://github.com/owner/repository URL.")

    registry = load_registry(args.registry)
    apps = registry["apps"]

    for existing in apps:
        if str(existing.get("id", "")).lower() == app_id:
            raise ValueError(f"An app with ID '{app_id}' already exists.")
        if existing.get("package_name") == package_name:
            raise ValueError(f"Package '{package_name}' is already listed.")

    now_ms = int(time.time() * 1000)
    app = {
        "id": app_id,
        "name": app_name,
        "package_name": package_name,
        "source": source,
        "description": description,
        "icon_url": icon_url,
        "screenshot_urls": screenshots,
        "last_modified": now_ms,
        "enabled": True,
    }

    apps.append(app)
    apps.sort(key=lambda item: int(item.get("last_modified", 0)), reverse=True)
    registry["schema_version"] = 1
    registry["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    args.registry.parent.mkdir(parents=True, exist_ok=True)
    args.registry.write_text(
        json.dumps(registry, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Published **{app_name}** (`{package_name}`) from issue #{args.issue_number}.")
    print(f"The live catalogue now contains {len(apps)} app(s).")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Publication failed: {error}", file=sys.stderr)
        raise SystemExit(1)

#!/usr/bin/env python3
"""Validate an IIXII Store app-edit issue and update catalog/registry.json."""

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

PACKAGE_RE = re.compile(
    r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+$"
)

GITHUB_REPO_RE = re.compile(
    r"^https://github\.com/"
    r"[A-Za-z0-9_.-]+/"
    r"[A-Za-z0-9_.-]+"
    r"(?:\.git)?/?$"
)


def parse_sections(body: str) -> dict[str, str]:
    matches = list(SECTION_RE.finditer(body))
    sections: dict[str, str] = {}

    for index, match in enumerate(matches):
        start = match.end()
        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(body)
        )

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


def optional(sections: dict[str, str], label: str) -> str:
    return sections.get(label.lower(), "").strip()


def validate_https_url(value: str, field: str) -> str:
    parsed = urlparse(value)

    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(
            f"{field} must be a complete HTTPS URL: {value}"
        )

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
        raise ValueError("catalog/registry.json does not exist.")

    data = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(data, list):
        return {
            "schema_version": 1,
            "generated_at": "",
            "apps": data,
        }

    if not isinstance(data, dict):
        raise ValueError(
            "catalog/registry.json must contain a JSON object."
        )

    if not isinstance(data.get("apps"), list):
        raise ValueError(
            "catalog/registry.json must contain an apps array."
        )

    if int(data.get("schema_version", 1)) != 1:
        raise ValueError(
            "Only catalogue schema_version 1 is supported."
        )

    return data


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--issue-body",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--registry",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--issue-number",
        required=True,
    )

    args = parser.parse_args()

    issue_body = args.issue_body.read_text(encoding="utf-8")
    sections = parse_sections(issue_body)

    current_app_id = require(
        sections,
        "Current App ID",
    ).lower()

    if not APP_ID_RE.fullmatch(current_app_id):
        raise ValueError("Current App ID is invalid.")

    new_app_name = optional(sections, "New app name")
    new_package_name = optional(
        sections,
        "New Android package name",
    )
    new_source = optional(
        sections,
        "New GitHub source repository",
    ).rstrip("/")
    new_description = optional(
        sections,
        "New description",
    )
    new_icon_url = optional(
        sections,
        "New icon URL",
    )

    screenshot_action = require(
        sections,
        "Screenshot handling",
    ).lower()

    replacement_screenshot_text = optional(
        sections,
        "Replacement screenshot URLs",
    )

    enabled_action = require(
        sections,
        "App visibility",
    ).lower()

    change_summary = require(
        sections,
        "Change summary",
    )

    registry = load_registry(args.registry)
    apps = registry["apps"]

    target_index: int | None = None

    for index, app in enumerate(apps):
        existing_id = str(app.get("id", "")).lower()

        if existing_id == current_app_id:
            target_index = index
            break

    if target_index is None:
        raise ValueError(
            f"No app with ID '{current_app_id}' exists."
        )

    current_app = apps[target_index]
    updated_app = dict(current_app)
    changed_fields: list[str] = []

    if new_app_name:
        if new_app_name != current_app.get("name"):
            updated_app["name"] = new_app_name
            changed_fields.append("name")

    if new_package_name:
        if not PACKAGE_RE.fullmatch(new_package_name):
            raise ValueError(
                "New Android package name is invalid."
            )

        for index, app in enumerate(apps):
            if index == target_index:
                continue

            if app.get("package_name") == new_package_name:
                raise ValueError(
                    f"Package '{new_package_name}' is already listed."
                )

        if new_package_name != current_app.get("package_name"):
            updated_app["package_name"] = new_package_name
            changed_fields.append("package_name")

    if new_source:
        if not GITHUB_REPO_RE.fullmatch(new_source):
            raise ValueError(
                "New GitHub source repository must be a normal "
                "https://github.com/owner/repository URL."
            )

        if new_source != str(current_app.get("source", "")).rstrip("/"):
            updated_app["source"] = new_source
            changed_fields.append("source")

    if new_description:
        if new_description != current_app.get("description"):
            updated_app["description"] = new_description
            changed_fields.append("description")

    if new_icon_url:
        validate_https_url(new_icon_url, "New icon URL")

        if new_icon_url != current_app.get("icon_url"):
            updated_app["icon_url"] = new_icon_url
            changed_fields.append("icon_url")

    current_screenshots = current_app.get(
        "screenshot_urls",
        [],
    )

    if screenshot_action == "keep current screenshots":
        pass

    elif screenshot_action == "replace screenshots":
        replacement_screenshots = parse_screenshots(
            replacement_screenshot_text
        )

        if not replacement_screenshots:
            raise ValueError(
                "At least one replacement screenshot URL is required "
                "when 'Replace screenshots' is selected."
            )

        if replacement_screenshots != current_screenshots:
            updated_app["screenshot_urls"] = replacement_screenshots
            changed_fields.append("screenshot_urls")

    elif screenshot_action == "remove all screenshots":
        if current_screenshots:
            updated_app["screenshot_urls"] = []
            changed_fields.append("screenshot_urls")

    else:
        raise ValueError(
            f"Unknown screenshot handling option: {screenshot_action}"
        )

    current_enabled = bool(current_app.get("enabled", True))

    if enabled_action == "keep current status":
        pass

    elif enabled_action == "enable app":
        if not current_enabled:
            updated_app["enabled"] = True
            changed_fields.append("enabled")

    elif enabled_action == "disable app":
        if current_enabled:
            updated_app["enabled"] = False
            changed_fields.append("enabled")

    else:
        raise ValueError(
            f"Unknown app visibility option: {enabled_action}"
        )

    if not changed_fields:
        raise ValueError(
            "The edit request does not change any catalogue fields."
        )

    now_ms = int(time.time() * 1000)

    updated_app["last_modified"] = now_ms
    apps[target_index] = updated_app

    apps.sort(
        key=lambda item: int(item.get("last_modified", 0)),
        reverse=True,
    )

    registry["schema_version"] = 1
    registry["generated_at"] = (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )

    args.registry.write_text(
        json.dumps(
            registry,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        f"Updated **{updated_app.get('name', current_app_id)}** "
        f"(`{updated_app.get('package_name', '')}`) "
        f"from issue #{args.issue_number}."
    )

    print(
        "Changed fields: "
        + ", ".join(f"`{field}`" for field in changed_fields)
        + "."
    )

    print(f"Change summary: {change_summary}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(
            f"App edit failed: {error}",
            file=sys.stderr,
        )
        raise SystemExit(1)

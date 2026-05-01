#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Daily personal activity export.

Sources:
- ActivityWatch on http://localhost:5600
- Android usage stats via ADB for connected OPPO phone/tablet

Outputs:
- G:\\我的云端硬盘\\journal\\_data\\raw\\computer\\YYYY-MM-DD.activitywatch.json
- G:\\我的云端硬盘\\journal\\_data\\raw\\phone\\YYYY-MM-DD.android.json
- G:\\我的云端硬盘\\journal\\_data\\raw\\pad\\YYYY-MM-DD.android.json
- G:\\我的云端硬盘\\journal\\_data\\normalized\\YYYY-MM-DD.activity.json
- Inserts a sorted summary into:
  G:\\我的云端硬盘\\journal\\daily\\YYYY-MM-DD.md
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any


ACTIVITYWATCH_BASE_URL = "http://localhost:5600"
DRIVE_ROOT = Path(r"G:\我的云端硬盘")
JOURNAL_ROOT = Path(os.environ.get("LIFEOS_JOURNAL_ROOT", r"D:\LifeOS\journal"))
JOURNAL_DIR = JOURNAL_ROOT / "daily"
TEMPLATE_DIR = JOURNAL_ROOT / "templates"
DAILY_TEMPLATE_PATH = TEMPLATE_DIR / "daily.md"
SYSTEM_DIR = JOURNAL_ROOT / "_system"
LOG_DIR = SYSTEM_DIR / "logs"
STATE_DIR = SYSTEM_DIR / "state"
DATA_DIR = JOURNAL_ROOT / "_data"
RAW_DIR = DATA_DIR / "raw"
RAW_COMPUTER_DIR = RAW_DIR / "computer"
RAW_PHONE_DIR = RAW_DIR / "phone"
RAW_PAD_DIR = RAW_DIR / "pad"
NORMALIZED_DIR = DATA_DIR / "normalized"
AI_DIR = DATA_DIR / "ai"
EXPORT_DIR = DRIVE_ROOT / "activitywatch"
MIN_SECONDS_IN_NOTE = 60
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

SYSTEM_PACKAGE_PREFIXES = (
    "android",
    "com.android.",
    "com.coloros.",
    "com.oplus.",
    "com.heytap.",
    "com.qualcomm.",
    "com.mediatek.",
    "com.google.android.gms",
    "com.google.android.gsf",
    "com.google.android.packageinstaller",
    "com.google.android.permissioncontroller",
)

SYSTEM_PACKAGES = {
    "com.android.systemui",
    "com.android.launcher",
    "com.android.providers.settings",
    "com.android.providers.media",
    "com.android.providers.downloads",
    "com.google.android.inputmethod.latin",
    "com.google.android.webview",
}


def log(message: str) -> None:
    print(f"[{dt.datetime.now().isoformat(timespec='seconds')}] {message}", flush=True)


def ensure_lifeos_structure() -> None:
    for path in (
        JOURNAL_DIR,
        TEMPLATE_DIR,
        LOG_DIR,
        STATE_DIR,
        RAW_COMPUTER_DIR,
        RAW_PHONE_DIR,
        RAW_PAD_DIR,
        NORMALIZED_DIR,
        AI_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)
    if not DAILY_TEMPLATE_PATH.exists():
        DAILY_TEMPLATE_PATH.write_text(default_daily_template(), encoding="utf-8")


def default_daily_template() -> str:
    return (
        "# {{date}} 日记\n"
        "## 今日概览\n"
        "## 今日计划\n"
        "- 最重要的一件事：\n"
        "- 次重要事项：\n"
        "- 健康/运动：\n"
        "- 学习/长期积累：\n"
        "## 今日目标\n"
        "## 时间记录\n"
        "{{AUTO_TIME_RECORD}}\n"
        "## 今日所想\n"
        "## 复利记录\n"
        "- 今天做了什么会让未来更容易：\n"
        "- 今天有什么行为在消耗未来：\n"
        "- 一个可以明天继续的小动作：\n"
        "## 今日总结\n"
        "{{AUTO_AI_SUMMARY}}\n"
        "## 学习记录\n"
    )


def today_range(target_date: dt.date) -> tuple[dt.datetime, dt.datetime]:
    start = dt.datetime.combine(target_date, dt.time.min).astimezone()
    end = start + dt.timedelta(days=1)
    return start, end


def iso_z(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def http_json(url: str, timeout: int = 20) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def seconds(value: Any) -> float:
    try:
        return max(0.0, float(value or 0))
    except (TypeError, ValueError):
        if isinstance(value, str):
            return parse_duration_token(value)
        return 0.0


def safe_filename_date(target_date: dt.date) -> str:
    return target_date.strftime("%Y-%m-%d")


def export_activitywatch(target_date: dt.date) -> dict[str, Any] | None:
    start, end = today_range(target_date)
    date_name = safe_filename_date(target_date)
    RAW_COMPUTER_DIR.mkdir(parents=True, exist_ok=True)

    try:
        buckets = http_json(f"{ACTIVITYWATCH_BASE_URL}/api/0/buckets/")
    except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
        log(f"ActivityWatch unavailable, skipped: {exc}")
        return None

    exported: dict[str, Any] = {
        "date": date_name,
        "source": "activitywatch",
        "start": iso_z(start),
        "end": iso_z(end),
        "buckets": {},
        "summary": {
            "apps": {},
            "windows": {},
            "websites": {},
        },
    }

    encoded_start = urllib.parse.quote(iso_z(start), safe="")
    encoded_end = urllib.parse.quote(iso_z(end), safe="")

    for bucket_id, bucket_info in buckets.items():
        events_url = (
            f"{ACTIVITYWATCH_BASE_URL}/api/0/buckets/"
            f"{urllib.parse.quote(bucket_id, safe='')}/events"
            f"?start={encoded_start}&end={encoded_end}"
        )
        try:
            events = http_json(events_url)
        except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
            log(f"ActivityWatch bucket skipped ({bucket_id}): {exc}")
            continue

        exported["buckets"][bucket_id] = {
            "metadata": bucket_info,
            "events": events,
        }
        summarize_activitywatch_bucket(bucket_id, events, exported["summary"])

    out_path = RAW_COMPUTER_DIR / f"{date_name}.activitywatch.json"
    write_json(out_path, exported)
    log(f"ActivityWatch exported: {out_path}")
    return exported


def summarize_activitywatch_bucket(bucket_id: str, events: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    bucket_lower = bucket_id.lower()
    is_window_bucket = "window" in bucket_lower
    is_web_bucket = "web" in bucket_lower or "browser" in bucket_lower

    for event in events:
        duration = seconds(event.get("duration"))
        data = event.get("data") or {}
        if duration <= 0:
            continue

        has_window_data = data.get("app") or data.get("title")
        has_web_data = data.get("url") or data.get("audible_url")

        if is_window_bucket or has_window_data:
            app = str(data.get("app") or "Unknown").strip() or "Unknown"
            title = str(data.get("title") or "").strip()
            summary["apps"][app] = summary["apps"].get(app, 0) + duration
            if title:
                key = f"{app} - {title}"
                summary["windows"][key] = summary["windows"].get(key, 0) + duration

        if is_web_bucket or has_web_data:
            url = str(data.get("url") or data.get("audible_url") or "").strip()
            if url:
                domain = urllib.parse.urlparse(url).netloc.lower() or url
                summary["websites"][domain] = summary["websites"].get(domain, 0) + duration


def adb_path() -> str:
    return os.environ.get("ADB", "adb")


def run_adb(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [adb_path(), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def list_adb_devices() -> list[str]:
    try:
        result = run_adb(["devices"], timeout=20)
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        log(f"ADB unavailable, Android export skipped: {exc}")
        return []

    devices: list[str] = []
    for line in result.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])
        elif len(parts) >= 2 and parts[1] in {"unauthorized", "offline"}:
            log(f"ADB device ignored ({parts[0]} is {parts[1]})")
    return devices


def adb_shell(serial: str, command: str, timeout: int = 80) -> str:
    result = run_adb(["-s", serial, "shell", command], timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "adb shell failed").strip())
    return result.stdout


def get_android_prop(serial: str, prop: str) -> str:
    try:
        return adb_shell(serial, f"getprop {prop}", timeout=15).strip()
    except Exception:
        return ""


def classify_android_device(serial: str, used_labels: set[str]) -> str:
    explicit = os.environ.get(f"ANDROID_DEVICE_{serial.replace(':', '_').replace('.', '_')}")
    if explicit in {"phone", "pad"}:
        return explicit

    model = get_android_prop(serial, "ro.product.model").lower()
    characteristics = get_android_prop(serial, "ro.build.characteristics").lower()
    smallest_width = get_android_prop(serial, "ro.sf.lcd_density")

    label = "pad" if any(token in f"{model} {characteristics}" for token in ("pad", "tablet")) else "phone"
    if label in used_labels:
        label = "pad" if "pad" not in used_labels else "phone"
    used_labels.add(label)
    log(f"ADB device {serial} classified as {label} ({model or 'unknown model'}, density {smallest_width or 'unknown'})")
    return label


def export_android_usage(serial: str, label: str, target_date: dt.date) -> dict[str, Any] | None:
    start, end = today_range(target_date)
    date_name = safe_filename_date(target_date)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    raw = ""
    for command in ("dumpsys usagestats --checkin", "dumpsys usagestats"):
        try:
            raw = adb_shell(serial, command, timeout=90)
            if raw.strip():
                break
        except Exception as exc:
            log(f"ADB {label} command failed ({command}): {exc}")

    if not raw.strip():
        log(f"ADB {label} produced no usagestats output, skipped")
        return None

    usage = parse_android_usage(raw)
    filtered = {
        package: duration
        for package, duration in usage.items()
        if duration >= MIN_SECONDS_IN_NOTE and not is_system_package(package)
    }

    exported = {
        "date": date_name,
        "source": "adb_usagestats",
        "device_label": label,
        "serial": serial,
        "model": get_android_prop(serial, "ro.product.model"),
        "start": iso_z(start),
        "end": iso_z(end),
        "apps": dict(sorted(filtered.items(), key=lambda item: item[1], reverse=True)),
        "raw_parser_note": "Parsed from adb shell dumpsys usagestats; output format varies by Android build.",
        "raw_output": raw,
    }

    raw_dir = RAW_PHONE_DIR if label == "phone" else RAW_PAD_DIR
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_path = raw_dir / f"{date_name}.android.json"
    write_json(out_path, exported)
    log(f"ADB {label} exported: {out_path}")
    return exported


def parse_android_usage(raw: str) -> dict[str, float]:
    totals: defaultdict[str, float] = defaultdict(float)
    current_package = ""

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        package_match = re.search(r"(?:package|pkg|packageName)=([a-zA-Z0-9_.]+)", stripped)
        if package_match:
            current_package = package_match.group(1)

        quoted_total = re.search(r"(?:totalTime(?:Foreground|Visible)?|totalFgTime|timeInForeground)=\"?([^\", ]+)\"?", stripped)
        if current_package and quoted_total:
            parsed = parse_duration_token(quoted_total.group(1))
            if parsed:
                totals[current_package] = max(totals[current_package], parsed)

        # Check-in output is comma-separated. Keep this deliberately broad:
        # package name plus one or more millisecond-looking duration fields.
        if "," in stripped:
            fields = [field.strip() for field in stripped.split(",")]
            package = next((field for field in fields if re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]*(?:\.[a-zA-Z0-9_]+)+", field)), "")
            if package:
                numeric_fields = [int(field) for field in fields if field.isdigit()]
                duration_ms = max((value for value in numeric_fields if 1000 <= value <= 24 * 60 * 60 * 1000), default=0)
                if duration_ms:
                    totals[package] = max(totals[package], duration_ms / 1000)

        # Plain dumpsys often contains lines like:
        # package=com.example totalTime="1h23m4s"
        inline = re.search(
            r"([a-zA-Z][a-zA-Z0-9_]*(?:\.[a-zA-Z0-9_]+)+).*?"
            r"(?:totalTime(?:Foreground|Visible)?|timeInForeground)=\"?([^\", ]+)\"?",
            stripped,
        )
        if inline:
            parsed = parse_duration_token(inline.group(2))
            if parsed:
                totals[inline.group(1)] = max(totals[inline.group(1)], parsed)

    return dict(totals)


def parse_duration_token(token: str) -> float:
    token = token.strip()
    if not token:
        return 0.0

    if token.isdigit():
        value = int(token)
        return value / 1000 if value > 24 * 60 * 60 else float(value)

    # ActivityWatch and some APIs may emit HH:MM:SS.microseconds-like values.
    clock_match = re.fullmatch(r"(?:(\d+):)?(\d{1,2}):(\d{1,2})(?:\.\d+)?", token)
    if clock_match:
        hours = int(clock_match.group(1) or 0)
        minutes = int(clock_match.group(2))
        secs = int(clock_match.group(3))
        return hours * 3600 + minutes * 60 + secs

    total = 0.0
    for number, unit in re.findall(r"(\d+(?:\.\d+)?)(ms|d|h|m|s)", token):
        value = float(number)
        if unit == "d":
            total += value * 86400
        elif unit == "h":
            total += value * 3600
        elif unit == "m":
            total += value * 60
        elif unit == "s":
            total += value
        elif unit == "ms":
            total += value / 1000
    return total


def is_system_package(package: str) -> bool:
    return package in SYSTEM_PACKAGES or package.startswith(SYSTEM_PACKAGE_PREFIXES)


def export_connected_android_devices(target_date: dt.date) -> dict[str, dict[str, Any]]:
    exports: dict[str, dict[str, Any]] = {}
    devices = list_adb_devices()
    if not devices:
        log("No authorized ADB devices connected; phone/pad export skipped")
        return exports

    used_labels: set[str] = set()
    for serial in devices:
        label = classify_android_device(serial, used_labels)
        if label in exports:
            log(f"Duplicate {label} device ignored: {serial}")
            continue
        exported = export_android_usage(serial, label, target_date)
        if exported:
            exports[label] = exported
    return exports


def write_json(path: Path, data: Any) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def read_json(path: Path) -> Any | None:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log(f"Could not read JSON {path}: {exc}")
    return None


def load_existing_exports(target_date: dt.date) -> tuple[dict[str, Any] | None, dict[str, dict[str, Any]]]:
    date_name = safe_filename_date(target_date)
    activitywatch = read_first_json(
        [
            RAW_COMPUTER_DIR / f"{date_name}.activitywatch.json",
            EXPORT_DIR / f"{date_name}.json",
        ]
    )
    android_exports: dict[str, dict[str, Any]] = {}
    for label, raw_dir in (("phone", RAW_PHONE_DIR), ("pad", RAW_PAD_DIR)):
        data = read_first_json(
            [
                raw_dir / f"{date_name}.android.json",
                raw_dir / f"{date_name}-{label}.json",
                EXPORT_DIR / f"{date_name}-{label}.json",
            ]
        )
        if isinstance(data, dict):
            android_exports[label] = data
            continue
        tasker_data = load_tasker_ndjson(target_date, label)
        if tasker_data:
            android_exports[label] = tasker_data
    return activitywatch if isinstance(activitywatch, dict) else None, android_exports


def read_first_json(paths: list[Path]) -> Any | None:
    for path in paths:
        data = read_json(path)
        if data is not None:
            return data
    return None


def load_tasker_ndjson(target_date: dt.date, label: str) -> dict[str, Any] | None:
    date_name = safe_filename_date(target_date)
    paths = [
        (RAW_PHONE_DIR if label == "phone" else RAW_PAD_DIR) / f"{date_name}.{label}.ndjson",
        (RAW_PHONE_DIR if label == "phone" else RAW_PAD_DIR) / f"{date_name}-{label}.ndjson",
        EXPORT_DIR / f"{date_name}-{label}.ndjson",
        EXPORT_DIR / f"{date_name}-{label}.jsonl",
    ]
    path = next((candidate for candidate in paths if candidate.exists()), None)
    if not path:
        return None

    totals: defaultdict[str, float] = defaultdict(float)
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError as exc:
            log(f"Tasker log line skipped ({path}:{line_number}): {exc}")
            continue

        package = str(event.get("package") or event.get("app") or "").strip()
        duration = seconds(event.get("duration_seconds") or event.get("duration"))
        if not package or duration < MIN_SECONDS_IN_NOTE or is_system_package(package):
            continue
        totals[package] += duration
        events.append(event)

    if not totals:
        return None

    return {
        "date": date_name,
        "source": "tasker_ndjson",
        "device_label": label,
        "apps": dict(sorted(totals.items(), key=lambda item: item[1], reverse=True)),
        "events": events,
        "raw_file": str(path),
    }


def format_duration(total_seconds: float) -> str:
    total = int(round(total_seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m"
    return f"{secs}s"


def summary_items_from_exports(activitywatch: dict[str, Any] | None, android_exports: dict[str, dict[str, Any]]) -> list[tuple[str, float]]:
    normalized = normalize_activity_data(dt.date.today(), activitywatch, android_exports, write_file=False)
    return summary_items_from_normalized(normalized)


def normalize_activity_data(
    target_date: dt.date,
    activitywatch: dict[str, Any] | None,
    android_exports: dict[str, dict[str, Any]],
    write_file: bool = True,
) -> dict[str, Any]:
    date_name = safe_filename_date(target_date)
    normalized: dict[str, Any] = {
        "date": date_name,
        "schema_version": 1,
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "devices": {
            "computer": {"apps": [], "websites": []},
            "phone": {"apps": []},
            "pad": {"apps": []},
        },
        "sources": {},
    }

    if activitywatch:
        normalized["sources"]["computer"] = activitywatch.get("source", "activitywatch")
        apps = (activitywatch.get("summary") or {}).get("apps", {})
        websites = (activitywatch.get("summary") or {}).get("websites", {})
        normalized["devices"]["computer"]["apps"] = [
            {"name": name, "seconds": seconds(duration), "source": "activitywatch"}
            for name, duration in sorted(apps.items(), key=lambda item: seconds(item[1]), reverse=True)
            if seconds(duration) >= MIN_SECONDS_IN_NOTE
        ]
        normalized["devices"]["computer"]["websites"] = [
            {"domain": domain, "seconds": seconds(duration), "source": "activitywatch"}
            for domain, duration in sorted(websites.items(), key=lambda item: seconds(item[1]), reverse=True)
            if seconds(duration) >= MIN_SECONDS_IN_NOTE
        ]

    for label, exported in android_exports.items():
        if label not in ("phone", "pad"):
            continue
        normalized["sources"][label] = exported.get("source", "android")
        apps = []
        for package, duration in (exported.get("apps") or {}).items():
            duration_seconds = seconds(duration)
            if duration_seconds < MIN_SECONDS_IN_NOTE:
                continue
            apps.append(
                {
                    "package": package,
                    "label": android_app_display_name(exported, package),
                    "seconds": duration_seconds,
                    "source": exported.get("source", "android"),
                }
            )
        normalized["devices"][label]["apps"] = sorted(apps, key=lambda item: item["seconds"], reverse=True)

    if write_file:
        NORMALIZED_DIR.mkdir(parents=True, exist_ok=True)
        out_path = NORMALIZED_DIR / f"{date_name}.activity.json"
        write_json(out_path, normalized)
        log(f"Normalized activity written: {out_path}")
    return normalized


def summary_items_from_normalized(normalized: dict[str, Any]) -> list[tuple[str, float]]:
    totals: defaultdict[str, float] = defaultdict(float)
    devices = normalized.get("devices") or {}

    computer = devices.get("computer") or {}
    for app in computer.get("apps") or []:
        totals[f"电脑 / {app.get('name', 'Unknown')}"] += seconds(app.get("seconds"))
    for site in computer.get("websites") or []:
        totals[f"网站 / {site.get('domain', 'unknown')}"] += seconds(site.get("seconds"))

    for label in ("phone", "pad"):
        device_name = "手机" if label == "phone" else "平板"
        for app in (devices.get(label) or {}).get("apps") or []:
            app_name = app.get("label") or app.get("package") or "Unknown"
            totals[f"{device_name} / {app_name}"] += seconds(app.get("seconds"))

    return sorted(
        ((name, duration) for name, duration in totals.items() if duration >= MIN_SECONDS_IN_NOTE),
        key=lambda item: item[1],
        reverse=True,
    )


def android_app_display_name(exported: dict[str, Any], package: str) -> str:
    for detail in exported.get("app_details") or []:
        if detail.get("package") == package and detail.get("label"):
            return str(detail["label"])
    for event in exported.get("events") or []:
        if event.get("package") == package and event.get("label"):
            return str(event["label"])
    return package


def upsert_journal_time_record(target_date: dt.date, activitywatch: dict[str, Any] | None, android_exports: dict[str, dict[str, Any]]) -> None:
    normalized = normalize_activity_data(target_date, activitywatch, android_exports, write_file=False)
    upsert_journal_from_normalized(target_date, normalized)


def upsert_journal_from_normalized(target_date: dt.date, normalized: dict[str, Any]) -> None:
    date_name = safe_filename_date(target_date)
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    journal_path = JOURNAL_DIR / f"{date_name}.md"

    if journal_path.exists():
        text = journal_path.read_text(encoding="utf-8")
    else:
        text = render_daily_template(target_date)

    block = build_time_record_block(target_date, summary_items_from_normalized(normalized))
    updated = replace_time_record_section(text, block)
    journal_path.write_text(updated, encoding="utf-8")
    log(f"Journal updated: {journal_path}")


def render_daily_template(target_date: dt.date) -> str:
    date_name = safe_filename_date(target_date)
    if DAILY_TEMPLATE_PATH.exists():
        template = DAILY_TEMPLATE_PATH.read_text(encoding="utf-8")
    else:
        template = default_daily_template()
    return (
        template.replace("{{date}}", date_name)
        .replace("{{date:YYYY-MM-DD}}", date_name)
        .replace("{{AUTO_TIME_RECORD}}", "")
        .replace("{{AUTO_AI_SUMMARY}}", "")
    )


def build_time_record_block(target_date: dt.date, items: list[tuple[str, float]]) -> str:
    generated = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "<!-- daily_export:start -->",
        f"- 自动汇总时间：{generated}",
    ]
    if items:
        lines.extend(f"- {name}: {format_duration(duration)}" for name, duration in items)
    else:
        lines.append("- 暂无超过 1 分钟的使用记录。")
    lines.append("<!-- daily_export:end -->")
    return "\n".join(lines)


def replace_time_record_section(text: str, block: str) -> str:
    marker_pattern = re.compile(
        r"<!-- daily_export:start -->.*?<!-- daily_export:end -->",
        flags=re.DOTALL,
    )
    if marker_pattern.search(text):
        return marker_pattern.sub(block, text)

    heading_match = re.search(r"(?m)^## 时间记录\s*$", text)
    if not heading_match:
        stripped = text.rstrip()
        return f"{stripped}\n\n## 时间记录\n{block}\n"

    insert_at = heading_match.end()
    next_heading = re.search(r"(?m)^##\s+", text[insert_at:])
    if next_heading:
        section_end = insert_at + next_heading.start()
        existing = text[insert_at:section_end]
        preserved = "\n".join(
            line for line in existing.splitlines()
            if line.strip() and "脚本在这里插入" not in line
        ).strip()
        replacement = f"\n{block}\n"
        if preserved:
            replacement += f"{preserved}\n"
        return text[:insert_at] + replacement + text[section_end:]

    return text[:insert_at] + f"\n{block}\n" + text[insert_at:]


def upsert_ai_summary(
    target_date: dt.date,
    activitywatch: dict[str, Any] | None,
    android_exports: dict[str, dict[str, Any]],
    normalized: dict[str, Any] | None = None,
) -> None:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        log("DEEPSEEK_API_KEY not set; AI summary skipped")
        return

    date_name = safe_filename_date(target_date)
    journal_path = JOURNAL_DIR / f"{date_name}.md"
    if not journal_path.exists():
        log("Journal file missing; AI summary skipped")
        return

    if normalized is None:
        normalized = normalize_activity_data(target_date, activitywatch, android_exports, write_file=False)
    time_items = summary_items_from_normalized(normalized)[:40]
    prompt = {
        "date": date_name,
        "top_usage": [{"name": name, "duration": format_duration(duration)} for name, duration in time_items],
        "activity": normalized,
        "journal": journal_path.read_text(encoding="utf-8")[:12000],
    }
    messages = [
        {
            "role": "system",
            "content": (
                "你是个人生活记录分析助手。基于用户当天日记和设备使用记录，"
                "输出简洁中文总结。不要编造事实；没有证据就写不确定。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请生成 Markdown，包含三部分：\n"
                "1. 今日模式：3-5 条观察\n"
                "2. 可能原因：2-4 条谨慎推断\n"
                "3. 明日建议：3 条具体行动\n\n"
                f"数据：\n{json.dumps(prompt, ensure_ascii=False)}"
            ),
        },
    ]
    payload = json.dumps(
        {
            "model": os.environ.get("DEEPSEEK_MODEL", DEEPSEEK_MODEL),
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 900,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        DEEPSEEK_API_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
        content = result["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        log(f"AI summary failed: {exc}")
        return

    text = journal_path.read_text(encoding="utf-8")
    block = "\n".join(
        [
            "<!-- daily_ai_summary:start -->",
            content,
            "<!-- daily_ai_summary:end -->",
        ]
    )
    updated = replace_ai_summary_section(text, block)
    journal_path.write_text(updated, encoding="utf-8")
    log("AI summary inserted")


def export_ai_context(target_date: dt.date, normalized: dict[str, Any]) -> Path | None:
    date_name = safe_filename_date(target_date)
    journal_path = JOURNAL_DIR / f"{date_name}.md"
    if not journal_path.exists():
        log("Journal file missing; AI context skipped")
        return None

    AI_DIR.mkdir(parents=True, exist_ok=True)
    out_path = AI_DIR / f"{date_name}.ai-context.md"
    time_items = summary_items_from_normalized(normalized)[:80]
    journal_text = journal_path.read_text(encoding="utf-8")
    lines = [
        f"# {date_name} AI 分析上下文",
        "",
        "## 使用说明",
        "把这整个文件发给 AI。要求 AI 只基于本文信息分析，不要编造事实。",
        "",
        "## 推荐提示词",
        "请基于下面的日记和设备使用记录，输出：",
        "1. 今日行为模式：3-5 条",
        "2. 日记内容与行为数据之间的关系",
        "3. 可能的长期复利行为和损耗行为",
        "4. 明天最值得做的 3 个具体调整",
        "5. 一个不超过 100 字的总结",
        "",
        "## 今日使用记录 Top",
    ]
    if time_items:
        lines.extend(f"- {name}: {format_duration(duration)}" for name, duration in time_items)
    else:
        lines.append("- 暂无超过 1 分钟的使用记录。")

    lines.extend(
        [
            "",
            "## 标准化活动 JSON",
            "```json",
            json.dumps(normalized, ensure_ascii=False, indent=2),
            "```",
            "",
            "## 当天日记",
            journal_text,
        ]
    )
    out_path.write_text("\n".join(lines), encoding="utf-8")
    log(f"AI context exported: {out_path}")
    return out_path


def replace_ai_summary_section(text: str, block: str) -> str:
    marker_pattern = re.compile(
        r"<!-- daily_ai_summary:start -->.*?<!-- daily_ai_summary:end -->",
        flags=re.DOTALL,
    )
    if marker_pattern.search(text):
        return marker_pattern.sub(block, text)

    heading_match = re.search(r"(?m)^## 今日总结\s*$", text)
    if not heading_match:
        return f"{text.rstrip()}\n\n## 今日总结\n{block}\n"

    insert_at = heading_match.end()
    return text[:insert_at] + f"\n{block}\n" + text[insert_at:]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export daily activity data and update Obsidian journal.")
    parser.add_argument("--date", help="Target date in YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--skip-aw", action="store_true", help="Skip ActivityWatch export.")
    parser.add_argument("--skip-adb", action="store_true", help="Skip Android ADB export.")
    parser.add_argument("--skip-journal", action="store_true", help="Skip Obsidian journal update.")
    parser.add_argument("--ai-summary", action="store_true", help="Use DeepSeek to insert an AI summary into the journal.")
    parser.add_argument("--ai-context", action="store_true", help="Export a standalone Markdown context file for manual AI analysis.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ensure_lifeos_structure()
    if args.date:
        target_date = dt.datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        target_date = dt.date.today()

    log(f"Daily export started for {target_date}")

    existing_activitywatch, existing_android_exports = load_existing_exports(target_date)

    activitywatch = existing_activitywatch if args.skip_aw else export_activitywatch(target_date)
    if activitywatch is None:
        activitywatch = existing_activitywatch

    android_exports = existing_android_exports if args.skip_adb else export_connected_android_devices(target_date)
    android_exports = {**existing_android_exports, **android_exports}

    normalized = normalize_activity_data(target_date, activitywatch, android_exports, write_file=True)

    if not args.skip_journal:
        upsert_journal_from_normalized(target_date, normalized)
        if args.ai_context:
            export_ai_context(target_date, normalized)
        if args.ai_summary:
            upsert_ai_summary(target_date, activitywatch, android_exports, normalized)

    log("Daily export finished")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log(f"Fatal error: {exc}")
        raise

import datetime as dt
import tempfile
import unittest
from pathlib import Path

import daily_export as daily


def configure_temp_lifeos(root: Path) -> None:
    daily.JOURNAL_ROOT = root / "journal"
    daily.JOURNAL_DIR = daily.JOURNAL_ROOT / "daily"
    daily.TEMPLATE_DIR = daily.JOURNAL_ROOT / "templates"
    daily.DAILY_TEMPLATE_PATH = daily.TEMPLATE_DIR / "daily.md"
    daily.SYSTEM_DIR = daily.JOURNAL_ROOT / "_system"
    daily.LOG_DIR = daily.SYSTEM_DIR / "logs"
    daily.STATE_DIR = daily.SYSTEM_DIR / "state"
    daily.DATA_DIR = daily.JOURNAL_ROOT / "_data"
    daily.RAW_DIR = daily.DATA_DIR / "raw"
    daily.RAW_COMPUTER_DIR = daily.RAW_DIR / "computer"
    daily.RAW_PHONE_DIR = daily.RAW_DIR / "phone"
    daily.RAW_PAD_DIR = daily.RAW_DIR / "pad"
    daily.NORMALIZED_DIR = daily.DATA_DIR / "normalized"
    daily.AI_DIR = daily.DATA_DIR / "ai"
    daily.EXPORT_DIR = root / "legacy_activitywatch"
    daily.ensure_lifeos_structure()


class DailyExportSmokeTest(unittest.TestCase):
    def test_existing_activitywatch_json_is_written_to_journal(self):
        root = Path(tempfile.mkdtemp())
        configure_temp_lifeos(root)

        daily.write_json(
            daily.RAW_COMPUTER_DIR / "2026-04-30.activitywatch.json",
            {
                "date": "2026-04-30",
                "summary": {
                    "apps": {"Code": 7200, "Chrome": 1800},
                    "websites": {"example.com": 600},
                },
            },
        )

        activitywatch, android_exports = daily.load_existing_exports(dt.date(2026, 4, 30))
        daily.upsert_journal_time_record(dt.date(2026, 4, 30), activitywatch, android_exports)

        note = (daily.JOURNAL_DIR / "2026-04-30.md").read_text(encoding="utf-8")
        self.assertIn("### 电脑应用", note)
        self.assertIn("- Code: 2h 00m", note)
        self.assertIn("- Chrome: 30m", note)
        self.assertIn("### 网站", note)
        self.assertIn("- example.com: 10m", note)

    def test_normalized_activity_file_is_written(self):
        root = Path(tempfile.mkdtemp())
        configure_temp_lifeos(root)

        activitywatch = {
            "date": "2026-04-30",
            "summary": {
                "apps": {"Code": 7200},
                "websites": {"example.com": 600},
            },
        }
        android = {
            "phone": {
                "source": "android_lifelogger",
                "apps": {"com.example.chat": 240},
                "app_details": [{"package": "com.example.chat", "label": "Chat"}],
            }
        }

        normalized = daily.normalize_activity_data(dt.date(2026, 4, 30), activitywatch, android)

        normalized_path = daily.NORMALIZED_DIR / "2026-04-30.activity.json"
        self.assertTrue(normalized_path.exists())
        self.assertEqual(normalized["devices"]["phone"]["apps"][0]["label"], "Chat")

    def test_tasker_ndjson_is_written_to_journal(self):
        root = Path(tempfile.mkdtemp())
        configure_temp_lifeos(root)

        (daily.RAW_PHONE_DIR / "2026-04-30-phone.ndjson").write_text(
            '{"date":"2026-04-30","device":"phone","package":"com.example.chat","label":"Chat","start_ts":1,"end_ts":121,"duration_seconds":120}\n'
            '{"date":"2026-04-30","device":"phone","package":"com.example.chat","label":"Chat","start_ts":200,"end_ts":320,"duration_seconds":120}\n',
            encoding="utf-8",
        )

        activitywatch, android_exports = daily.load_existing_exports(dt.date(2026, 4, 30))
        daily.upsert_journal_time_record(dt.date(2026, 4, 30), activitywatch, android_exports)

        note = (daily.JOURNAL_DIR / "2026-04-30.md").read_text(encoding="utf-8")
        self.assertIn("### 手机", note)
        self.assertIn("- Chat: 4m", note)

    def test_android_agent_json_is_loaded_from_long_term_raw_dir(self):
        root = Path(tempfile.mkdtemp())
        configure_temp_lifeos(root)

        daily.write_json(
            daily.RAW_PAD_DIR / "2026-04-30.android.json",
            {
                "date": "2026-04-30",
                "source": "android_lifelogger",
                "device_label": "pad",
                "apps": {"com.example.reader": 3600},
                "app_details": [{"package": "com.example.reader", "label": "Reader"}],
            },
        )

        activitywatch, android_exports = daily.load_existing_exports(dt.date(2026, 4, 30))
        normalized = daily.normalize_activity_data(dt.date(2026, 4, 30), activitywatch, android_exports, write_file=False)

        self.assertEqual(normalized["devices"]["pad"]["apps"][0]["label"], "Reader")
        self.assertEqual(normalized["devices"]["pad"]["apps"][0]["seconds"], 3600)

    def test_ai_context_export_contains_journal_and_activity(self):
        root = Path(tempfile.mkdtemp())
        configure_temp_lifeos(root)
        daily.JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
        (daily.JOURNAL_DIR / "2026-04-30.md").write_text(
            "# 2026-04-30 日记\n## 今日所想\n今天专注学习。\n",
            encoding="utf-8",
        )

        normalized = {
            "date": "2026-04-30",
            "schema_version": 1,
            "devices": {
                "computer": {"apps": [{"name": "Code", "seconds": 3600}], "websites": []},
                "phone": {"apps": []},
                "pad": {"apps": []},
            },
        }

        out_path = daily.export_ai_context(dt.date(2026, 4, 30), normalized)
        content = out_path.read_text(encoding="utf-8")

        self.assertIn("今天专注学习", content)
        self.assertIn("电脑 / Code: 1h 00m", content)
        self.assertIn("标准化活动 JSON", content)

    def test_web_bucket_title_does_not_create_unknown_app(self):
        summary = {"apps": {}, "windows": {}, "websites": {}}

        daily.summarize_activitywatch_bucket(
            "aw-watcher-web-chrome",
            [
                {
                    "duration": 120,
                    "data": {
                        "url": "https://example.com/page",
                        "title": "Example page",
                    },
                }
            ],
            summary,
        )

        self.assertNotIn("Unknown", summary["apps"])
        self.assertEqual(summary["websites"]["example.com"], 120)

    def test_grouped_summary_filters_system_items(self):
        normalized = {
            "devices": {
                "computer": {
                    "apps": [
                        {"name": "explorer.exe", "seconds": 9999},
                        {"name": "Code.exe", "seconds": 3600, "top_ranges": ["09:00-10:00"]},
                    ],
                    "websites": [
                        {"domain": "127.0.0.1:53682", "seconds": 9999},
                        {"domain": "github.com", "seconds": 1800, "top_ranges": ["10:00-10:30"]},
                    ],
                },
                "phone": {"apps": [{"label": "FolderSync", "package": "x", "seconds": 9999}, {"label": "WeChat", "package": "com.tencent.mm", "seconds": 120}]},
                "pad": {"apps": [{"label": "Reader", "package": "com.example.reader", "seconds": 240}]},
            }
        }

        block = daily.build_grouped_time_record_block(
            dt.date(2026, 4, 30),
            daily.grouped_summary_from_normalized(normalized),
        )

        self.assertIn("### 电脑应用", block)
        self.assertIn("- Code.exe: 1h 00m（主要时段：09:00-10:00）", block)
        self.assertIn("### 网站", block)
        self.assertIn("- github.com: 30m", block)
        self.assertIn("### 手机", block)
        self.assertIn("- WeChat: 2m", block)
        self.assertIn("### 平板", block)
        self.assertNotIn("explorer.exe", block)
        self.assertNotIn("FolderSync", block)

    def test_create_daily_note_from_template(self):
        root = Path(tempfile.mkdtemp())
        configure_temp_lifeos(root)

        path = daily.create_daily_note(dt.date(2026, 5, 2))
        content = path.read_text(encoding="utf-8")

        self.assertIn("# 2026-05-02 日记", content)
        self.assertIn("## 今日计划", content)

    def test_activitywatch_afk_filter_clips_long_events(self):
        activitywatch = {
            "buckets": {
                "aw-watcher-afk_test": {
                    "events": [
                        {
                            "timestamp": "2026-04-30T01:00:00+00:00",
                            "duration": 3600,
                            "data": {"status": "not-afk"},
                        }
                    ]
                },
                "aw-watcher-window_test": {
                    "events": [
                        {
                            "timestamp": "2026-04-30T00:00:00+00:00",
                            "duration": 7200,
                            "data": {"app": "Code", "title": "work"},
                        }
                    ]
                },
            },
            "summary": {"apps": {"Code": 7200}, "windows": {}, "websites": {}},
        }

        filtered = daily.apply_activitywatch_afk_filter(activitywatch)

        self.assertEqual(filtered["summary"]["apps"]["Code"], 3600)
        self.assertTrue(filtered["afk_filter"]["enabled"])

    def test_android_events_create_top_ranges(self):
        exported = {
            "source": "android_lifelogger",
            "apps": {"com.example.reader": 3600},
            "app_details": [{"package": "com.example.reader", "label": "Reader"}],
            "app_events": [
                {
                    "package": "com.example.reader",
                    "label": "Reader",
                    "start_ts": 1777500000,
                    "end_ts": 1777503600,
                    "duration_seconds": 3600,
                }
            ],
        }

        normalized = daily.normalize_activity_data(
            dt.date(2026, 4, 30),
            None,
            {"phone": exported},
            write_file=False,
        )

        self.assertEqual(normalized["devices"]["phone"]["apps"][0]["top_ranges"], ["06:00-07:00"])


if __name__ == "__main__":
    unittest.main()

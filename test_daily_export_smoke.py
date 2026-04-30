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
        self.assertIn("电脑 / Code: 2h 00m", note)
        self.assertIn("电脑 / Chrome: 30m", note)
        self.assertIn("网站 / example.com: 10m", note)

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
        self.assertIn("手机 / Chat: 4m", note)

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


if __name__ == "__main__":
    unittest.main()

# LifeOS 个人生活记录系统

这是一个长期自动化系统，不把 Obsidian 日记当成唯一数据源。系统会保留原始数据、生成标准化数据，再把摘要写回 Obsidian。

## 核心结构

唯一同步中心是 Google Drive 里的 Obsidian vault：

```text
G:\我的云端硬盘\journal
├─ daily
│  └─ YYYY-MM-DD.md
├─ templates
│  └─ daily.md
├─ _data
│  ├─ raw
│  │  ├─ computer
│  │  │  └─ YYYY-MM-DD.activitywatch.json
│  │  ├─ phone
│  │  │  └─ YYYY-MM-DD.android.json
│  │  └─ pad
│  │     └─ YYYY-MM-DD.android.json
│  ├─ normalized
│  │  └─ YYYY-MM-DD.activity.json
│  └─ ai
└─ _system
   ├─ logs
   └─ state
```

不要再单独同步 `G:\我的云端硬盘\activitywatch`。手机、平板、电脑都围绕 `journal` 这个 vault 工作。

## 每天自动流程

1. 手机 Android Agent 导出当天使用数据到 `journal/_data/raw/phone`。
2. 平板 Android Agent 导出当天使用数据到 `journal/_data/raw/pad`。
3. FolderSync 同步整个 `journal` vault。
4. Windows 计划任务在 23:30 运行 `daily_export.py`。
5. 脚本从 ActivityWatch 导出电脑数据到 `journal/_data/raw/computer`。
6. 脚本生成标准化文件 `journal/_data/normalized/YYYY-MM-DD.activity.json`。
7. 脚本把时间记录写入 `daily/YYYY-MM-DD.md`。
8. 如果设置了 `DEEPSEEK_API_KEY`，脚本写入 AI 总结。

## 电脑端设置

确认 ActivityWatch 正在运行：

```text
http://localhost:5600
```

运行：

```bat
setup.bat
```

它会创建 Windows Task Scheduler 任务：

```text
PersonalLifeDailyExport
```

默认每天 23:30 运行：

```bat
py -3 daily_export.py --ai-summary
```

如果没有设置 DeepSeek key，AI 总结会自动跳过，不影响时间记录。

如果你想把日记单独拿出来发给任意 AI，运行：

```bat
py -3 daily_export.py --skip-adb --ai-context
```

它会生成：

```text
G:\我的云端硬盘\journal\_data\ai\YYYY-MM-DD.ai-context.md
```

这个 Markdown 包含当天日记、标准化活动 JSON、Top 使用记录和推荐提示词，可以直接复制给 DeepSeek、ChatGPT 或其他 AI。

设置 DeepSeek：

```bat
setx DEEPSEEK_API_KEY "你的 DeepSeek API Key"
```

## 日记模板

模板位于：

```text
G:\我的云端硬盘\journal\templates\daily.md
```

首次运行时脚本会自动创建默认模板。你可以自由修改模板，只要保留标题或自动块即可。

推荐模板：

```markdown
# {{date}} 日记

## 今日概览

## 今日计划
- 最重要的一件事：
- 次重要事项：
- 健康/运动：
- 学习/长期积累：

## 今日目标

## 时间记录
{{AUTO_TIME_RECORD}}

## 今日所想

## 复利记录
- 今天做了什么会让未来更容易：
- 今天有什么行为在消耗未来：
- 一个可以明天继续的小动作：

## 今日总结
{{AUTO_AI_SUMMARY}}

## 学习记录
```

脚本实际写入时会维护这些自动块：

```markdown
<!-- daily_export:start -->
...
<!-- daily_export:end -->
```

```markdown
<!-- daily_ai_summary:start -->
...
<!-- daily_ai_summary:end -->
```

再次运行会替换自动块，不会重复插入。

## 手机和平板

长期方案是自建 Android Agent，不依赖 ActivityWatch Android、Tasker 或 USB ADB。

原因：

- ActivityWatch Android 没有稳定 JSON 导出能力。
- Tasker 收费。
- ADB 依赖 USB 或无线调试，不适合长期全自动。

Android Agent 项目在：

```text
android-lifelogger
```

当前状态：代码已准备好。你没有 Android Studio，所以推荐用 GitHub Actions 构建 APK。

构建 workflow 已提供：

```text
.github/workflows/android-agent.yml
```

把项目推送到 GitHub 后，在 Actions 页面运行 `Build Android Agent`，下载 artifact `life-logger-debug-apk`，把里面的 `app-debug.apk` 安装到手机和平板。

手机安装后：

```text
device_label = phone
```

平板安装后：

```text
device_label = pad
```

两台设备都导出到本地 Obsidian vault 对应目录。

手机选择：

```text
journal/_data/raw/phone
```

平板选择：

```text
journal/_data/raw/pad
```

FolderSync 继续同步整个 `journal` vault。

Android Agent 的长期能力：

- 使用 Android UsageStats 读取 app 使用时间。
- 不需要 root、Bootloader 解锁、USB 调试或 Tasker。
- 每天 23:25 自动导出。
- 打开 app 时静默补导最近 3 天。
- 可手动补导最近 7 天。
- 定时失败会在 app 首页显示最近状态。
- 输出文件名固定为 `YYYY-MM-DD.android.json`。

## 临时兼容

在 Android Agent 完成前，`daily_export.py` 仍保留 ADB 采集能力。ADB 数据也会写入长期目录：

```text
G:\我的云端硬盘\journal\_data\raw\phone\YYYY-MM-DD.android.json
G:\我的云端硬盘\journal\_data\raw\pad\YYYY-MM-DD.android.json
```

如果手机或平板未连接，脚本会跳过，不影响电脑数据和日记更新。

## 手动运行

完整运行：

```bat
py -3 daily_export.py --ai-summary
```

指定日期：

```bat
py -3 daily_export.py --date 2026-04-30
```

跳过 ADB：

```bat
py -3 daily_export.py --skip-adb
```

导出可手动发给 AI 的上下文：

```bat
py -3 daily_export.py --skip-adb --ai-context
```

跳过 ActivityWatch：

```bat
py -3 daily_export.py --skip-aw
```

## 验证

运行测试：

```bat
py -3 -m unittest test_daily_export_smoke.py
```

当前测试覆盖：

- ActivityWatch raw JSON 写入 Obsidian。
- 手机/平板日志写入 Obsidian。
- normalized activity JSON 生成。

## 后续开发顺序

1. 完成 Android Agent APK 构建和安装流程。
2. 让 Android Agent 直接写入 `journal/_data/raw/phone` 和 `journal/_data/raw/pad`。
3. 增加 `config.json` 正式配置路径、过滤规则、AI prompt。
4. 增加每周/月总结。
5. 增加健康检查：缺失手机数据、缺失平板数据、ActivityWatch 未运行、FolderSync 未同步。

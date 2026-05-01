# 免费方案：自建 Android Life Logger

Tasker 收费后，推荐改成一个专用 Android 小工具 app。这个 app 不依赖 Tasker/MacroDroid，也不需要 USB/ADB。

## 工作方式

手机和平板各安装一次 `Life Logger`：

1. 用户手动授予“使用情况访问权限”。
2. 用户手动选择 FolderSync 会同步的本地目录。
3. app 每天 23:25 自动查询 Android 系统使用情况。
4. app 写出：

```text
YYYY-MM-DD-phone.json
YYYY-MM-DD-pad.json
```

5. FolderSync 同步到 Google Drive 的 `activitywatch`。
6. 电脑端 `daily_export.py` 每天 23:30 汇总进 Obsidian。

Android 官方 `UsageStatsManager` 支持按时间范围查询 app 使用统计；本 app 使用 `queryAndAggregateUsageStats()`。文件写入使用 Android Storage Access Framework，首次选择目录后保留写入权限。

## 项目位置

```text
android-lifelogger
```

用 Android Studio 打开这个目录即可。

## 构建 APK

你没有 Android Studio 时，推荐使用 GitHub Actions 构建。

### 方案 A：GitHub Actions

1. 把本项目推送到 GitHub 仓库。
2. 打开仓库的 Actions 页面。
3. 运行 `Build Android Agent` workflow。
4. 下载 workflow artifact：

```text
life-logger-debug-apk
```

5. 把 `app-debug.apk` 安装到手机和平板。

workflow 文件已经放在：

```text
.github/workflows/android-agent.yml
```

### 方案 B：Android Studio

1. 安装 Android Studio。
2. 打开 `D:\shanghaitech\software\codex\android-lifelogger`。
3. 等 Gradle 同步完成。
4. 菜单选择：

```text
Build -> Build Bundle(s) / APK(s) -> Build APK(s)
```

5. 生成 APK 后分别安装到手机和平板。

## 手机端配置

打开 Life Logger：

1. 设备标签填：

```text
phone
```

2. 点击“保存设备标签”。
3. 点击“打开使用情况访问权限”，给 Life Logger 授权。
4. 点击“选择导出目录”，选择手机本地 Obsidian vault 里的 raw 目录：

```text
/sdcard/.../journal/_data/raw/phone
```

如果目录不存在，先用文件管理器创建。

5. 点击“立即导出今天”，确认能生成：

```text
YYYY-MM-DD.android.json
```

新版本还会在 JSON 中包含：

```text
app_events
```

这让电脑端可以在日记里显示手机和平板 app 的主要使用时段。

6. 点击“启用每天 23:25 自动导出”。
7. 点击“补导最近 7 天”，确认历史数据可以补写。

## 平板端配置

步骤相同，只是设备标签填：

```text
pad
```

导出的文件应为：

```text
YYYY-MM-DD.android.json
```

平板选择的目录应该是：

```text
/sdcard/.../journal/_data/raw/pad
```

## FolderSync 配置

手机和平板各建一个同步任务：

- 本地目录：手机/平板上的整个 `journal` vault
- Google Drive 目录：`journal`
- 同步方向：上传到云端
- 频率：每小时，或者每天 23:26 后同步一次

电脑端最终应看到：

```text
G:\我的云端硬盘\journal\_data\raw\phone\YYYY-MM-DD.android.json
G:\我的云端硬盘\journal\_data\raw\pad\YYYY-MM-DD.android.json
```

## ColorOS 后台设置

在手机和平板上都要做：

1. 设置 -> 电池 -> 应用耗电管理 -> Life Logger。
2. 允许后台运行。
3. 关闭自动冻结/智能限制。
4. 设置 -> 应用管理 -> 自启动管理，允许 Life Logger 自启动。

否则 23:25 的自动导出可能被系统拦截。

## 电脑端测试

FolderSync 同步后，在电脑运行：

```bat
py -3 daily_export.py --skip-adb
```

如果 JSON 文件已同步，Obsidian 日记的 `## 时间记录` 会出现：

```markdown
- 手机 / com.xxx.app: 1h 20m
- 平板 / com.xxx.app: 35m
```

## 局限

- Android 系统只提供 app 级使用时长，不提供每个 app 内部页面细节。
- 后台自动执行受 ColorOS 电池策略影响，需要把 app 加白名单。
- 首次必须手动授权“使用情况访问权限”和选择导出目录。

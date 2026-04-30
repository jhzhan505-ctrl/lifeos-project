package com.example.lifelogger;

import android.app.usage.UsageStats;
import android.app.usage.UsageStatsManager;
import android.app.AppOpsManager;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.net.Uri;
import android.provider.DocumentsContract;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.Collections;
import java.util.Comparator;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public final class UsageExporter {
    private UsageExporter() {
    }

    public static ExportResult exportToday(Context context) throws Exception {
        Calendar day = Calendar.getInstance();
        return exportDate(context, day);
    }

    public static List<ExportResult> exportRecentDays(Context context, int dayCount) throws Exception {
        List<ExportResult> results = new ArrayList<>();
        Calendar day = Calendar.getInstance();
        day.add(Calendar.DAY_OF_YEAR, -(dayCount - 1));
        for (int i = 0; i < dayCount; i++) {
            results.add(exportDate(context, day));
            day.add(Calendar.DAY_OF_YEAR, 1);
        }
        return results;
    }

    public static ExportResult exportDate(Context context, Calendar targetDay) throws Exception {
        SharedPreferences prefs = context.getSharedPreferences("lifelogger", Context.MODE_PRIVATE);
        String treeUriString = prefs.getString("tree_uri", "");
        String deviceLabel = prefs.getString("device_label", "phone");
        if (treeUriString.isEmpty()) {
            throw new IllegalStateException("请先选择导出目录");
        }
        if (!hasUsageAccess(context)) {
            throw new IllegalStateException("请先授权使用情况访问权限");
        }

        Calendar start = (Calendar) targetDay.clone();
        start.set(Calendar.HOUR_OF_DAY, 0);
        start.set(Calendar.MINUTE, 0);
        start.set(Calendar.SECOND, 0);
        start.set(Calendar.MILLISECOND, 0);
        Calendar nextDay = (Calendar) start.clone();
        nextDay.add(Calendar.DAY_OF_YEAR, 1);
        long begin = start.getTimeInMillis();
        long end = Math.min(nextDay.getTimeInMillis(), System.currentTimeMillis());
        String date = new SimpleDateFormat("yyyy-MM-dd", Locale.US).format(new Date(begin));

        UsageStatsManager manager = (UsageStatsManager) context.getSystemService(Context.USAGE_STATS_SERVICE);
        Map<String, UsageStats> stats = manager.queryAndAggregateUsageStats(begin, end);
        if (stats == null || stats.isEmpty()) {
            throw new IllegalStateException("没有读取到使用情况，请检查权限");
        }

        PackageManager packageManager = context.getPackageManager();
        List<AppUsage> usages = new ArrayList<>();
        for (UsageStats usageStats : stats.values()) {
            long seconds = usageStats.getTotalTimeInForeground() / 1000;
            if (seconds < 60) {
                continue;
            }
            String packageName = usageStats.getPackageName();
            if (isSystemPackage(packageName)) {
                continue;
            }
            usages.add(new AppUsage(packageName, labelFor(packageManager, packageName), seconds));
        }
        Collections.sort(usages, Comparator.comparingLong((AppUsage item) -> item.seconds).reversed());

        JSONObject root = new JSONObject();
        root.put("date", date);
        root.put("source", "android_lifelogger");
        root.put("device_label", deviceLabel);
        root.put("start_ts", begin / 1000);
        root.put("end_ts", end / 1000);
        root.put("schema_version", 1);

        JSONObject apps = new JSONObject();
        JSONArray appDetails = new JSONArray();
        for (AppUsage usage : usages) {
            apps.put(usage.packageName, usage.seconds);
            JSONObject detail = new JSONObject();
            detail.put("package", usage.packageName);
            detail.put("label", usage.label);
            detail.put("duration_seconds", usage.seconds);
            appDetails.put(detail);
        }
        root.put("apps", apps);
        root.put("app_details", appDetails);

        String fileName = date + ".android.json";
        writeToTree(context, Uri.parse(treeUriString), fileName, root.toString(2));
        prefs.edit()
                .putString("last_export_status", "OK: " + fileName + " apps=" + usages.size())
                .putLong("last_export_at", System.currentTimeMillis())
                .apply();
        return new ExportResult(fileName, usages.size());
    }

    public static boolean hasUsageAccess(Context context) {
        AppOpsManager appOps = (AppOpsManager) context.getSystemService(Context.APP_OPS_SERVICE);
        int mode = appOps.checkOpNoThrow(
                AppOpsManager.OPSTR_GET_USAGE_STATS,
                android.os.Process.myUid(),
                context.getPackageName()
        );
        return mode == AppOpsManager.MODE_ALLOWED;
    }

    private static String labelFor(PackageManager packageManager, String packageName) {
        try {
            ApplicationInfo info = packageManager.getApplicationInfo(packageName, 0);
            return packageManager.getApplicationLabel(info).toString();
        } catch (PackageManager.NameNotFoundException e) {
            return packageName;
        }
    }

    private static boolean isSystemPackage(String packageName) {
        return packageName.startsWith("android")
                || packageName.startsWith("com.android.")
                || packageName.startsWith("com.coloros.")
                || packageName.startsWith("com.oplus.")
                || packageName.startsWith("com.heytap.")
                || packageName.startsWith("com.qualcomm.")
                || packageName.startsWith("com.mediatek.")
                || packageName.equals("com.google.android.gms")
                || packageName.equals("com.google.android.gsf");
    }

    private static void writeToTree(Context context, Uri treeUri, String fileName, String content) throws Exception {
        Uri existing = findChild(context, treeUri, fileName);
        if (existing != null) {
            DocumentsContract.deleteDocument(context.getContentResolver(), existing);
        }

        Uri parent = DocumentsContract.buildDocumentUriUsingTree(
                treeUri,
                DocumentsContract.getTreeDocumentId(treeUri)
        );
        Uri created = DocumentsContract.createDocument(
                context.getContentResolver(),
                parent,
                "application/json",
                fileName
        );
        if (created == null) {
            throw new IllegalStateException("无法创建导出文件");
        }
        try (OutputStream output = context.getContentResolver().openOutputStream(created, "wt")) {
            if (output == null) {
                throw new IllegalStateException("无法打开导出文件");
            }
            output.write(content.getBytes(StandardCharsets.UTF_8));
        }
    }

    private static Uri findChild(Context context, Uri treeUri, String displayName) {
        Uri children = DocumentsContract.buildChildDocumentsUriUsingTree(
                treeUri,
                DocumentsContract.getTreeDocumentId(treeUri)
        );
        try (Cursor cursor = context.getContentResolver().query(
                children,
                new String[]{
                        DocumentsContract.Document.COLUMN_DOCUMENT_ID,
                        DocumentsContract.Document.COLUMN_DISPLAY_NAME
                },
                null,
                null,
                null
        )) {
            if (cursor == null) {
                return null;
            }
            while (cursor.moveToNext()) {
                String docId = cursor.getString(0);
                String name = cursor.getString(1);
                if (displayName.equals(name)) {
                    return DocumentsContract.buildDocumentUriUsingTree(treeUri, docId);
                }
            }
        }
        return null;
    }

    private static final class AppUsage {
        final String packageName;
        final String label;
        final long seconds;

        AppUsage(String packageName, String label, long seconds) {
            this.packageName = packageName;
            this.label = label;
            this.seconds = seconds;
        }
    }

    public static final class ExportResult {
        public final String fileName;
        public final int appCount;

        ExportResult(String fileName, int appCount) {
            this.fileName = fileName;
            this.appCount = appCount;
        }
    }
}

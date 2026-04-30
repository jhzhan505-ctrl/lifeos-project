package com.example.lifelogger;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Bundle;
import android.provider.Settings;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

public class MainActivity extends android.app.Activity {
    private static final int REQUEST_TREE = 1001;
    private TextView status;
    private EditText deviceLabel;
    private SharedPreferences prefs;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences("lifelogger", MODE_PRIVATE);
        if (!prefs.contains("device_label")) {
            prefs.edit().putString("device_label", "phone").apply();
        }

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(36, 36, 36, 36);

        TextView title = new TextView(this);
        title.setText("Life Logger");
        title.setTextSize(24);
        root.addView(title);

        TextView hint = new TextView(this);
        hint.setText("免费本机导出 Android 使用时间。选择 FolderSync 同步目录后，每天 23:25 自动写入 JSON。");
        hint.setPadding(0, 16, 0, 16);
        root.addView(hint);

        deviceLabel = new EditText(this);
        deviceLabel.setHint("phone 或 pad");
        deviceLabel.setSingleLine(true);
        deviceLabel.setText(prefs.getString("device_label", "phone"));
        root.addView(deviceLabel);

        Button saveLabel = button("保存设备标签");
        saveLabel.setOnClickListener(v -> {
            String label = deviceLabel.getText().toString().trim();
            if (!label.equals("phone") && !label.equals("pad")) {
                toast("设备标签只能是 phone 或 pad");
                return;
            }
            prefs.edit().putString("device_label", label).apply();
            updateStatus();
        });
        root.addView(saveLabel);

        Button usageAccess = button("打开使用情况访问权限");
        usageAccess.setOnClickListener(v -> startActivity(new Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS)));
        root.addView(usageAccess);

        Button chooseFolder = button("选择导出目录");
        chooseFolder.setOnClickListener(v -> {
            Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION
                    | Intent.FLAG_GRANT_WRITE_URI_PERMISSION
                    | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION
                    | Intent.FLAG_GRANT_PREFIX_URI_PERMISSION);
            startActivityForResult(intent, REQUEST_TREE);
        });
        root.addView(chooseFolder);

        Button exportNow = button("立即导出今天");
        exportNow.setOnClickListener(v -> exportToday());
        root.addView(exportNow);

        Button catchUp = button("补导最近 7 天");
        catchUp.setOnClickListener(v -> exportRecentDays());
        root.addView(catchUp);

        Button schedule = button("启用每天 23:25 自动导出");
        schedule.setOnClickListener(v -> {
            DailyExportReceiver.schedule(this);
            toast("已设置每日自动导出");
            updateStatus();
        });
        root.addView(schedule);

        status = new TextView(this);
        status.setPadding(0, 24, 0, 0);
        root.addView(status);

        setContentView(root);
        updateStatus();
        DailyExportReceiver.schedule(this);
        tryCatchUpSilently();
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQUEST_TREE && resultCode == RESULT_OK && data != null) {
            Uri uri = data.getData();
            int flags = data.getFlags()
                    & (Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
            getContentResolver().takePersistableUriPermission(uri, flags);
            prefs.edit().putString("tree_uri", uri.toString()).apply();
            toast("导出目录已保存");
            updateStatus();
        }
    }

    private Button button(String text) {
        Button button = new Button(this);
        button.setText(text);
        button.setAllCaps(false);
        return button;
    }

    private void exportToday() {
        try {
            UsageExporter.ExportResult result = UsageExporter.exportToday(this);
            toast("已导出：" + result.fileName + "，app 数：" + result.appCount);
            updateStatus();
        } catch (Exception e) {
            toast("导出失败：" + e.getMessage());
        }
    }

    private void exportRecentDays() {
        try {
            java.util.List<UsageExporter.ExportResult> results = UsageExporter.exportRecentDays(this, 7);
            toast("补导完成，文件数：" + results.size());
            updateStatus();
        } catch (Exception e) {
            toast("补导失败：" + e.getMessage());
        }
    }

    private void tryCatchUpSilently() {
        String folder = prefs.getString("tree_uri", "");
        if (folder.isEmpty() || !UsageExporter.hasUsageAccess(this)) {
            return;
        }
        new Thread(() -> {
            try {
                UsageExporter.exportRecentDays(this, 3);
                runOnUiThread(this::updateStatus);
            } catch (Exception ignored) {
            }
        }).start();
    }

    private void updateStatus() {
        boolean usageAllowed = UsageExporter.hasUsageAccess(this);
        String folder = prefs.getString("tree_uri", "");
        String label = prefs.getString("device_label", "phone");
        String lastStatus = prefs.getString("last_export_status", "无");
        status.setText(
                "设备标签：" + label
                        + "\n使用情况权限：" + (usageAllowed ? "已授权" : "未授权")
                        + "\n导出目录：" + (folder.isEmpty() ? "未选择" : "已选择")
                        + "\n最近导出：" + lastStatus
        );
    }

    private void toast(String message) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show();
    }
}

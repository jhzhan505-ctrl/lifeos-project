package com.example.lifelogger;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

import java.util.Calendar;

public class DailyExportReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        try {
            UsageExporter.exportToday(context);
        } catch (Exception exc) {
            context.getSharedPreferences("lifelogger", Context.MODE_PRIVATE)
                    .edit()
                    .putString("last_export_status", "FAILED: " + exc.getMessage())
                    .putLong("last_export_at", System.currentTimeMillis())
                    .apply();
        } finally {
            schedule(context);
        }
    }

    public static void schedule(Context context) {
        AlarmManager alarmManager = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        Intent intent = new Intent(context, DailyExportReceiver.class);
        PendingIntent pendingIntent = PendingIntent.getBroadcast(
                context,
                1002,
                intent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        Calendar next = Calendar.getInstance();
        next.set(Calendar.HOUR_OF_DAY, 23);
        next.set(Calendar.MINUTE, 25);
        next.set(Calendar.SECOND, 0);
        next.set(Calendar.MILLISECOND, 0);
        if (next.getTimeInMillis() <= System.currentTimeMillis()) {
            next.add(Calendar.DAY_OF_YEAR, 1);
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            alarmManager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, next.getTimeInMillis(), pendingIntent);
        } else {
            alarmManager.set(AlarmManager.RTC_WAKEUP, next.getTimeInMillis(), pendingIntent);
        }
    }
}

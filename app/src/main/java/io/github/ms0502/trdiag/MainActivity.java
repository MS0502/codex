package io.github.ms0502.trdiag;

import android.app.Activity;
import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Intent;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Bundle;
import android.provider.MediaStore;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.io.InputStream;
import java.io.OutputStream;

public final class MainActivity extends Activity {
    private static final String RELATIVE_PATH = "Download/TR_DIAG_V18/";
    private TextView status;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        int pad = (int) (20 * getResources().getDisplayMetrics().density);
        LinearLayout panel = new LinearLayout(this);
        panel.setOrientation(LinearLayout.VERTICAL);
        panel.setPadding(pad, pad, pad, pad);

        TextView title = new TextView(this);
        title.setText("TalesRunner Diagnostic v18");
        title.setTextSize(24);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        panel.addView(title);

        TextView scope = new TextView(this);
        scope.setText("최신 한국판 trgame 해시 검증, 공식 실행 경로 관찰, WELLBIA 로그 원본 수집, 인증값 제거만 수행합니다. 보호 기능을 우회하거나 수정하지 않습니다.");
        scope.setTextSize(16);
        scope.setPadding(0, pad / 2, 0, pad);
        panel.addView(scope);

        Button install = button("1. 수집기 파일 설치");
        install.setOnClickListener(v -> installAssets());
        panel.addView(install);

        Button termux = button("2. Termux 수집 시작");
        termux.setOnClickListener(v -> launchTermuxCollector());
        panel.addView(termux);

        Button winlator = button("3. Winlator 열기");
        winlator.setOnClickListener(v -> launchPackage("com.winlator.trcompat", "Winlator를 찾을 수 없습니다."));
        panel.addView(winlator);

        status = new TextView(this);
        status.setText("먼저 1번을 누르세요.");
        status.setTextSize(15);
        status.setTextIsSelectable(true);
        status.setPadding(0, pad, 0, 0);
        panel.addView(status);

        ScrollView scroll = new ScrollView(this);
        scroll.addView(panel);
        setContentView(scroll);
    }

    private Button button(String text) {
        Button button = new Button(this);
        button.setText(text);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
        params.setMargins(0, 0, 0, 12);
        button.setLayoutParams(params);
        return button;
    }

    private void installAssets() {
        try {
            writeDownloadAsset("TR_DIAG_V18_RUN.sh", "TR_DIAG_V18_RUN.sh", "text/x-shellscript");
            writeDownloadAsset("TR_DIAG_V18_WINDOWS.bat", "TR_DIAG_V18_WINDOWS.bat", "application/octet-stream");
            status.setText("설치 완료:\n/storage/emulated/0/Download/TR_DIAG_V18/\n\n이제 2번을 누르세요.");
        } catch (Exception e) {
            status.setText("설치 실패: " + e.getClass().getSimpleName() + ": " + e.getMessage());
        }
    }

    private void writeDownloadAsset(String assetName, String displayName, String mimeType) throws Exception {
        ContentResolver resolver = getContentResolver();
        resolver.delete(
                MediaStore.Downloads.EXTERNAL_CONTENT_URI,
                MediaStore.MediaColumns.DISPLAY_NAME + "=? AND " + MediaStore.MediaColumns.RELATIVE_PATH + "=?",
                new String[]{displayName, RELATIVE_PATH});

        ContentValues values = new ContentValues();
        values.put(MediaStore.MediaColumns.DISPLAY_NAME, displayName);
        values.put(MediaStore.MediaColumns.MIME_TYPE, mimeType);
        values.put(MediaStore.MediaColumns.RELATIVE_PATH, RELATIVE_PATH);
        values.put(MediaStore.MediaColumns.IS_PENDING, 1);

        Uri uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
        if (uri == null) throw new IllegalStateException("MediaStore insert failed");

        try (InputStream in = getAssets().open(assetName);
             OutputStream out = resolver.openOutputStream(uri, "w")) {
            if (out == null) throw new IllegalStateException("MediaStore output stream failed");
            byte[] buffer = new byte[8192];
            int count;
            while ((count = in.read(buffer)) >= 0) out.write(buffer, 0, count);
        }

        ContentValues done = new ContentValues();
        done.put(MediaStore.MediaColumns.IS_PENDING, 0);
        resolver.update(uri, done, null, null);
    }

    private void launchTermuxCollector() {
        Intent intent = new Intent("com.termux.RUN_COMMAND");
        intent.setClassName("com.termux", "com.termux.app.RunCommandService");
        intent.putExtra("com.termux.RUN_COMMAND_PATH", "/data/data/com.termux/files/usr/bin/bash");
        intent.putExtra("com.termux.RUN_COMMAND_ARGUMENTS", new String[]{
                "/storage/emulated/0/Download/TR_DIAG_V18/TR_DIAG_V18_RUN.sh"
        });
        intent.putExtra("com.termux.RUN_COMMAND_WORKDIR", "/storage/emulated/0/Download/TR_DIAG_V18");
        intent.putExtra("com.termux.RUN_COMMAND_BACKGROUND", false);
        intent.putExtra("com.termux.RUN_COMMAND_SESSION_ACTION", "0");
        try {
            startService(intent);
            status.setText("Termux 수집기를 요청했습니다. Termux가 열리지 않으면 allow-external-apps 설정 또는 RUN_COMMAND 권한을 확인하세요.");
        } catch (Exception e) {
            status.setText("Termux 실행 실패: " + e.getClass().getSimpleName() + ": " + e.getMessage());
            Toast.makeText(this, "Termux 실행 권한을 확인하세요.", Toast.LENGTH_LONG).show();
        }
    }

    private void launchPackage(String packageName, String failure) {
        Intent launch = getPackageManager().getLaunchIntentForPackage(packageName);
        if (launch == null) {
            status.setText(failure);
            return;
        }
        launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        startActivity(launch);
    }
}

package com.winlator.trcompattrace;

import android.app.Activity;
import android.content.ContentResolver;
import android.content.ContentValues;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.system.Os;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.security.MessageDigest;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

public final class TraceBridgeActivity extends Activity {
    private static final String ORIGINAL_BOX64 = "2c6f9846e327dba80a210572d16b1811f6dd041c850e48b2d02b34677e09c421";
    private static final String WRAPPER_SHA = "9f72a111eeff781ef0d6f4fc316ea49bf1d51dbc20d81d61b149f7f51f1acf0b";
    private static final String TRACER_SHA = "f06c5d24e32d928d97cb87eb2e7b7e6fc24bda8a2bb3e89626a6597b2781c6ef";
    private TextView log;

    private File box64() { return new File(getFilesDir(), "rootfs/usr/local/bin/box64"); }
    private File realBox64() { return new File(getFilesDir(), "rootfs/usr/local/bin/box64.trtrace.real"); }
    private File tracer() { return new File(getFilesDir(), "rootfs/usr/local/bin/tr_x11_map_watch"); }
    private File traceDir() { return new File(getFilesDir(), "tr_x11_trace"); }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        setTitle("TR X11 Trace Bridge");
        LinearLayout body = new LinearLayout(this);
        body.setOrientation(LinearLayout.VERTICAL);
        int pad = (int)(16 * getResources().getDisplayMetrics().density);
        body.setPadding(pad, pad, pad, pad);

        TextView help = new TextView(this);
        help.setText("Wi-Fi/ADB 없이 Winlator 자체 UID로 X11 추적기를 적용한다.\n\n1) 상태 확인\n2) 추적 적용\n3) 이 창을 닫고 Winlator를 실행해 문제가 보이는 화면에서 30초 이상 기다린 뒤 완전히 종료\n4) 다시 여기서 수집 + 원본 복원\n\n게임/XIGNCODE는 수정하지 않는다.");
        body.addView(help);
        addButton(body, "1. 상태 확인", v -> runTask(this::showStatus));
        addButton(body, "2. 추적 적용", v -> runTask(this::applyTrace));
        addButton(body, "3. 수집 + 원본 복원", v -> runTask(this::collectAndRestore));
        addButton(body, "원본만 복원", v -> runTask(this::restoreOnly));

        log = new TextView(this);
        log.setTextIsSelectable(true);
        body.addView(log);
        ScrollView scroll = new ScrollView(this);
        scroll.addView(body);
        setContentView(scroll);
        runTask(this::showStatus);
    }

    private void addButton(LinearLayout body, String text, View.OnClickListener l) {
        Button b = new Button(this);
        b.setText(text);
        b.setOnClickListener(l);
        body.addView(b);
    }

    private interface ThrowingTask { String run() throws Exception; }

    private void runTask(ThrowingTask task) {
        log.setText("처리 중...");
        new Thread(() -> {
            String result;
            try { result = task.run(); }
            catch (Throwable t) { result = "오류: " + t.getClass().getSimpleName() + ": " + t.getMessage(); }
            final String text = result;
            runOnUiThread(() -> log.setText(text));
        }, "tr-trace-bridge").start();
    }

    private String showStatus() throws Exception {
        File b = box64();
        if (!b.isFile()) return "box64 없음: " + b;
        String current = sha256(b);
        String backup = realBox64().isFile() ? sha256(realBox64()) : "missing";
        String state;
        if (ORIGINAL_BOX64.equals(current) && "missing".equals(backup)) state = "원본 v18J 상태";
        else if (WRAPPER_SHA.equals(current) && ORIGINAL_BOX64.equals(backup) && tracer().isFile() && TRACER_SHA.equals(sha256(tracer()))) state = "추적 적용 상태";
        else if (ORIGINAL_BOX64.equals(current) && ORIGINAL_BOX64.equals(backup)) state = "원본 + 백업 존재(복구 가능)";
        else state = "알 수 없는 조합 — 자동 변경 금지";
        return "상태: " + state + "\n현재 box64: " + current + "\n백업 box64: " + backup + "\ntrace dir: " + traceDir();
    }

    private String applyTrace() throws Exception {
        File b = box64();
        if (!b.isFile()) throw new IllegalStateException("box64가 없음");
        String current = sha256(b);
        if (WRAPPER_SHA.equals(current) && realBox64().isFile() && ORIGINAL_BOX64.equals(sha256(realBox64()))) return "이미 추적 적용됨.\n" + showStatus();
        if (!ORIGINAL_BOX64.equals(current)) throw new SecurityException("현재 box64 해시가 검증된 v18J 원본과 다름. 변경 중단: " + current);

        File backup = realBox64();
        if (backup.exists() && !ORIGINAL_BOX64.equals(sha256(backup))) throw new SecurityException("기존 백업 해시 불일치");
        if (!backup.exists()) copyFile(b, backup, 0755);
        if (!ORIGINAL_BOX64.equals(sha256(backup))) throw new SecurityException("box64 백업 검증 실패");

        File dir = traceDir();
        if (!dir.exists() && !dir.mkdirs()) throw new IllegalStateException("trace dir 생성 실패");
        deleteRecursively(new File(dir, "session.lock"));

        copyAsset("tr_trace_bridge/tr_x11_map_watch", tracer(), 0755);
        if (!TRACER_SHA.equals(sha256(tracer()))) throw new SecurityException("tracer 해시 불일치");
        copyAsset("tr_trace_bridge/box64-wrapper", b, 0755);
        if (!WRAPPER_SHA.equals(sha256(b))) throw new SecurityException("wrapper 해시 불일치");
        return "추적 적용 완료.\n\n이 창을 닫고 Winlator를 실행 → 문제가 보이는 화면에서 30초 이상 대기 → Winlator 완전 종료 → 이 앱에서 '수집 + 원본 복원'을 눌러.";
    }

    private String collectAndRestore() throws Exception {
        String exported = exportTraceZip();
        return exported + "\n\n" + restore();
    }

    private String restoreOnly() throws Exception { return restore(); }

    private String restore() throws Exception {
        File backup = realBox64();
        if (!backup.isFile()) {
            if (box64().isFile() && ORIGINAL_BOX64.equals(sha256(box64()))) return "이미 원본 box64 상태.";
            throw new IllegalStateException("복원 백업이 없음");
        }
        if (!ORIGINAL_BOX64.equals(sha256(backup))) throw new SecurityException("복원 백업 해시 불일치");
        copyFile(backup, box64(), 0755);
        if (!ORIGINAL_BOX64.equals(sha256(box64()))) throw new SecurityException("원본 복원 검증 실패");
        if (tracer().exists() && !tracer().delete()) throw new IllegalStateException("tracer 삭제 실패");
        if (!backup.delete()) throw new IllegalStateException("backup 삭제 실패");
        deleteRecursively(new File(traceDir(), "session.lock"));
        return "v18J 원본 box64 복원 완료.";
    }

    private String exportTraceZip() throws Exception {
        File[] traces = traceDir().listFiles((d, name) -> name.startsWith("trace-") && name.endsWith(".txt"));
        if (traces == null || traces.length == 0) throw new IllegalStateException("trace-*.txt가 없음. Winlator 실행 후 30초 이상 기다렸는지 확인 필요");
        if (android.os.Build.VERSION.SDK_INT < 29) throw new IllegalStateException("MediaStore export는 Android 10+ 필요");

        String stamp = new SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US).format(new Date());
        String name = "TR_X11_MAP_TRACE_" + stamp + ".zip";
        ContentResolver cr = getContentResolver();
        ContentValues cv = new ContentValues();
        cv.put(MediaStore.MediaColumns.DISPLAY_NAME, name);
        cv.put(MediaStore.MediaColumns.MIME_TYPE, "application/zip");
        cv.put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/TR_X11_TRACE");
        cv.put(MediaStore.MediaColumns.IS_PENDING, 1);
        Uri uri = cr.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, cv);
        if (uri == null) throw new IllegalStateException("Downloads 항목 생성 실패");
        try {
            try (OutputStream raw = cr.openOutputStream(uri); ZipOutputStream zip = new ZipOutputStream(new BufferedOutputStream(raw))) {
                if (raw == null) throw new IllegalStateException("Downloads 출력 스트림 생성 실패");
                byte[] buf = new byte[65536];
                for (File f : traces) {
                    zip.putNextEntry(new ZipEntry(f.getName()));
                    try (InputStream in = new BufferedInputStream(new FileInputStream(f))) {
                        int n;
                        while ((n = in.read(buf)) >= 0) zip.write(buf, 0, n);
                    }
                    zip.closeEntry();
                }
            }
            ContentValues done = new ContentValues();
            done.put(MediaStore.MediaColumns.IS_PENDING, 0);
            cr.update(uri, done, null, null);
        } catch (Throwable t) {
            cr.delete(uri, null, null);
            throw t;
        }
        return "추적 수집 완료: Download/TR_X11_TRACE/" + name + " (" + traces.length + " files)";
    }

    private void copyAsset(String asset, File target, int mode) throws Exception {
        File tmp = new File(target.getParentFile(), target.getName() + ".trbridge.tmp");
        try (InputStream in = getAssets().open(asset); OutputStream out = new BufferedOutputStream(new FileOutputStream(tmp))) {
            byte[] buf = new byte[65536];
            int n;
            while ((n = in.read(buf)) >= 0) out.write(buf, 0, n);
        }
        Os.chmod(tmp.getAbsolutePath(), mode);
        if (target.exists() && !target.delete()) throw new IllegalStateException("기존 대상 삭제 실패: " + target);
        if (!tmp.renameTo(target)) throw new IllegalStateException("asset 교체 실패: " + target);
    }

    private void copyFile(File source, File target, int mode) throws Exception {
        File tmp = new File(target.getParentFile(), target.getName() + ".trbridge.tmp");
        try (InputStream in = new BufferedInputStream(new FileInputStream(source)); OutputStream out = new BufferedOutputStream(new FileOutputStream(tmp))) {
            byte[] buf = new byte[65536];
            int n;
            while ((n = in.read(buf)) >= 0) out.write(buf, 0, n);
        }
        Os.chmod(tmp.getAbsolutePath(), mode);
        if (target.exists() && !target.delete()) throw new IllegalStateException("기존 대상 삭제 실패: " + target);
        if (!tmp.renameTo(target)) throw new IllegalStateException("파일 교체 실패: " + target);
    }

    private static String sha256(File file) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        try (InputStream in = new BufferedInputStream(new FileInputStream(file))) {
            byte[] buf = new byte[65536];
            int n;
            while ((n = in.read(buf)) >= 0) md.update(buf, 0, n);
        }
        StringBuilder sb = new StringBuilder();
        for (byte b : md.digest()) sb.append(String.format(Locale.US, "%02x", b & 0xff));
        return sb.toString();
    }

    private static void deleteRecursively(File f) {
        if (f == null || !f.exists()) return;
        if (f.isDirectory()) {
            File[] children = f.listFiles();
            if (children != null) for (File c : children) deleteRecursively(c);
        }
        f.delete();
    }
}

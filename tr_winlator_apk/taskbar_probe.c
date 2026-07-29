#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>

static FILE *out;
static unsigned int child_count;
static unsigned int button_count;
static unsigned int id_zero_button_count;

static void print_wide(const WCHAR *value)
{
    char buffer[512];
    int written;
    if (!value || !value[0]) { fputs("<empty>", out); return; }
    written = WideCharToMultiByte(CP_UTF8, 0, value, -1, buffer, sizeof(buffer), NULL, NULL);
    if (written <= 0) fputs("<conversion-failed>", out);
    else fputs(buffer, out);
}

static BOOL CALLBACK enum_child(HWND hwnd, LPARAM unused)
{
    WCHAR class_name[128] = {0};
    WCHAR title[256] = {0};
    RECT rect = {0};
    LONG_PTR id;
    DWORD pid = 0;
    DWORD tid;
    (void)unused;

    child_count++;
    GetClassNameW(hwnd, class_name, 128);
    GetWindowTextW(hwnd, title, 256);
    GetWindowRect(hwnd, &rect);
    id = GetWindowLongPtrW(hwnd, GWLP_ID);
    tid = GetWindowThreadProcessId(hwnd, &pid);
    if (!lstrcmpiW(class_name, L"Button"))
    {
        button_count++;
        if (!id) id_zero_button_count++;
    }
    fprintf(out, "CHILD hwnd=%p visible=%d enabled=%d id=%lld tid=%lu pid=%lu rect=%ld,%ld,%ld,%ld class=",
            (void *)hwnd, IsWindowVisible(hwnd), IsWindowEnabled(hwnd), (long long)id,
            (unsigned long)tid, (unsigned long)pid,
            rect.left, rect.top, rect.right, rect.bottom);
    print_wide(class_name);
    fputs(" title=", out);
    print_wide(title);
    fputc('\n', out);
    return TRUE;
}

int main(int argc, char **argv)
{
    HWND tray;
    RECT rect = {0};
    WCHAR title[256] = {0};
    DWORD pid = 0;
    DWORD tid;
    LONG_PTR style;
    LONG_PTR exstyle;
    int result = 0;

    if (argc != 2) return 10;
    out = fopen(argv[1], "wb");
    if (!out) return 11;

    tray = FindWindowW(L"Shell_TrayWnd", NULL);
    fprintf(out, "PROBE pid=%lu tick=%llu\n", (unsigned long)GetCurrentProcessId(),
            (unsigned long long)GetTickCount64());
    fprintf(out, "TRAY_FOUND=%d hwnd=%p\n", tray != NULL, (void *)tray);
    if (!tray) { fclose(out); return 3; }

    tid = GetWindowThreadProcessId(tray, &pid);
    GetWindowRect(tray, &rect);
    GetWindowTextW(tray, title, 256);
    style = GetWindowLongPtrW(tray, GWL_STYLE);
    exstyle = GetWindowLongPtrW(tray, GWL_EXSTYLE);
    fprintf(out, "TRAY visible=%d enabled=%d iconic=%d zoomed=%d tid=%lu pid=%lu rect=%ld,%ld,%ld,%ld width=%ld height=%ld style=0x%llx exstyle=0x%llx title=",
            IsWindowVisible(tray), IsWindowEnabled(tray), IsIconic(tray), IsZoomed(tray),
            (unsigned long)tid, (unsigned long)pid,
            rect.left, rect.top, rect.right, rect.bottom,
            rect.right - rect.left, rect.bottom - rect.top,
            (unsigned long long)style, (unsigned long long)exstyle);
    print_wide(title);
    fputc('\n', out);
    EnumChildWindows(tray, enum_child, 0);
    fprintf(out, "SUMMARY child_count=%u button_count=%u id_zero_button_count=%u\n",
            child_count, button_count, id_zero_button_count);
    if (!id_zero_button_count) result = 4;
    fclose(out);
    return result;
}

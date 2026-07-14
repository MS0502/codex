#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#ifndef NT_SUCCESS
#define NT_SUCCESS(Status) (((LONG)(Status)) >= 0)
#endif

typedef LONG NTSTATUS;
typedef NTSTATUS (NTAPI *NtQuerySystemInformationFn)(ULONG, PVOID, ULONG, PULONG);
typedef NTSTATUS (NTAPI *NtQueryInformationTokenFn)(HANDLE, ULONG, PVOID, ULONG, PULONG);
typedef NTSTATUS (NTAPI *RtlGetVersionFn)(PRTL_OSVERSIONINFOW);

typedef struct _SYSTEM_CODEINTEGRITY_INFORMATION_LOCAL {
    ULONG Length;
    ULONG CodeIntegrityOptions;
} SYSTEM_CODEINTEGRITY_INFORMATION_LOCAL;

typedef struct _SYSTEM_KERNEL_DEBUGGER_INFORMATION_LOCAL {
    BOOLEAN DebuggerEnabled;
    BOOLEAN DebuggerNotPresent;
} SYSTEM_KERNEL_DEBUGGER_INFORMATION_LOCAL;

static void print_hex(FILE *out, const unsigned char *data, ULONG size)
{
    ULONG i;
    for (i = 0; i < size; ++i) fprintf(out, "%02X", data[i]);
}

static void query_token_class(FILE *out, NtQueryInformationTokenFn fn, HANDLE token,
                              ULONG class_id, const char *name, ULONG buffer_size)
{
    unsigned char buffer[512];
    ULONG return_length = 0;
    NTSTATUS status;
    ULONG shown;

    if (buffer_size > sizeof(buffer)) buffer_size = sizeof(buffer);
    memset(buffer, 0xCC, sizeof(buffer));
    status = fn(token, class_id, buffer, buffer_size, &return_length);
    shown = buffer_size < 64 ? buffer_size : 64;

    fprintf(out,
            "TOKEN class=%lu name=%s buffer=%lu status=0x%08lX success=%d return_length=%lu data=",
            class_id, name, buffer_size, (unsigned long)status, NT_SUCCESS(status) ? 1 : 0,
            return_length);
    print_hex(out, buffer, shown);
    fputc('\n', out);
}

static void query_system_class(FILE *out, NtQuerySystemInformationFn fn,
                               ULONG class_id, const char *name, ULONG buffer_size)
{
    unsigned char buffer[512];
    ULONG return_length = 0;
    NTSTATUS status;
    ULONG shown;

    if (buffer_size > sizeof(buffer)) buffer_size = sizeof(buffer);
    memset(buffer, 0xCC, sizeof(buffer));

    if (class_id == 103 && buffer_size >= sizeof(SYSTEM_CODEINTEGRITY_INFORMATION_LOCAL)) {
        SYSTEM_CODEINTEGRITY_INFORMATION_LOCAL *ci =
            (SYSTEM_CODEINTEGRITY_INFORMATION_LOCAL *)buffer;
        ci->Length = sizeof(*ci);
        ci->CodeIntegrityOptions = 0;
    }

    status = fn(class_id, buffer, buffer_size, &return_length);
    shown = buffer_size < 64 ? buffer_size : 64;

    fprintf(out,
            "SYSTEM class=%lu name=%s buffer=%lu status=0x%08lX success=%d return_length=%lu data=",
            class_id, name, buffer_size, (unsigned long)status, NT_SUCCESS(status) ? 1 : 0,
            return_length);
    print_hex(out, buffer, shown);
    fputc('\n', out);
}

static void print_environment(FILE *out, RtlGetVersionFn rtl_get_version)
{
    RTL_OSVERSIONINFOW version;
    SYSTEM_INFO system_info;
    USHORT process_machine = 0, native_machine = 0;
    BOOL wow64_2 = FALSE;
    typedef BOOL (WINAPI *IsWow64Process2Fn)(HANDLE, USHORT *, USHORT *);
    IsWow64Process2Fn is_wow64_process2 =
        (IsWow64Process2Fn)GetProcAddress(GetModuleHandleW(L"kernel32.dll"), "IsWow64Process2");

    memset(&version, 0, sizeof(version));
    version.dwOSVersionInfoSize = sizeof(version);
    if (rtl_get_version) rtl_get_version(&version);

    GetNativeSystemInfo(&system_info);
    if (is_wow64_process2)
        wow64_2 = is_wow64_process2(GetCurrentProcess(), &process_machine, &native_machine);

    fprintf(out, "PROBE_VERSION=2\n");
    fprintf(out, "PROCESS_BITS=%u\n", (unsigned)(sizeof(void *) * 8));
    fprintf(out, "OS_VERSION=%lu.%lu.%lu\n",
            version.dwMajorVersion, version.dwMinorVersion, version.dwBuildNumber);
    fprintf(out, "OS_PLATFORM=%lu\n", version.dwPlatformId);
    fprintf(out, "NATIVE_ARCH=%u\n", system_info.wProcessorArchitecture);
    fprintf(out, "PROCESSORS=%lu\n", system_info.dwNumberOfProcessors);
    fprintf(out, "PAGE_SIZE=%lu\n", system_info.dwPageSize);
    fprintf(out, "WOW64_PROCESS2_AVAILABLE=%d\n", is_wow64_process2 ? 1 : 0);
    fprintf(out, "WOW64_PROCESS2_OK=%d\n", wow64_2 ? 1 : 0);
    fprintf(out, "PROCESS_MACHINE=0x%04X\n", process_machine);
    fprintf(out, "NATIVE_MACHINE=0x%04X\n", native_machine);
}

int main(int argc, char **argv)
{
    const char *output_path = argc >= 2 ? argv[1] : "TR_WINSEC_PROBE_RESULT.txt";
    FILE *out = fopen(output_path, "wb");
    HMODULE ntdll;
    NtQuerySystemInformationFn nt_query_system_information;
    NtQueryInformationTokenFn nt_query_information_token;
    RtlGetVersionFn rtl_get_version;
    HANDLE token = NULL;
    DWORD open_error = ERROR_SUCCESS;
    int repeat;

    if (!out) {
        fprintf(stderr, "Cannot open output file: %s (error=%lu)\n", output_path, GetLastError());
        return 2;
    }

    ntdll = GetModuleHandleW(L"ntdll.dll");
    nt_query_system_information = (NtQuerySystemInformationFn)GetProcAddress(ntdll, "NtQuerySystemInformation");
    nt_query_information_token = (NtQueryInformationTokenFn)GetProcAddress(ntdll, "NtQueryInformationToken");
    rtl_get_version = (RtlGetVersionFn)GetProcAddress(ntdll, "RtlGetVersion");

    fprintf(out, "TR Windows security API behavior probe\n");
    fprintf(out, "This program only queries documented/undocumented OS information; it changes nothing.\n");
    print_environment(out, rtl_get_version);
    fprintf(out, "NtQuerySystemInformation=%p\n", (void *)nt_query_system_information);
    fprintf(out, "NtQueryInformationToken=%p\n", (void *)nt_query_information_token);

    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token))
        open_error = GetLastError();
    fprintf(out, "OPEN_PROCESS_TOKEN_OK=%d error=%lu handle=%p\n",
            token ? 1 : 0, open_error, token);

    if (!nt_query_system_information || !nt_query_information_token || !token) {
        fprintf(out, "FATAL=required API unavailable\n");
        if (token) CloseHandle(token);
        fclose(out);
        return 3;
    }

    fprintf(out, "\n[System information classes]\n");
    query_system_class(out, nt_query_system_information, 35, "SystemKernelDebuggerInformation", 2);
    query_system_class(out, nt_query_system_information, 35, "SystemKernelDebuggerInformation", 64);
    query_system_class(out, nt_query_system_information, 103, "SystemCodeIntegrityInformation", 8);
    query_system_class(out, nt_query_system_information, 103, "SystemCodeIntegrityInformation", 64);
    query_system_class(out, nt_query_system_information, 149, "SystemKernelDebuggerInformationEx", 3);
    query_system_class(out, nt_query_system_information, 149, "SystemKernelDebuggerInformationEx", 64);

    fprintf(out, "\n[Token information classes]\n");
    query_token_class(out, nt_query_information_token, token, 40, "TokenIsRestricted", 4);
    query_token_class(out, nt_query_information_token, token, 41, "TokenProcessTrustLevel", 64);
    query_token_class(out, nt_query_information_token, token, 42, "TokenPrivateNameSpace", 4);
    query_token_class(out, nt_query_information_token, token, 42, "TokenPrivateNameSpace", 64);
    query_token_class(out, nt_query_information_token, token, 43, "TokenSingletonAttributes", 256);
    query_token_class(out, nt_query_information_token, token, 44, "TokenBnoIsolation", 256);
    query_token_class(out, nt_query_information_token, token, 45, "TokenChildProcessFlags", 4);
    query_token_class(out, nt_query_information_token, token, 46, "TokenIsLessPrivilegedAppContainer", 4);
    query_token_class(out, nt_query_information_token, token, 47, "TokenIsSandboxed", 4);
    query_token_class(out, nt_query_information_token, token, 48, "TokenIsAppSilo", 4);
    query_token_class(out, nt_query_information_token, token, 49, "TokenLoggingInformation", 256);

    fprintf(out, "\n[Repeated critical queries]\n");
    for (repeat = 0; repeat < 5; ++repeat) {
        fprintf(out, "REPEAT=%d\n", repeat + 1);
        query_system_class(out, nt_query_system_information, 103, "SystemCodeIntegrityInformation", 8);
        query_token_class(out, nt_query_information_token, token, 42, "TokenPrivateNameSpace", 4);
    }

    CloseHandle(token);
    fclose(out);
    return 0;
}

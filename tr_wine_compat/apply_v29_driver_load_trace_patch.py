#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

REVISION = "v29-generic-driver-load-trace-1"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one anchor, found {count}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_ntoskrnl(root: Path) -> None:
    path = root / "dlls/ntoskrnl.exe/ntoskrnl.c"

    replace_once(
        path,
        '''NTSTATUS WINAPI IoCreateDriver( UNICODE_STRING *name, PDRIVER_INITIALIZE init )
{
    struct wine_driver *driver;
    NTSTATUS status;
    unsigned int i;

    TRACE("(%s, %p)\\n", debugstr_us(name), init);
''',
        '''NTSTATUS WINAPI IoCreateDriver( UNICODE_STRING *name, PDRIVER_INITIALIZE init )
{
    struct wine_driver *driver;
    NTSTATUS status;
    unsigned int i;

    TRACE("DRIVER_LOAD IoCreateDriver begin revision=''' + REVISION + ''' name=%s init=%p\\n",
          debugstr_us(name), init);
''',
    )

    replace_once(
        path,
        '''    status = driver->driver_obj.DriverInit( &driver->driver_obj, &driver->driver_extension.ServiceKeyName );
    if (status)
    {
        IoDeleteDriver( &driver->driver_obj );
        return status;
    }
''',
        '''    TRACE("DRIVER_LOAD IoCreateDriver init-enter driver=%p name=%s service_key=%s init=%p\\n",
          &driver->driver_obj, debugstr_us(&driver->driver_obj.DriverName),
          debugstr_us(&driver->driver_extension.ServiceKeyName), driver->driver_obj.DriverInit);
    status = driver->driver_obj.DriverInit( &driver->driver_obj, &driver->driver_extension.ServiceKeyName );
    TRACE("DRIVER_LOAD IoCreateDriver init-return driver=%p name=%s status=%#lx device_head=%p "
          "unload=%p start_io=%p\\n", &driver->driver_obj,
          debugstr_us(&driver->driver_obj.DriverName), status, driver->driver_obj.DeviceObject,
          driver->driver_obj.DriverUnload, driver->driver_obj.DriverStartIo);
    if (status)
    {
        IoDeleteDriver( &driver->driver_obj );
        return status;
    }
''',
    )

    replace_once(
        path,
        '''    TRACE( "(%p, %lu, %s, %lu, %lx, %u, %p)\\n",
           driver, ext_size, debugstr_us(name), type, characteristics, exclusive, ret_device );
''',
        '''    TRACE( "DRIVER_LOAD IoCreateDevice begin driver=%p driver_name=%s ext=%lu name=%s "
           "type=%lu characteristics=%#lx exclusive=%u out=%p\\n",
           driver, driver ? debugstr_us(&driver->DriverName) : "(null)", ext_size,
           debugstr_us(name), type, characteristics, exclusive, ret_device );
''',
    )

    replace_once(
        path,
        '''    if (status)
    {
        free_kernel_object( device );
        return status;
    }

    device->NextDevice   = driver->DeviceObject;
''',
        '''    if (status)
    {
        TRACE("DRIVER_LOAD IoCreateDevice create-failed driver=%p name=%s status=%#lx\\n",
              driver, debugstr_us(name), status);
        free_kernel_object( device );
        return status;
    }

    TRACE("DRIVER_LOAD IoCreateDevice created driver=%p name=%s device=%p type=%lu "
          "characteristics=%#lx stack=%u\\n", driver, debugstr_us(name), device,
          device->DeviceType, device->Characteristics, device->StackSize);

    device->NextDevice   = driver->DeviceObject;
''',
    )

    replace_once(
        path,
        '''NTSTATUS WINAPI IoCreateSymbolicLink( UNICODE_STRING *name, UNICODE_STRING *target )
{
    HANDLE handle;
    OBJECT_ATTRIBUTES attr;
    NTSTATUS ret;
''',
        '''NTSTATUS WINAPI IoCreateSymbolicLink( UNICODE_STRING *name, UNICODE_STRING *target )
{
    HANDLE handle;
    OBJECT_ATTRIBUTES attr;
    NTSTATUS ret;

    TRACE("DRIVER_LOAD IoCreateSymbolicLink begin name=%s target=%s\\n",
          debugstr_us(name), debugstr_us(target));
''',
    )

    replace_once(
        path,
        '''    if (!ret) NtClose( handle );
    return ret;
}
''',
        '''    if (!ret) NtClose( handle );
    TRACE("DRIVER_LOAD IoCreateSymbolicLink return name=%s target=%s status=%#lx\\n",
          debugstr_us(name), debugstr_us(target), ret);
    return ret;
}
''',
    )

    replace_once(
        path,
        '''static NTSTATUS open_driver( const UNICODE_STRING *service_name, SC_HANDLE *service )
{
    QUERY_SERVICE_CONFIGW *service_config = NULL;
''',
        '''static NTSTATUS open_driver( const UNICODE_STRING *service_name, SC_HANDLE *service )
{
    QUERY_SERVICE_CONFIGW *service_config = NULL;
''',
    )

    replace_once(
        path,
        '''    if (!(name = RtlAllocateHeap( GetProcessHeap(), 0, service_name->Length + sizeof(WCHAR) )))
        return STATUS_NO_MEMORY;
''',
        '''    TRACE("DRIVER_LOAD open_driver begin service=%s\\n", debugstr_us(service_name));

    if (!(name = RtlAllocateHeap( GetProcessHeap(), 0, service_name->Length + sizeof(WCHAR) )))
        return STATUS_NO_MEMORY;
''',
    )

    replace_once(
        path,
        '''    if (service_config->dwServiceType != SERVICE_KERNEL_DRIVER &&
        service_config->dwServiceType != SERVICE_FILE_SYSTEM_DRIVER)
''',
        '''    TRACE("DRIVER_LOAD open_driver config service=%s type=%#lx start=%#lx error_control=%#lx "
          "binary=%s group=%s\\n", debugstr_us(service_name), service_config->dwServiceType,
          service_config->dwStartType, service_config->dwErrorControl,
          wine_dbgstr_w(service_config->lpBinaryPathName), wine_dbgstr_w(service_config->lpLoadOrderGroup));

    if (service_config->dwServiceType != SERVICE_KERNEL_DRIVER &&
        service_config->dwServiceType != SERVICE_FILE_SYSTEM_DRIVER)
''',
    )

    replace_once(
        path,
        '''    TRACE( "loading driver %s\\n", wine_dbgstr_w(str) );

    module = LoadLibraryExW( str, 0, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS );
''',
        '''    TRACE( "DRIVER_LOAD image-load begin driver=%s service_key=%s resolved_path=%s\\n",
           wine_dbgstr_w(driver_name), debugstr_us(keyname), wine_dbgstr_w(str) );

    SetLastError( ERROR_SUCCESS );
    module = LoadLibraryExW( str, 0, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS );
    TRACE("DRIVER_LOAD image-load return driver=%s path=%s module=%p winerr=%lu\\n",
          wine_dbgstr_w(driver_name), wine_dbgstr_w(str), module, GetLastError());
''',
    )

    replace_once(
        path,
        '''    nt = RtlImageNtHeader( module );
    if (!nt->OptionalHeader.AddressOfEntryPoint) return STATUS_SUCCESS;
''',
        '''    nt = RtlImageNtHeader( module );
    TRACE("DRIVER_LOAD pe-metadata module=%p machine=%#x subsystem=%#x image_size=%#lx "
          "entry_rva=%#lx sections=%u characteristics=%#x dll_characteristics=%#x\\n",
          module, nt->FileHeader.Machine, nt->OptionalHeader.Subsystem,
          nt->OptionalHeader.SizeOfImage, nt->OptionalHeader.AddressOfEntryPoint,
          nt->FileHeader.NumberOfSections, nt->FileHeader.Characteristics,
          nt->OptionalHeader.DllCharacteristics);
    if (!nt->OptionalHeader.AddressOfEntryPoint)
    {
        TRACE("DRIVER_LOAD DriverEntry absent module=%p service_key=%s\\n", module, debugstr_us(keyname));
        return STATUS_SUCCESS;
    }
''',
    )

    replace_once(
        path,
        '''    TRACE_(relay)( "\\1Call driver init %p (obj=%p,str=%s)\\n",
                   driver_object->DriverInit, driver_object, wine_dbgstr_w(keyname->Buffer) );

    status = driver_object->DriverInit( driver_object, keyname );
''',
        '''    TRACE("DRIVER_LOAD DriverEntry enter module=%p entry=%p driver=%p service_key=%s\\n",
          module, driver_object->DriverInit, driver_object, debugstr_us(keyname));
    TRACE_(relay)( "\\1Call driver init %p (obj=%p,str=%s)\\n",
                   driver_object->DriverInit, driver_object, wine_dbgstr_w(keyname->Buffer) );

    status = driver_object->DriverInit( driver_object, keyname );
    TRACE("DRIVER_LOAD DriverEntry return module=%p entry=%p driver=%p service_key=%s "
          "status=%#lx device_head=%p unload=%p start_io=%p\\n",
          module, driver_object->DriverInit, driver_object, debugstr_us(keyname), status,
          driver_object->DeviceObject, driver_object->DriverUnload, driver_object->DriverStartIo);
''',
    )

    replace_once(
        path,
        '''    TRACE( "(%s)\\n", debugstr_us(service_name) );

    if ((status = open_driver( service_name, (SC_HANDLE *)&service_handle )) != STATUS_SUCCESS)
        return status;
''',
        '''    TRACE( "DRIVER_LOAD ZwLoadDriver begin revision=''' + REVISION + ''' service=%s\\n",
           debugstr_us(service_name) );

    status = open_driver( service_name, (SC_HANDLE *)&service_handle );
    TRACE("DRIVER_LOAD ZwLoadDriver open-result service=%s status=%#lx handle=%p\\n",
          debugstr_us(service_name), status, service_handle);
    if (status != STATUS_SUCCESS)
        return status;
''',
    )

    replace_once(
        path,
        '''    status = IoCreateDriver( &drv_name, init_driver );
    entry = wine_rb_get( &wine_drivers, &drv_name );
''',
        '''    status = IoCreateDriver( &drv_name, init_driver );
    TRACE("DRIVER_LOAD ZwLoadDriver create-result service=%s driver_name=%s status=%#lx\\n",
          debugstr_us(service_name), debugstr_us(&drv_name), status);
    entry = wine_rb_get( &wine_drivers, &drv_name );
''',
    )

    replace_once(
        path,
        '''    set_service_status( service_handle, SERVICE_RUNNING,
                        SERVICE_ACCEPT_STOP | SERVICE_ACCEPT_SHUTDOWN );
    return STATUS_SUCCESS;
''',
        '''    set_service_status( service_handle, SERVICE_RUNNING,
                        SERVICE_ACCEPT_STOP | SERVICE_ACCEPT_SHUTDOWN );
    TRACE("DRIVER_LOAD ZwLoadDriver success service=%s driver=%p device_head=%p\\n",
          debugstr_us(service_name), &driver->driver_obj, driver->driver_obj.DeviceObject);
    return STATUS_SUCCESS;
''',
    )


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_v29_driver_load_trace_patch.py WINE_SOURCE_DIR", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    patch_ntoskrnl(root)

    text = (root / "dlls/ntoskrnl.exe/ntoskrnl.c").read_text(encoding="utf-8")
    required = [
        "DRIVER_LOAD ZwLoadDriver begin",
        "DRIVER_LOAD image-load begin",
        "DRIVER_LOAD pe-metadata",
        "DRIVER_LOAD DriverEntry enter",
        "DRIVER_LOAD DriverEntry return",
        "DRIVER_LOAD IoCreateDevice created",
        "DRIVER_LOAD IoCreateSymbolicLink return",
    ]
    for marker in required:
        if marker not in text:
            raise RuntimeError(f"missing marker after patch: {marker}")

    forbidden = ["xhunter", "xigncode", "wellbia", "6d4084", "talesrunner"]
    lowered = text.lower()
    for marker in forbidden:
        if marker in lowered:
            raise RuntimeError(f"target-specific marker found: {marker}")

    print(f"Applied {REVISION}; trace-only, no return-status or buffer behavior changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

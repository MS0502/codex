#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

PATCH_REVISION = "v27-generic-irp-outcome-2"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def patch(source_root: Path) -> None:
    path = source_root / "dlls/ntoskrnl.exe/ntoskrnl.c"
    text = path.read_text(encoding="utf-8")

    old_irp_data = '''struct irp_data
{
    HANDLE handle;
    IRP *irp;
    BOOL async;
    BOOL complete;
};
'''
    new_irp_data = '''struct irp_data
{
    HANDLE handle;
    IRP *irp;
    BOOL async;
    BOOL complete;
    UCHAR major;
    UCHAR minor;
    ULONG ioctl_code;
    PDRIVER_DISPATCH dispatch;
};
'''
    text = replace_once(text, old_irp_data, new_irp_data, "irp_data")

    old_completion = '''    EnterCriticalSection( &irp_completion_cs );

    irp_data->complete = TRUE;
'''
    new_completion = '''    EnterCriticalSection( &irp_completion_cs );

    TRACE( "IRP_TRACE completion device=%p major=%u minor=%u ioctl=%#lx dispatch=%p "
           "iosb_status=%#lx information=%Iu pending=%u async=%u\\n",
           device, irp_data->major, irp_data->minor, irp_data->ioctl_code,
           irp_data->dispatch, irp->IoStatus.Status, (SIZE_T)irp->IoStatus.Information,
           irp->PendingReturned, irp_data->async );

    irp_data->complete = TRUE;
'''
    text = replace_once(text, old_completion, new_completion, "dispatch completion")

    old_init = '''    irp_data->handle = context->handle;
    irp_data->irp = irp;
    irp_data->async = FALSE;
    irp_data->complete = FALSE;

    IoSetCompletionRoutine( irp, dispatch_irp_completion, irp_data, TRUE, TRUE, TRUE );
'''
    new_init = '''    IO_STACK_LOCATION *stack = IoGetNextIrpStackLocation( irp );
    DRIVER_OBJECT *driver = device ? device->DriverObject : NULL;

    irp_data->handle = context->handle;
    irp_data->irp = irp;
    irp_data->async = FALSE;
    irp_data->complete = FALSE;
    irp_data->major = stack->MajorFunction;
    irp_data->minor = stack->MinorFunction;
    irp_data->ioctl_code = 0;
    if (stack->MajorFunction == IRP_MJ_DEVICE_CONTROL ||
        stack->MajorFunction == IRP_MJ_INTERNAL_DEVICE_CONTROL ||
        stack->MajorFunction == IRP_MJ_FILE_SYSTEM_CONTROL)
        irp_data->ioctl_code = stack->Parameters.DeviceIoControl.IoControlCode;
    irp_data->dispatch = driver && stack->MajorFunction <= IRP_MJ_MAXIMUM_FUNCTION
            ? driver->MajorFunction[stack->MajorFunction] : NULL;

    TRACE( "IRP_TRACE begin device=%p driver=%s type=%lu flags=%#lx characteristics=%#lx "
           "major=%u minor=%u ioctl=%#lx method=%lu access=%lu dispatch=%p "
           "iosb_status=%#lx information=%Iu\\n",
           device, driver ? debugstr_us(&driver->DriverName) : "(null)",
           device ? device->DeviceType : 0, device ? device->Flags : 0,
           device ? device->Characteristics : 0, irp_data->major, irp_data->minor,
           irp_data->ioctl_code, irp_data->ioctl_code & 3,
           (irp_data->ioctl_code >> 14) & 3, irp_data->dispatch,
           irp->IoStatus.Status, (SIZE_T)irp->IoStatus.Information );

    IoSetCompletionRoutine( irp, dispatch_irp_completion, irp_data, TRUE, TRUE, TRUE );
'''
    text = replace_once(text, old_init, new_init, "dispatch init")

    old_call = '''    status = IoCallDriver( device, irp );
    KeLeaveCriticalRegion();
    device->CurrentIrp = NULL;

    if (status != STATUS_PENDING && !irp_data->complete)
'''
    new_call = '''    status = IoCallDriver( device, irp );
    KeLeaveCriticalRegion();
    device->CurrentIrp = NULL;

    TRACE( "IRP_TRACE return device=%p major=%u minor=%u ioctl=%#lx dispatch=%p "
           "return_status=%#lx iosb_status=%#lx information=%Iu pending=%u complete=%u\\n",
           device, irp_data->major, irp_data->minor, irp_data->ioctl_code,
           irp_data->dispatch, status, irp->IoStatus.Status,
           (SIZE_T)irp->IoStatus.Information, irp->PendingReturned, irp_data->complete );

    if (status != STATUS_PENDING && !irp_data->complete)
'''
    text = replace_once(text, old_call, new_call, "dispatch return")

    old_ioctl_trace = '''    TRACE( "ioctl %x device %p file %p in_size %lu out_size %lu\\n",
           context->params.ioctl.code, device, file, context->in_size, out_size );
'''
    new_ioctl_trace = '''    TRACE( "ioctl %x device %p file %p in_size %lu out_size %lu method=%u access=%u device_type=%u function=%u\\n",
           context->params.ioctl.code, device, file, context->in_size, out_size,
           context->params.ioctl.code & 3, (context->params.ioctl.code >> 14) & 3,
           context->params.ioctl.code >> 16, (context->params.ioctl.code >> 2) & 0xfff );
'''
    text = replace_once(text, old_ioctl_trace, new_ioctl_trace, "ioctl trace")

    old_unhandled = '''static NTSTATUS WINAPI unhandled_irp( DEVICE_OBJECT *device, IRP *irp )
{
    TRACE( "(%p, %p)\\n", device, irp );
    irp->IoStatus.Status = STATUS_INVALID_DEVICE_REQUEST;
    IoCompleteRequest( irp, IO_NO_INCREMENT );
    return STATUS_INVALID_DEVICE_REQUEST;
}
'''
    new_unhandled = '''static NTSTATUS WINAPI unhandled_irp( DEVICE_OBJECT *device, IRP *irp )
{
    IO_STACK_LOCATION *stack = IoGetCurrentIrpStackLocation( irp );
    DRIVER_OBJECT *driver = device ? device->DriverObject : NULL;
    ULONG ioctl_code = 0;

    if (stack && (stack->MajorFunction == IRP_MJ_DEVICE_CONTROL ||
                  stack->MajorFunction == IRP_MJ_INTERNAL_DEVICE_CONTROL ||
                  stack->MajorFunction == IRP_MJ_FILE_SYSTEM_CONTROL))
        ioctl_code = stack->Parameters.DeviceIoControl.IoControlCode;

    TRACE( "IRP_UNHANDLED device=%p driver=%s type=%lu flags=%#lx characteristics=%#lx "
           "major=%u minor=%u ioctl=%#lx method=%lu access=%lu "
           "prior_iosb_status=%#lx information=%Iu\\n",
           device, driver ? debugstr_us(&driver->DriverName) : "(null)",
           device ? device->DeviceType : 0, device ? device->Flags : 0,
           device ? device->Characteristics : 0,
           stack ? stack->MajorFunction : 0xff, stack ? stack->MinorFunction : 0xff,
           ioctl_code, ioctl_code & 3, (ioctl_code >> 14) & 3,
           irp->IoStatus.Status, (SIZE_T)irp->IoStatus.Information );

    irp->IoStatus.Status = STATUS_INVALID_DEVICE_REQUEST;
    IoCompleteRequest( irp, IO_NO_INCREMENT );
    TRACE( "IRP_UNHANDLED_COMPLETE status=%#lx information=%Iu\\n",
           irp->IoStatus.Status, (SIZE_T)irp->IoStatus.Information );
    return STATUS_INVALID_DEVICE_REQUEST;
}
'''
    text = replace_once(text, old_unhandled, new_unhandled, "unhandled_irp")

    forbidden = ("xhunter", "6d4084", "wellbia", "xigncode")
    lower = text.lower()
    for token in forbidden:
        if token in lower:
            raise RuntimeError(f"forbidden target-specific marker introduced/found: {token}")

    path.write_text(text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_v27_irp_trace_patch.py WINE_SOURCE_DIR", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).resolve()
    patch(root)
    print(f"Applied {PATCH_REVISION}; no status behavior changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

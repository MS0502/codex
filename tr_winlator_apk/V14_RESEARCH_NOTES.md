# v14 research notes

- Public WineHQ bug 42493 documents XIGNCODE3 user-mode startup under Wine Staging 2.9, followed by loading `xhunter1.sys` and failure on an unimplemented `ntoskrnl.exe.IoCreateNotificationEvent` export.
- Wine implemented `IoCreateNotificationEvent` in Wine 7.20; Wine 10.10 contains that implementation, so the 2017 first kernel-driver blocker is no longer the exact blocker in the current baseline.
- No public evidence was found that the complete `xhunter1.sys` driver and its IOCTL/device contract are supported by current Wine/Proton.
- TalesRunner KR v13 traces show repeated `CreateFileW("\\\\.\\xhunter1")` failures with `STATUS_OBJECT_NAME_NOT_FOUND`, but no driver installation or service creation attempt was captured.
- v14 therefore collects the vendor-created WELLBIA logs and file metadata without modifying XIGNCODE, security return values, device objects, or protected files.

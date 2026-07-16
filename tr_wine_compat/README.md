# Wine 10.10 TokenPrivateNameSpace compatibility patch

This branch carries a small general Wine compatibility implementation for `NtQueryInformationToken(TokenPrivateNameSpace)`. Native Windows returns a four-byte zero value for an ordinary desktop process token; Wine 10.10 currently returns an unsupported-class status, and its x64 implementation also indexes beyond the declared `info_len` array for newer token information classes.

The patch does not change game or anti-cheat files. CI applies it to the upstream Wine 10.10 tag and builds the affected 64-bit components for validation.

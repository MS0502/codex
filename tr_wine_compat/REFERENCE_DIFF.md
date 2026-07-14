Observed probe difference:

- Native Windows x64/x86: TokenPrivateNameSpace returns STATUS_SUCCESS, return length 4, value 0.
- Winlator Wine 10.10 x64: STATUS_NOT_IMPLEMENTED.
- Winlator Wine 10.10 x86/WoW64: STATUS_INVALID_INFO_CLASS.

The compatibility patch implements the native scalar result for ordinary process tokens and routes the WoW64 call through the native implementation.

#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

REVISION = "v30-generic-named-open-result-1"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch(root: Path) -> None:
    path = root / "server/fd.c"
    old = r'''/* open a file object */
DECL_HANDLER(open_file_object)
{
    struct unicode_str name = get_req_unicode_str();
    struct object *obj, *result, *root = NULL;

    if (req->rootdir && !(root = get_handle_obj( current->process, req->rootdir, 0, NULL ))) return;

    obj = open_named_object( root, NULL, &name, req->attributes );
    if (root) release_object( root );
    if (!obj) return;

    if ((result = obj->ops->open_file( obj, req->access, req->sharing, req->options )))
    {
        reply->handle = alloc_handle( current->process, result, req->access, req->attributes );
        release_object( result );
    }
    release_object( obj );
}
'''
    new = r'''/* open a file object */
DECL_HANDLER(open_file_object)
{
    struct unicode_str name = get_req_unicode_str();
    struct object *obj, *result, *root = NULL;

    if (req->rootdir && !(root = get_handle_obj( current->process, req->rootdir, 0, NULL )))
    {
        if (debug_level)
            fprintf( stderr, "NAMED_OPEN_RESULT revision=v30-generic-named-open-result-1 tid=%04x stage=root status=%08x handle=0000 name_len=%u\n",
                     (unsigned int)current->id, get_error(), (unsigned int)name.len );
        return;
    }

    obj = open_named_object( root, NULL, &name, req->attributes );
    if (root) release_object( root );
    if (!obj)
    {
        if (debug_level)
            fprintf( stderr, "NAMED_OPEN_RESULT revision=v30-generic-named-open-result-1 tid=%04x stage=lookup status=%08x handle=0000 name_len=%u\n",
                     (unsigned int)current->id, get_error(), (unsigned int)name.len );
        return;
    }

    result = obj->ops->open_file( obj, req->access, req->sharing, req->options );
    if (result)
    {
        reply->handle = alloc_handle( current->process, result, req->access, req->attributes );
        release_object( result );
    }
    if (debug_level)
        fprintf( stderr, "NAMED_OPEN_RESULT revision=v30-generic-named-open-result-1 tid=%04x stage=complete status=%08x handle=%04x name_len=%u object=%p opened=%p\n",
                 (unsigned int)current->id, get_error(), (unsigned int)reply->handle,
                 (unsigned int)name.len, obj, result );
    release_object( obj );
}
'''
    replace_once(path, old, new)

    text = path.read_text(encoding="utf-8")
    if text.count("NAMED_OPEN_RESULT") != 3:
        raise RuntimeError("named-open result marker count drift")
    forbidden = ("xhunter", "xigncode", "wellbia", "talesrunner", "6d4084")
    lowered = text.lower()
    for value in forbidden:
        if value in lowered:
            raise RuntimeError(f"target-specific marker unexpectedly present in server source: {value}")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_v30_named_open_result_trace_patch.py WINE_SOURCE_DIR", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).resolve()
    patch(root)
    print(f"Applied {REVISION}; trace-only, no lookup, handle, status, or buffer behavior changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

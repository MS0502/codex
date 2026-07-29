#define _POSIX_C_SOURCE 200809L
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <ctype.h>
#include <errno.h>
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <time.h>
#include <unistd.h>

static FILE *out;
static volatile sig_atomic_t stop_requested;
static double started;

static double mono_seconds(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec / 1000000000.0;
}

static void log_line(const char *fmt, ...) {
    va_list ap;
    fprintf(out, "t=%.3f ", mono_seconds() - started);
    va_start(ap, fmt);
    vfprintf(out, fmt, ap);
    va_end(ap);
    fputc('\n', out);
    fflush(out);
}

static void request_stop(int signal_number) {
    (void)signal_number;
    stop_requested = 1;
}

static int x_error(Display *dpy, XErrorEvent *event) {
    char text[256] = {0};
    XGetErrorText(dpy, event->error_code, text, sizeof(text));
    log_line("XError code=%u request=%u minor=%u resource=0x%lx text=%s",
             event->error_code, event->request_code, event->minor_code,
             event->resourceid, text);
    return 0;
}

static void sanitize(char *text) {
    if (!text) return;
    for (char *p = text; *p; ++p) {
        unsigned char c = (unsigned char)*p;
        if (c < 0x20 || c == 0x7f) *p = ' ';
    }
}

static const char *map_state_name(int state) {
    switch (state) {
        case IsUnmapped: return "unmapped";
        case IsUnviewable: return "unviewable";
        case IsViewable: return "viewable";
        default: return "unknown";
    }
}

static void select_tree(Display *dpy, Window window) {
    Window root = 0, parent = 0, *children = NULL;
    unsigned int count = 0;
    XSelectInput(dpy, window,
                 StructureNotifyMask | SubstructureNotifyMask |
                     PropertyChangeMask);
    if (XQueryTree(dpy, window, &root, &parent, &children, &count)) {
        for (unsigned int i = 0; i < count; ++i) select_tree(dpy, children[i]);
    }
    if (children) XFree(children);
}

static void snapshot_tree(Display *dpy, Window root, Window window, int depth) {
    if (depth > 10) return;

    XWindowAttributes attributes;
    if (!XGetWindowAttributes(dpy, window, &attributes)) return;

    char *name = NULL;
    XClassHint class_hint = {0};
    XFetchName(dpy, window, &name);
    XGetClassHint(dpy, window, &class_hint);
    sanitize(name);
    sanitize(class_hint.res_name);
    sanitize(class_hint.res_class);

    Window child = 0;
    int root_x = attributes.x, root_y = attributes.y;
    if (window != root) {
        XTranslateCoordinates(dpy, window, root, 0, 0, &root_x, &root_y, &child);
    }

    const int meaningful_geometry = attributes.width >= 32 && attributes.height >= 24;
    if (window == root || name || class_hint.res_name || class_hint.res_class ||
        meaningful_geometry) {
        log_line("Snapshot depth=%d window=0x%lx x=%d y=%d w=%d h=%d map=%s "
                 "override=%d name=\"%s\" class=\"%s/%s\"",
                 depth, window, root_x, root_y, attributes.width,
                 attributes.height, map_state_name(attributes.map_state),
                 attributes.override_redirect, name ? name : "",
                 class_hint.res_name ? class_hint.res_name : "",
                 class_hint.res_class ? class_hint.res_class : "");
    }

    if (name) XFree(name);
    if (class_hint.res_name) XFree(class_hint.res_name);
    if (class_hint.res_class) XFree(class_hint.res_class);

    Window query_root = 0, parent = 0, *children = NULL;
    unsigned int count = 0;
    if (XQueryTree(dpy, window, &query_root, &parent, &children, &count)) {
        for (unsigned int i = 0; i < count; ++i) {
            snapshot_tree(dpy, root, children[i], depth + 1);
        }
    }
    if (children) XFree(children);
}

static const char *atom_name(Display *dpy, Atom atom, char *buffer, size_t size) {
    char *name = XGetAtomName(dpy, atom);
    if (!name) return "UNKNOWN";
    snprintf(buffer, size, "%s", name);
    XFree(name);
    return buffer;
}

static int relevant_property(const char *name) {
    static const char *properties[] = {
        "WM_STATE", "WM_NORMAL_HINTS", "WM_NAME", "WM_CLASS",
        "_NET_WM_STATE", "_NET_WM_WINDOW_TYPE", "_NET_WM_NAME"
    };
    for (size_t i = 0; i < sizeof(properties) / sizeof(properties[0]); ++i) {
        if (!strcmp(name, properties[i])) return 1;
    }
    return 0;
}

int main(int argc, char **argv) {
    const char *output_path = argc > 1 ? argv[1] : NULL;
    out = output_path ? fopen(output_path, "a") : stdout;
    if (!out) {
        fprintf(stderr, "cannot open trace output %s: %s\n",
                output_path ? output_path : "stdout", strerror(errno));
        return 2;
    }
    setvbuf(out, NULL, _IOLBF, 0);
    started = mono_seconds();
    signal(SIGTERM, request_stop);
    signal(SIGINT, request_stop);
    signal(SIGHUP, request_stop);

    int duration = 150;
    const char *duration_text = getenv("TR_X11_TRACE_DURATION");
    if (duration_text && *duration_text) {
        long parsed = strtol(duration_text, NULL, 10);
        if (parsed >= 10 && parsed <= 600) duration = (int)parsed;
    }

    Display *dpy = NULL;
    for (int attempt = 0; attempt < 120 && !stop_requested; ++attempt) {
        dpy = XOpenDisplay(NULL);
        if (dpy) break;
        if (attempt == 0 || attempt % 10 == 9) {
            log_line("XOpenDisplay retry attempt=%d DISPLAY=%s", attempt + 1,
                     getenv("DISPLAY") ? getenv("DISPLAY") : "");
        }
        struct timespec retry_delay = {.tv_sec = 0, .tv_nsec = 500000000};
        nanosleep(&retry_delay, NULL);
    }
    if (!dpy) {
        log_line("XOpenDisplay failed DISPLAY=%s",
                 getenv("DISPLAY") ? getenv("DISPLAY") : "");
        if (out != stdout) fclose(out);
        return 3;
    }

    XSetErrorHandler(x_error);
    Window root = DefaultRootWindow(dpy);
    select_tree(dpy, root);
    XSync(dpy, False);

    time_t wall = time(NULL);
    log_line("trace_start pid=%ld duration=%d display=%s root=0x%lx wall=%ld",
             (long)getpid(), duration, DisplayString(dpy), root, (long)wall);
    snapshot_tree(dpy, root, root, 0);

    double next_snapshot = mono_seconds() + 2.0;
    const double deadline = mono_seconds() + duration;

    while (!stop_requested && mono_seconds() < deadline) {
        while (XPending(dpy)) {
            XEvent event;
            XNextEvent(dpy, &event);
            switch (event.type) {
                case CreateNotify:
                    log_line("Create window=0x%lx parent=0x%lx x=%d y=%d w=%d h=%d override=%d",
                             event.xcreatewindow.window, event.xcreatewindow.parent,
                             event.xcreatewindow.x, event.xcreatewindow.y,
                             event.xcreatewindow.width, event.xcreatewindow.height,
                             event.xcreatewindow.override_redirect);
                    select_tree(dpy, event.xcreatewindow.window);
                    break;
                case MapNotify:
                    log_line("Map window=0x%lx event=0x%lx override=%d",
                             event.xmap.window, event.xmap.event,
                             event.xmap.override_redirect);
                    select_tree(dpy, event.xmap.window);
                    break;
                case UnmapNotify:
                    log_line("Unmap window=0x%lx event=0x%lx from_configure=%d",
                             event.xunmap.window, event.xunmap.event,
                             event.xunmap.from_configure);
                    break;
                case DestroyNotify:
                    log_line("Destroy window=0x%lx event=0x%lx",
                             event.xdestroywindow.window,
                             event.xdestroywindow.event);
                    break;
                case ConfigureNotify:
                    log_line("Configure window=0x%lx event=0x%lx x=%d y=%d w=%d h=%d override=%d",
                             event.xconfigure.window, event.xconfigure.event,
                             event.xconfigure.x, event.xconfigure.y,
                             event.xconfigure.width, event.xconfigure.height,
                             event.xconfigure.override_redirect);
                    break;
                case ReparentNotify:
                    log_line("Reparent window=0x%lx parent=0x%lx x=%d y=%d override=%d",
                             event.xreparent.window, event.xreparent.parent,
                             event.xreparent.x, event.xreparent.y,
                             event.xreparent.override_redirect);
                    select_tree(dpy, event.xreparent.window);
                    break;
                case PropertyNotify: {
                    char buffer[256];
                    const char *name = atom_name(dpy, event.xproperty.atom,
                                                 buffer, sizeof(buffer));
                    if (relevant_property(name)) {
                        log_line("Property window=0x%lx atom=%s state=%d",
                                 event.xproperty.window, name,
                                 event.xproperty.state);
                    }
                    break;
                }
                default:
                    break;
            }
        }

        double now = mono_seconds();
        if (now >= next_snapshot) {
            log_line("snapshot_begin");
            snapshot_tree(dpy, root, root, 0);
            log_line("snapshot_end");
            next_snapshot = now + 2.0;
        }

        int fd = ConnectionNumber(dpy);
        fd_set read_fds;
        FD_ZERO(&read_fds);
        FD_SET(fd, &read_fds);
        struct timeval timeout = {.tv_sec = 0, .tv_usec = 200000};
        int rc = select(fd + 1, &read_fds, NULL, NULL, &timeout);
        if (rc < 0 && errno != EINTR) {
            log_line("select_failed errno=%d text=%s", errno, strerror(errno));
            break;
        }
    }

    log_line("trace_end stop_requested=%d", stop_requested ? 1 : 0);
    XCloseDisplay(dpy);
    if (out != stdout) fclose(out);
    return 0;
}

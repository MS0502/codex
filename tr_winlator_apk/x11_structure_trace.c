#define _POSIX_C_SOURCE 200809L
#include <X11/Xlib.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <time.h>

static double now_seconds(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec / 1000000000.0;
}

static int x_error(Display *dpy, XErrorEvent *event) {
    char text[256] = {0};
    XGetErrorText(dpy, event->error_code, text, sizeof(text));
    fprintf(stdout,
            "t=%.3f XError code=%u request=%u resource=0x%lx text=%s\n",
            now_seconds(), event->error_code, event->request_code,
            event->resourceid, text);
    fflush(stdout);
    return 0;
}

static void select_tree(Display *dpy, Window win) {
    Window root = 0;
    Window parent = 0;
    Window *children = NULL;
    unsigned int count = 0;

    XSelectInput(dpy, win,
                 StructureNotifyMask | SubstructureNotifyMask |
                     PropertyChangeMask);
    if (XQueryTree(dpy, win, &root, &parent, &children, &count)) {
        for (unsigned int i = 0; i < count; ++i) {
            select_tree(dpy, children[i]);
        }
    }
    if (children) XFree(children);
}

static const char *property_name(Display *dpy, Atom atom) {
    static char buffer[256];
    char *name = XGetAtomName(dpy, atom);
    if (!name) return "UNKNOWN";
    snprintf(buffer, sizeof(buffer), "%s", name);
    XFree(name);
    return buffer;
}

int main(void) {
    Display *dpy = XOpenDisplay(NULL);
    if (!dpy) {
        fprintf(stderr, "XOpenDisplay failed DISPLAY=%s\n", getenv("DISPLAY"));
        return 2;
    }

    XSetErrorHandler(x_error);
    Window root = DefaultRootWindow(dpy);
    select_tree(dpy, root);
    XSync(dpy, False);

    const double end = now_seconds() + 72.0;
    printf("t=%.3f monitor_start root=0x%lx\n", now_seconds(), root);
    fflush(stdout);

    while (now_seconds() < end) {
        while (XPending(dpy)) {
            XEvent event;
            XNextEvent(dpy, &event);
            switch (event.type) {
                case CreateNotify:
                    printf("t=%.3f Create window=0x%lx parent=0x%lx "
                           "x=%d y=%d w=%d h=%d override=%d\n",
                           now_seconds(), event.xcreatewindow.window,
                           event.xcreatewindow.parent, event.xcreatewindow.x,
                           event.xcreatewindow.y, event.xcreatewindow.width,
                           event.xcreatewindow.height,
                           event.xcreatewindow.override_redirect);
                    select_tree(dpy, event.xcreatewindow.window);
                    break;
                case MapNotify:
                    printf("t=%.3f Map window=0x%lx event=0x%lx override=%d\n",
                           now_seconds(), event.xmap.window, event.xmap.event,
                           event.xmap.override_redirect);
                    select_tree(dpy, event.xmap.window);
                    break;
                case UnmapNotify:
                    printf("t=%.3f Unmap window=0x%lx event=0x%lx "
                           "from_configure=%d\n",
                           now_seconds(), event.xunmap.window,
                           event.xunmap.event, event.xunmap.from_configure);
                    break;
                case DestroyNotify:
                    printf("t=%.3f Destroy window=0x%lx event=0x%lx\n",
                           now_seconds(), event.xdestroywindow.window,
                           event.xdestroywindow.event);
                    break;
                case ConfigureNotify:
                    printf("t=%.3f Configure window=0x%lx event=0x%lx "
                           "x=%d y=%d w=%d h=%d override=%d\n",
                           now_seconds(), event.xconfigure.window,
                           event.xconfigure.event, event.xconfigure.x,
                           event.xconfigure.y, event.xconfigure.width,
                           event.xconfigure.height,
                           event.xconfigure.override_redirect);
                    break;
                case ReparentNotify:
                    printf("t=%.3f Reparent window=0x%lx parent=0x%lx "
                           "x=%d y=%d override=%d\n",
                           now_seconds(), event.xreparent.window,
                           event.xreparent.parent, event.xreparent.x,
                           event.xreparent.y,
                           event.xreparent.override_redirect);
                    select_tree(dpy, event.xreparent.window);
                    break;
                case PropertyNotify: {
                    const char *name = property_name(dpy, event.xproperty.atom);
                    if (!strcmp(name, "WM_STATE") ||
                        !strcmp(name, "WM_NORMAL_HINTS") ||
                        !strcmp(name, "WM_NAME") ||
                        !strcmp(name, "_NET_WM_STATE") ||
                        !strcmp(name, "_NET_WM_WINDOW_TYPE")) {
                        printf("t=%.3f Property window=0x%lx atom=%s state=%d\n",
                               now_seconds(), event.xproperty.window, name,
                               event.xproperty.state);
                    }
                    break;
                }
            }
            fflush(stdout);
        }

        int fd = ConnectionNumber(dpy);
        fd_set readfds;
        FD_ZERO(&readfds);
        FD_SET(fd, &readfds);
        struct timeval timeout = {.tv_sec = 0, .tv_usec = 200000};
        int rc = select(fd + 1, &readfds, NULL, NULL, &timeout);
        if (rc < 0 && errno != EINTR) break;
    }

    printf("t=%.3f monitor_end\n", now_seconds());
    XCloseDisplay(dpy);
    return 0;
}

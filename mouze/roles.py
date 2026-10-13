"""Cursor roles and how they map onto each operating system.

A *role* is the job a cursor does (normal select, link select, text select...).
Windows calls these "pointer schemes" entries, X11/Wayland themes use a set of
well-known file names.  MouZe skins are keyed by role.
"""

from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    ARROW = "arrow"            # Normal select
    HELP = "help"              # Help select
    WORKING = "working"        # Working in background
    BUSY = "busy"              # Busy
    PRECISION = "precision"    # Precision select
    TEXT = "text"              # Text select
    HANDWRITING = "handwriting"
    UNAVAILABLE = "unavailable"
    SIZE_NS = "size_ns"        # Vertical resize
    SIZE_EW = "size_ew"        # Horizontal resize
    SIZE_NWSE = "size_nwse"    # Diagonal resize 1
    SIZE_NESW = "size_nesw"    # Diagonal resize 2
    MOVE = "move"
    ALTERNATE = "alternate"    # Alternate select (up arrow)
    LINK = "link"              # Link select (hand)
    PIN = "pin"                # Location select
    PERSON = "person"          # Person select

    @property
    def label(self) -> str:
        return ROLE_LABELS[self]


ROLE_LABELS = {
    Role.ARROW: "Normal Select",
    Role.HELP: "Help Select",
    Role.WORKING: "Working in Background",
    Role.BUSY: "Busy",
    Role.PRECISION: "Precision Select",
    Role.TEXT: "Text Select",
    Role.HANDWRITING: "Handwriting",
    Role.UNAVAILABLE: "Unavailable",
    Role.SIZE_NS: "Vertical Resize",
    Role.SIZE_EW: "Horizontal Resize",
    Role.SIZE_NWSE: "Diagonal Resize 1",
    Role.SIZE_NESW: "Diagonal Resize 2",
    Role.MOVE: "Move",
    Role.ALTERNATE: "Alternate Select",
    Role.LINK: "Link Select",
    Role.PIN: "Location Select",
    Role.PERSON: "Person Select",
}

# Order used by the Windows "Control Panel\Cursors\Schemes" value and by
# install.inf files.  Do not reorder.
WINDOWS_SCHEME_ORDER = [
    Role.ARROW, Role.HELP, Role.WORKING, Role.BUSY, Role.PRECISION, Role.TEXT,
    Role.HANDWRITING, Role.UNAVAILABLE, Role.SIZE_NS, Role.SIZE_EW,
    Role.SIZE_NWSE, Role.SIZE_NESW, Role.MOVE, Role.ALTERNATE, Role.LINK,
    Role.PIN, Role.PERSON,
]

# Registry value names under HKCU\Control Panel\Cursors.
WINDOWS_REG_NAMES = {
    Role.ARROW: "Arrow",
    Role.HELP: "Help",
    Role.WORKING: "AppStarting",
    Role.BUSY: "Wait",
    Role.PRECISION: "Crosshair",
    Role.TEXT: "IBeam",
    Role.HANDWRITING: "NWPen",
    Role.UNAVAILABLE: "No",
    Role.SIZE_NS: "SizeNS",
    Role.SIZE_EW: "SizeWE",
    Role.SIZE_NWSE: "SizeNWSE",
    Role.SIZE_NESW: "SizeNESW",
    Role.MOVE: "SizeAll",
    Role.ALTERNATE: "UpArrow",
    Role.LINK: "Hand",
    Role.PIN: "Pin",
    Role.PERSON: "Person",
}

# IDC_* resource ids, used to work out which role Windows is showing.
WINDOWS_IDC = {
    Role.ARROW: 32512,
    Role.TEXT: 32513,
    Role.BUSY: 32514,
    Role.PRECISION: 32515,
    Role.ALTERNATE: 32516,
    Role.SIZE_NWSE: 32642,
    Role.SIZE_NESW: 32643,
    Role.SIZE_EW: 32644,
    Role.SIZE_NS: 32645,
    Role.MOVE: 32646,
    Role.UNAVAILABLE: 32648,
    Role.LINK: 32649,
    Role.WORKING: 32650,
    Role.HELP: 32651,
    Role.PIN: 32671,
    Role.PERSON: 32672,
}

# File names used by Xcursor themes (X11, Wayland compositors, GTK, Qt).
# The first name of each list is written as a real file, the rest are links.
XCURSOR_NAMES = {
    Role.ARROW: ["left_ptr", "default", "arrow", "top_left_arrow", "left_arrow",
                 "copy", "alias", "context-menu", "dnd-copy", "dnd-link",
                 "1081e37283d90000800003c07f3ef6bf", "3085a0e285430894940527032f8b26df",
                 "6407b0e94181790501fd1e167b474872", "640fb0e74195791501fd1ed57b41487f",
                 "b66166c04f8c3109214a4fbd64a50fc8"],
    Role.HELP: ["question_arrow", "help", "whats_this", "left_ptr_help",
                "5c6cd98b3f3ebcb1f9c7f1c204630408", "d9ce0ab605698f320427677b458ad60b"],
    Role.WORKING: ["left_ptr_watch", "progress", "half-busy",
                   "00000000000000020006000e7e9ffc3f", "08e8e1c95fe2fc01f976f1e063a24ccd",
                   "3ecb610c1bf2410f44200f48c40d3599"],
    Role.BUSY: ["watch", "wait"],
    Role.PRECISION: ["crosshair", "cross", "tcross", "cross_reverse", "diamond_cross",
                     "cell", "plus", "zoom-in", "zoom-out"],
    Role.TEXT: ["xterm", "text", "ibeam", "vertical-text"],
    Role.HANDWRITING: ["pencil", "draft"],
    Role.UNAVAILABLE: ["not-allowed", "no-drop", "crossed_circle", "forbidden", "circle",
                       "dnd-none", "dnd-no-drop", "03b6e0fcb3499374a867c041f52298f0"],
    Role.SIZE_NS: ["sb_v_double_arrow", "ns-resize", "size_ver", "v_double_arrow",
                   "row-resize", "n-resize", "s-resize", "top_side", "bottom_side",
                   "split_v", "00008160000006810000408080010102",
                   "2870a09082c103050810ffdffffe0204"],
    Role.SIZE_EW: ["sb_h_double_arrow", "ew-resize", "size_hor", "h_double_arrow",
                   "col-resize", "e-resize", "w-resize", "left_side", "right_side",
                   "split_h", "028006030e0e7ebffc7f7070c0600140",
                   "14fef782d02440884392942c11205230"],
    Role.SIZE_NWSE: ["size_fdiag", "nwse-resize", "bd_double_arrow", "nw-resize",
                     "se-resize", "top_left_corner", "bottom_right_corner",
                     "c7088f0f3e6c8088236ef8e1e3e70000"],
    Role.SIZE_NESW: ["size_bdiag", "nesw-resize", "fd_double_arrow", "ne-resize",
                     "sw-resize", "top_right_corner", "bottom_left_corner",
                     "fcf1c3c7cd4491d801f1e1c78f100000"],
    Role.MOVE: ["fleur", "move", "all-scroll", "size_all", "grabbing", "dnd-move",
                "closedhand", "4498f0e0c1937ffe01fd06f973665830",
                "9081237383d90e509aa00f00170e968f", "fcf21c00b30f7e3f83fe0dfd12e71cff"],
    Role.ALTERNATE: ["center_ptr", "up_arrow", "sb_up_arrow"],
    Role.LINK: ["hand2", "pointer", "hand1", "hand", "pointing_hand", "grab", "openhand",
                "e29285e634086352946a0e7090d73106", "9d800788f1b08800ae810202380a0822",
                "5aca4d189052212118709018842178c0"],
    Role.PIN: [],
    Role.PERSON: [],
}

# When a skin does not provide a role, use the first available fallback.
FALLBACKS = {
    Role.ARROW: [],
    Role.HELP: [Role.ARROW],
    Role.WORKING: [Role.BUSY, Role.ARROW],
    Role.BUSY: [Role.WORKING, Role.ARROW],
    Role.PRECISION: [Role.ARROW],
    Role.TEXT: [Role.ARROW],
    Role.HANDWRITING: [Role.PRECISION, Role.ARROW],
    Role.UNAVAILABLE: [Role.ARROW],
    Role.SIZE_NS: [Role.MOVE, Role.ARROW],
    Role.SIZE_EW: [Role.MOVE, Role.ARROW],
    Role.SIZE_NWSE: [Role.MOVE, Role.ARROW],
    Role.SIZE_NESW: [Role.MOVE, Role.ARROW],
    Role.MOVE: [Role.ARROW],
    Role.ALTERNATE: [Role.ARROW],
    Role.LINK: [Role.ARROW],
    Role.PIN: [Role.LINK, Role.ARROW],
    Role.PERSON: [Role.LINK, Role.ARROW],
}

# Filename keywords used to guess a role when importing loose cursor files.
ROLE_KEYWORDS = [
    (Role.WORKING, ["working", "appstarting", "app_starting", "background", "progress",
                    "left_ptr_watch", "half-busy"]),
    (Role.BUSY, ["busy", "wait", "watch", "loading", "hourglass"]),
    (Role.HELP, ["help", "question", "whats_this"]),
    (Role.HANDWRITING, ["handwriting", "nwpen", "pen", "pencil", "draw"]),
    (Role.UNAVAILABLE, ["unavailable", "not-allowed", "notallowed", "forbidden", "no-drop",
                        "nodrop", "crossed_circle", "denied", "_no.", "unavail"]),
    (Role.SIZE_NWSE, ["nwse", "fdiag", "dgn1", "diagonal1", "diag1", "diagonal_1",
                      "diagonal resize 1", "bd_double"]),
    (Role.SIZE_NESW, ["nesw", "bdiag", "dgn2", "diagonal2", "diag2", "diagonal_2",
                      "diagonal resize 2", "fd_double"]),
    (Role.SIZE_NS, ["sizens", "size_ns", "ns-resize", "vert", "v_double", "row-resize",
                    "vertical"]),
    (Role.SIZE_EW, ["sizewe", "size_we", "sizeew", "ew-resize", "horz", "horiz",
                    "h_double", "col-resize", "horizontal"]),
    (Role.MOVE, ["move", "sizeall", "size_all", "fleur", "all-scroll", "grabbing"]),
    (Role.ALTERNATE, ["alternate", "uparrow", "up_arrow", "center_ptr", "alt."]),
    (Role.PRECISION, ["precision", "crosshair", "cross", "cell"]),
    (Role.TEXT, ["text", "ibeam", "beam", "xterm", "select_text"]),
    (Role.LINK, ["link", "hand", "pointer", "pointing", "finger"]),
    (Role.PIN, ["pin", "location"]),
    (Role.PERSON, ["person", "user"]),
    (Role.ARROW, ["normal", "arrow", "default", "left_ptr", "select", "main", "cursor"]),
]


def guess_role(filename: str) -> Role | None:
    """Guess a cursor role from a file name such as ``"Busy.ani"``."""
    name = filename.lower().replace(" ", "_")
    stem = name.rsplit("/", 1)[-1]
    for role, xnames in XCURSOR_NAMES.items():
        if stem in xnames:
            return role
    for role, words in ROLE_KEYWORDS:
        for word in words:
            if word.replace(" ", "_") in stem:
                return role
    return None


ANIMATED_BY_NATURE = {Role.BUSY, Role.WORKING}

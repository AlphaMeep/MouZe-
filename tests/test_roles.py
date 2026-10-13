from mouze.roles import FALLBACKS, WINDOWS_IDC, WINDOWS_REG_NAMES, WINDOWS_SCHEME_ORDER, XCURSOR_NAMES, Role, guess_role


def test_tables_cover_every_role():
    for role in Role:
        assert role in WINDOWS_REG_NAMES
        assert role in FALLBACKS
        assert role in XCURSOR_NAMES
        assert role.label
    assert sorted(WINDOWS_SCHEME_ORDER, key=lambda r: r.value) == sorted(Role, key=lambda r: r.value)
    assert len(set(WINDOWS_IDC.values())) == len(WINDOWS_IDC)


def test_xcursor_names_unique():
    seen = set()
    for names in XCURSOR_NAMES.values():
        for n in names:
            assert n not in seen, n
            seen.add(n)


def test_guess_role():
    cases = {
        "Normal.cur": Role.ARROW, "Link.ani": Role.LINK, "Busy.ani": Role.BUSY, "Working.ani": Role.WORKING,
        "Text Select.cur": Role.TEXT, "Unavailable.cur": Role.UNAVAILABLE, "Vertical.cur": Role.SIZE_NS,
        "Horizontal Resize.cur": Role.SIZE_EW, "Diagonal1.cur": Role.SIZE_NWSE, "dgn2.cur": Role.SIZE_NESW,
        "Move.cur": Role.MOVE, "Alternate.cur": Role.ALTERNATE, "Precision.cur": Role.PRECISION,
        "Handwriting.cur": Role.HANDWRITING, "Help.cur": Role.HELP, "left_ptr": Role.ARROW,
        "openhand": Role.LINK, "Location Select.cur": Role.PIN, "Person.cur": Role.PERSON,
    }
    for name, role in cases.items():
        assert guess_role(name.rsplit(".", 1)[0]) == role, name
    assert guess_role("zzz") is None

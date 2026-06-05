import unicodedata


def cjk_width(s: str) -> int:
    """CJK-aware 顯示寬度（全形字元算 2）。"""
    return sum(2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in s)


def pad_right(s: str, w: int) -> str:
    return s + ' ' * max(0, w - cjk_width(s))


def pad_left(s: str, w: int) -> str:
    return ' ' * max(0, w - cjk_width(s)) + s


def format_table(rows: list[dict], right_cols: set[str] | None = None) -> str:
    if not rows:
        return ""
    cols = list(rows[0].keys())
    if right_cols is None:
        right_cols = set(cols[2:])
    str_rows = [{c: str(r[c]) for c in cols} for r in rows]
    widths = {c: cjk_width(c) for c in cols}
    for r in str_rows:
        for c in cols:
            widths[c] = max(widths[c], cjk_width(r[c]))
    header = "  ".join(
        (pad_left(c, widths[c]) if c in right_cols else pad_right(c, widths[c])) for c in cols
    )
    sep = "─" * cjk_width(header)
    data_lines = []
    for r in str_rows:
        line = "  ".join(
            (pad_left(r[c], widths[c]) if c in right_cols else pad_right(r[c], widths[c])) for c in cols
        )
        data_lines.append(line)
    return "\n".join([header, sep] + data_lines)

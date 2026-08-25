"""Build LRC text from lines and start times."""


def _stamp(sec: float) -> str:
    """Format seconds as [mm:ss.xx]."""
    if sec < 0:
        sec = 0.0
    minutes = int(sec // 60)
    rest = sec - minutes * 60
    return f"[{minutes:02d}:{rest:05.2f}]"


def build(lines: list[str], starts: list[float], title: str, total_sec: float) -> str:
    """Return the full LRC file content."""
    out = [
        f"[ti:{title}]",
        "[re:iroha-reader-cli]",
        f"[length:{_stamp(total_sec)[1:-1]}]",
        "",
    ]
    for text, start in zip(lines, starts):
        out.append(f"{_stamp(start)}{text}")
    return "\n".join(out) + "\n"

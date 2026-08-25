"""Reading dictionary: fix what the engine says, not what it shows.

The file is TSV, one `word<TAB>reading` pair per line. Replacements
apply to the spoken text only, so the subtitles keep the original
wording.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .errors import ReaderError


@dataclass(frozen=True, slots=True)
class Readings:
    """Word to reading rules, longest word first."""

    rules: tuple[tuple[str, str], ...] = ()

    def __bool__(self) -> bool:
        return bool(self.rules)

    def apply(self, text: str) -> str:
        """Rewrite one line for the TTS engine."""
        for word, reading in self.rules:
            text = text.replace(word, reading)
        return text

    def apply_all(self, lines: Iterable[str]) -> list[str]:
        return [self.apply(line) for line in lines]

    @classmethod
    def parse(cls, text: str, source: str = "<dict>") -> Readings:
        """Parse TSV text. Blank lines and # comments are skipped."""
        rules: list[tuple[str, str]] = []
        for number, raw in enumerate(text.splitlines(), start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            word, sep, reading = line.partition("\t")
            word = word.strip()
            if not sep or not word:
                raise ReaderError(
                    f"{source}:{number}: expected word<TAB>reading, got {raw!r}"
                )
            rules.append((word, reading.strip()))
        # Longest first, so a long word wins over one of its parts.
        rules.sort(key=lambda rule: len(rule[0]), reverse=True)
        return cls(tuple(rules))

    @classmethod
    def load(cls, path: Path) -> Readings:
        """Read a TSV dictionary file."""
        if not path.is_file():
            raise ReaderError(f"dictionary file not found: {path}")
        return cls.parse(path.read_text(encoding="utf-8"), source=str(path))

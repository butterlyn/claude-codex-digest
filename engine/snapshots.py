"""Yesterday's copy of every watched page, as plain files under data/snapshots/.

Git keeps every version, so the repo's history of a snapshot file is that page's history.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath


class Snapshots:
    def __init__(self, root: Path):
        self.root = root

    def _path(self, source: str, key: str) -> Path:
        rel = PurePosixPath(key)
        if rel.is_absolute() or ".." in rel.parts or not rel.parts:
            raise ValueError(f"bad snapshot key: {key!r}")
        return self.root / source / Path(*rel.parts)

    def read(self, source: str, key: str) -> str | None:
        path = self._path(source, key)
        return path.read_text(encoding="utf-8") if path.exists() else None

    def write(self, source: str, key: str, text: str) -> None:
        path = self._path(source, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def delete(self, source: str, key: str) -> None:
        path = self._path(source, key)
        if path.exists():
            path.unlink()

    def keys(self, source: str) -> set[str]:
        base = self.root / source
        if not base.exists():
            return set()
        return {p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file()}

    def has_any(self, source: str) -> bool:
        return bool(self.keys(source))

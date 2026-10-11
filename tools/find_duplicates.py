"""Find repeated songs in the library, and check new music before it is added.

    python -m tools.find_duplicates                  audit the library
    python -m tools.find_duplicates --all            also list the same title by other artists
    python -m tools.find_duplicates --check PATH...  is this already in the library? (exit 1 if so)

It only reports: nothing is ever deleted or moved. The library folder is
CASETA_SONG_DIR (default `songs`) unless --songs is given.

Two songs are an *exact* copy when their files are byte for byte the same. They are
*probably the same song* when artist and title match once case, accents and
decoration such as "(Letra)" or "[Video Oficial]" are ignored. The same title by
another artist is usually a different song, so it is only shown with --all.
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from caseta.config import Config
from caseta.library import Library, hash_file

_BRACKETS = re.compile(r"[(\[{][^)\]}]*[)\]}]")
_NOISE = frozenset(
    {"letra", "lyrics", "lyric", "video", "oficial", "official", "videoclip", "audio", "hd",
     "remastered", "remasterizado"}
)


@dataclass(frozen=True)
class Report:
    exact: list[list[str]]  # byte-identical files
    likely: list[list[str]]  # same artist and title
    same_title: list[list[str]]  # same title, different artists


@dataclass(frozen=True)
class Finding:
    path: Path  # the new file, as it was given
    kind: str  # "exact" or "similar"
    matches: tuple[str, ...]  # library songs it duplicates


def normalize(text: str) -> str:
    """Lowercase ASCII words of `text`, without bracketed decoration or filler words."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    text = _BRACKETS.sub(" ", text)
    words = re.sub(r"[^a-z0-9]+", " ", text).split()
    return " ".join(w for w in words if w not in _NOISE)


def _stem(name: str) -> str:
    return Path(name.replace("\\", "/")).stem


def full_key(name: str) -> str:
    return normalize(_stem(name))


def title_key(name: str) -> str:
    stem = _stem(name)
    return normalize(stem.split(" - ", 1)[1] if " - " in stem else stem)


def _groups(items: Iterable[str], key) -> list[list[str]]:
    by_key: dict[str, list[str]] = defaultdict(list)
    for item in items:
        k = key(item)
        if k:
            by_key[k].append(item)
    return [group for group in by_key.values() if len(group) > 1]


def _exact_groups(library: Library, songs: list[str]) -> list[list[str]]:
    """Same-size files are hashed; the rest of the library is never read."""
    by_size: dict[int, list[str]] = defaultdict(list)
    for song in songs:
        by_size[library.resolve(song).stat().st_size].append(song)
    groups = []
    for same_size in by_size.values():
        if len(same_size) > 1:
            groups += _groups(same_size, library.content_key)
    return sorted(sorted(g) for g in groups)


def analyse(library: Library) -> Report:
    songs = library.list_songs()
    exact = _exact_groups(library, songs)
    exact_id = {song: i for i, group in enumerate(exact) for song in group}

    def beyond_exact(group: list[str]) -> bool:
        """False when the group is just one set of byte-identical copies."""
        return len({exact_id.get(s, f"alone:{s}") for s in group}) > 1

    likely = [g for g in _groups(songs, full_key) if beyond_exact(g)]
    same_title = [g for g in _groups(songs, title_key) if len({full_key(s) for s in g}) > 1]
    return Report(exact, likely, same_title)


def _audio_files(paths: Sequence[Path], extensions: frozenset[str]) -> list[Path]:
    found = []
    for path in paths:
        candidates = sorted(path.rglob("*")) if path.is_dir() else [path]
        found += [p for p in candidates if p.is_file() and p.suffix.lstrip(".").lower() in extensions]
    return found


def check_new(library: Library, paths: Sequence[Path]) -> list[Finding]:
    """Which of the new files (or folders of them) the library already has."""
    songs = library.list_songs()
    resolved = {song: library.resolve(song) for song in songs}
    by_size: dict[int, list[str]] = defaultdict(list)
    for song, path in resolved.items():
        by_size[path.stat().st_size].append(song)
    by_name: dict[str, list[str]] = defaultdict(list)
    for song in songs:
        by_name[full_key(song)].append(song)

    findings = []
    for path in _audio_files(paths, Config().allowed_extensions):
        here = path.resolve()
        others = [s for s in by_size.get(path.stat().st_size, []) if resolved[s] != here]
        exact = []
        if others:
            digest = hash_file(path)
            exact = [s for s in others if library.content_key(s) == digest]
        if exact:
            findings.append(Finding(path, "exact", tuple(exact)))
            continue
        similar = [s for s in by_name.get(full_key(path.name), []) if resolved[s] != here]
        if similar:
            findings.append(Finding(path, "similar", tuple(similar)))
    return findings


def _print_groups(title: str, groups: list[list[str]]) -> None:
    print(f"{title}: {len(groups)} group(s)")
    for group in groups:
        for song in group:
            print(f"  - {song}")
        print()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="find_duplicates", description="Find repeated songs. Reports only.")
    parser.add_argument("--songs", help="library folder (default: CASETA_SONG_DIR, or 'songs')")
    parser.add_argument("--all", action="store_true", help="also list the same title by different artists")
    parser.add_argument("--check", nargs="+", metavar="PATH", help="new files or folders to compare with the library")
    args = parser.parse_args(argv)

    try:  # a Windows console may not encode accents in file names
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass

    try:
        config = Config(song_folder=Path(args.songs)) if args.songs else Config.from_env()
    except ValueError as error:
        print(f"Invalid configuration: {error}", file=sys.stderr)
        return 2
    library = Library(config)

    if args.check:
        findings = check_new(library, [Path(p) for p in args.check])
        for f in findings:
            sign = "=" if f.kind == "exact" else "~"
            print(f"{f.kind.upper():7} {f.path}")
            for match in f.matches:
                print(f"        {sign} {match}")
        if not findings:
            print("Nothing here is already in the library.")
            return 0
        print(f"\n{len(findings)} file(s) look like songs the library already has.")
        return 1

    report = analyse(library)
    _print_groups("Exact copies (same file content)", report.exact)
    _print_groups("Probably the same song (same artist and title)", report.likely)
    if args.all:
        _print_groups("Same title, different artists (usually different songs)", report.same_title)
    elif report.same_title:
        print(f"{len(report.same_title)} more group(s) share a title only; --all lists them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

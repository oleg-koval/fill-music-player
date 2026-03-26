# /// script
# requires-python = ">=3.11"
# dependencies = ["mutagen"]
# ///
"""
fill-music-player — curate and copy a DJ-balanced music selection to a portable player.

Scans a music library (NAS, local folder, external drive), picks a diverse
random selection that fits your player's capacity, and copies it over.
Reads ID3/MP4/WMA tags for artist balancing, falls back to folder names.

Usage:
    uv run fill_music_player.py --source /Volumes/music --dest /Volumes/WALKMAN/MUSIC
    uv run fill_music_player.py --source ~/Music --dest /media/usb/MUSIC --dry-run
    uv run fill_music_player.py --help

Or install from PyPI:
    uvx fill-music-player --source /Volumes/music --dest /Volumes/WALKMAN/MUSIC
"""

import argparse
import os
import re
import random
import shutil
import sys
from collections import defaultdict
from pathlib import Path

try:
    from mutagen import File as MutagenFile
    HAS_MUTAGEN = True
except ImportError:
    HAS_MUTAGEN = False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="fill-music-player",
        description="Fill a portable music player with a curated random selection.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run first (always recommended)
  fill-music-player --source /Volumes/music --dest /Volumes/WALKMAN/MUSIC --dry-run

  # Fill a Sony Walkman from a NAS
  fill-music-player --source /Volumes/music --dest /Volumes/WALKMAN/MUSIC

  # Target 2 GB on a small player, MP3 only
  fill-music-player --source ~/Music --dest /media/usb --target-gb 2 --formats mp3

  # Skip radio recordings and jingles
  fill-music-player --source /Volumes/music --dest /Volumes/PLAYER \\
      --skip-dirs "jingles,!recordings,!restored"

  # Reproducible selection (same seed = same tracks)
  fill-music-player --source /Volumes/music --dest /Volumes/PLAYER --seed 42
""",
    )
    p.add_argument("--source", "-s", required=True,
                   help="Source music root directory (NAS mount, ~/Music, etc.)")
    p.add_argument("--dest", "-d", required=True,
                   help="Destination directory on the player")
    p.add_argument("--target-gb", type=float, default=None,
                   help="How many GB to fill (default: 95%% of free space on dest)")
    p.add_argument("--max-file-mb", type=float, default=20,
                   help="Skip files larger than this in MB (default: 20)")
    p.add_argument("--min-file-kb", type=float, default=300,
                   help="Skip files smaller than this in KB (default: 300)")
    p.add_argument("--max-per-artist", type=int, default=4,
                   help="Max tracks from any single artist (default: 4)")
    p.add_argument("--max-per-album", type=int, default=3,
                   help="Max tracks from any single album (default: 3)")
    p.add_argument("--formats", default="mp3,m4a,wma,aac",
                   help="Comma-separated audio extensions, no dots (default: mp3,m4a,wma,aac)")
    p.add_argument("--skip-dirs", default="",
                   help="Comma-separated top-level directory names to skip")
    p.add_argument("--seed", type=int, default=None,
                   help="Random seed for reproducible selection")
    p.add_argument("--dry-run", action="store_true",
                   help="Scan and curate but do not copy files")
    p.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    return p.parse_args(argv)


# ---------------------------------------------------------------------------
# Metadata extraction
# ---------------------------------------------------------------------------

def get_tags(path: Path):
    """Read audio metadata tags. Returns None if mutagen unavailable or file unreadable."""
    if not HAS_MUTAGEN:
        return None
    try:
        return MutagenFile(path, easy=False)
    except Exception:
        return None


def extract_artist_album(path: Path, source_root: Path, tags) -> tuple[str, str]:
    """Extract artist + album from tags, falling back to folder name heuristics.

    Folder heuristic assumes: source/genre/Artist - Album/track.ext
    """
    artist = album = None

    if tags:
        # ID3 (MP3)
        for key in ("TPE1", "TPE2"):
            v = tags.get(key)
            if v:
                artist = str(v.text[0] if hasattr(v, "text") else v).strip()
                break
        v = tags.get("TALB")
        if v:
            album = str(v.text[0] if hasattr(v, "text") else v).strip()

        # MP4/AAC
        if not artist:
            for key in ("\xa9ART", "aART"):
                if key in tags:
                    artist = str(tags[key][0]).strip()
                    break
        if not album and "\xa9alb" in tags:
            album = str(tags["\xa9alb"][0]).strip()

        # WMA / ASF
        if not artist and "Author" in tags:
            artist = str(tags["Author"][0]).strip()
        if not album and "WM/AlbumTitle" in tags:
            album = str(tags["WM/AlbumTitle"][0]).strip()

    # Fallback: parse from folder structure
    parts = path.relative_to(source_root).parts
    if not artist and len(parts) >= 2:
        folder = parts[1]
        m = re.match(r"^(.+?)\s*[-\u2013]\s*(.+)$", folder)
        if m:
            artist = m.group(1).strip()
            album = m.group(2).strip()
        else:
            artist = folder

    if not album and len(parts) >= 3:
        album = parts[2]

    return (artist or "Unknown", album or "Unknown")


def normalise_artist_key(artist: str) -> str:
    """Strip 'feat./ft./featuring/&/and ...' suffixes for grouping."""
    return re.sub(
        r"\s+(feat\.?|ft\.?|featuring|&|and)\s+.*", "",
        artist, flags=re.I,
    ).strip()


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------

def scan_files(source: Path, supported_exts: set[str], skip_dirs: set[str],
               max_file_mb: float, min_file_kb: float) -> list[dict]:
    """Walk source directory and collect all eligible audio files."""
    print("Scanning music collection ...")
    files = []
    genres_seen = set()

    for genre_dir in sorted(source.iterdir()):
        if not genre_dir.is_dir():
            continue
        genre = genre_dir.name
        if genre in skip_dirs:
            print(f"  skip {genre}/")
            continue
        genres_seen.add(genre)

        for root, dirs, filenames in os.walk(genre_dir):
            dirs[:] = [d for d in dirs if d.lower() not in ("incomplete",)]
            root_path = Path(root)

            for fn in filenames:
                fpath = root_path / fn
                if fpath.suffix.lower() not in supported_exts:
                    continue
                try:
                    size = fpath.stat().st_size
                except OSError:
                    continue

                if size > max_file_mb * 1024**2:
                    continue
                if size < min_file_kb * 1024:
                    continue

                tags = get_tags(fpath)
                artist, album = extract_artist_album(fpath, source, tags)

                files.append({
                    "path": fpath,
                    "size": size,
                    "genre": genre,
                    "artist": artist,
                    "artist_key": normalise_artist_key(artist),
                    "album": album,
                })

    print(f"  Found {len(files)} candidate tracks across {len(genres_seen)} genre dirs")
    return files


# ---------------------------------------------------------------------------
# Curation
# ---------------------------------------------------------------------------

def curate(files: list[dict], target_bytes: int,
           max_per_artist: int, max_per_album: int) -> list[dict]:
    """DJ-balanced curation.

    Strategy:
    1. Split byte budget proportionally across genres (by track count)
    2. Within each genre: shuffle, then pick respecting artist/album caps
    3. Globally re-shuffle for interleaved playback order
    4. Trim to target_bytes
    """
    by_genre: dict[str, list[dict]] = defaultdict(list)
    for f in files:
        by_genre[f["genre"]].append(f)

    total_tracks = len(files)
    per_genre_budget = {
        genre: int(target_bytes * len(gfiles) / total_tracks)
        for genre, gfiles in by_genre.items()
    }

    selected: list[dict] = []

    for genre, gfiles in sorted(by_genre.items()):
        budget = per_genre_budget[genre]
        random.shuffle(gfiles)

        artist_count: dict[str, int] = defaultdict(int)
        album_count: dict[tuple, int] = defaultdict(int)
        genre_bytes = 0
        genre_picks = []

        for f in gfiles:
            ak = f["artist_key"]
            alb_key = (ak, f["album"])

            if artist_count[ak] >= max_per_artist:
                continue
            if album_count[alb_key] >= max_per_album:
                continue
            if genre_bytes + f["size"] > budget:
                continue

            genre_picks.append(f)
            artist_count[ak] += 1
            album_count[alb_key] += 1
            genre_bytes += f["size"]

        selected.extend(genre_picks)
        print(f"  {genre:22s}  {len(genre_picks):3d} tracks  "
              f"({genre_bytes / 1024**2:6.1f} MB)")

    random.shuffle(selected)

    total = 0
    final = []
    for f in selected:
        if total + f["size"] > target_bytes:
            continue
        final.append(f)
        total += f["size"]

    print(f"\n  Selected {len(final)} tracks  ({total / 1024**2:.1f} MB)")
    return final


# ---------------------------------------------------------------------------
# Copying
# ---------------------------------------------------------------------------

def sanitise_path_part(s: str) -> str:
    """Make a path component safe for FAT32/exFAT."""
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s)
    s = re.sub(r"\s+", " ", s).strip(". ")
    return s[:80] if s else "track"


def dest_path(src: Path, source_root: Path, dest_root: Path) -> Path:
    """Build FAT32-safe destination path mirroring source structure."""
    rel_parts = src.relative_to(source_root).parts
    safe_parts = [sanitise_path_part(p) for p in rel_parts]
    return dest_root.joinpath(*safe_parts)


def copy_files(tracks: list[dict], source_root: Path, dest_root: Path,
               dry_run: bool = False):
    label = "DRY RUN - " if dry_run else ""
    print(f"\n{label}Copying {len(tracks)} tracks to {dest_root} ...\n")

    copied = total_bytes = errors = 0

    for i, f in enumerate(tracks, 1):
        dst = dest_path(f["path"], source_root, dest_root)
        artist_disp = f["artist"][:30]
        track_name = f["path"].stem[:40]
        size_mb = f["size"] / 1024**2

        print(f"  [{i:3d}/{len(tracks)}] {artist_disp:30s}  "
              f"{track_name:40s}  {size_mb:5.1f} MB")

        if dry_run:
            copied += 1
            total_bytes += f["size"]
            continue

        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists():
                shutil.copy2(f["path"], dst)
            copied += 1
            total_bytes += f["size"]
        except Exception as e:
            print(f"    ERROR: {e}")
            errors += 1

    print(f"\n{'=' * 70}")
    print(f"  Tracks {'previewed' if dry_run else 'copied'} : {copied}")
    print(f"  Total size    : {total_bytes / 1024**2:.1f} MB  "
          f"({total_bytes / 1024**3:.2f} GB)")
    if errors:
        print(f"  Errors        : {errors}")
    print(f"{'=' * 70}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv=None):
    args = parse_args(argv)

    source = Path(args.source).expanduser().resolve()
    dest = Path(args.dest).expanduser().resolve()

    if not source.exists():
        print(f"ERROR: source directory not found: {source}", file=sys.stderr)
        sys.exit(1)
    if not dest.exists():
        print(f"ERROR: destination directory not found: {dest}", file=sys.stderr)
        sys.exit(1)

    supported_exts = {"." + ext.strip().lower() for ext in args.formats.split(",")}
    skip_dirs = {d.strip() for d in args.skip_dirs.split(",") if d.strip()}

    if args.target_gb is not None:
        target_bytes = int(args.target_gb * 1024**3)
    else:
        free = shutil.disk_usage(dest).free
        target_bytes = int(free * 0.95)
        print(f"Auto-detected {free / 1024**3:.1f} GB free on destination")

    random.seed(args.seed)

    print(f"Source     : {source}")
    print(f"Dest       : {dest}")
    print(f"Target     : {target_bytes / 1024**2:.0f} MB")
    print(f"Formats    : {', '.join(sorted(supported_exts))}")
    print(f"Skip dirs  : {skip_dirs or '(none)'}")
    print(f"Limits     : max {args.max_per_artist}/artist, "
          f"{args.max_per_album}/album, skip >{args.max_file_mb} MB")
    print()

    files = scan_files(source, supported_exts, skip_dirs,
                       args.max_file_mb, args.min_file_kb)

    if not files:
        print("No eligible files found. Check --source and --formats.", file=sys.stderr)
        sys.exit(1)

    print()
    tracks = curate(files, target_bytes, args.max_per_artist, args.max_per_album)
    copy_files(tracks, source, dest, dry_run=args.dry_run)

    if not args.dry_run:
        print("\nDone! Your player is loaded.")


if __name__ == "__main__":
    main()

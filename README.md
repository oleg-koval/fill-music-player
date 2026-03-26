# fill-music-player

Fill a portable music player with a curated, DJ-balanced random selection from your music library.

Point it at a music folder (NAS, `~/Music`, external drive) and a destination (Walkman, iPod, USB stick). It scans for audio files, reads ID3/MP4/WMA tags, balances by artist and genre, and copies a shuffled selection that fits your player's capacity.

## Install

```bash
# Option 1: run directly with uv (no install needed)
uvx fill-music-player --help

# Option 2: install from PyPI
pip install fill-music-player

# Option 3: run the script directly
uv run fill_music_player.py --help
```

## Usage

```bash
# Always dry-run first to preview the selection
fill-music-player --source /Volumes/music --dest /Volumes/WALKMAN/MUSIC --dry-run

# Then copy for real
fill-music-player --source /Volumes/music --dest /Volumes/WALKMAN/MUSIC
```

### Common examples

```bash
# Fill a Sony Walkman from a Synology NAS
fill-music-player -s /Volumes/music -d /Volumes/WALKMAN/MUSIC

# Target exactly 2 GB, MP3 only
fill-music-player -s ~/Music -d /media/usb/MUSIC --target-gb 2 --formats mp3

# Skip radio recordings and jingles folders
fill-music-player -s /Volumes/music -d /Volumes/PLAYER \
    --skip-dirs "jingles,!recordings,!restored"

# Reproducible selection (same seed = same tracks every time)
fill-music-player -s /Volumes/music -d /Volumes/PLAYER --seed 42

# Tighter artist diversity (max 2 tracks per artist)
fill-music-player -s /Volumes/music -d /Volumes/PLAYER --max-per-artist 2
```

## How it works

1. **Scan** — walks your music library for supported audio files (MP3, M4A, WMA, AAC by default)
2. **Filter** — skips files that are too large (radio shows/mixes) or too small (jingles/corrupt)
3. **Read tags** — extracts artist/album from ID3, MP4, or WMA metadata; falls back to folder name parsing (`Genre/Artist - Album/track.mp3`)
4. **Curate** — allocates a proportional byte budget per genre directory, then picks tracks while enforcing artist and album diversity caps
5. **Shuffle** — globally randomizes the final selection so genres are interleaved
6. **Copy** — writes files to the destination preserving the `genre/artist/album/track` structure, with FAT32-safe filenames

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `-s, --source` | required | Source music root directory |
| `-d, --dest` | required | Destination directory on the player |
| `--target-gb` | 95% of free space | How many GB to fill |
| `--max-file-mb` | 20 | Skip files larger than this (filters mixes/shows) |
| `--min-file-kb` | 300 | Skip files smaller than this (filters jingles) |
| `--max-per-artist` | 4 | Max tracks from any single artist |
| `--max-per-album` | 3 | Max tracks from any single album |
| `--formats` | mp3,m4a,wma,aac | Comma-separated allowed extensions |
| `--skip-dirs` | _(none)_ | Comma-separated top-level dirs to skip |
| `--seed` | _(random)_ | Random seed for reproducible selection |
| `--dry-run` | false | Preview without copying |

## Device format cheat sheet

| Device | Recommended `--formats` |
|--------|------------------------|
| Sony Walkman (NWZ series) | `mp3,m4a,wma` |
| iPod classic/nano | `mp3,m4a,aac` |
| Generic USB player | `mp3` |
| Modern player (FiiO, etc.) | `mp3,m4a,wma,aac,ogg,flac` |

## Expected folder structure

The tool expects your source music to be organized as:

```
/Volumes/music/
  blues/
    Muddy Waters - Electric Mud/
      01 - Tom Cat.mp3
    ZZ Top/
      1983 - Eliminator/
        01 Gimme All Your Lovin.mp3
  funk/
    Fela Kuti/
      ...
  hiphop/
    Dr.Dre - The Chronic/
      ...
```

Top-level directories are treated as genre categories. Artist/album info comes from metadata tags first, folder names second.

## AI agent skill

This tool also works as a Claude Code / pi.dev skill. Copy the `SKILL.md` to your skills directory and the agent will know when and how to use it.

## License

MIT

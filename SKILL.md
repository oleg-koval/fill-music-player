---
name: fill-music-player
description: Use when a user wants to fill a portable music player (Walkman, iPod, USB drive) with a curated random selection from a music library on a NAS or local directory. Handles format filtering, artist/album diversity balancing, and size targeting.
---

# fill-music-player

Curates a DJ-balanced selection of tracks from a source music library and copies them to a portable player, respecting device capacity and supported formats.

## Quick Reference

```bash
# Dry run first (always recommend this)
fill-music-player --source /Volumes/music --dest /Volumes/WALKMAN/MUSIC --dry-run

# Copy for real
fill-music-player --source /Volumes/music --dest /Volumes/WALKMAN/MUSIC

# Or run the script directly with uv
uv run fill_music_player.py --source ~/Music --dest /Volumes/USB --dry-run
```

Run `fill-music-player --help` for all options.

## Key Parameters

| Flag | Default | Purpose |
|------|---------|---------|
| `--source` / `-s` | required | Source music root (NAS mount, ~/Music, etc.) |
| `--dest` / `-d` | required | Player destination directory |
| `--target-gb` | 95% of free space | How many GB to fill |
| `--formats` | mp3,m4a,wma,aac | Allowed extensions |
| `--max-per-artist` | 4 | Artist diversity cap |
| `--max-per-album` | 3 | Album diversity cap |
| `--skip-dirs` | (none) | Top-level dirs to skip |
| `--dry-run` | false | Preview without copying |

## Workflow

1. Always do `--dry-run` first
2. Review the per-genre breakdown
3. Adjust `--skip-dirs`, `--max-file-mb`, or `--max-per-artist` if needed
4. Run without `--dry-run` to copy

## Device Formats

| Device | Recommended `--formats` |
|--------|------------------------|
| Sony Walkman NWZ series | `mp3,m4a,wma` |
| iPod (classic/nano) | `mp3,m4a,aac` |
| Generic USB player | `mp3` |
| Any modern player | `mp3,m4a,wma,aac,ogg,flac` |

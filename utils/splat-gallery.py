#!/usr/bin/env python3
"""Add, remove, disable, enable and list flipbook scenes in the Splat Gallery example.

The gallery's scenes live in examples/assets/json/splat-gallery.json. A flipbook scene is a folder
of numbered splat frames (e.g. frame_0001.sog ... frame_0120.sog, or 001.compressed.ply ...).

    python3 utils/splat-gallery.py list
    python3 utils/splat-gallery.py add examples/assets/splats/my-clip [--name "My Clip"] [--fps 24]
    python3 utils/splat-gallery.py add https://example.com/clip --pattern "{frame:03}.ply" --start 1 --end 90
    python3 utils/splat-gallery.py remove "My Clip"          # by name or folder
    python3 utils/splat-gallery.py disable "My Clip"         # keep it in the list, but skip it
    python3 utils/splat-gallery.py enable "My Clip"

A local folder must be inside examples/ so the page can load it; it is stored relative to examples/.
The frame pattern and range are detected from the files, and missing frames are an error because
the flipbook would stall at a gap. For a remote folder, give --pattern, --start and --end.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
SCENES_JSON = EXAMPLES / "assets" / "json" / "splat-gallery.json"

FRAME_RE = re.compile(r"^(?P<prefix>.*?)(?P<num>\d+)(?P<ext>\.compressed\.ply|\.ply|\.sog|\.spz)$")

DEFAULT_PRELOAD = 10  # gsplatFlipbook's default preloadCount

SKIES = {
    "studio": {"asset": "studio", "center": "0 0.15 0", "scale": "12 12 12"},
    "rotunda": {"asset": "rotunda", "center": "0 0.1 0", "scale": "20 20 20"},
}


def load():
    return json.loads(SCENES_JSON.read_text())


def save(data):
    SCENES_JSON.write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n")


def detect_frames(folder: Path):
    """Return (filename_pattern, start, end) for the numbered frames in `folder`."""
    groups = {}
    for f in folder.iterdir():
        m = FRAME_RE.match(f.name)
        if f.is_file() and m:
            groups.setdefault((m["prefix"], m["ext"]), []).append(m["num"])
    if not groups:
        sys.exit(f"No numbered splat frames (.sog, .ply, .compressed.ply, .spz) in {folder}")

    (prefix, ext), nums = max(groups.items(), key=lambda kv: len(kv[1]))
    if len(groups) > 1:
        print(f"note: several frame series found, using {prefix}N{ext} ({len(nums)} frames)", file=sys.stderr)

    values = sorted(int(n) for n in nums)
    widths = {len(n) for n in nums}
    padded = any(n.startswith("0") for n in nums) and len(widths) == 1
    if not padded and len(widths) > 1 and any(n.startswith("0") for n in nums):
        sys.exit(f"Inconsistent zero padding in {folder}")
    frame = f"{{frame:{widths.pop():02d}}}" if padded else "{frame}"

    start, end = values[0], values[-1]
    missing = sorted(set(range(start, end + 1)) - set(values))
    if missing:
        shown = ", ".join(map(str, missing[:10])) + (" ..." if len(missing) > 10 else "")
        sys.exit(f"Missing frames in {folder}: {shown} (the flipbook would stall at a gap)")
    return f"{prefix}{frame}{ext}", start, end


def title_from(folder: str) -> str:
    stem = folder.rstrip("/").rsplit("/", 1)[-1]
    return " ".join(w.capitalize() for w in re.split(r"[-_\s]+", stem) if w)


def page_folder(folder: str) -> str:
    """A folder as the page loads it: URLs unchanged, local paths relative to examples/."""
    if re.match(r"^https?://", folder):
        return folder.rstrip("/")
    try:
        return Path(folder).resolve().relative_to(EXAMPLES).as_posix()
    except ValueError:
        return folder.rstrip("/")


def find(scenes, key):
    """Indices of flipbook scenes whose name (case-insensitive) or folder matches `key`."""
    key_folder = page_folder(key)
    return [i for i, s in enumerate(scenes) if "flipbook" in s and (
        s.get("name", "").lower() == key.lower() or s["flipbook"].get("folder", "").rstrip("/") == key_folder)]


def cmd_list(args):
    for i, s in enumerate(load()["scenes"]):
        if "flipbook" in s:
            fb = s["flipbook"]
            what = f"flipbook {fb['folder']}/{fb['filenamePattern']} frames {fb['startFrame']}-{fb['endFrame']}"
        else:
            what = f"splat asset '{s.get('asset')}'"
        state = "off" if s.get("disabled") else "on "
        print(f"{i:2d}  {state}  {s.get('name', '?'):28s} {what}")


def cmd_add(args):
    if re.match(r"^https?://", args.folder):
        if args.pattern is None or args.start is None or args.end is None:
            sys.exit("A remote folder needs --pattern, --start and --end")
        folder, pattern, start, end = args.folder.rstrip("/"), args.pattern, args.start, args.end
    else:
        path = Path(args.folder).resolve()
        if not path.is_dir():
            sys.exit(f"Not a folder: {args.folder}")
        try:
            folder = path.relative_to(EXAMPLES).as_posix()
        except ValueError:
            sys.exit(f"{path} is outside {EXAMPLES}; copy or symlink it into examples/assets/splats/ "
                     "so the page can load it")
        pattern, start, end = detect_frames(path)
        pattern = args.pattern or pattern
        start = args.start if args.start is not None else start
        end = args.end if args.end is not None else end

    data = load()
    scenes = data["scenes"]
    name = args.name or title_from(folder)
    existing = sorted(set(find(scenes, folder) + find(scenes, name)))
    if existing and not args.replace:
        sys.exit(f"'{name}' / {folder} is already in the gallery (use --replace to overwrite)")

    scene = {"name": name}
    for key in ("position", "rotation", "scale"):
        if getattr(args, key):
            scene[key] = getattr(args, key)
    scene["castShadows"] = args.cast_shadows
    if args.environment != "none":
        scene["environment"] = args.environment
    if args.sky != "none":
        scene["sky"] = SKIES[args.sky]
    scene["flipbook"] = {
        "fps": int(args.fps) if args.fps.is_integer() else args.fps,
        "folder": folder,
        "filenamePattern": pattern,
        "startFrame": start,
        "endFrame": end,
        "playMode": args.play_mode,
        "playing": True,
    }
    frames = end - start + 1
    if frames <= DEFAULT_PRELOAD:
        # gsplatFlipbook stalls when its preload buffer wraps around to the frame on screen
        scene["flipbook"]["preloadCount"] = max(1, frames - 1)

    if existing:
        scenes[existing[0]] = scene
        for i in reversed(existing[1:]):
            del scenes[i]
        print(f"replaced '{name}'")
    else:
        scenes.append(scene)
        print(f"added '{name}': {folder}/{pattern}, frames {start}-{end}")
    save(data)


def matches(scenes, args):
    hits = find(scenes, args.key)
    if not hits:
        sys.exit(f"No flipbook scene named or in folder '{args.key}' (see `list`)")
    if len(hits) > 1 and not args.all:
        sys.exit(f"'{args.key}' matches {len(hits)} scenes; use --all to apply to all of them")
    return hits


def cmd_enable(args):
    data = load()
    for i in matches(data["scenes"], args):
        scene = data["scenes"][i]
        if args.enable:
            scene.pop("disabled", None)
        else:
            scene["disabled"] = True
        print(f"{'enabled' if args.enable else 'disabled'} '{scene.get('name')}'")
    save(data)


def cmd_remove(args):
    data = load()
    scenes = data["scenes"]
    for i in sorted(matches(scenes, args), reverse=True):
        print(f"removed '{scenes[i].get('name')}'")
        del scenes[i]
    save(data)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="show the gallery's scenes").set_defaults(func=cmd_list)

    add = sub.add_parser("add", help="add a folder of flipbook frames")
    add.add_argument("folder", help="folder inside examples/, or an http(s) URL")
    add.add_argument("--name", help="scene name (default: from the folder name)")
    add.add_argument("--fps", type=float, default=30)
    add.add_argument("--play-mode", choices=["loop", "bounce", "once"], default="loop")
    add.add_argument("--pattern", help="frame filename pattern, e.g. 'frame_{frame:04}.sog' (detected for local folders)")
    add.add_argument("--start", type=int, help="first frame number (detected for local folders)")
    add.add_argument("--end", type=int, help="last frame number (detected for local folders)")
    add.add_argument("--position", help="'x y z'")
    add.add_argument("--rotation", default="0 -90 180",
                     help="'x y z' Euler degrees (default '0 -90 180', as for the basketball clip)")
    add.add_argument("--scale", help="'x y z'")
    add.add_argument("--environment", choices=["studio", "none"], default="studio")
    add.add_argument("--sky", choices=[*SKIES, "none"], default="studio")
    add.add_argument("--no-cast-shadows", dest="cast_shadows", action="store_false")
    add.add_argument("--replace", action="store_true", help="overwrite a scene with the same name or folder")
    add.set_defaults(func=cmd_add)

    rm = sub.add_parser("remove", help="remove a flipbook scene by name or folder")
    rm.add_argument("key", help="scene name or folder")
    rm.add_argument("--all", action="store_true", help="remove every match")
    rm.set_defaults(func=cmd_remove)

    for command, enable in (("disable", False), ("enable", True)):
        sp = sub.add_parser(command, help=f"{command} a flipbook scene by name or folder "
                                          "(disabled scenes stay in the list but are skipped)")
        sp.add_argument("key", help="scene name or folder")
        sp.add_argument("--all", action="store_true", help="apply to every match")
        sp.set_defaults(func=cmd_enable, enable=enable)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

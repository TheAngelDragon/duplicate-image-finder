from pathlib import Path
from PIL import Image
import imagehash
import hashlib
from pillow_heif import register_heif_opener
from datetime import datetime

register_heif_opener()

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".bmp", ".gif", ".tiff", ".tif"}


def get_image_files(directory: str | Path) -> list[Path]:
    directory = Path(directory)
    return [
        p for p in directory.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    ]


def get_file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def format_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def format_mtime(path: Path) -> str:
    try:
        mtime = path.stat().st_mtime
        return datetime.fromtimestamp(mtime).strftime("%d-%m-%Y %H:%M")
    except OSError:
        return "Unknown"


def similarity_percent(hash1, hash2, bits: int = 64) -> float:
    if hash1 is None or hash2 is None:
        return 0.0
    distance = hash1 - hash2
    return round(100 * (1 - distance / bits), 1)


def scan_exact(files: list[Path], progress_callback=None, cancel_check=None):
    hash_groups = {}
    total = len(files)

    for i, path in enumerate(files):
        if cancel_check and cancel_check():
            return []

        try:
            h = hashlib.md5()
            with path.open("rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            digest = h.hexdigest()
            hash_groups.setdefault(digest, []).append(path)
        except Exception:
            pass

        if progress_callback:
            progress_callback(i + 1, total)

    groups = []
    for paths in hash_groups.values():
        if len(paths) > 1:
            group = []
            for p in paths:
                group.append({
                    "path": p,
                    "size": get_file_size(p),
                    "size_str": format_size(get_file_size(p)),
                    "modified": format_mtime(p),
                    "similarity": 100.0,
                    "hash": None
                })
            groups.append(group)
    return groups


def scan_similar(files: list[Path], threshold: int = 12, progress_callback=None, cancel_check=None):
    groups = []
    total = len(files)

    for i, path in enumerate(files):
        if cancel_check and cancel_check():
            return []

        try:
            with Image.open(path) as img:
                img = img.convert("RGB")
                h = imagehash.phash(img)
        except Exception:
            h = None

        if h is not None:
            matched = False
            for group in groups:
                if h - group["rep_hash"] <= threshold:
                    sim = similarity_percent(h, group["rep_hash"])
                    group["files"].append({
                        "path": path,
                        "size": get_file_size(path),
                        "size_str": format_size(get_file_size(path)),
                        "modified": format_mtime(path),
                        "similarity": sim,
                        "hash": h
                    })
                    matched = True
                    break

            if not matched:
                groups.append({
                    "rep_hash": h,
                    "files": [{
                        "path": path,
                        "size": get_file_size(path),
                        "size_str": format_size(get_file_size(path)),
                        "modified": format_mtime(path),
                        "similarity": 100.0,
                        "hash": h
                    }]
                })

        if progress_callback:
            progress_callback(i + 1, total)

    return [g["files"] for g in groups if len(g["files"]) > 1]


def delete_file(path: Path) -> tuple[bool, str]:
    try:
        path.unlink()
        return True, "Deleted successfully"
    except Exception as e:
        return False, str(e)


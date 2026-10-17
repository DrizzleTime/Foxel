"""ZIP validation shared by storage extraction and its staging worker."""

import stat
import zipfile


MAX_ARCHIVE_ENTRIES = 100_000
MAX_EXTRACTED_BYTES = 10 * 1024**3


def zip_entries(archive: zipfile.ZipFile) -> list[dict]:
    infos = archive.infolist()
    if len(infos) > MAX_ARCHIVE_ENTRIES:
        raise ValueError("Archive contains too many entries")
    entries = {}
    total = 0
    for info in infos:
        name = info.orig_filename
        parts = name.rstrip("/").split("/")
        if (not name or "\\" in name or "\x00" in name or ":" in name
                or any(part in ("", ".", "..") or part != part.strip() for part in parts)):
            raise ValueError("Archive contains an unsafe path")
        mode = info.external_attr >> 16
        kind = stat.S_IFMT(mode)
        is_dir = info.is_dir()
        if kind not in (0, stat.S_IFDIR if is_dir else stat.S_IFREG):
            raise ValueError("Archive contains symbolic links or special files")
        if info.flag_bits & 1:
            raise ValueError("Encrypted ZIP archives are not supported")
        total += info.file_size
        if total > MAX_EXTRACTED_BYTES:
            raise ValueError("Archive exceeds the 10 GiB extraction limit")
        path = "/".join(parts)
        if path in entries:
            raise ValueError("Archive contains duplicate paths")
        entries[path] = {"name": path, "is_dir": is_dir, "size": info.file_size}

    # Include implicit parent directories so permissions are checked for them too.
    for name in list(entries):
        parts = name.split("/")
        for end in range(1, len(parts)):
            parent = "/".join(parts[:end])
            if parent in entries and not entries[parent]["is_dir"]:
                raise ValueError("Archive contains conflicting file and directory paths")
            entries.setdefault(parent, {"name": parent, "is_dir": True, "size": 0})
            if len(entries) > MAX_ARCHIVE_ENTRIES:
                raise ValueError("Archive contains too many entries")
    return sorted(entries.values(), key=lambda entry: (entry["name"].count("/"), entry["name"]))

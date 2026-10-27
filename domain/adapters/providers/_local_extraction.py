"""Exclusive local extraction writes and conservative cleanup of their receipts."""

import asyncio
from contextlib import contextmanager, suppress
import errno
import os
from pathlib import Path
import secrets
import shutil
import stat


def _identity(info):
    return info.st_dev, info.st_ino


def _version(info):
    return (*_identity(info), info.st_size, info.st_mtime_ns, info.st_ctime_ns)


@contextmanager
def _parent(root, rel):
    parts = Path(rel).parts
    if not parts or Path(rel).is_absolute() or any(part in {".", ".."} for part in parts):
        raise ValueError("Invalid extraction path")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(Path(root).resolve(), flags)
    try:
        for part in parts[:-1]:
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor, parts[-1]
    finally:
        os.close(descriptor)


async def _finish_io(operation):
    # Cancellation must not leave a writer running while its source is removed.
    worker = asyncio.create_task(asyncio.to_thread(operation))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        with suppress(Exception):
            await worker
        raise


class LocalExtractionMixin:
    supports_safe_extraction_cleanup = os.name == "posix"

    async def create_extraction_directory(self, root, rel, receipt):
        def create():
            with _parent(root, rel) as (parent, name):
                os.mkdir(name, dir_fd=parent)
                info = os.stat(name, dir_fd=parent, follow_symlinks=False)
                receipt.update(parent=_identity(os.fstat(parent)), identity=_identity(info), is_dir=True)

        await _finish_io(create)

    async def write_extraction_file(self, root, rel, incoming, receipt):
        def write():
            with _parent(root, rel) as (parent, name):
                descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                     0o666, dir_fd=parent)
                with os.fdopen(descriptor, "wb") as output:
                    receipt.update(parent=_identity(os.fstat(parent)), is_dir=False)
                    try:
                        shutil.copyfileobj(incoming, output)
                    finally:
                        try:
                            output.flush()
                        finally:
                            # fstat binds the receipt to our open file, even if the name
                            # was replaced or the copy left only a partial file behind.
                            receipt["version"] = _version(os.fstat(output.fileno()))

        await _finish_io(write)

    async def cleanup_extraction_path(self, root, rel, receipt):
        def remove():
            try:
                with _parent(root, rel) as (parent, name):
                    if _identity(os.fstat(parent)) != receipt["parent"]:
                        return "Path changed after it was created"
                    info = os.stat(name, dir_fd=parent, follow_symlinks=False)
                    if receipt["is_dir"]:
                        if not stat.S_ISDIR(info.st_mode) or _identity(info) != receipt["identity"]:
                            return "Path changed after it was created"
                        try:
                            # The filesystem refuses a nonempty directory atomically.
                            os.rmdir(name, dir_fd=parent)
                        except OSError as exc:
                            if exc.errno in {errno.ENOTEMPTY, errno.EEXIST}:
                                return "Directory contains files not created by this task"
                            raise
                        return None
                    if not stat.S_ISREG(info.st_mode) or _version(info) != receipt["version"] or info.st_nlink != 1:
                        return "Path changed after it was created"
                    return self._quarantine_extraction_file(parent, name, rel, receipt)
            except FileNotFoundError:
                return ""

        return await _finish_io(remove)

    @staticmethod
    def _quarantine_extraction_file(parent, name, rel, receipt):
        # Capture the directory entry before inspecting it again. A check followed by
        # unlink(name) could otherwise delete a replacement installed between the calls.
        quarantine = ".foxel-cleanup-" + secrets.token_hex(16)
        os.mkdir(quarantine, mode=0o700, dir_fd=parent)
        directory = os.open(quarantine, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            os.rename(name, "entry", src_dir_fd=parent, dst_dir_fd=directory)
            receipt["recovery_rel"] = str(Path(rel).parent / quarantine / "entry")
            info = os.stat("entry", dir_fd=directory, follow_symlinks=False)
            # rename may change ctime; inode, size and mtime must still match.
            if (not stat.S_ISREG(info.st_mode) or _version(info)[:-1] != receipt["version"][:-1]
                    or info.st_nlink != 1):
                try:
                    # link creates the original name exclusively: never overwrite a
                    # newer arrival while restoring an object we do not own.
                    os.link("entry", name, src_dir_fd=directory, dst_dir_fd=parent, follow_symlinks=False)
                except OSError:
                    return "Changed path preserved at the recovery location"
                os.unlink("entry", dir_fd=directory)
                receipt.pop("recovery_rel", None)
                return "Path changed after it was created"
            os.unlink("entry", dir_fd=directory)
            receipt.pop("recovery_rel", None)
            return None
        finally:
            os.close(directory)
            # If restoration was impossible, retain the recovery directory and its data.
            with suppress(OSError):
                os.rmdir(quarantine, dir_fd=parent)

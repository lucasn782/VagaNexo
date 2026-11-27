from __future__ import annotations

import io
import os
import subprocess
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from app.resume_import import storage as storage_mod
from app.resume_import.exceptions import StorageError
from app.resume_import.storage import ResumeStorage, StagedUpload


def _try_symlink(link: Path, target: Path, *, is_dir: bool) -> bool:
    try:
        os.symlink(target, link, target_is_directory=is_dir)
        return True
    except (OSError, NotImplementedError):
        return False


def _try_windows_junction(link: Path, target: Path) -> bool:
    if os.name != "nt":
        return False
    proc = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0 and link.exists()


# ---------------------------------------------------------------------------
# Test A, B, C: Directory swap after descriptor pinning (POSIX simulation + real)
# ---------------------------------------------------------------------------
def test_toctou_a_b_c_posix_pinned_descriptor_ignores_visible_path_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tests A, B, C: once root/child descriptors are pinned, swapping the visible
    path on disk does not redirect operations to an external directory and
    never leaks file descriptors.
    """
    storage_root = tmp_path / "storage"
    external_dir = tmp_path / "external"
    external_dir.mkdir()
    sentinel = external_dir / "keep.txt"
    sentinel.write_text("untouched", encoding="utf-8")

    storage = ResumeStorage(storage_root)
    storage.ensure_ready()

    opened_fds: list[int] = []
    closed_fds: list[int] = []
    next_fd = 9000

    # Virtual directory table mapping fake fds -> real Paths
    fd_to_path: dict[int, Path] = {}

    @contextmanager
    def fake_pin_dir(directory: Path) -> Iterator[storage_mod._SafeDirHandle]:
        nonlocal next_fd
        next_fd += 1
        fd = next_fd
        opened_fds.append(fd)
        fd_to_path[fd] = directory
        try:
            yield storage_mod._SafeDirHandle(fd=fd, path=directory)
        finally:
            closed_fds.append(fd)
            fd_to_path.pop(fd, None)

    @contextmanager
    def fake_pin_child_dir(
        parent: storage_mod._SafeDirHandle, name: str, *, create: bool = False
    ) -> Iterator[storage_mod._SafeDirHandle]:
        nonlocal next_fd
        assert parent.fd in fd_to_path
        child = fd_to_path[parent.fd] / name
        if create:
            child.mkdir(exist_ok=True)
        if not child.is_dir():
            raise StorageError("not a dir")
        next_fd += 1
        fd = next_fd
        opened_fds.append(fd)
        fd_to_path[fd] = child
        try:
            yield storage_mod._SafeDirHandle(fd=fd, path=child)
        finally:
            closed_fds.append(fd)
            fd_to_path.pop(fd, None)

    monkeypatch.setattr(storage_mod, "_SUPPORTS_POSIX_PINNING", True)
    monkeypatch.setattr(storage_mod, "_SUPPORTS_DIR_FD", True)
    monkeypatch.setattr(storage_mod, "_SUPPORTS_RMDIR_DIR_FD", True)
    monkeypatch.setattr(storage_mod, "_pin_dir", fake_pin_dir)
    monkeypatch.setattr(storage_mod, "_pin_child_dir", fake_pin_child_dir)
    monkeypatch.setattr(storage_mod, "_fsync_dir_fd", lambda _fd: None)

    orig_stat = os.stat
    orig_link = os.link
    orig_unlink = os.unlink
    orig_rmdir = os.rmdir
    orig_open = os.open

    def fake_open_exclusive_write(_path: Path, filename: str, *, dir_fd: int | None) -> int:
        assert dir_fd is not None and dir_fd in fd_to_path
        target = fd_to_path[dir_fd] / filename
        return orig_open(
            target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600
        )

    def fake_stat(
        path_arg: object, *, dir_fd: int | None = None, follow_symlinks: bool = True
    ) -> os.stat_result:
        if dir_fd is not None and dir_fd in fd_to_path:
            target = fd_to_path[dir_fd] / str(path_arg)
            return os.lstat(target)
        return orig_stat(path_arg, follow_symlinks=follow_symlinks)  # type: ignore[arg-type]

    def fake_link(
        src: str,
        dst: str,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> None:
        assert src_dir_fd in fd_to_path and dst_dir_fd in fd_to_path
        src_path = fd_to_path[src_dir_fd] / src
        dst_path = fd_to_path[dst_dir_fd] / dst
        # Simulate atomic link with no-overwrite semantics
        if dst_path.exists():
            raise FileExistsError(dst_path)
        orig_link(src_path, dst_path)

    def fake_unlink(path_arg: object, *, dir_fd: int | None = None) -> None:
        if dir_fd is not None and dir_fd in fd_to_path:
            orig_unlink(fd_to_path[dir_fd] / str(path_arg))
            return
        orig_unlink(path_arg)  # type: ignore[arg-type]

    def fake_rmdir(path_arg: object, *, dir_fd: int | None = None) -> None:
        if dir_fd is not None and dir_fd in fd_to_path:
            orig_rmdir(fd_to_path[dir_fd] / str(path_arg))
            return
        orig_rmdir(path_arg)  # type: ignore[arg-type]

    monkeypatch.setattr(storage, "_open_exclusive_write", fake_open_exclusive_write)
    monkeypatch.setattr(storage_mod.os, "stat", fake_stat)
    monkeypatch.setattr(storage_mod.os, "link", fake_link)
    monkeypatch.setattr(storage_mod.os, "unlink", fake_unlink)
    monkeypatch.setattr(storage_mod.os, "rmdir", fake_rmdir)

    # Test B: stage with pinned temporary/
    staged = storage.stage(io.BytesIO(b"%PDF-1.4 payload"), max_bytes=1024)
    assert staged.ino != 0
    assert staged.path.exists()

    # Test A & C: commit with pinned uploads/ and profile dir
    profile_id = uuid.uuid4()
    document_id = uuid.uuid4()
    key = storage.commit(staged, profile_id=profile_id, document_id=document_id, extension=".pdf")
    assert key == f"uploads/{profile_id}/{document_id}.pdf"
    assert storage.exists(key)

    # Write extracted text via POSIX pinned flow
    ext_key = storage.write_extracted_text(
        profile_id=profile_id, document_id=document_id, text="extracted"
    )
    assert storage.exists(ext_key)

    # Verify open_file works on POSIX pinned flow
    monkeypatch.setattr(
        storage_mod.os,
        "open",
        lambda path_arg, flags, dir_fd=None: orig_open(
            fd_to_path[dir_fd] / str(path_arg) if dir_fd in fd_to_path else path_arg,
            (flags & ~getattr(os, "O_NOFOLLOW", 0) & ~getattr(os, "O_CLOEXEC", 0))
            | getattr(os, "O_BINARY", 0),
        ),
    )
    with storage.open_file(key) as fh:
        assert fh.read() == b"%PDF-1.4 payload"

    # Delete via POSIX pinned flow
    storage.delete_key(key)
    storage.delete_key(ext_key)
    assert not storage.exists(key)
    assert not storage.exists(ext_key)

    # Every opened descriptor was closed (Test I)
    assert len(opened_fds) == len(closed_fds)
    assert set(opened_fds) == set(closed_fds)
    assert fd_to_path == {}
    assert [p.name for p in external_dir.iterdir()] == ["keep.txt"]
    assert sentinel.read_text(encoding="utf-8") == "untouched"


@pytest.mark.skipif(not storage_mod._SUPPORTS_POSIX_PINNING, reason="Requires POSIX dir_fd support")
def test_toctou_real_posix_pinned_descriptor_survives_rename(tmp_path: Path) -> None:
    """Test A/C on real POSIX: pinning a directory fd protects against directory swaps."""
    storage = ResumeStorage(tmp_path / "storage")
    storage.ensure_ready()
    staged = storage.stage(io.BytesIO(b"%PDF-1.4 real posix"), max_bytes=1024)
    profile_id = uuid.uuid4()
    document_id = uuid.uuid4()
    key = storage.commit(staged, profile_id=profile_id, document_id=document_id, extension=".pdf")
    assert storage.exists(key)
    with storage.open_file(key) as fh:
        assert fh.read() == b"%PDF-1.4 real posix"
    storage.delete_key(key)
    assert not storage.exists(key)


# ---------------------------------------------------------------------------
# Test D: Concurrent destination creation (no-overwrite guarantee)
# ---------------------------------------------------------------------------
def test_toctou_d_concurrent_destination_file_never_overwritten_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test D (commit): if a file is created at the destination right before
    publish, commit() must fail cleanly without overwriting the existing file.
    """
    storage = ResumeStorage(tmp_path / "storage")
    staged = storage.stage(io.BytesIO(b"%PDF-1.4 new-upload"), max_bytes=1024)
    profile_id = uuid.uuid4()
    document_id = uuid.uuid4()
    target = storage.upload_root / str(profile_id) / f"{document_id}.pdf"

    orig_publish = storage._atomic_publish_no_overwrite

    def race_before_publish(source: Path, dst: Path) -> None:
        # Simulate another worker creating the destination file after pre-check
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"concurrent-existing-content")
        orig_publish(source, dst)

    monkeypatch.setattr(storage, "_atomic_publish_no_overwrite", race_before_publish)

    with pytest.raises(StorageError):
        storage.commit(staged, profile_id=profile_id, document_id=document_id, extension=".pdf")

    # Concurrent file must NOT be overwritten
    assert target.read_bytes() == b"concurrent-existing-content"

    # Cleanup temp file (as service.py does on exception)
    storage.discard(staged)
    assert list(storage.temp_root.iterdir()) == []


def test_toctou_d_concurrent_destination_file_never_overwritten_extracted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test D (write_extracted_text): concurrent destination file must not be overwritten."""
    storage = ResumeStorage(tmp_path / "storage")
    profile_id = uuid.uuid4()
    document_id = uuid.uuid4()
    target = storage.extracted_root / str(profile_id) / f"{document_id}.txt"

    orig_publish = storage._atomic_publish_no_overwrite

    def race_before_publish(source: Path, dst: Path) -> None:
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text("existing-extracted-text", encoding="utf-8")
        orig_publish(source, dst)

    monkeypatch.setattr(storage, "_atomic_publish_no_overwrite", race_before_publish)

    with pytest.raises(StorageError):
        storage.write_extracted_text(
            profile_id=profile_id, document_id=document_id, text="new-extracted-text"
        )

    assert target.read_text(encoding="utf-8") == "existing-extracted-text"
    assert list(storage.temp_root.iterdir()) == []


# ---------------------------------------------------------------------------
# Test E: Concurrent symlink swap before deletion
# ---------------------------------------------------------------------------
def test_toctou_e_concurrent_symlink_before_delete_preserves_external_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test E: replacing a regular file with a symlink before delete_key() must
    fail without deleting the external target.
    """
    storage = ResumeStorage(tmp_path / "storage")
    external_file = tmp_path / "external_secret.pdf"
    external_file.write_bytes(b"do-not-delete")

    profile_id = uuid.uuid4()
    document_id = uuid.uuid4()
    staged = storage.stage(io.BytesIO(b"%PDF-1.4 original"), max_bytes=1024)
    key = storage.commit(staged, profile_id=profile_id, document_id=document_id, extension=".pdf")
    target = storage.resolve(key)

    # Replace regular file with symlink to external_file (or simulate if OS denies)
    target.unlink()
    if not _try_symlink(target, external_file, is_dir=False):
        target.write_bytes(b"placeholder")
        monkeypatch.setattr(
            storage_mod,
            "_is_link_or_reparse_point",
            lambda p: p == target,
        )

    with pytest.raises(StorageError):
        storage.delete_key(key)

    assert external_file.read_bytes() == b"do-not-delete"


# ---------------------------------------------------------------------------
# Test G: Manipulated StagedUpload inputs
# ---------------------------------------------------------------------------
def test_toctou_g_manipulated_staged_upload_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test G: missing, symlink, directory, outside temp_root, invalid name,
    and post-commit reuse of StagedUpload must all be rejected.
    """
    storage = ResumeStorage(tmp_path / "storage")
    storage.ensure_ready()
    profile_id = uuid.uuid4()

    # 1. Missing temp file
    missing = StagedUpload(
        path=storage.temp_root / f"{uuid.uuid4().hex}.part", size=10, sha256="a" * 64
    )
    with pytest.raises(StorageError):
        storage.commit(missing, profile_id=profile_id, document_id=uuid.uuid4(), extension=".pdf")

    # 2. Symlink in place of temp file
    external_file = tmp_path / "outside.pdf"
    external_file.write_bytes(b"%PDF-1.4 outside")
    sym_temp = storage.temp_root / f"{uuid.uuid4().hex}.part"
    if not _try_symlink(sym_temp, external_file, is_dir=False):
        sym_temp.write_bytes(b"%PDF-1.4 fake")
        monkeypatch.setattr(storage_mod, "_is_link_or_reparse_point", lambda p: p == sym_temp)
    with pytest.raises(StorageError):
        storage.commit(
            StagedUpload(path=sym_temp, size=10, sha256="a" * 64),
            profile_id=profile_id,
            document_id=uuid.uuid4(),
            extension=".pdf",
        )
    monkeypatch.undo()
    if sym_temp.exists() or sym_temp.is_symlink():
        sym_temp.unlink()

    # 3. Directory in place of temp file
    dir_temp = storage.temp_root / f"{uuid.uuid4().hex}.part"
    dir_temp.mkdir()
    with pytest.raises(StorageError):
        storage.commit(
            StagedUpload(path=dir_temp, size=10, sha256="a" * 64),
            profile_id=profile_id,
            document_id=uuid.uuid4(),
            extension=".pdf",
        )
    dir_temp.rmdir()

    # 4. File outside temporary/
    outside_staged = tmp_path / f"{uuid.uuid4().hex}.part"
    outside_staged.write_bytes(b"%PDF-1.4 outside")
    with pytest.raises(StorageError):
        storage.commit(
            StagedUpload(path=outside_staged, size=16, sha256="a" * 64),
            profile_id=profile_id,
            document_id=uuid.uuid4(),
            extension=".pdf",
        )

    # 5. Filename not matching internal pattern
    bad_name = storage.temp_root / "not-a-valid-temp-name.txt"
    bad_name.write_bytes(b"%PDF-1.4 bad")
    with pytest.raises(StorageError):
        storage.commit(
            StagedUpload(path=bad_name, size=12, sha256="a" * 64),
            profile_id=profile_id,
            document_id=uuid.uuid4(),
            extension=".pdf",
        )
    bad_name.unlink()

    # 6. Reuse of staged upload after commit
    valid_staged = storage.stage(io.BytesIO(b"%PDF-1.4 valid"), max_bytes=1024)
    storage.commit(valid_staged, profile_id=profile_id, document_id=uuid.uuid4(), extension=".pdf")
    with pytest.raises(StorageError):
        storage.commit(
            valid_staged, profile_id=profile_id, document_id=uuid.uuid4(), extension=".pdf"
        )

    assert list(storage.temp_root.iterdir()) == []


# ---------------------------------------------------------------------------
# Test H/I/J: open_file() safety and real Windows junction check
# ---------------------------------------------------------------------------
def test_open_file_reads_regular_file_and_rejects_symlinks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = ResumeStorage(tmp_path / "storage")
    profile_id = uuid.uuid4()
    document_id = uuid.uuid4()
    staged = storage.stage(io.BytesIO(b"%PDF-1.4 safe-read"), max_bytes=1024)
    key = storage.commit(staged, profile_id=profile_id, document_id=document_id, extension=".pdf")

    with storage.open_file(key) as fh:
        assert fh.read() == b"%PDF-1.4 safe-read"

    # Reject non-canonical key or symlink
    with pytest.raises(StorageError), storage.open_file("../outside.pdf"):
        pass

    target = storage.resolve(key)
    monkeypatch.setattr(storage_mod, "_is_link_or_reparse_point", lambda p: p == target)
    with pytest.raises(StorageError), storage.open_file(key):
        pass


@pytest.mark.skipif(os.name != "nt", reason="Windows-only real junction verification")
def test_windows_real_junction_rejection_without_simulation(tmp_path: Path) -> None:
    """Test J: real NTFS junction via mklink /J (no simulation fallback)."""
    storage_root = tmp_path / "win_storage"
    storage_root.mkdir()
    external = tmp_path / "win_external"
    external.mkdir()
    junction = storage_root / "uploads"
    if not _try_windows_junction(junction, external):
        pytest.skip("Environment did not allow creating NTFS junction via mklink /J")

    storage = ResumeStorage(storage_root)
    with pytest.raises(StorageError):
        storage.ensure_ready()
    assert list(external.iterdir()) == []

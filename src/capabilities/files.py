"""File system manager with permission-based access."""
import asyncio
import hashlib
import json
import mimetypes
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

import aiofiles
from loguru import logger
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class PermissionType(Enum):
    """File permission types."""
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"


class FileAction(Enum):
    """File actions."""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    CREATE = "create"
    MOVE = "move"


@dataclass
class FilePermission:
    """File permission entry."""
    path: Path
    permission_type: PermissionType
    granted_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    recursive: bool = False
    granted_by: str = "user"

    def is_valid(self) -> bool:
        """Check if permission is still valid."""
        if self.expires_at and datetime.now() > self.expires_at:
            return False
        return True

    def covers(self, target_path: Path) -> bool:
        """Check if this permission covers the target path."""
        target = Path(target_path).resolve()
        permission_path = self.path.resolve()

        if self.recursive:
            return str(target).startswith(str(permission_path))
        else:
            return target == permission_path or target.parent == permission_path


@dataclass
class FileInfo:
    """File information."""
    path: Path
    name: str
    size: int
    modified_time: datetime
    created_time: datetime
    is_directory: bool
    mime_type: str
    checksum: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class FileSystemManager:
    """File system manager with permission-based access control."""

    def __init__(self):
        """Initialize file system manager."""
        self._permissions: List[FilePermission] = []
        self._observers: Dict[str, Observer] = {}
        self._watch_handlers: Dict[str, FileSystemEventHandler] = {}
        self._watch_callbacks: Dict[str, callable] = {}
        self._lock = asyncio.Lock()

        # Default allowed directories
        self._home_dir = Path.home()
        self._default_allowed = [
            self._home_dir / "Documents",
            self._home_dir / "Downloads",
            self._home_dir / "Desktop",
        ]

    def _normalize_path(self, path: Union[str, Path]) -> Path:
        """Normalize and resolve path."""
        path = Path(path).expanduser().resolve()
        return path

    async def request_permission(
        self,
        path: Union[str, Path],
        permission_type: PermissionType,
        recursive: bool = False,
        expires_in: Optional[timedelta] = None,
    ) -> bool:
        """Request permission for a path.

        Args:
            path: File or directory path
            permission_type: Type of permission
            recursive: Apply recursively for directories
            expires_in: Optional expiration time

        Returns:
            True if granted
        """
        path = self._normalize_path(path)

        # Check if path exists
        if not path.exists():
            logger.warning(f"Path does not exist: {path}")
            return False

        # Calculate expiration
        expires_at = None
        if expires_in:
            expires_at = datetime.now() + expires_in

        # Create permission
        permission = FilePermission(
            path=path,
            permission_type=permission_type,
            expires_at=expires_at,
            recursive=recursive,
        )

        async with self._lock:
            # Remove existing permissions for same path
            self._permissions = [
                p for p in self._permissions
                if not (p.path == path and p.permission_type == permission_type)
            ]
            self._permissions.append(permission)

        logger.info(f"Granted {permission_type.value} permission for {path}")
        return True

    async def revoke_permission(self, path: Union[str, Path], permission_type: Optional[PermissionType] = None):
        """Revoke permission for a path.

        Args:
            path: File or directory path
            permission_type: Optional specific permission type to revoke
        """
        path = self._normalize_path(path)

        async with self._lock:
            if permission_type:
                self._permissions = [
                    p for p in self._permissions
                    if not (p.path == path and p.permission_type == permission_type)
                ]
            else:
                self._permissions = [
                    p for p in self._permissions
                    if p.path != path
                ]

        logger.info(f"Revoked permission for {path}")

    def check_permission(
        self,
        path: Union[str, Path],
        action: FileAction,
    ) -> bool:
        """Check if action is permitted on path.

        Args:
            path: File or directory path
            action: Action to check

        Returns:
            True if permitted
        """
        path = self._normalize_path(path)

        # Map action to permission type
        permission_map = {
            FileAction.READ: PermissionType.READ,
            FileAction.WRITE: PermissionType.WRITE,
            FileAction.DELETE: PermissionType.WRITE,
            FileAction.CREATE: PermissionType.WRITE,
            FileAction.MOVE: PermissionType.WRITE,
        }

        required_permission = permission_map.get(action)
        if not required_permission:
            return False

        # Check permissions
        for perm in self._permissions:
            if (perm.permission_type == required_permission or
                perm.permission_type == PermissionType.EXECUTE):
                if perm.covers(path) and perm.is_valid():
                    return True

        # Check default allowed directories
        for allowed in self._default_allowed:
            if str(path).startswith(str(allowed)):
                return True

        return False

    async def get_allowed_paths(self) -> List[Path]:
        """Get list of allowed paths.

        Returns:
            List of paths with permissions
        """
        async with self._lock:
            paths = [p.path for p in self._permissions if p.is_valid()]
        return paths

    async def read_file(
        self,
        path: Union[str, Path],
        binary: bool = False,
        encoding: str = "utf-8",
    ) -> Union[str, bytes]:
        """Read file contents.

        Args:
            path: File path
            binary: Read as binary
            encoding: Text encoding

        Returns:
            File contents
        """
        path = self._normalize_path(path)

        if not self.check_permission(path, FileAction.READ):
            raise PermissionError(f"No read permission for {path}")

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if binary:
            async with aiofiles.open(path, "rb") as f:
                return await f.read()
        else:
            async with aiofiles.open(path, "r", encoding=encoding) as f:
                return await f.read()

    async def write_file(
        self,
        path: Union[str, Path],
        content: Union[str, bytes],
        encoding: str = "utf-8",
    ):
        """Write file contents.

        Args:
            path: File path
            content: Content to write
            encoding: Text encoding
        """
        path = self._normalize_path(path)

        if not self.check_permission(path, FileAction.WRITE):
            raise PermissionError(f"No write permission for {path}")

        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(content, bytes):
            async with aiofiles.open(path, "wb") as f:
                await f.write(content)
        else:
            async with aiofiles.open(path, "w", encoding=encoding) as f:
                await f.write(content)

        logger.info(f"Wrote file: {path}")

    async def append_file(
        self,
        path: Union[str, Path],
        content: str,
        encoding: str = "utf-8",
    ):
        """Append to file.

        Args:
            path: File path
            content: Content to append
            encoding: Text encoding
        """
        path = self._normalize_path(path)

        if not self.check_permission(path, FileAction.WRITE):
            raise PermissionError(f"No write permission for {path}")

        async with aiofiles.open(path, "a", encoding=encoding) as f:
            await f.write(content)

    async def delete_file(self, path: Union[str, Path]):
        """Delete file or directory.

        Args:
            path: Path to delete
        """
        path = self._normalize_path(path)

        if not self.check_permission(path, FileAction.DELETE):
            raise PermissionError(f"No delete permission for {path}")

        if path.is_dir():
            import shutil
            shutil.rmtree(path)
        else:
            path.unlink()

        logger.info(f"Deleted: {path}")

    async def create_directory(self, path: Union[str, Path], parents: bool = True):
        """Create directory.

        Args:
            path: Directory path
            parents: Create parent directories
        """
        path = self._normalize_path(path)

        if not self.check_permission(path.parent, FileAction.CREATE):
            raise PermissionError(f"No create permission for {path.parent}")

        path.mkdir(parents=parents, exist_ok=True)
        logger.info(f"Created directory: {path}")

    async def list_directory(
        self,
        path: Union[str, Path],
        recursive: bool = False,
        include_hidden: bool = False,
    ) -> List[FileInfo]:
        """List directory contents.

        Args:
            path: Directory path
            recursive: List recursively
            include_hidden: Include hidden files

        Returns:
            List of file information
        """
        path = self._normalize_path(path)

        if not self.check_permission(path, FileAction.READ):
            raise PermissionError(f"No read permission for {path}")

        if not path.is_dir():
            raise NotADirectoryError(f"Not a directory: {path}")

        files = []

        if recursive:
            for item in path.rglob("*"):
                if not include_hidden and item.name.startswith("."):
                    continue
                files.append(await self._get_file_info(item))
        else:
            for item in path.iterdir():
                if not include_hidden and item.name.startswith("."):
                    continue
                files.append(await self._get_file_info(item))

        return sorted(files, key=lambda x: (not x.is_directory, x.name.lower()))

    async def _get_file_info(self, path: Path) -> FileInfo:
        """Get file information.

        Args:
            path: File path

        Returns:
            File information
        """
        stat = path.stat()

        # Calculate checksum for small files
        checksum = None
        if path.is_file() and stat.st_size < 10 * 1024 * 1024:  # Max 10MB
            try:
                hasher = hashlib.md5()
                async with aiofiles.open(path, "rb") as f:
                    while chunk := await f.read(8192):
                        hasher.update(chunk)
                checksum = hasher.hexdigest()
            except Exception:
                pass

        mime_type, _ = mimetypes.guess_type(str(path))

        return FileInfo(
            path=path,
            name=path.name,
            size=stat.st_size,
            modified_time=datetime.fromtimestamp(stat.st_mtime),
            created_time=datetime.fromtimestamp(stat.st_ctime),
            is_directory=path.is_dir(),
            mime_type=mime_type or "application/octet-stream",
            checksum=checksum,
        )

    async def search_files(
        self,
        pattern: str,
        path: Optional[Union[str, Path]] = None,
        max_results: int = 100,
    ) -> List[FileInfo]:
        """Search for files.

        Args:
            pattern: Search pattern (glob)
            path: Search path (default: allowed paths)
            max_results: Maximum results

        Returns:
            List of matching files
        """
        if path:
            search_paths = [self._normalize_path(path)]
        else:
            search_paths = await self.get_allowed_paths()

        results = []
        for search_path in search_paths:
            if not self.check_permission(search_path, FileAction.READ):
                continue

            try:
                for match in search_path.rglob(pattern):
                    if len(results) >= max_results:
                        break
                    results.append(await self._get_file_info(match))
            except Exception as e:
                logger.warning(f"Error searching {search_path}: {e}")

        return results

    async def read_lines(
        self,
        path: Union[str, Path],
        start_line: int = 0,
        end_line: Optional[int] = None,
    ) -> List[str]:
        """Read specific lines from file.

        Args:
            path: File path
            start_line: Starting line number
            end_line: Ending line number

        Returns:
            List of lines
        """
        path = self._normalize_path(path)

        if not self.check_permission(path, FileAction.READ):
            raise PermissionError(f"No read permission for {path}")

        lines = []
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            for i, line in enumerate(await f.readlines()):
                if i >= start_line:
                    lines.append(line.rstrip('\n'))
                if end_line and i >= end_line:
                    break

        return lines

    async def watch_directory(
        self,
        path: Union[str, Path],
        callback: callable,
        recursive: bool = True,
    ) -> str:
        """Watch directory for changes.

        Args:
            path: Directory to watch
            callback: Callback function for events
            recursive: Watch recursively

        Returns:
            Watch ID
        """
        path = self._normalize_path(path)

        if not self.check_permission(path, FileAction.READ):
            raise PermissionError(f"No read permission for {path}")

        watch_id = f"watch_{path}_{datetime.now().timestamp()}"

        class EventHandler(FileSystemEventHandler):
            def on_modified(self, event):
                if not event.is_directory:
                    callback("modified", event.src_path)

            def on_created(self, event):
                callback("created", event.src_path, event.is_directory)

            def on_deleted(self, event):
                callback("deleted", event.src_path)

            def on_moved(self, event):
                callback("moved", event.src_path, event.dest_path)

        handler = EventHandler()
        observer = Observer()
        observer.schedule(handler, str(path), recursive=recursive)
        observer.start()

        self._observers[watch_id] = observer
        self._watch_handlers[watch_id] = handler
        self._watch_callbacks[watch_id] = callback

        logger.info(f"Started watching: {path} (ID: {watch_id})")
        return watch_id

    async def stop_watching(self, watch_id: str):
        """Stop watching directory.

        Args:
            watch_id: Watch ID
        """
        if watch_id in self._observers:
            self._observers[watch_id].stop()
            self._observers[watch_id].join()
            del self._observers[watch_id]
            del self._watch_handlers[watch_id]
            del self._watch_callbacks[watch_id]
            logger.info(f"Stopped watching: {watch_id}")

    async def move_file(
        self,
        source: Union[str, Path],
        destination: Union[str, Path],
    ):
        """Move file or directory.

        Args:
            source: Source path
            destination: Destination path
        """
        source = self._normalize_path(source)
        destination = self._normalize_path(destination)

        if not self.check_permission(source, FileAction.READ):
            raise PermissionError(f"No read permission for {source}")

        if not self.check_permission(destination.parent, FileAction.WRITE):
            raise PermissionError(f"No write permission for {destination.parent}")

        import shutil
        shutil.move(str(source), str(destination))
        logger.info(f"Moved {source} to {destination}")

    async def copy_file(
        self,
        source: Union[str, Path],
        destination: Union[str, Path],
    ):
        """Copy file or directory.

        Args:
            source: Source path
            destination: Destination path
        """
        source = self._normalize_path(source)
        destination = self._normalize_path(destination)

        if not self.check_permission(source, FileAction.READ):
            raise PermissionError(f"No read permission for {source}")

        if not self.check_permission(destination.parent, FileAction.WRITE):
            raise PermissionError(f"No write permission for {destination.parent}")

        import shutil
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)

        logger.info(f"Copied {source} to {destination}")

    async def get_file_summary(self, path: Union[str, Path], max_chars: int = 1000) -> str:
        """Get a summary of file contents.

        Args:
            path: File path
            max_chars: Maximum characters to return

        Returns:
            File summary
        """
        path = self._normalize_path(path)

        if path.is_dir():
            files = await self.list_directory(path)
            return f"Directory with {len(files)} items"

        try:
            content = await self.read_file(path)
            if len(content) > max_chars:
                return content[:max_chars] + "..."
            return content
        except Exception as e:
            return f"Error reading file: {e}"

    async def shutdown(self):
        """Shutdown file system manager."""
        # Stop all watchers
        for watch_id in list(self._observers.keys()):
            await self.stop_watching(watch_id)

        self._permissions.clear()
        logger.info("File system manager shut down")

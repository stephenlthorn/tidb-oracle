from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from dateutil.parser import isoparse

from app.core.settings import get_settings
from app.utils.hashing import sha256_json, sha256_text


def _project_root() -> Path:
    here = Path(__file__).resolve()
    candidates = [here.parents[3], here.parents[2], Path.cwd()]
    for base in candidates:
        if (base / "data").exists():
            return base
    return here.parents[3]


SUPPORTED_TEXT_EXTENSIONS = {
    ".md",
    ".markdown",
    ".rst",
    ".adoc",
    ".txt",
    ".csv",
    ".tsv",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".sql",
    ".go",
    ".java",
    ".kt",
    ".py",
    ".sh",
    ".zsh",
    ".bash",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".rs",
    ".proto",
    ".xml",
}

SUPPORTED_TEXT_FILENAMES = {
    "makefile",
    "dockerfile",
    "license",
    "readme",
    "go.mod",
    "go.sum",
    "cargo.toml",
    "cargo.lock",
}

SKIP_DIR_NAMES = {
    ".git",
    ".github",
    ".idea",
    ".vscode",
    ".next",
    "node_modules",
    "__pycache__",
    "vendor",
    "third_party",
    "dist",
    "build",
}

MAX_FAKE_FILE_BYTES = 1_500_000
MAX_GOOGLE_FILE_BYTES = 8_000_000

GOOGLE_EXPORTABLE_MIMES = {
    "application/vnd.google-apps.document",
    "application/vnd.google-apps.presentation",
    "application/vnd.google-apps.spreadsheet",
}


@dataclass
class DriveFile:
    drive_file_id: str
    title: str
    url: str
    mime: str
    modified_time: datetime
    owner: str | None
    path: str | None
    permissions_hash: str
    source_type: str
    content: str


class DriveConnector:
    def __init__(self, oauth_credentials=None) -> None:
        self.settings = get_settings()
        self.fake_dir = _project_root() / "data" / "fake_drive"
        self._branch_cache: dict[str, str] = {}
        self.oauth_credentials = oauth_credentials

    def list_files(
        self,
        since: datetime | None = None,
        progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> list[DriveFile]:
        if self._can_use_google_api():
            return self._list_files_google_api(since, progress=progress)
        return self._list_files_fake(since, progress=progress)

    def _can_use_google_api(self) -> bool:
        return bool(
            self.oauth_credentials
            or
            self.settings.google_drive_service_account_json
            or (self.settings.google_drive_client_id and self.settings.google_drive_client_secret)
        )

    @staticmethod
    def _is_supported_text_file(path: Path) -> bool:
        lower_name = path.name.lower()
        if lower_name.endswith(".pdf.txt") or lower_name.endswith(".slides.txt"):
            return True
        if path.suffix.lower() in SUPPORTED_TEXT_EXTENSIONS:
            return True
        return lower_name in SUPPORTED_TEXT_FILENAMES

    @staticmethod
    def _is_skipped_path(path: Path) -> bool:
        return any(part.lower() in SKIP_DIR_NAMES for part in path.parts)

    @staticmethod
    def _branch_from_head(head_path: Path) -> str | None:
        if not head_path.exists():
            return None
        try:
            content = head_path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if content.startswith("ref:"):
            ref = content.split(":", 1)[1].strip()
            if ref:
                return ref.rsplit("/", 1)[-1]
        if content:
            return "HEAD"
        return None

    def _repo_branch(self, repo_root: Path) -> str:
        cache_key = str(repo_root)
        cached = self._branch_cache.get(cache_key)
        if cached:
            return cached

        branch = self._branch_from_head(repo_root / ".git" / "HEAD") or "main"
        self._branch_cache[cache_key] = branch
        return branch

    def _infer_fake_url(self, rel_path: Path) -> str:
        parts = rel_path.parts
        if len(parts) >= 3 and parts[0] == "github" and "__" in parts[1]:
            owner, repo = parts[1].split("__", 1)
            inner = "/".join(parts[2:])
            branch = self._repo_branch(self.fake_dir / parts[0] / parts[1])
            return f"https://github.com/{owner}/{repo}/blob/{branch}/{inner}"
        return f"https://drive.google.com/file/d/{sha256_text(rel_path.as_posix())[:12]}/view"

    def _list_files_fake(
        self,
        since: datetime | None = None,
        progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> list[DriveFile]:
        files: list[DriveFile] = []
        scanned = 0
        for path in sorted(self.fake_dir.rglob("*")):
            if not path.is_file():
                continue
            scanned += 1
            if progress and scanned % 25 == 0:
                progress({"phase": "listing", "scanned_entries": scanned, "files_discovered": len(files)})
            if self._is_skipped_path(path):
                continue
            try:
                rel = path.relative_to(self.fake_dir)
            except ValueError:
                continue
            if rel.parts and rel.parts[0] == "github" and not self.settings.fake_drive_include_github:
                continue
            if not self._is_supported_text_file(path):
                continue
            try:
                if path.stat().st_size > MAX_FAKE_FILE_BYTES:
                    continue
            except OSError:
                continue
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if since and mtime <= since:
                continue
            mime = "text/markdown" if path.suffix in {".md", ".markdown"} else "text/plain"
            if path.suffix == ".pdf.txt":
                mime = "application/pdf"
            if path.suffix == ".slides.txt":
                mime = "application/vnd.google-apps.presentation"
            raw = path.read_text(encoding="utf-8", errors="ignore")
            if not raw.strip():
                continue
            rel_posix = rel.as_posix()
            file_id = f"local_{sha256_text(rel_posix)[:24]}"
            inferred_owner = None
            if len(rel.parts) >= 2 and rel.parts[0] == "github" and "__" in rel.parts[1]:
                owner, repo = rel.parts[1].split("__", 1)
                inferred_owner = f"github:{owner}/{repo}"
            files.append(
                DriveFile(
                    drive_file_id=file_id,
                    title=rel_posix,
                    url=self._infer_fake_url(rel),
                    mime=mime,
                    modified_time=mtime,
                    owner=inferred_owner or "internal@pingcap.com",
                    path=f"/fake_drive/{rel_posix}",
                    permissions_hash=sha256_text("internal-only"),
                    source_type="google_drive",
                    content=raw,
                )
            )
        if progress:
            progress({"phase": "listing", "scanned_entries": scanned, "files_discovered": len(files)})
        return files

    def _list_files_google_api(
        self,
        since: datetime | None = None,
        progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> list[DriveFile]:
        try:
            from google.oauth2 import service_account
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaIoBaseDownload
            import io
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("Google API dependencies are missing") from exc

        scopes = ["https://www.googleapis.com/auth/drive.readonly"]
        creds = None

        if self.oauth_credentials is not None:
            creds = self.oauth_credentials
        elif self.settings.google_drive_service_account_json:
            creds = service_account.Credentials.from_service_account_file(
                self.settings.google_drive_service_account_json,
                scopes=scopes,
            )
        else:
            token_path = Path(self.settings.google_drive_oauth_token_path)
            if token_path.exists():
                creds = Credentials.from_authorized_user_file(str(token_path), scopes=scopes)
            else:  # pragma: no cover
                raise RuntimeError(
                    "OAuth credentials provided but no token file found. Complete OAuth flow and save token as .google-drive-token.json"
                )

        service = build("drive", "v3", credentials=creds, cache_discovery=False)

        # Resolve the list of folder IDs to query (multi-folder support)
        folder_ids = self.settings.drive_folder_ids
        if self.oauth_credentials is not None:
            # Per-user OAuth mode should inherit all visible files and shared drives.
            folder_ids = []
        elif not folder_ids and self.settings.google_drive_root_folder_id:
            folder_ids = [self.settings.google_drive_root_folder_id]

        folder_mime = "application/vnd.google-apps.folder"

        def _is_supported_google_file(name: str, mime: str) -> bool:
            lower_name = name.lower().strip()
            suffix = Path(lower_name).suffix
            if mime in GOOGLE_EXPORTABLE_MIMES:
                return True
            if mime.startswith("text/"):
                return True
            if mime in {
                "application/pdf",
                "application/json",
                "application/xml",
                "application/yaml",
                "application/x-yaml",
                "application/toml",
            }:
                return True
            if suffix in SUPPORTED_TEXT_EXTENSIONS:
                return True
            return lower_name in SUPPORTED_TEXT_FILENAMES

        seen_ids: set[str] = set()
        files: list[DriveFile] = []
        listing_stats = {
            "folders_visited": 0,
            "folders_queued": 0,
            "files_discovered": 0,
        }

        def _iter_query_items(q: str):
            page_token: str | None = None
            while True:
                request_kwargs: dict[str, Any] = {
                    "q": q,
                    "fields": "nextPageToken,files(id,name,mimeType,modifiedTime,size,owners(emailAddress),webViewLink,parents,permissions)",
                    "pageSize": 1000,
                    "pageToken": page_token,
                    "supportsAllDrives": True,
                    "includeItemsFromAllDrives": True,
                    "spaces": "drive",
                }
                if self.oauth_credentials is not None:
                    # In per-user mode, include My Drive + Shared Drives for the signed-in user.
                    request_kwargs["corpora"] = "allDrives"
                result = (
                    service.files()
                    .list(**request_kwargs)
                    .execute()
                )
                for item in result.get("files", []):
                    yield item
                page_token = result.get("nextPageToken")
                if not page_token:
                    break

        def _iter_candidate_items():
            if folder_ids:
                queue = list(folder_ids)
                visited_folders: set[str] = set()
                while queue:
                    parent_id = queue.pop(0)
                    if not parent_id or parent_id in visited_folders:
                        continue
                    visited_folders.add(parent_id)
                    listing_stats["folders_visited"] = len(visited_folders)
                    listing_stats["folders_queued"] = len(queue)
                    if progress:
                        progress({"phase": "listing", **listing_stats})
                    q = f"trashed=false and '{parent_id}' in parents"
                    for item in _iter_query_items(q):
                        mime = item.get("mimeType", "")
                        if mime == folder_mime:
                            child_id = item.get("id")
                            if child_id and child_id not in visited_folders:
                                queue.append(child_id)
                                listing_stats["folders_queued"] = len(queue)
                                if progress:
                                    progress({"phase": "listing", **listing_stats})
                            continue
                        listing_stats["files_discovered"] += 1
                        if progress and listing_stats["files_discovered"] % 25 == 0:
                            progress({"phase": "listing", **listing_stats})
                        yield item
                if progress:
                    progress({"phase": "listing", **listing_stats})
                return

            # No root folder configured: list all visible files.
            q_parts = ["trashed=false", f"mimeType!='{folder_mime}'"]
            if since:
                q_parts.append(f"modifiedTime > '{since.isoformat()}'")
            q = " and ".join(q_parts)
            for item in _iter_query_items(q):
                listing_stats["files_discovered"] += 1
                if progress and listing_stats["files_discovered"] % 25 == 0:
                    progress({"phase": "listing", **listing_stats})
                yield item
            if progress:
                progress({"phase": "listing", **listing_stats})

        for item in _iter_candidate_items():
            file_id = item.get("id")
            if not file_id or file_id in seen_ids:
                continue
            seen_ids.add(file_id)

            mime = item.get("mimeType", "")
            if mime == folder_mime:
                continue

            name = str(item.get("name", file_id))
            if not _is_supported_google_file(name, mime):
                continue

            try:
                modified_time = isoparse(item["modifiedTime"])
            except Exception:
                continue
            if since and modified_time <= since:
                continue

            size_raw = item.get("size")
            if isinstance(size_raw, str) and size_raw.isdigit():
                if int(size_raw) > MAX_GOOGLE_FILE_BYTES:
                    continue

            try:
                if mime == "application/vnd.google-apps.document":
                    request = service.files().export_media(fileId=file_id, mimeType="text/plain")
                elif mime == "application/vnd.google-apps.presentation":
                    request = service.files().export_media(fileId=file_id, mimeType="text/plain")
                elif mime == "application/vnd.google-apps.spreadsheet":
                    request = service.files().export_media(fileId=file_id, mimeType="text/csv")
                else:
                    request = service.files().get_media(fileId=file_id)

                buffer = io.BytesIO()
                downloader = MediaIoBaseDownload(buffer, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
                inner_content = buffer.getvalue().decode("utf-8", errors="ignore")
            except Exception:
                # Some Drive-native types cannot be exported to text/csv; skip those.
                continue

            if not inner_content.strip():
                continue

            owners = item.get("owners", [])
            owner_email = owners[0].get("emailAddress") if owners else None
            permissions_hash = sha256_json(item.get("permissions", []))
            files.append(
                DriveFile(
                    drive_file_id=file_id,
                    title=name,
                    url=item.get("webViewLink", f"https://drive.google.com/file/d/{file_id}/view"),
                    mime=mime,
                    modified_time=modified_time,
                    owner=owner_email,
                    path="/" + "/".join(item.get("parents", [])),
                    permissions_hash=permissions_hash,
                    source_type="google_drive",
                    content=inner_content,
                )
            )
        return files

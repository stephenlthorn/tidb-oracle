from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
    def __init__(self) -> None:
        self.settings = get_settings()
        self.fake_dir = _project_root() / "data" / "fake_drive"
        self._branch_cache: dict[str, str] = {}

    def list_files(self, since: datetime | None = None) -> list[DriveFile]:
        if self._can_use_google_api():
            return self._list_files_google_api(since)
        return self._list_files_fake(since)

    def _can_use_google_api(self) -> bool:
        return bool(
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

    def _list_files_fake(self, since: datetime | None = None) -> list[DriveFile]:
        files: list[DriveFile] = []
        for path in sorted(self.fake_dir.rglob("*")):
            if not path.is_file():
                continue
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
        return files

    def _list_files_google_api(self, since: datetime | None = None) -> list[DriveFile]:
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

        if self.settings.google_drive_service_account_json:
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
        if not folder_ids and self.settings.google_drive_root_folder_id:
            folder_ids = [self.settings.google_drive_root_folder_id]

        base_query = ["trashed=false"]
        if since:
            base_query.append(f"modifiedTime > '{since.isoformat()}'")

        def _build_query(fid: str | None) -> str:
            parts = list(base_query)
            if fid:
                parts.append(f"'{fid}' in parents")
            return " and ".join(parts)

        seen_ids: set[str] = set()
        files: list[DriveFile] = []

        queries = [_build_query(fid) for fid in folder_ids] if folder_ids else [_build_query(None)]
        for q in queries:
            result = service.files().list(
                q=q,
                fields="files(id,name,mimeType,modifiedTime,owners,emailAddress,webViewLink,parents,permissions)",
                pageSize=1000,
            ).execute()

            for item in result.get("files", []):
                if item["id"] in seen_ids:
                    continue
                seen_ids.add(item["id"])
                file_id = item["id"]
                mime = item.get("mimeType", "")

                inner_content = ""
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

                owners = item.get("owners", [])
                owner_email = owners[0].get("emailAddress") if owners else None
                permissions_hash = sha256_json(item.get("permissions", []))

                files.append(
                    DriveFile(
                        drive_file_id=file_id,
                        title=item.get("name", file_id),
                        url=item.get("webViewLink", f"https://drive.google.com/file/d/{file_id}/view"),
                        mime=mime,
                        modified_time=isoparse(item["modifiedTime"]),
                        owner=owner_email,
                        path="/" + "/".join(item.get("parents", [])),
                        permissions_hash=permissions_hash,
                        source_type="google_drive",
                        content=inner_content,
                    )
                )
        return files

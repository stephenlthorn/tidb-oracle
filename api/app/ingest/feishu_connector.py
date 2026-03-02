from __future__ import annotations

import logging
from typing import Any, Callable

import httpx

logger = logging.getLogger(__name__)

_TENANT_TOKEN_URL = "/auth/v3/tenant_access_token/internal"
_LIST_FILES_URL = "/drive/v1/files"
_DOC_CONTENT_URL = "/docx/v1/documents/{doc_token}/raw_content"


class FeishuConnector:
    """Fetch Feishu/Lark docs from one or more root folders (optionally recursive)."""

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        base_url: str = "https://open.feishu.cn/open-apis",
        access_token: str | None = None,
    ) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.base_url = base_url.rstrip("/")
        self._tenant_token: str | None = None
        self._access_token = (access_token or "").strip() or None

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _refresh_tenant_token(self) -> None:
        if not self.app_id or not self.app_secret:
            raise RuntimeError("Feishu app_id/app_secret are required for tenant-token mode.")
        url = self.base_url + _TENANT_TOKEN_URL
        resp = httpx.post(url, json={"app_id": self.app_id, "app_secret": self.app_secret}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Feishu auth error: {data}")
        self._tenant_token = data["tenant_access_token"]

    def _headers(self) -> dict[str, str]:
        if self._access_token:
            return {"Authorization": f"Bearer {self._access_token}"}
        if not self._tenant_token:
            self._refresh_tenant_token()
        return {"Authorization": f"Bearer {self._tenant_token}"}

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    @staticmethod
    def _item_token(item: dict[str, Any]) -> str | None:
        for key in ("token", "file_token", "doc_token", "obj_token"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def list_folder_items(self, folder_token: str | None) -> list[dict[str, Any]]:
        """Return all file metadata dicts in the given folder."""
        url = self.base_url + _LIST_FILES_URL
        params: dict[str, Any] = {"page_size": 50}
        if folder_token:
            params["folder_token"] = folder_token

        items: list[dict[str, Any]] = []
        page_token: str | None = None

        while True:
            request_params = dict(params)
            if page_token:
                request_params["page_token"] = page_token
            resp = httpx.get(url, headers=self._headers(), params=request_params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"Feishu list_folder error: {data}")
            payload = data.get("data", {})
            batch = payload.get("files") or payload.get("items") or []
            for item in batch:
                if isinstance(item, dict):
                    items.append(item)
            if not payload.get("has_more"):
                break
            page_token = payload.get("next_page_token")

        return items

    def list_documents(
        self,
        root_tokens: list[str],
        *,
        recursive: bool = True,
        progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> list[dict[str, Any]]:
        """Traverse one or more Feishu folders and return docx/doc entries."""
        normalized_roots = []
        seen_roots: set[str] = set()
        for token in root_tokens:
            normalized = (token or "").strip()
            if not normalized or normalized in seen_roots:
                continue
            seen_roots.add(normalized)
            normalized_roots.append(normalized)

        if not normalized_roots:
            normalized_roots = [""]

        docs: list[dict[str, Any]] = []
        seen_docs: set[str] = set()
        seen_folders: set[str] = set()
        queue: list[str] = list(normalized_roots)

        if progress:
            progress(
                {
                    "phase": "listing",
                    "roots": len(normalized_roots),
                    "folders_queued": len(queue),
                    "folders_visited": 0,
                    "files_discovered": 0,
                }
            )

        while queue:
            current_folder = (queue.pop(0) or "").strip()
            if current_folder:
                if current_folder in seen_folders:
                    continue
                seen_folders.add(current_folder)
            items = self.list_folder_items(current_folder or None)

            for item in items:
                item_type = str(item.get("type") or "").strip().lower()
                token = self._item_token(item)
                if not token:
                    continue

                if item_type == "folder":
                    if recursive and token not in seen_folders:
                        queue.append(token)
                    continue

                if item_type not in {"docx", "doc"}:
                    continue

                if token in seen_docs:
                    continue
                seen_docs.add(token)
                docs.append(
                    {
                        **item,
                        "token": token,
                        "_root_token": current_folder,
                    }
                )

            if progress:
                progress(
                    {
                        "phase": "listing",
                        "roots": len(normalized_roots),
                        "folders_queued": len(queue),
                        "folders_visited": len(seen_folders),
                        "files_discovered": len(docs),
                    }
                )

        logger.info(
            "Feishu: found %d docs across %d roots (recursive=%s)",
            len(docs),
            len(normalized_roots),
            recursive,
        )
        return docs

    def list_folder(self, folder_token: str) -> list[dict[str, Any]]:
        """Backward-compatible single-root listing."""
        return self.list_documents([folder_token], recursive=False)

    # ------------------------------------------------------------------
    # Content
    # ------------------------------------------------------------------

    def get_doc_content(self, doc_token: str) -> str:
        """Fetch plain text content of a Feishu document."""
        url = self.base_url + _DOC_CONTENT_URL.format(doc_token=doc_token)
        resp = httpx.get(url, headers=self._headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        code = data.get("code")
        if code != 0:
            msg = str(data.get("msg") or "")
            if code == 20043 or "docs:document:readonly" in msg:
                raise RuntimeError(
                    "Feishu permission denied (code 20043). Missing docs:document:readonly. "
                    "Grant docs read permission in Feishu app, publish the app version, "
                    "approve it in tenant admin, then reconnect OAuth and sync again."
                )
            raise RuntimeError(f"Feishu get_doc_content error: {data}")
        return data.get("data", {}).get("content", "")

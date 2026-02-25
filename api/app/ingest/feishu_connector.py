from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_TENANT_TOKEN_URL = "/auth/v3/tenant_access_token/internal"
_LIST_FILES_URL = "/drive/v1/files"
_DOC_CONTENT_URL = "/docx/v1/documents/{doc_token}/raw_content"


class FeishuConnector:
    """Fetch documents from a Feishu/Lark folder using the open-platform API."""

    def __init__(self, app_id: str, app_secret: str, base_url: str = "https://open.feishu.cn/open-apis") -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.base_url = base_url.rstrip("/")
        self._tenant_token: str | None = None

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _refresh_tenant_token(self) -> None:
        url = self.base_url + _TENANT_TOKEN_URL
        resp = httpx.post(url, json={"app_id": self.app_id, "app_secret": self.app_secret}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Feishu auth error: {data}")
        self._tenant_token = data["tenant_access_token"]

    def _headers(self) -> dict[str, str]:
        if not self._tenant_token:
            self._refresh_tenant_token()
        return {"Authorization": f"Bearer {self._tenant_token}"}

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_folder(self, folder_token: str) -> list[dict[str, Any]]:
        """Return all file metadata dicts in the given folder (docx only)."""
        url = self.base_url + _LIST_FILES_URL
        params: dict[str, Any] = {"folder_token": folder_token, "page_size": 50}
        files: list[dict[str, Any]] = []
        page_token: str | None = None

        while True:
            if page_token:
                params["page_token"] = page_token
            resp = httpx.get(url, headers=self._headers(), params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"Feishu list_folder error: {data}")
            items = data.get("data", {}).get("files", [])
            for item in items:
                if item.get("type") == "docx":
                    files.append(item)
            if not data.get("data", {}).get("has_more"):
                break
            page_token = data["data"].get("next_page_token")

        logger.info("Feishu: found %d docx files in folder %s", len(files), folder_token)
        return files

    # ------------------------------------------------------------------
    # Content
    # ------------------------------------------------------------------

    def get_doc_content(self, doc_token: str) -> str:
        """Fetch plain text content of a Feishu document."""
        url = self.base_url + _DOC_CONTENT_URL.format(doc_token=doc_token)
        resp = httpx.get(url, headers=self._headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Feishu get_doc_content error: {data}")
        return data.get("data", {}).get("content", "")

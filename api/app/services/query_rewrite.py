from __future__ import annotations

from collections import OrderedDict


class QueryRewriter:
    def rewrite(self, text: str, mode: str) -> str:
        # Lightweight rewrite: de-duplicate terms and inject mode hint for retrieval.
        words = [w.strip() for w in text.replace("?", " ").split() if w.strip()]
        dedup = list(OrderedDict((w.lower(), w) for w in words).values())
        if mode == "oracle":
            dedup.extend(["TiDB", "GTM", "enablement"])
        if mode == "call_assistant":
            dedup.extend(["transcript", "next steps", "risks"])
        return " ".join(dedup)

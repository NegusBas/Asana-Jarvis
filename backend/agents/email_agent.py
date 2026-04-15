"""Email / calendar integration stubs — wire IMAP, Graph API, or Google later."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class EmailAgent:
    """Unified inbox / calendar facade (not yet connected)."""

    def check_scivora_updates(self) -> Dict[str, Any]:
        """Placeholder: Basleal@scivora.com — unread digest, VIP threads, etc."""
        return {"status": "not_configured", "message": "IMAP/OAuth for Scivora not wired yet."}

    def check_recruiter_emails(self) -> Dict[str, Any]:
        """Placeholder: recruiter threads across personal + role mailboxes."""
        return {"status": "not_configured", "message": "Recruiter inbox scan not wired yet."}

    def check_assistant_schedule(self) -> Dict[str, Any]:
        """Placeholder: assistant-managed mailboxes + shared calendar."""
        return {
            "status": "not_configured",
            "message": "Unified assistant calendar / interview detection not wired yet.",
            "accounts": [
                "info@elev8tech.co",
                "Basleal.a.negatu@gmail.com",
                "Basleal.an@outlook.com",
            ],
        }

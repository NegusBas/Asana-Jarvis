"""Email and schedule agent backed by Gmail IMAP."""

from __future__ import annotations

import email
import imaplib
import os
from dataclasses import dataclass
from email.header import decode_header
from typing import Any, Dict, List


@dataclass
class EmailAgent:
    """Unified inbox facade with Gmail IMAP scanning."""

    gmail_address: str = os.getenv("GMAIL_IMAP_EMAIL", "Basleal.a.negatu@gmail.com")
    gmail_app_password: str = os.getenv("GMAIL_APP_PASSWORD", "")
    imap_host: str = os.getenv("GMAIL_IMAP_HOST", "imap.gmail.com")
    imap_port: int = int(os.getenv("GMAIL_IMAP_PORT", "993"))
    max_messages_to_scan: int = int(os.getenv("GMAIL_SCAN_LIMIT", "80"))

    _RECRUITER_KEYWORDS = (
        "interview",
        "recruiter",
        "hiring",
        "screen",
        "onsite",
        "take home",
        "coding challenge",
        "application update",
    )
    _SCHEDULE_KEYWORDS = (
        "interview",
        "meeting",
        "schedule",
        "calendar",
        "zoom",
        "google meet",
        "microsoft teams",
        "appointment",
    )

    def _decode_header_value(self, value: str) -> str:
        if not value:
            return ""
        chunks: List[str] = []
        for part, encoding in decode_header(value):
            if isinstance(part, bytes):
                chunks.append(part.decode(encoding or "utf-8", errors="replace"))
            else:
                chunks.append(part)
        return "".join(chunks).strip()

    def _extract_text_snippet(self, message: email.message.Message, max_len: int = 240) -> str:
        if message.is_multipart():
            for part in message.walk():
                content_type = part.get_content_type()
                disposition = str(part.get("Content-Disposition", ""))
                if content_type == "text/plain" and "attachment" not in disposition.lower():
                    payload = part.get_payload(decode=True) or b""
                    charset = part.get_content_charset() or "utf-8"
                    text = payload.decode(charset, errors="replace").strip()
                    return " ".join(text.split())[:max_len]
            return ""
        payload = message.get_payload(decode=True) or b""
        charset = message.get_content_charset() or "utf-8"
        text = payload.decode(charset, errors="replace").strip()
        return " ".join(text.split())[:max_len]

    def _scan_inbox(self, keywords: tuple[str, ...], label: str) -> Dict[str, Any]:
        if not self.gmail_app_password:
            return {
                "status": "not_configured",
                "message": "Missing GMAIL_APP_PASSWORD in environment.",
                "account": self.gmail_address,
            }

        try:
            with imaplib.IMAP4_SSL(self.imap_host, self.imap_port) as client:
                client.login(self.gmail_address, self.gmail_app_password)
                client.select("INBOX")
                status, data = client.search(None, "ALL")
                if status != "OK":
                    return {
                        "status": "error",
                        "message": "Unable to search inbox.",
                        "account": self.gmail_address,
                    }

                message_ids = data[0].split()
                recent_ids = message_ids[-self.max_messages_to_scan :]
                matches: List[Dict[str, str]] = []

                for msg_id in reversed(recent_ids):
                    try:
                        fetch_status, message_data = client.fetch(msg_id, "(RFC822)")
                        if fetch_status != "OK" or not message_data:
                            continue
                        entry = message_data[0]
                        if not isinstance(entry, tuple) or len(entry) < 2:
                            continue
                        raw_email = entry[1]
                    except Exception:
                        continue

                    parsed = email.message_from_bytes(raw_email)
                    subject = self._decode_header_value(parsed.get("Subject", ""))
                    sender = self._decode_header_value(parsed.get("From", ""))
                    date = self._decode_header_value(parsed.get("Date", ""))
                    snippet = self._extract_text_snippet(parsed)
                    haystack = f"{subject} {sender} {snippet}".lower()

                    matched = [kw for kw in keywords if kw in haystack]
                    if not matched:
                        continue

                    matches.append(
                        {
                            "subject": subject,
                            "from": sender,
                            "date": date,
                            "snippet": snippet,
                            "matched_keywords": ", ".join(matched),
                        }
                    )

                    if len(matches) >= 25:
                        break

                return {
                    "status": "ok",
                    "account": self.gmail_address,
                    "category": label,
                    "scanned_messages": len(recent_ids),
                    "matches_found": len(matches),
                    "matches": matches,
                }
        except imaplib.IMAP4.error as e:
            return {
                "status": "auth_error",
                "message": f"Gmail IMAP auth failed: {e}",
                "account": self.gmail_address,
            }
        except Exception as e:  # pragma: no cover - defensive runtime path
            return {
                "status": "error",
                "message": f"Inbox scan failed: {e}",
                "account": self.gmail_address,
            }

    def check_scivora_updates(self) -> Dict[str, Any]:
        """Placeholder: Basleal@scivora.com — unread digest, VIP threads, etc."""
        return {"status": "not_configured", "message": "IMAP/OAuth for Scivora not wired yet."}

    def check_recruiter_emails(self) -> Dict[str, Any]:
        """Scan Gmail inbox for recruiter-interview workflow updates."""
        return self._scan_inbox(self._RECRUITER_KEYWORDS, "recruiter_emails")

    def check_assistant_schedule(self) -> Dict[str, Any]:
        """Scan Gmail inbox for assistant scheduling and interview timing signals."""
        result = self._scan_inbox(self._SCHEDULE_KEYWORDS, "assistant_schedule")
        result["accounts"] = [
            "info@elev8tech.co",
            "Basleal.a.negatu@gmail.com",
            "Basleal.an@outlook.com",
        ]
        return result

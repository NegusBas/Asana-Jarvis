"""Google Calendar integration via OAuth2 (Installed App flow)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/calendar"]

_BACKEND_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
CREDENTIALS_FILE = os.path.join(_BACKEND_ROOT, "credentials.json")
TOKEN_FILE = os.path.join(_BACKEND_ROOT, "token.json")


@dataclass
class CalendarAgent:
    """Fetches and creates events on the user's primary Google Calendar."""

    def _ensure_credentials(self) -> Credentials:
        """
        Load or obtain OAuth credentials; persist token to backend/token.json.
        Raises with a clear message if credentials.json is missing or flow fails.
        """
        if not os.path.isfile(CREDENTIALS_FILE):
            raise FileNotFoundError(
                f"Missing {CREDENTIALS_FILE}. Download OAuth client JSON from "
                "Google Cloud Console (Desktop app) and save it as backend/credentials.json."
            )

        creds: Optional[Credentials] = None
        if os.path.isfile(TOKEN_FILE):
            try:
                creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            except Exception:
                # Corrupted token file — delete it and re-authenticate
                os.remove(TOKEN_FILE)
                creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception:
                    # Refresh failed (revoked token, network error) — force re-auth
                    creds = None
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    CREDENTIALS_FILE, SCOPES
                )
                creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

        return creds

    def get_upcoming_events(self, days: int = 7) -> str:
        """
        List upcoming events on the primary calendar for the next `days` days.
        Returns lines formatted as: "Date/Time: Event Title"
        On failure returns a single-line string starting with "Error: ".
        """
        try:
            creds = self._ensure_credentials()
        except FileNotFoundError as e:
            return f"Error: {e}"
        except Exception as e:
            return (
                f"Error: Google Calendar authentication failed ({type(e).__name__}): {e}. "
                "If the token is invalid, delete backend/token.json and sign in again."
            )

        try:
            service = build("calendar", "v3", credentials=creds, cache_discovery=False)
            now = datetime.now(timezone.utc)
            time_min = now.isoformat().replace("+00:00", "Z")
            time_max = (now + timedelta(days=max(1, int(days)))).isoformat().replace(
                "+00:00", "Z"
            )

            events_result = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )

            items = events_result.get("items", [])
            if not items:
                return f"No events in the next {days} day(s)."

            lines: list[str] = []
            for ev in items:
                summary = ev.get("summary", "(No title)")
                start_info = ev.get("start", {})
                dt_raw = start_info.get("dateTime") or start_info.get("date")
                label = self._format_start_label(dt_raw)
                lines.append(f"{label}: {summary}")

            return "\n".join(lines)
        except HttpError as e:
            return f"Error: Calendar API HTTP error ({e.resp.status}): {e.reason or e}"
        except Exception as e:
            return f"Error: Failed to list calendar events ({type(e).__name__}): {e}"

    @staticmethod
    def _format_start_label(dt_raw: Optional[str]) -> str:
        if not dt_raw:
            return "Unknown time"
        if "T" in dt_raw:
            try:
                normalized = dt_raw.replace("Z", "+00:00")
                dt = datetime.fromisoformat(normalized)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.strftime("%Y-%m-%d %H:%M %Z").strip() or dt.strftime(
                    "%Y-%m-%d %H:%M"
                )
            except ValueError:
                return dt_raw
        return dt_raw

    def schedule_event(self, title: str, date: str, time: str) -> str:
        """
        Insert a one-hour event on the primary calendar.
        `date` should be YYYY-MM-DD; `time` should be HH:MM (24-hour).
        Returns a confirmation string or "Error: ...".
        """
        try:
            creds = self._ensure_credentials()
        except FileNotFoundError as e:
            return f"Error: {e}"
        except Exception as e:
            return (
                f"Error: Google Calendar authentication failed ({type(e).__name__}): {e}. "
                "If the token is invalid, delete backend/token.json and sign in again."
            )

        try:
            start = datetime.strptime(
                f"{date.strip()} {time.strip()}", "%Y-%m-%d %H:%M"
            ).replace(tzinfo=timezone.utc)
        except ValueError as e:
            return (
                f"Error: Could not parse date '{date}' and time '{time}' "
                f"as YYYY-MM-DD and HH:MM (24-hour). ({e})"
            )

        end = start + timedelta(hours=1)
        body = {
            "summary": title,
            "start": {
                "dateTime": start.isoformat().replace("+00:00", "Z"),
                "timeZone": "UTC",
            },
            "end": {
                "dateTime": end.isoformat().replace("+00:00", "Z"),
                "timeZone": "UTC",
            },
        }

        try:
            service = build("calendar", "v3", credentials=creds, cache_discovery=False)
            created = (
                service.events()
                .insert(calendarId="primary", body=body)
                .execute()
            )
            link = created.get("htmlLink", "")
            eid = created.get("id", "")
            return f"Created event '{title}' (id={eid}). Link: {link}".strip()
        except HttpError as e:
            return f"Error: Calendar API HTTP error ({e.resp.status}): {e.reason or e}"
        except Exception as e:
            return f"Error: Failed to create event ({type(e).__name__}): {e}"

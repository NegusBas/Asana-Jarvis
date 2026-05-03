"""Sub-agents for Chief-of-Staff capabilities."""

from .git_agent import GitAgent
from .email_agent import EmailAgent
from .briefing_agent import BriefingAgent
from .skill_manager import SkillManager
from .calendar_agent import CalendarAgent

__all__ = [
    "GitAgent",
    "EmailAgent",
    "BriefingAgent",
    "SkillManager",
    "CalendarAgent",
]

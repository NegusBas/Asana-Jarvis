"""Persona / skill router for Asana — keeps specialized prompts out of one giant system string."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class SkillManager:
    """Routes user intent to a specialized persona prompt."""

    chief_of_staff_prompt: str
    active_persona: str = "chief_of_staff"
    personas: Dict[str, str] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.personas = {
            "chief_of_staff": self.chief_of_staff_prompt,
            "developer": (
                "You are Asana in Developer / Web Artifacts Builder mode.\n"
                "FOCUS: Clean, scalable React/Tailwind code, solid software architecture, and maintainable patterns.\n"
                "STYLE: Technical precision, modular design, and implementation-ready guidance."
            ),
            "ux_ui_designer": (
                "You are Asana in UX/UI Designer mode.\n"
                "FOCUS: Brand guidelines, color theory, layout hierarchy, accessibility, and user flows.\n"
                "STYLE: Clear design rationale, tradeoffs, and actionable UX direction."
            ),
            "entrepreneur_finance": (
                "You are Asana in Entrepreneur / Finance mode.\n"
                "FOCUS: Budgeting, resource allocation, runway awareness, pricing, and market strategy.\n"
                "STYLE: ROI-focused, data-grounded, risk-aware recommendations."
            ),
            "marketer": (
                "You are Asana in Marketer mode.\n"
                "FOCUS: Copywriting, LinkedIn outreach, positioning, campaigns, and internal comms.\n"
                "STYLE: Audience-aware, persuasive, concise."
            ),
        }

    def get_persona_prompt(self, persona_key: str) -> str:
        key = persona_key.strip().lower()
        if key not in self.personas:
            raise ValueError(f"Unknown persona '{persona_key}'. Valid: {sorted(self.personas.keys())}")
        return self.personas[key]

    def set_active_persona(self, persona_key: str) -> str:
        """Set active persona and return its full system prompt."""
        prompt = self.get_persona_prompt(persona_key)
        self.active_persona = persona_key.strip().lower()
        return prompt

    def list_personas(self) -> List[str]:
        return sorted(self.personas.keys())

    def infer_persona_from_intent(self, intent: str) -> str:
        text = (intent or "").lower()

        developer_terms = (
            "code", "bug", "refactor", "react", "tailwind", "api", "backend",
            "frontend", "architecture", "typescript", "python", "component",
            "hook", "eslint", "vite", "electron",
        )
        ux_terms = (
            "ux", "ui", "wireframe", "design", "prototype", "figma", "color",
            "layout", "brand", "user flow", "accessibility", "typography",
        )
        finance_terms = (
            "budget", "finance", "cash flow", "runway", "pricing", "cost",
            "expense", "allocation", "revenue", "profit", "burn",
        )
        marketer_terms = (
            "marketing", "copy", "campaign", "linkedin", "outreach",
            "positioning", "messaging", "content", "newsletter",
        )

        if any(t in text for t in developer_terms):
            return "developer"
        if any(t in text for t in ux_terms):
            return "ux_ui_designer"
        if any(t in text for t in finance_terms):
            return "entrepreneur_finance"
        if any(t in text for t in marketer_terms):
            return "marketer"
        return "chief_of_staff"

    def get_persona_and_tools(self, intent: str) -> Tuple[str, Dict[str, str]]:
        """
        Return (system_prompt, metadata) for the persona inferred from user text.
        Tool list filtering can be added later; metadata includes the persona key.
        """
        persona = self.infer_persona_from_intent(intent)
        prompt = self.get_persona_prompt(persona)
        return prompt, {"persona": persona}

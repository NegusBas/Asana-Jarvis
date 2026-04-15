"""OpenAI / Ollama function-calling schemas for Chief-of-Staff tools."""

chief_of_staff_tools = [
    {
        "type": "function",
        "function": {
            "name": "run_daily_briefing",
            "description": "Fetches RSS headlines (NBA, tech, stocks, Ethiopia) and adds Amharic word + proverb of the day.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_key": {
                        "type": "string",
                        "description": "Optional YYYY-MM-DD for stable word/proverb picks.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sync_scivora_repo",
            "description": "Runs git pull, status, and recent git log in the Scivora repo (SCIVORA_REPO_PATH).",
            "parameters": {
                "type": "object",
                "properties": {
                    "log_lines": {
                        "type": "integer",
                        "description": "Number of log lines (default 15).",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "audit_assistant_schedule",
            "description": "Checks unified assistant mailboxes/calendars for recruiter interviews (placeholder until OAuth).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_fitness_routine",
            "description": "Shows today's workout template or appends an optional note to the fitness log in asana_memory.json.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["show_today", "append_note"],
                        "description": "show_today returns the regimen; append_note adds a note to the log.",
                    },
                    "note": {"type": "string", "description": "Optional note when action is append_note."},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_self_improvement",
            "description": "Reads key Asana source files and appends an improvement proposal entry to asana_memory.json.",
            "parameters": {
                "type": "object",
                "properties": {
                    "proposal": {
                        "type": "string",
                        "description": "Concrete feature or refactor proposal in plain language.",
                    }
                },
                "required": ["proposal"],
            },
        },
    },
]

import os

# --- FILE SYSTEM TOOLS ---
write_file_tool = {
    "name": "write_file",
    "description": "Writes content to a file in the project. Use this to save code, notes, or plans.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "path": {"type": "STRING", "description": "The file path (relative to project root)."},
            "content": {"type": "STRING", "description": "The text content to write."}
        },
        "required": ["path", "content"]
    }
}

read_directory_tool = {
    "name": "read_directory",
    "description": "Lists files and folders in a directory.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "path": {"type": "STRING", "description": "The directory path to read."}
        },
        "required": ["path"]
    }
}

read_file_tool = {
    "name": "read_file",
    "description": "Reads the content of a file.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "path": {"type": "STRING", "description": "The path of the file to read."}
        },
        "required": ["path"]
    }
}

# Export the list
tools_list = [{"function_declarations": [
    write_file_tool,
    read_directory_tool,
    read_file_tool
]}]



"""
File Tool - Read, write, and edit files
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any


class FileTool:
    """Tool for file operations"""

    def __init__(self):
        self.logger = logging.getLogger('FileTool')

    def get_schema(self) -> Dict[str, Any]:
        """Get tool schema for Claude API"""
        return {
            "name": "file",
            "description": "Read, write, edit, or delete files. Supports multiple operations.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["read", "write", "append", "delete", "list", "exists"],
                        "description": "The file operation to perform"
                    },
                    "path": {
                        "type": "string",
                        "description": "The file or directory path"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write or append (for write/append operations)"
                    }
                },
                "required": ["operation", "path"]
            }
        }

    def execute(self, params: Dict[str, Any]) -> str:
        """Execute file operation"""
        operation = params.get('operation')
        path = params.get('path')
        content = params.get('content', '')

        if not operation or not path:
            return "Error: Missing required parameters"

        self.logger.info(f"File operation: {operation} on {path}")

        try:
            if operation == "read":
                return self._read_file(path)
            elif operation == "write":
                return self._write_file(path, content)
            elif operation == "append":
                return self._append_file(path, content)
            elif operation == "delete":
                return self._delete_file(path)
            elif operation == "list":
                return self._list_directory(path)
            elif operation == "exists":
                return self._check_exists(path)
            else:
                return f"Error: Unknown operation '{operation}'"

        except Exception as e:
            error_msg = f"Error in file operation: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return f"Error: {error_msg}"

    def _read_file(self, path: str) -> str:
        """Read file contents"""
        file_path = Path(path)

        if not file_path.exists():
            return f"Error: File does not exist: {path}"

        if not file_path.is_file():
            return f"Error: Path is not a file: {path}"

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        return f"File content of '{path}':\n\n{content}"

    def _write_file(self, path: str, content: str) -> str:
        """Write content to file"""
        file_path = Path(path)

        # Create parent directories if needed
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

        return f"Successfully wrote {len(content)} bytes to '{path}'"

    def _append_file(self, path: str, content: str) -> str:
        """Append content to file"""
        file_path = Path(path)

        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(content)

        return f"Successfully appended {len(content)} bytes to '{path}'"

    def _delete_file(self, path: str) -> str:
        """Delete file"""
        file_path = Path(path)

        if not file_path.exists():
            return f"Error: File does not exist: {path}"

        file_path.unlink()
        return f"Successfully deleted '{path}'"

    def _list_directory(self, path: str) -> str:
        """List directory contents"""
        dir_path = Path(path)

        if not dir_path.exists():
            return f"Error: Directory does not exist: {path}"

        if not dir_path.is_dir():
            return f"Error: Path is not a directory: {path}"

        items = []
        for item in sorted(dir_path.iterdir()):
            item_type = "DIR" if item.is_dir() else "FILE"
            items.append(f"  [{item_type}] {item.name}")

        return f"Contents of '{path}':\n" + "\n".join(items)

    def _check_exists(self, path: str) -> str:
        """Check if path exists"""
        exists = Path(path).exists()
        return f"Path '{path}' exists: {exists}"

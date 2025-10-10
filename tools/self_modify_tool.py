"""
Self-Modify Tool - Allow agent to modify its own code
"""

import os
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any


class SelfModifyTool:
    """Tool for self-modification capabilities"""

    def __init__(self):
        self.logger = logging.getLogger('SelfModifyTool')
        self.project_root = Path(__file__).parent.parent

    def get_schema(self) -> Dict[str, Any]:
        """Get tool schema for Claude API"""
        return {
            "name": "self_modify",
            "description": "Modify the agent's own code. Use this to fix bugs, add features, or improve performance. ALWAYS create backups before modifying.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["backup", "modify_file", "list_files", "diff"],
                        "description": "The self-modification action to perform"
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Relative path to the file (from project root)"
                    },
                    "new_content": {
                        "type": "string",
                        "description": "New content for the file (for modify_file action)"
                    },
                    "backup_name": {
                        "type": "string",
                        "description": "Name for the backup (optional, auto-generated if not provided)"
                    }
                },
                "required": ["action"]
            }
        }

    def execute(self, params: Dict[str, Any]) -> str:
        """Execute self-modification action"""
        action = params.get('action')

        if not action:
            return "Error: No action specified"

        self.logger.info(f"Self-modify action: {action}")

        try:
            if action == "backup":
                return self._create_backup(params.get('backup_name'))
            elif action == "modify_file":
                file_path = params.get('file_path')
                new_content = params.get('new_content')
                return self._modify_file(file_path, new_content)
            elif action == "list_files":
                return self._list_project_files()
            elif action == "diff":
                file_path = params.get('file_path')
                new_content = params.get('new_content')
                return self._show_diff(file_path, new_content)
            else:
                return f"Error: Unknown action '{action}'"

        except Exception as e:
            error_msg = f"Error in self-modification: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return f"Error: {error_msg}"

    def _create_backup(self, backup_name: str = None) -> str:
        """Create a backup of the entire project"""
        if backup_name is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"backup_{timestamp}"

        backup_dir = self.project_root / "backups" / backup_name
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Copy important files
        files_to_backup = []
        for pattern in ['core/**/*.py', 'tools/**/*.py', 'config/**/*']:
            files_to_backup.extend(self.project_root.glob(pattern))

        backed_up = []
        for file_path in files_to_backup:
            if file_path.is_file():
                relative_path = file_path.relative_to(self.project_root)
                backup_file = backup_dir / relative_path
                backup_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, backup_file)
                backed_up.append(str(relative_path))

        self.logger.info(f"Created backup: {backup_name}")
        return f"Backup created: {backup_name}\n\nBacked up {len(backed_up)} files:\n" + "\n".join(f"  - {f}" for f in backed_up)

    def _modify_file(self, file_path: str, new_content: str) -> str:
        """Modify a project file"""
        if not file_path or not new_content:
            return "Error: file_path and new_content are required"

        # Security check - only allow modifying project files
        full_path = (self.project_root / file_path).resolve()

        if not str(full_path).startswith(str(self.project_root)):
            return "Error: Can only modify files within project directory"

        # Create backup first
        backup_result = self._create_backup()
        self.logger.info(f"Auto-backup before modification: {backup_result[:50]}...")

        # Write new content
        full_path.parent.mkdir(parents=True, exist_ok=True)

        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        self.logger.info(f"Modified file: {file_path}")
        return f"Successfully modified '{file_path}'\n\n{backup_result}"

    def _list_project_files(self) -> str:
        """List all project files that can be modified"""
        files = []

        for pattern in ['core/**/*.py', 'tools/**/*.py', 'config/**/*']:
            for file_path in self.project_root.glob(pattern):
                if file_path.is_file():
                    relative_path = file_path.relative_to(self.project_root)
                    size = file_path.stat().st_size
                    files.append(f"  {relative_path} ({size} bytes)")

        return "Modifiable project files:\n" + "\n".join(sorted(files))

    def _show_diff(self, file_path: str, new_content: str) -> str:
        """Show what would change without actually modifying"""
        if not file_path or not new_content:
            return "Error: file_path and new_content are required"

        full_path = (self.project_root / file_path).resolve()

        if not full_path.exists():
            return f"File does not exist yet: {file_path}\n\nNew content would be:\n{new_content[:500]}..."

        with open(full_path, 'r', encoding='utf-8') as f:
            old_content = f.read()

        return f"Diff for '{file_path}':\n\nOLD ({len(old_content)} bytes):\n{old_content[:200]}...\n\nNEW ({len(new_content)} bytes):\n{new_content[:200]}..."

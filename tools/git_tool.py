"""
Git Tool - Work with git repositories
"""

import subprocess
import logging
from typing import Dict, Any
from pathlib import Path


class GitTool:
    """Tool for git operations"""

    def __init__(self):
        self.logger = logging.getLogger('GitTool')
        self.project_root = Path(__file__).parent.parent

    def get_schema(self) -> Dict[str, Any]:
        """Get tool schema for Claude API"""
        return {
            "name": "git",
            "description": "Perform git operations: init, clone, add, commit, push, pull, status, etc. Full git command support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Git command to execute (e.g., 'status', 'add .', 'commit -m \"message\"', 'push origin main')"
                    },
                    "repo_url": {
                        "type": "string",
                        "description": "Repository URL (for clone operations)"
                    },
                    "working_dir": {
                        "type": "string",
                        "description": "Working directory (defaults to project root)"
                    }
                },
                "required": ["command"]
            }
        }

    def execute(self, params: Dict[str, Any]) -> str:
        """Execute git command"""
        command = params.get('command')
        working_dir = params.get('working_dir', str(self.project_root))

        if not command:
            return "Error: No command provided"

        # Build full git command
        full_command = f"git {command}"

        self.logger.info(f"Executing git command: {full_command} in {working_dir}")

        try:
            result = subprocess.run(
                full_command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=working_dir,
                timeout=60
            )

            output = ""
            if result.stdout:
                output += f"STDOUT:\n{result.stdout}\n"
            if result.stderr:
                output += f"STDERR:\n{result.stderr}\n"
            output += f"\nReturn code: {result.returncode}"

            if result.returncode == 0:
                self.logger.info(f"Git command executed successfully")
            else:
                self.logger.warning(f"Git command returned non-zero exit code: {result.returncode}")

            return output

        except subprocess.TimeoutExpired:
            error_msg = "Git command timed out after 60 seconds"
            self.logger.error(error_msg)
            return f"Error: {error_msg}"

        except Exception as e:
            error_msg = f"Error executing git command: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return f"Error: {error_msg}"

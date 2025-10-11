"""
Bash Tool - Execute bash commands
"""

import subprocess
import logging
import sys
from typing import Dict, Any


class BashTool:
    """Tool for executing bash commands"""

    def __init__(self):
        self.logger = logging.getLogger('BashTool')

    def get_schema(self) -> Dict[str, Any]:
        """Get tool schema for Ollama API"""
        return {
            "name": "bash",
            "description": """Execute shell commands. Run any command line tool.
Examples:
- List files: {"command": "ls -la"}
- Check Python: {"command": "python --version"}
- Install package: {"command": "pip install requests"}
- Run script: {"command": "python script.py"}
Timeout: 30 seconds default.""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to run. Single command string like 'ls -la' or 'python test.py'"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Maximum seconds to wait before timeout. Default: 30"
                    }
                },
                "required": ["command"]
            }
        }

    def execute(self, params: Dict[str, Any]) -> str:
        """Execute bash command"""
        command = params.get('command')
        timeout = params.get('timeout', 30)

        if not command:
            return "Error: No command provided"

        self.logger.info(f"Executing: {command}")

        try:
            # Detect system encoding (cp1251 on Russian Windows, utf-8 on Linux)
            system_encoding = sys.stdout.encoding or 'utf-8'

            # Execute command
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                encoding=system_encoding,
                errors='replace',  # Replace invalid chars instead of crashing
                timeout=timeout
            )

            # Combine stdout and stderr
            output = ""
            if result.stdout:
                output += f"STDOUT:\n{result.stdout}\n"
            if result.stderr:
                output += f"STDERR:\n{result.stderr}\n"

            output += f"\nReturn code: {result.returncode}"

            self.logger.info(f"Command executed successfully. Return code: {result.returncode}")
            return output

        except subprocess.TimeoutExpired:
            error_msg = f"Command timed out after {timeout} seconds"
            self.logger.error(error_msg)
            return f"Error: {error_msg}"

        except Exception as e:
            error_msg = f"Error executing command: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return f"Error: {error_msg}"

"""
Bash Tool - Execute bash commands
"""

import subprocess
import logging
from typing import Dict, Any


class BashTool:
    """Tool for executing bash commands"""

    def __init__(self):
        self.logger = logging.getLogger('BashTool')

    def get_schema(self) -> Dict[str, Any]:
        """Get tool schema for Claude API"""
        return {
            "name": "bash",
            "description": "Execute bash commands on the system. Use this to run scripts, check files, install packages, etc.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The bash command to execute"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default: 30)",
                        "default": 30
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
            # Execute command
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
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

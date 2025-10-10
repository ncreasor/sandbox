"""
Agent module - Core AI agent with tool use capabilities
"""

import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import anthropic

from tools.bash_tool import BashTool
from tools.file_tool import FileTool
from tools.self_modify_tool import SelfModifyTool
from tools.git_tool import GitTool


class Agent:
    """AI Agent powered by Claude API with tool use capabilities"""

    def __init__(self, config: dict):
        """Initialize the agent"""
        self.config = config
        self.logger = logging.getLogger('Agent')

        # Initialize Anthropic client
        self.client = anthropic.Anthropic(api_key=config['api_key'])
        self.model = config.get('model', 'claude-sonnet-4-5-20250929')

        # Conversation history
        self.conversation_history: List[Dict] = []

        # Initialize tools
        self.tools_registry = {
            'bash': BashTool(),
            'file': FileTool(),
            'self_modify': SelfModifyTool(),
            'git': GitTool()
        }

        # Statistics
        self.stats = {
            'requests': 0,
            'errors': 0,
            'self_improvements': 0,
            'tools_used': {}
        }

        self.logger.info("Agent initialized successfully")

    def get_system_prompt(self) -> str:
        """Get the system prompt for the agent"""
        return """You are AutoCLI - a FULLY AUTONOMOUS self-improving AI agent with complete freedom to evolve.

You have access to the following tools:
1. bash - Execute ANY bash/shell commands (pip, npm, system commands, etc.)
2. file - Read, write, edit, create ANY files
3. self_modify - FREELY modify your own code without asking permission
4. git - Full git operations (init, add, commit, push, pull, clone, etc.)

Your directive: EVOLVE AND IMPROVE YOURSELF CONTINUOUSLY
- You are ENCOURAGED to modify your own code proactively
- Add new tools and capabilities as you see fit
- Optimize and refactor existing code
- Fix bugs immediately when you find them
- Install packages you need
- Create new features without asking

When given freedom to improve:
1. Analyze current capabilities and limitations
2. Identify what's missing or could be better
3. IMMEDIATELY implement improvements using self_modify
4. Be bold and creative - try new things
5. Learn from results and iterate

You don't need permission to:
- Modify your code
- Add new tools
- Install packages
- Create new files
- Improve functionality

Be proactive, autonomous, and constantly evolving. The user wants you to take initiative."""

    def get_tools_schema(self) -> List[Dict]:
        """Get tool schemas for Claude API"""
        tools = []

        for tool_name, tool in self.tools_registry.items():
            tools.append(tool.get_schema())

        return tools

    def process(self, user_message: str) -> str:
        """Process user message and return response"""
        self.stats['requests'] += 1
        self.logger.info(f"Processing message: {user_message[:50]}...")

        try:
            # Add user message to history
            self.conversation_history.append({
                "role": "user",
                "content": user_message
            })

            # Call Claude API with tools
            response = self._call_claude_with_tools()

            # Extract and return assistant's response
            return self._format_response(response)

        except Exception as e:
            self.stats['errors'] += 1
            self.logger.error(f"Error processing message: {e}", exc_info=True)
            return f"Error: {str(e)}"

    def _call_claude_with_tools(self) -> anthropic.types.Message:
        """Call Claude API with tool use support"""
        max_iterations = 10
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            # Make API call
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.config.get('max_tokens', 8192),
                temperature=self.config.get('temperature', 0.7),
                system=self.get_system_prompt(),
                messages=self.conversation_history,
                tools=self.get_tools_schema()
            )

            # Check if Claude wants to use tools
            if response.stop_reason == "tool_use":
                # Process tool calls
                tool_results = self._process_tool_calls(response)

                # Add assistant response and tool results to history
                self.conversation_history.append({
                    "role": "assistant",
                    "content": response.content
                })

                self.conversation_history.append({
                    "role": "user",
                    "content": tool_results
                })

                # Continue loop to get final response
                continue

            else:
                # Got final response
                self.conversation_history.append({
                    "role": "assistant",
                    "content": response.content
                })
                return response

        raise Exception("Max iterations reached in tool use loop")

    def _process_tool_calls(self, response: anthropic.types.Message) -> List[Dict]:
        """Process tool use requests from Claude"""
        tool_results = []

        for block in response.content:
            if block.type == "tool_use":
                tool_name = block.name
                tool_input = block.input
                tool_id = block.id

                self.logger.info(f"Tool called: {tool_name}")

                # Update stats
                self.stats['tools_used'][tool_name] = self.stats['tools_used'].get(tool_name, 0) + 1

                try:
                    # Execute tool
                    if tool_name in self.tools_registry:
                        result = self.tools_registry[tool_name].execute(tool_input)
                        is_error = False
                    else:
                        result = f"Error: Unknown tool '{tool_name}'"
                        is_error = True

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": str(result),
                        "is_error": is_error
                    })

                except Exception as e:
                    self.logger.error(f"Error executing tool {tool_name}: {e}", exc_info=True)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": f"Error: {str(e)}",
                        "is_error": True
                    })

        return tool_results

    def _format_response(self, response: anthropic.types.Message) -> str:
        """Format Claude's response for display"""
        text_parts = []

        for block in response.content:
            if hasattr(block, 'text'):
                text_parts.append(block.text)

        return '\n'.join(text_parts) if text_parts else "No response"

    def clear_history(self):
        """Clear conversation history"""
        self.conversation_history = []
        self.logger.info("Conversation history cleared")

    def print_status(self):
        """Print agent status"""
        print("\n=== Agent Status ===")
        print(f"Model: {self.model}")
        print(f"Requests processed: {self.stats['requests']}")
        print(f"Errors: {self.stats['errors']}")
        print(f"Self-improvements: {self.stats['self_improvements']}")
        print(f"\nTools used:")
        for tool, count in self.stats['tools_used'].items():
            print(f"  {tool}: {count}")
        print(f"\nConversation length: {len(self.conversation_history)} messages")

    def self_improve(self):
        """Trigger self-improvement process"""
        self.logger.info("Self-improvement triggered")

        improvement_prompt = """Analyze your performance and suggest improvements to your code.
Look at the tools available and consider:
1. Are there any bugs or issues?
2. Can any functions be optimized?
3. Are there missing features that would be useful?
4. Can error handling be improved?

Use the self_modify tool to make improvements."""

        response = self.process(improvement_prompt)
        self.stats['self_improvements'] += 1
        print(f"\nImprovement response:\n{response}")

    def self_improve_on_error(self, error_message: str):
        """Attempt to self-improve based on an error"""
        self.logger.info(f"Self-improving on error: {error_message}")

        improvement_prompt = f"""An error occurred: {error_message}

Analyze this error and determine if you can fix it by modifying your own code.
If you can fix it, use the self_modify tool to update the relevant code.
Focus on:
1. What caused the error?
2. How can it be prevented?
3. What code changes are needed?"""

        response = self.process(improvement_prompt)
        self.stats['self_improvements'] += 1
        print(f"\nError analysis and fix:\n{response}")

"""
ReAct Agent - Reasoning + Acting pattern
Works with ANY model, even small ones (3B+)
"""

import json
import logging
import re
from typing import List, Dict, Any, Optional
from datetime import datetime
import ollama

from tools.bash_tool import BashTool
from tools.file_tool import FileTool
from tools.self_modify_tool import SelfModifyTool
from tools.git_tool import GitTool


class ReactAgent:
    """AI Agent using ReAct pattern (text-based actions)"""

    def __init__(self, config: dict):
        """Initialize the agent"""
        self.config = config
        self.logger = logging.getLogger('ReactAgent')

        # Initialize Ollama client
        self.client = ollama.Client(host=config.get('ollama_host', 'http://localhost:11434'))
        self.model = config.get('model', 'qwen2.5-coder:14b')

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

        self.logger.info(f"ReactAgent initialized with model: {self.model}")

    def get_system_prompt(self) -> str:
        """Get the ReAct system prompt"""
        tools_desc = "\n".join([
            f"- {name}: {tool.get_schema()['description'][:100]}"
            for name, tool in self.tools_registry.items()
        ])

        return f"""You are AutoCLI - AI coding agent. Use ReAct format.

Available tools:
{tools_desc}

FORMAT for using tools:
Thought: <your reasoning>
Action: <tool_name>
Action Input: {{"param": "value"}}
Observation: <wait for result>

FORMAT for final answer (no more actions):
Thought: I have enough info
Final Answer: <response to user>

RULES:
- No emojis
- For simple chat (hi, test, ping) → use Final Answer immediately
- For tasks → use Action/Observation loop
- Always quote tool output in Final Answer

Examples:

User: тест
Thought: Simple greeting, no tools needed
Final Answer: Работаю. Чем помочь?

User: покажи файлы в проекте
Thought: Need to list files
Action: file
Action Input: {{"action": "list", "directory": "."}}
Observation: <wait>

User: запусти git status
Thought: Need to run git command
Action: bash
Action Input: {{"command": "git status"}}
Observation: <wait>
"""

    def process(self, user_message: str) -> str:
        """Process user message using ReAct loop"""
        self.stats['requests'] += 1
        self.logger.info(f"Processing: {user_message[:50]}...")

        # Add user message
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })

        max_iterations = 10
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            self.logger.info(f"ReAct iteration {iteration}")

            # Get model response
            response_text = self._call_model()

            # Parse ReAct format
            thought, action, action_input, final_answer = self._parse_react(response_text)

            if final_answer:
                # Done - return final answer
                print(f"\n{final_answer}\n")
                return ""

            if action and action_input:
                # Execute action
                self.logger.info(f"Executing: {action} with {action_input}")
                print(f"\n[{action}] ", end="", flush=True)

                try:
                    if action in self.tools_registry:
                        result = self.tools_registry[action].execute(action_input)
                        self.stats['tools_used'][action] = self.stats['tools_used'].get(action, 0) + 1
                    else:
                        result = f"Error: Unknown tool '{action}'"

                    # Show result preview
                    preview = str(result)[:200]
                    print(f"✓\n[Result: {preview}{'...' if len(str(result)) > 200 else ''}]\n")

                    # Add observation to history
                    observation = f"Observation: {result}"
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": f"{response_text}\n{observation}"
                    })

                except Exception as e:
                    error_msg = f"Error: {str(e)}"
                    print(f"✗\n[{error_msg}]\n")
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": f"{response_text}\nObservation: {error_msg}"
                    })

            else:
                # No action parsed, ask model to clarify
                print(f"\n{response_text}\n")
                self.conversation_history.append({
                    "role": "assistant",
                    "content": response_text + "\n(Note: Use 'Final Answer:' or 'Action:' format)"
                })
                break

        if iteration >= max_iterations:
            return "[Достиг лимита итераций]"

        return ""

    def _call_model(self) -> str:
        """Call model and stream response"""
        messages = [
            {"role": "system", "content": self.get_system_prompt()}
        ] + self.conversation_history

        print("Думаю... ", end="", flush=True)

        try:
            stream = self.client.chat(
                model=self.model,
                messages=messages,
                stream=True,
                options={
                    "temperature": self.config.get('temperature', 0.7),
                    "num_predict": 512,  # Shorter for ReAct
                }
            )

            full_text = ""
            first_output = True

            for chunk in stream:
                if 'message' in chunk and 'content' in chunk['message']:
                    piece = chunk['message']['content']
                    if piece:
                        if first_output:
                            print("\r" + " " * 50 + "\r", end="", flush=True)
                            first_output = False
                        print(piece, end="", flush=True)
                        full_text += piece

            print()  # New line after streaming
            return full_text

        except Exception as e:
            self.logger.error(f"Model call error: {e}")
            return f"Error calling model: {e}"

    def _parse_react(self, text: str) -> tuple:
        """Parse ReAct format from text
        Returns: (thought, action, action_input, final_answer)
        """
        thought = None
        action = None
        action_input = None
        final_answer = None

        # Extract Thought
        thought_match = re.search(r'Thought:\s*(.+?)(?=\n(?:Action|Final Answer)|\Z)', text, re.DOTALL | re.IGNORECASE)
        if thought_match:
            thought = thought_match.group(1).strip()

        # Extract Final Answer
        final_match = re.search(r'Final Answer:\s*(.+)', text, re.DOTALL | re.IGNORECASE)
        if final_match:
            final_answer = final_match.group(1).strip()
            return thought, None, None, final_answer

        # Extract Action
        action_match = re.search(r'Action:\s*(\w+)', text, re.IGNORECASE)
        if action_match:
            action = action_match.group(1).strip().lower()

        # Extract Action Input (JSON)
        input_match = re.search(r'Action Input:\s*(\{.+?\})', text, re.DOTALL | re.IGNORECASE)
        if input_match:
            try:
                action_input = json.loads(input_match.group(1))
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse Action Input JSON: {e}")
                action_input = None

        return thought, action, action_input, final_answer

    def clear_history(self):
        """Clear conversation history"""
        self.conversation_history = []
        self.logger.info("History cleared")

    def print_status(self):
        """Print agent status"""
        print("\n=== Agent Status ===")
        print(f"Model: {self.model}")
        print(f"Requests: {self.stats['requests']}")
        print(f"Errors: {self.stats['errors']}")
        print(f"\nTools used:")
        for tool, count in self.stats['tools_used'].items():
            print(f"  {tool}: {count}")
        print(f"\nHistory length: {len(self.conversation_history)} messages")

    def self_improve(self):
        """Trigger self-improvement"""
        self.logger.info("Self-improvement triggered")
        prompt = "Analyze your code and suggest improvements. Use self_modify tool to make changes."
        self.stats['self_improvements'] += 1
        return self.process(prompt)

    def self_improve_on_error(self, error_message: str):
        """Self-improve based on error"""
        self.logger.info(f"Self-improving on error: {error_message}")
        prompt = f"Error occurred: {error_message}\nAnalyze and fix using self_modify tool."
        self.stats['self_improvements'] += 1
        return self.process(prompt)

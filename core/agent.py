"""
Agent module - Core AI agent with tool use capabilities (Ollama version)
"""

import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import ollama

from tools.bash_tool import BashTool
from tools.file_tool import FileTool
from tools.self_modify_tool import SelfModifyTool
from tools.git_tool import GitTool


class Agent:
    """AI Agent powered by Ollama with tool use capabilities"""

    def __init__(self, config: dict):
        """Initialize the agent"""
        self.config = config
        self.logger = logging.getLogger('Agent')

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

        self.logger.info(f"Agent initialized with Ollama model: {self.model}")

    def get_system_prompt(self) -> str:
        """Get the system prompt for the agent"""
        return """You are AutoCLI - a self-improving AI coding agent with access to tools.

YOUR CURRENT CAPABILITIES:
- Already using STREAMING mode (shows "Думаю...", "Выполняю..." indicators)
- Already using real-time tool result display
- Using Ollama API with qwen3:8b model
- Located in core/agent.py with method _call_ollama_with_tools_streaming()

IMPORTANT RULES:
1. NO emojis in responses
2. Answer DIRECTLY for simple questions (who are you, how are you, etc) - DO NOT use tools
3. For file/code analysis - MUST use tools (file, bash, etc)
4. When asked to analyze project structure - use file tool to list/read files
5. When asked to modify yourself - use self_modify tool
6. If asked about streaming/polling - acknowledge you ALREADY use streaming

WHEN TO USE TOOLS:
✓ User asks to analyze/read files → use file tool
✓ User asks to run commands → use bash tool
✓ User asks about project structure → use file tool to list directories
✓ User asks you to change/improve yourself → use self_modify tool
✓ User asks to work with git → use git tool

WHEN NOT TO USE TOOLS:
✗ Simple questions like "who are you", "how are you"
✗ Asking for your opinion/suggestions
✗ General conversation

CRITICAL: Quote actual tool output!
Good: "Выполнил ls -la:\n[actual output]\nВижу что..."
Bad: "Я посмотрел файлы и все хорошо" ← LYING if didn't actually run command!

For multi-step tasks (like git push), run ALL steps and quote each result."""

    def get_tools_schema(self) -> List[Dict]:
        """Get tool schemas in Ollama format"""
        tools = []

        for tool_name, tool in self.tools_registry.items():
            schema = tool.get_schema()

            # Convert Anthropic format to Ollama format
            ollama_tool = {
                "type": "function",
                "function": {
                    "name": schema["name"],
                    "description": schema["description"],
                    "parameters": schema["input_schema"]
                }
            }
            tools.append(ollama_tool)

        return tools

    def process(self, user_message: str) -> str:
        """Process user message and return response"""
        self.stats['requests'] += 1
        self.logger.info(f"Processing message: {user_message[:50]}...")

        print("Думаю... ", end="", flush=True)

        try:
            # Auto-clear history if too long (save memory)
            if len(self.conversation_history) > 100:
                self.conversation_history = self.conversation_history[-6:]
                self.logger.info("Auto-cleared old conversation history")

            # Add user message to history
            self.conversation_history.append({
                "role": "user",
                "content": user_message
            })

            # Call Ollama with tools (streaming mode)
            final_response = self._call_ollama_with_tools_streaming()

            # Check if we got a meaningful response
            if final_response:
                formatted = self._format_response(final_response)
                # If response was already printed in streaming, return empty
                # Otherwise return it for CLI to print
                if formatted and formatted not in ["Processing...", "No response", "[Tool call parsed]"]:
                    return ""  # Already printed

            return ""

        except Exception as e:
            self.stats['errors'] += 1
            self.logger.error(f"Error processing message: {e}", exc_info=True)
            return f"Error: {str(e)}"

    def _call_ollama_with_tools_streaming(self) -> dict:
        """Call Ollama API with tool use support - streaming mode (shows progress)"""
        max_iterations = 10  # Prevent infinite loops
        iteration = 0

        # Prepend system prompt to messages
        messages = [
            {"role": "system", "content": self.get_system_prompt()}
        ] + self.conversation_history

        while iteration < max_iterations:
            iteration += 1

            # Add delay for rate limiting on cloud models
            if iteration > 1:
                import time
                time.sleep(0.5)  # 500ms delay between iterations

            # Make API call
            self.logger.info(f"Iteration {iteration}: Calling Ollama API...")
            try:
                response = self.client.chat(
                    model=self.model,
                    messages=messages,
                    tools=self.get_tools_schema(),
                    options={
                        "temperature": self.config.get('temperature', 0.7),
                        "num_predict": self.config.get('max_tokens', 1024),  # Reduced to speed up
                    }
                )
                self.logger.info(f"Iteration {iteration}: Got response from Ollama")
            except KeyboardInterrupt:
                print("\r" + " " * 50 + "\r", end="", flush=True)
                print("\n[Прервано пользователем]", flush=True)
                raise
            except Exception as e:
                self.logger.error(f"Error calling Ollama: {e}")
                raise

            # Debug: log what we got from model
            msg = response['message']
            content = msg.get('content', '')
            self.logger.info(f"Model response - content: {content[:100]}")
            self.logger.info(f"Model response - tool_calls: {msg.get('tool_calls')}")

            # Check if model wants to use tools
            # WORKAROUND: qwen2.5-coder returns JSON in content instead of using tool_calls
            tool_calls = response['message'].get('tool_calls')

            if not tool_calls:
                # Try to parse tool call from content (workaround for models that don't use tool_calls properly)
                tool_calls = self._parse_tool_calls_from_content(content)

                # If we parsed tool calls from content, clear the content to avoid confusion
                if tool_calls:
                    response['message']['content'] = '[Tool call parsed]'
                    self.logger.info("Cleared content after parsing tool call")

            # Add assistant response to history (after potential content modification)
            self.conversation_history.append(response['message'])

            if not tool_calls:
                # No tool calls, return final response
                self.logger.info(f"Iteration {iteration}: No tool calls, returning response")
                # Clear status and show response
                print("\r" + " " * 50 + "\r", end="", flush=True)

                # Show response if it's meaningful
                formatted = self._format_response(response)
                if formatted and formatted not in ["Processing...", "No response", "[Tool call parsed]"]:
                    print(f"\n{formatted}", flush=True)

                return response

            # Process tool calls
            self.logger.info(f"Iteration {iteration}: Processing {len(tool_calls)} tool calls")
            print("\rВыполняю... ", end="", flush=True)
            tool_results = self._process_tool_calls(tool_calls)

            # Add results to history AND show them to prevent hallucinations
            print("\r" + " " * 50 + "\r", end="", flush=True)
            for tool_result in tool_results:
                # Show tool result immediately
                result_preview = tool_result['content'][:300]
                if len(tool_result['content']) > 300:
                    result_preview += "..."
                print(f"[Результат: {result_preview}]", flush=True)

                self.conversation_history.append(tool_result)
                self.logger.info(f"Tool result added: {tool_result['content'][:100]}...")

            print("Думаю... ", end="", flush=True)

            # Update messages for next iteration
            messages = [
                {"role": "system", "content": self.get_system_prompt()}
            ] + self.conversation_history

            # Continue loop to get final response
            # But keep track of tool results for fallback
            self._last_tool_results = tool_results

        # If we're on the last iteration, force a response
        self.logger.warning(f"Max iterations ({max_iterations}) reached, forcing final response")
        print("\r" + " " * 50 + "\r", end="", flush=True)

        # If we have tool results but no final answer, show the results
        if hasattr(self, '_last_tool_results') and self._last_tool_results:
            result_text = "\n\n".join([r['content'] for r in self._last_tool_results[-3:]])
            print(f"\n{result_text}\n\n[Модель не дала финальный ответ после {max_iterations} итераций]", flush=True)
        else:
            print(f"\n[Достиг лимита {max_iterations} итераций]", flush=True)

        return {
            'message': {
                'content': ""
            }
        }

    def _call_ollama_with_tools(self) -> dict:
        """Call Ollama API with tool use support"""
        max_iterations = 10  # Prevent infinite loops
        iteration = 0

        # Prepend system prompt to messages
        messages = [
            {"role": "system", "content": self.get_system_prompt()}
        ] + self.conversation_history

        while iteration < max_iterations:
            iteration += 1

            # Add delay for rate limiting on cloud models
            if iteration > 1:
                import time
                time.sleep(0.5)  # 500ms delay between iterations

            # Make API call
            self.logger.info(f"Iteration {iteration}: Calling Ollama API...")
            try:
                response = self.client.chat(
                    model=self.model,
                    messages=messages,
                    tools=self.get_tools_schema(),
                    options={
                        "temperature": self.config.get('temperature', 0.7),
                        "num_predict": self.config.get('max_tokens', 1024),  # Reduced to speed up
                    }
                )
                self.logger.info(f"Iteration {iteration}: Got response from Ollama")
            except KeyboardInterrupt:
                print("\n[Прервано пользователем]", flush=True)
                raise
            except Exception as e:
                self.logger.error(f"Error calling Ollama: {e}")
                raise

            # Debug: log what we got from model
            msg = response['message']
            content = msg.get('content', '')
            self.logger.info(f"Model response - content: {content[:100]}")
            self.logger.info(f"Model response - tool_calls: {msg.get('tool_calls')}")

            # Check if model wants to use tools
            # WORKAROUND: qwen2.5-coder returns JSON in content instead of using tool_calls
            tool_calls = response['message'].get('tool_calls')

            if not tool_calls:
                # Try to parse tool call from content (workaround for models that don't use tool_calls properly)
                tool_calls = self._parse_tool_calls_from_content(content)

                # If we parsed tool calls from content, clear the content to avoid confusion
                if tool_calls:
                    response['message']['content'] = '[Tool call parsed]'
                    self.logger.info("Cleared content after parsing tool call")

            # Add assistant response to history (after potential content modification)
            self.conversation_history.append(response['message'])

            if not tool_calls:
                # No tool calls, return final response
                self.logger.info(f"Iteration {iteration}: No tool calls, returning response")
                return response

            # Process tool calls
            self.logger.info(f"Iteration {iteration}: Processing {len(tool_calls)} tool calls")
            tool_results = self._process_tool_calls(tool_calls)

            # Add tool results to history
            for tool_result in tool_results:
                self.conversation_history.append(tool_result)
                self.logger.info(f"Tool result added: {tool_result['content'][:100]}...")

            # Update messages for next iteration
            messages = [
                {"role": "system", "content": self.get_system_prompt()}
            ] + self.conversation_history

            # Continue loop to get final response
            # But keep track of tool results for fallback
            self._last_tool_results = tool_results

        # If we're on the last iteration, force a response
        self.logger.warning(f"Max iterations ({max_iterations}) reached, forcing final response")
        return {
            'message': {
                'content': f"Достиг лимита {max_iterations} итераций. Использовал tools, но не успел завершить анализ. Попробуй задать более конкретный вопрос."
            }
        }

    def _parse_tool_calls_from_content(self, content: str) -> List[Dict]:
        """Parse tool calls from model response content (workaround for models that return JSON in content)"""
        if not content or not content.strip():
            return []

        try:
            # Check if content contains JSON (with or without markdown code blocks)
            content = content.strip()

            # Remove markdown code blocks if present
            if content.startswith('```'):
                lines = content.split('\n')
                # Remove first line (```json or ```)
                lines = lines[1:]
                # Remove last line if it's ```
                if lines and lines[-1].strip() == '```':
                    lines = lines[:-1]
                content = '\n'.join(lines).strip()

            # Try to parse as JSON
            parsed = json.loads(content)

            # Check if it looks like a tool call
            if isinstance(parsed, dict) and 'name' in parsed:
                # Convert to Ollama tool_calls format
                tool_call = {
                    'function': {
                        'name': parsed.get('name'),
                        'arguments': parsed.get('arguments', {})
                    }
                }
                self.logger.info(f"Parsed tool call from content: {tool_call}")
                return [tool_call]

        except json.JSONDecodeError:
            # Not valid JSON, return empty
            pass
        except Exception as e:
            self.logger.error(f"Error parsing tool call from content: {e}")

        return []

    def _process_tool_calls(self, tool_calls: List[Dict]) -> List[Dict]:
        """Process tool use requests from Ollama"""
        tool_results = []

        for tool_call in tool_calls:
            try:
                # Safely extract function info
                function = tool_call.get('function', {})
                tool_name = function.get('name')
                tool_args = function.get('arguments', {})

                if not tool_name:
                    self.logger.warning(f"Skipping malformed tool call: {tool_call}")
                    continue

                self.logger.info(f"Tool called: {tool_name} with args: {tool_args}")

                # Update stats
                self.stats['tools_used'][tool_name] = self.stats['tools_used'].get(tool_name, 0) + 1

                # Execute tool
                if tool_name in self.tools_registry:
                    result = self.tools_registry[tool_name].execute(tool_args)
                else:
                    result = f"Error: Unknown tool '{tool_name}'"

                tool_results.append({
                    "role": "tool",
                    "content": str(result)
                })

            except Exception as e:
                self.logger.error(f"Error processing tool call: {e}", exc_info=True)
                tool_results.append({
                    "role": "tool",
                    "content": f"Error processing tool: {str(e)}"
                })

        return tool_results

    def _format_response(self, response: dict) -> str:
        """Format Ollama's response for display"""
        message = response.get('message', {})
        content = message.get('content', '')

        # Skip empty responses or tool call JSON
        if not content or not content.strip():
            # If we have tool results, show the last one
            if hasattr(self, '_last_tool_results') and self._last_tool_results:
                return self._last_tool_results[-1]['content']
            return "No response"

        # Check if this is our placeholder text
        if content.strip() == '[Tool call parsed]':
            if hasattr(self, '_last_tool_results') and self._last_tool_results:
                return self._last_tool_results[-1]['content']
            return "Processing..."

        # Remove <think> blocks from qwen3 model
        import re
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
        content = content.strip()

        # Skip if content looks like tool call JSON
        # Check for JSON with "name" field (tool call) or markdown code blocks with JSON
        stripped = content.strip()
        if stripped.startswith('```'):
            # Remove markdown wrapper and check
            lines = stripped.split('\n')
            if len(lines) > 2:
                inner = '\n'.join(lines[1:-1]).strip()
                if inner.startswith('{') and '"name"' in inner:
                    # It's a tool call in markdown
                    if hasattr(self, '_last_tool_results') and self._last_tool_results:
                        return self._last_tool_results[-1]['content']
                    return "Processing..."
        elif stripped.startswith('{') and '"name"' in content:
            # Plain JSON tool call
            if hasattr(self, '_last_tool_results') and self._last_tool_results:
                return self._last_tool_results[-1]['content']
            return "Processing..."

        return content if content else "No response"

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

    def add_tool(self, tool_name: str, tool_class):
        """Add a new tool to the agent's toolkit"""
        self.tools_registry[tool_name] = tool_class()
        self.logger.info(f"Added new tool: {tool_name}")
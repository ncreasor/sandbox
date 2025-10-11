#!/usr/bin/env python3
"""
AutoCLI - Self-improving CLI agent
Main entry point for the application
"""

import sys
import json
import logging
from pathlib import Path
from typing import Optional

from core.agent_react import ReactAgent as Agent


class AutoCLI:
    """Main CLI application class"""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize AutoCLI"""
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "config.json"

        self.config = self._load_config(config_path)
        self._setup_logging()
        self.agent = Agent(self.config)
        self.running = True
        self.history_file = Path(__file__).parent.parent / "logs" / "history.json"

        # Load history if exists
        self._load_history()

    def _load_config(self, config_path: Path) -> dict:
        """Load configuration from JSON file"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            sys.exit(1)

    def _setup_logging(self):
        """Setup logging configuration"""
        if not self.config.get('logging', {}).get('enabled', True):
            return

        log_level = self.config.get('logging', {}).get('level', 'INFO')
        log_file = Path(__file__).parent.parent / self.config.get('logging', {}).get('file', 'logs/autocli.log')

        # Create logs directory if it doesn't exist
        log_file.parent.mkdir(parents=True, exist_ok=True)

        logging.basicConfig(
            level=getattr(logging, log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8')
                # Removed StreamHandler - logs only to file now
            ]
        )

        # Suppress noisy loggers
        logging.getLogger('httpx').setLevel(logging.WARNING)
        logging.getLogger('ollama').setLevel(logging.WARNING)

        self.logger = logging.getLogger('AutoCLI')

    def print_banner(self):
        """Print welcome banner"""
        model_name = self.config.get('model', 'qwen2.5-coder:14b')
        banner = f"""
+-------------------------------------------+
|         AutoCLI v0.1.0                    |
|    Self-improving AI Agent                |
|    Powered by Ollama ({model_name})       |
+-------------------------------------------+

Type 'help' for commands, 'exit' to quit
Type anything else to chat with the agent
        """
        print(banner)

    def _load_history(self):
        """Load conversation history from file"""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
                    self.agent.conversation_history = history
                    self.logger.info(f"Loaded {len(history)} messages from history")
            except Exception as e:
                self.logger.error(f"Failed to load history: {e}")

    def _save_history(self):
        """Save conversation history to file"""
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.agent.conversation_history, f, ensure_ascii=False, indent=2)
            self.logger.info("History saved")
        except Exception as e:
            self.logger.error(f"Failed to save history: {e}")

    def print_help(self):
        """Print help message"""
        help_text = """
Available commands:
  help              - Show this help message
  exit, quit        - Exit the CLI
  clear             - Clear conversation history
  status            - Show agent status
  improve           - Trigger self-improvement
  config            - Show current configuration
  restart           - Save history and restart agent

  Or just type your request naturally!
        """
        print(help_text)

    def run(self):
        """Main CLI loop"""
        self.print_banner()

        while self.running:
            try:
                user_input = input("\n> ").strip()

                if not user_input:
                    continue

                # Handle built-in commands
                if user_input.lower() in ['exit', 'quit']:
                    print("Сохраняю историю...")
                    self._save_history()
                    print("Goodbye!")
                    self.running = False
                    break

                elif user_input.lower() == 'help':
                    self.print_help()
                    continue

                elif user_input.lower() == 'clear':
                    self.agent.clear_history()
                    print("Conversation history cleared.")
                    continue

                elif user_input.lower() == 'status':
                    self.agent.print_status()
                    continue

                elif user_input.lower() == 'improve':
                    print("Triggering self-improvement...")
                    self.agent.self_improve()
                    continue

                elif user_input.lower() == 'config':
                    print(json.dumps(self.config, indent=2))
                    continue

                elif user_input.lower() == 'restart':
                    print("Сохраняю историю и перезапускаюсь...")
                    self._save_history()
                    import os
                    import sys
                    os.execv(sys.executable, [sys.executable] + sys.argv)

                # Process user input through agent
                response = self.agent.process(user_input)
                if response:  # Only print if not empty (streaming mode prints directly)
                    print(f"\n{response}")

            except KeyboardInterrupt:
                print("\n\nInterrupted. Type 'exit' to quit.")
            except Exception as e:
                self.logger.error(f"Error in main loop: {e}", exc_info=True)
                print(f"\nError: {e}")

                # Auto-improve on error if enabled
                if self.config.get('self_improvement', {}).get('auto_improve_on_error', False):
                    print("\nAttempting self-improvement...")
                    self.agent.self_improve_on_error(str(e))


def main():
    """Entry point for the CLI"""
    cli = AutoCLI()
    cli.run()


if __name__ == "__main__":
    main()
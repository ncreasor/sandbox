#!/usr/bin/env python3
"""
Test script to verify all modules can be imported correctly
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

print("Testing AutoCLI imports...")
print("=" * 50)

try:
    print("\n1. Testing core imports...")
    from core import cli
    from core import agent
    print("   [OK] Core modules imported successfully")

    print("\n2. Testing tools imports...")
    from tools import bash_tool
    from tools import file_tool
    from tools import self_modify_tool
    print("   [OK] Tool modules imported successfully")

    print("\n3. Testing tool instantiation...")
    bash = bash_tool.BashTool()
    file = file_tool.FileTool()
    self_mod = self_modify_tool.SelfModifyTool()
    print("   [OK] All tools instantiated successfully")

    print("\n4. Testing tool schemas...")
    bash_schema = bash.get_schema()
    file_schema = file.get_schema()
    self_mod_schema = self_mod.get_schema()
    print(f"   [OK] Bash tool: {bash_schema['name']}")
    print(f"   [OK] File tool: {file_schema['name']}")
    print(f"   [OK] Self-modify tool: {self_mod_schema['name']}")

    print("\n5. Testing config loading...")
    import json
    config_path = project_root / "config" / "config.json"
    with open(config_path, 'r') as f:
        config = json.load(f)
    print(f"   [OK] Config loaded: model={config['model']}")

    print("\n" + "=" * 50)
    print("[SUCCESS] All tests passed! AutoCLI is ready to use.")
    print("\nTo start AutoCLI, run:")
    print("  python core/cli.py")
    print("\nor")
    print("  python -m core.cli")

except Exception as e:
    print(f"\n[ERROR] Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

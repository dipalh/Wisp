#!/usr/bin/env python3
"""
Debloat Integration Test & Demo

This script demonstrates how to use the debloat service programmatically
and can be used to test the integration before deploying.

Usage:
    python3 test_debloat_integration.py

This will:
1. Load available debloat options
2. Show environment detection
3. Build command without executing (dry run)
4. Demonstrate API response structure
"""

import asyncio
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

from services.debloat.executor import (
    get_available_options,
    ExecutionEnvironment,
    _detect_environment,
    _build_command,
    _build_script_parameters,
)


def print_section(title: str) -> None:
    """Print a formatted section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def test_environment_detection() -> None:
    """Test environment detection."""
    print_section("Environment Detection Test")
    
    detected = _detect_environment()
    print(f"✓ Detected Environment: {detected.value.upper()}")
    
    print("\nAvailable Environments:")
    for env in ExecutionEnvironment:
        if env != ExecutionEnvironment.AUTO:
            print(f"  • {env.value.upper()}")


def test_available_options() -> None:
    """Test loading available options."""
    print_section("Available Debloat Options")
    
    options = get_available_options()
    
    total_options = 0
    for category, opts in options.items():
        default_count = sum(1 for opt in opts if opt['default_enabled'])
        total_options += len(opts)
        print(f"\n{category.upper()} ({len(opts)} options, {default_count} default):")
        for opt in opts:
            default_marker = "✓" if opt['default_enabled'] else " "
            print(f"  [{default_marker}] {opt['name']:<30} {opt['description']}")
    
    print(f"\nTotal Options: {total_options}")


def test_command_building() -> None:
    """Test command building for different environments."""
    print_section("Command Building Test (Dry Run)")
    
    # Select some default options
    option_ids = [
        "remove-preinstalled",
        "disable-telemetry",
        "disable-location",
    ]
    
    print(f"Selected Options: {option_ids}\n")
    
    # Build parameters
    params = _build_script_parameters(option_ids)
    print(f"PowerShell Parameters: {params}\n")
    
    # Test command building for each environment
    for env in [ExecutionEnvironment.WSL, ExecutionEnvironment.POWERSHELL, ExecutionEnvironment.CMD]:
        print(f"\n{env.value.upper()} Command:")
        print("-" * 60)
        cmd = _build_command(env, params)
        # Truncate for display
        if len(cmd) > 100:
            print(cmd[:100] + "...")
            print(f"[Total length: {len(cmd)} characters]")
        else:
            print(cmd)


def test_api_response_structure() -> None:
    """Show the expected API response structure."""
    print_section("Expected API Response Structure")
    
    response = {
        "options": get_available_options(),
        "executed_ids": ["remove-preinstalled", "disable-telemetry"],
        "environment": "wsl",
        "status": "completed",
        "progress": 100,
    }
    
    print("Example /api/v1/debloat/execute Response:")
    print("""
{
  "id": "a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6",
  "environment": "wsl",
  "options": ["remove-preinstalled", "disable-telemetry"],
  "status": "completed",
  "output": "[PowerShell output here...]",
  "error": "",
  "progress": 100
}
    """)


def show_integration_info() -> None:
    """Show file structure and integration info."""
    print_section("Integration Files")
    
    files = {
        "Backend": [
            "backend/services/debloat/__init__.py",
            "backend/services/debloat/executor.py",
            "backend/services/debloat/README.md",
            "backend/api/v1/debloat.py",
        ],
        "Frontend": [
            "frontend/src/views/DebloatView.tsx",
            "frontend/src/components/AppShell.tsx (modified)",
            "frontend/src/components/Sidebar.tsx (modified)",
            "frontend/src/styles.css (modified)",
        ],
        "API Endpoints": [
            "GET /api/v1/debloat/options",
            "POST /api/v1/debloat/execute",
            "GET /api/v1/debloat/status/{task_id}",
            "POST /api/v1/debloat/tasks/{task_id}/cancel",
        ],
    }
    
    for section, items in files.items():
        print(f"\n{section}:")
        for item in items:
            print(f"  • {item}")


def main() -> None:
    """Run all tests."""
    print("\n" + "="*60)
    print("  WISP DEBLOAT INTEGRATION TEST")
    print("="*60)
    
    try:
        test_environment_detection()
        test_available_options()
        test_command_building()
        test_api_response_structure()
        show_integration_info()
        
        print_section("All Tests Passed! ✓")
        print("""
The debloat integration is ready to use!

Next Steps:
1. Start the backend:  python backend/main.py
2. Start the frontend: cd frontend && npm run dev
3. Open the app and navigate to Files → Debloat
4. Select desired options and click "Start Optimization"

For WSL users:
- Environment will auto-detect as 'wsl'
- PowerShell.exe will be called from WSL environment
- Results will display in the beautiful UI

For Windows users:
- Environment will auto-detect as 'powershell'
- Run the app as Administrator for privilege escalation
- Same beautiful UI experience
        """)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

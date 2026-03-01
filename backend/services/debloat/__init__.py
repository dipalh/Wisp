"""
Windows debloating service.

Wraps the Win11Debloat PowerShell script with support for:
- WSL (Windows Subsystem for Linux)
- CMD (Command Prompt)
- PowerShell

Provides category-based debloating options.
"""
from .executor import (
    DebloatOption,
    DebloatTask,
    ExecutionEnvironment,
    execute_debloat,
    get_available_options,
)

__all__ = [
    "DebloatOption",
    "DebloatTask",
    "ExecutionEnvironment",
    "execute_debloat",
    "get_available_options",
]

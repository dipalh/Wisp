"""
Debloat execution engine.

Handles running Win11Debloat with different environments and options.
"""
import asyncio
import base64
import json
import logging
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from pathlib import Path
import platform

logger = logging.getLogger(__name__)


class ExecutionEnvironment(str, Enum):
    """Execution environment for debloat script."""
    WSL = "wsl"
    POWERSHELL = "powershell"
    CMD = "cmd"
    AUTO = "auto"  # Auto-detect


@dataclass
class DebloatSubOption:
    """A granular sub-option within a debloat category."""
    id: str
    name: str
    description: str
    parameters: list[str] = field(default_factory=list)
    default_enabled: bool = False


@dataclass
class DebloatOption:
    """A debloat configuration option."""
    id: str
    name: str
    description: str
    category: str
    parameters: list[str] = field(default_factory=list)
    default_enabled: bool = False
    sub_options: list[DebloatSubOption] = field(default_factory=list)


@dataclass
class DebloatTask:
    """A debloat task execution record."""
    id: str
    environment: ExecutionEnvironment
    options: list[str]
    status: str = "pending"  # pending, running, completed, failed
    output: str = ""
    error: str = ""
    progress: int = 0  # 0-100


ALLOWED_SWITCHES = {
    "RemoveApps",
    "DisableTelemetry",
    "DisableSuggestions",
    "DisableLocationServices",
    "DisableBing",
    "DisableCopilot",
    "DisableRecall",
    "DisableGameBarIntegration",
    "ForceRemoveEdge",
    "DisableFastStartup",
    "DisableBitlockerAutoEncryption",
    "DisableDeliveryOptimization",
    "DisableUpdateASAP",
    "PreventUpdateAutoReboot",
    "EnableDarkMode",
    "DisableAnimations",
    "DisableStickyKeys",
    "DisableMouseAcceleration",
    "DisableDragTray",
    "DisableModernStandbyNetworking",
}


# Available debloat options categorized
DEBLOAT_OPTIONS = {
    "apps": [
        DebloatOption(
            id="remove-preinstalled",
            name="Remove Preinstalled Apps",
            description="Selectively remove Microsoft bloatware",
            category="apps",
            parameters=[],
            default_enabled=False,
            sub_options=[
                DebloatSubOption(
                    id="remove-preinstalled-candy-crush",
                    name="Candy Crush",
                    description="Remove Candy Crush Saga",
                    parameters=["AppId:king.com.CandyCrushSaga"],
                    default_enabled=True,
                ),
                DebloatSubOption(
                    id="remove-preinstalled-weather",
                    name="Weather",
                    description="Remove Weather app",
                    parameters=["AppId:Microsoft.BingWeather"],
                    default_enabled=True,
                ),
                DebloatSubOption(
                    id="remove-preinstalled-maps",
                    name="Maps",
                    description="Remove Maps app",
                    parameters=["AppId:Microsoft.WindowsMaps"],
                    default_enabled=False,
                ),
                DebloatSubOption(
                    id="remove-preinstalled-news",
                    name="News",
                    description="Remove News app",
                    parameters=["AppId:Microsoft.BingNews"],
                    default_enabled=False,
                ),
                DebloatSubOption(
                    id="remove-preinstalled-sports",
                    name="Sports",
                    description="Remove Sports app",
                    parameters=["AppId:Microsoft.BingSports"],
                    default_enabled=False,
                ),
                DebloatSubOption(
                    id="remove-preinstalled-stocks",
                    name="Stocks",
                    description="Remove Stocks app",
                    parameters=["AppId:Microsoft.BingFinance"],
                    default_enabled=False,
                ),
                DebloatSubOption(
                    id="remove-preinstalled-tips",
                    name="Windows Tips",
                    description="Remove Windows Tips app",
                    parameters=["AppId:Microsoft.Getstarted"],
                    default_enabled=True,
                ),
                DebloatSubOption(
                    id="remove-preinstalled-xbox",
                    name="Xbox App",
                    description="Remove Xbox app",
                    parameters=["AppId:Microsoft.XboxApp"],
                    default_enabled=False,
                ),
                DebloatSubOption(
                    id="remove-preinstalled-people",
                    name="People",
                    description="Remove People app",
                    parameters=["AppId:Microsoft.People"],
                    default_enabled=False,
                ),
                DebloatSubOption(
                    id="remove-preinstalled-zune",
                    name="Groove Music",
                    description="Remove Groove Music app",
                    parameters=["AppId:Microsoft.ZuneMusic"],
                    default_enabled=False,
                ),
            ],
        ),
        DebloatOption(
            id="remove-gamebar",
            name="Remove Xbox Game Bar",
            description="Disable Xbox Game Bar and gaming features",
            category="apps",
            parameters=["DisableGameBarIntegration"],
            default_enabled=False,
        ),
        DebloatOption(
            id="remove-edge",
            name="Remove Microsoft Edge",
            description="Remove Microsoft Edge browser",
            category="apps",
            parameters=["ForceRemoveEdge"],
            default_enabled=False,
        ),
        DebloatOption(
            id="remove-onedrive",
            name="Remove OneDrive",
            description="Remove Microsoft OneDrive cloud storage",
            category="apps",
            parameters=["RemoveOneDrive"],
            default_enabled=False,
        ),
        DebloatOption(
            id="remove-paint3d",
            name="Remove Paint 3D",
            description="Remove Paint 3D application",
            category="apps",
            parameters=["RemovePaint3D"],
            default_enabled=False,
        ),
        DebloatOption(
            id="remove-3dviewer",
            name="Remove 3D Viewer",
            description="Remove 3D Viewer and model viewers",
            category="apps",
            parameters=["Remove3DViewer"],
            default_enabled=False,
        ),
    ],
    "privacy": [
        DebloatOption(
            id="disable-telemetry",
            name="Disable Telemetry",
            description="Stop sending usage data to Microsoft",
            category="privacy",
            parameters=["DisableTelemetry"],
            default_enabled=True,
        ),
        DebloatOption(
            id="disable-location",
            name="Disable Location Services",
            description="Turn off location tracking",
            category="privacy",
            parameters=["DisableLocationServices"],
            default_enabled=True,
        ),
        DebloatOption(
            id="disable-suggestions",
            name="Disable Suggestions",
            description="Remove tips, app suggestions, and ads",
            category="privacy",
            parameters=["DisableSuggestions"],
            default_enabled=True,
        ),
        DebloatOption(
            id="disable-activity-history",
            name="Disable Activity History",
            description="Stop tracking activity history",
            category="privacy",
            parameters=["DisableActivityHistory"],
            default_enabled=False,
        ),
        DebloatOption(
            id="disable-advertising-id",
            name="Disable Advertising ID",
            description="Turn off advertising tracking ID",
            category="privacy",
            parameters=["DisableAdvertisingID"],
            default_enabled=False,
        ),
        DebloatOption(
            id="disable-app-suggestions",
            name="Disable App Store Suggestions",
            description="Stop Microsoft Store suggestions",
            category="privacy",
            parameters=["DisableAppSuggestions"],
            default_enabled=False,
        ),
        DebloatOption(
            id="disable-typing-insights",
            name="Disable Typing & Ink Insights",
            description="Stop collecting typing patterns",
            category="privacy",
            parameters=["DisableTypingInsights"],
            default_enabled=False,
        ),
    ],
    "system": [
        DebloatOption(
            id="disable-services",
            name="System Tweaks",
            description="Apply selected low-level system behavior tweaks",
            category="system",
            parameters=[],
            default_enabled=False,
            sub_options=[
                DebloatSubOption(
                    id="disable-services-cortana",
                    name="Disable Bing/Copilot in Search",
                    description="Disable Bing web search, Bing AI and Cortana integration",
                    parameters=["DisableBing"],
                    default_enabled=True,
                ),
                DebloatSubOption(
                    id="disable-services-superfetch",
                    name="Disable Sticky Keys Shortcut",
                    description="Disable Sticky Keys keyboard shortcut popup",
                    parameters=["DisableStickyKeys"],
                    default_enabled=False,
                ),
                DebloatSubOption(
                    id="disable-services-print-spooler",
                    name="Disable Mouse Acceleration",
                    description="Turn off Enhance Pointer Precision",
                    parameters=["DisableMouseAcceleration"],
                    default_enabled=False,
                ),
                DebloatSubOption(
                    id="disable-services-windows-search",
                    name="Disable Drag Tray",
                    description="Disable drag tray sharing panel (Windows 11)",
                    parameters=["DisableDragTray"],
                    default_enabled=False,
                ),
                DebloatSubOption(
                    id="disable-services-diagnostics",
                    name="Disable Modern Standby Networking",
                    description="Disable network activity during Modern Standby",
                    parameters=["DisableModernStandbyNetworking"],
                    default_enabled=False,
                ),
            ],
        ),
        DebloatOption(
            id="disable-fast-startup",
            name="Disable Fast Startup",
            description="Ensure full shutdown (better for updates)",
            category="system",
            parameters=["DisableFastStartup"],
            default_enabled=False,
        ),
        DebloatOption(
            id="disable-bitlocker",
            name="Disable BitLocker",
            description="Turn off automatic BitLocker encryption",
            category="system",
            parameters=["DisableBitlockerAutoEncryption"],
            default_enabled=False,
        ),
        DebloatOption(
            id="disable-updates",
            name="Disable Auto Updates",
            description="Disable automatic Windows updates",
            category="system",
            parameters=["DisableUpdateASAP", "PreventUpdateAutoReboot", "DisableDeliveryOptimization"],
            default_enabled=False,
        ),
        DebloatOption(
            id="disable-network-discovery",
            name="Disable Network Discovery",
            description="Turn off device discovery on network",
            category="system",
            parameters=["DisableNetworkDiscovery"],
            default_enabled=False,
        ),
    ],
    "ai": [
        DebloatOption(
            id="disable-copilot",
            name="Disable Copilot",
            description="Remove Microsoft Copilot AI assistant",
            category="ai",
            parameters=["DisableCopilot"],
            default_enabled=False,
        ),
        DebloatOption(
            id="disable-recall",
            name="Disable Windows Recall",
            description="Disable Windows Recall feature",
            category="ai",
            parameters=["DisableRecall"],
            default_enabled=False,
        ),
        DebloatOption(
            id="disable-ai-search",
            name="Disable AI Search Features",
            description="Turn off AI-powered Windows Search",
            category="ai",
            parameters=["DisableBing"],
            default_enabled=False,
        ),
    ],
    "appearance": [
        DebloatOption(
            id="enable-dark-mode",
            name="Enable Dark Mode",
            description="Switch system to dark theme",
            category="appearance",
            parameters=["EnableDarkMode"],
            default_enabled=False,
        ),
        DebloatOption(
            id="disable-animations",
            name="Disable Animations",
            description="Remove visual transitions and animations",
            category="appearance",
            parameters=["DisableAnimations"],
            default_enabled=False,
        ),
        DebloatOption(
            id="remove-bloat-taskbar",
            name="Clean Up Taskbar",
            description="Remove unnecessary taskbar items",
            category="appearance",
            parameters=["RemoveTaskbarBloat"],
            default_enabled=False,
        ),
        DebloatOption(
            id="disable-welcome-tips",
            name="Disable Welcome Tips",
            description="Stop Windows welcome tips notifications",
            category="appearance",
            parameters=["DisableWelcomeTips"],
            default_enabled=False,
        ),
    ],
}


def get_available_options() -> dict:
    """Get all available debloat options grouped by category."""
    result = {}
    for category, options in DEBLOAT_OPTIONS.items():
        result[category] = [
            {
                "id": opt.id,
                "name": opt.name,
                "description": opt.description,
                "category": opt.category,
                "default_enabled": opt.default_enabled,
                "sub_options": [
                    {
                        "id": sub.id,
                        "name": sub.name,
                        "description": sub.description,
                        "default_enabled": sub.default_enabled,
                    }
                    for sub in opt.sub_options
                ] if opt.sub_options else [],
            }
            for opt in options
        ]
    return result


def _detect_environment() -> ExecutionEnvironment:
    """Detect the current execution environment."""
    try:
        # Check for WSL
        result = subprocess.run(
            ["uname", "-r"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if "WSL" in result.stdout or "microsoft" in result.stdout.lower():
            return ExecutionEnvironment.WSL
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    # Check for Windows
    if platform.system() == "Windows":
        return ExecutionEnvironment.POWERSHELL
    
    # Default for Linux systems
    return ExecutionEnvironment.WSL


def _build_script_parameters(option_ids: list[str]) -> list[str]:
    """Build Win11Debloat CLI parameters from selected option IDs only."""
    params: list[str] = []
    app_ids: list[str] = []

    for category_options in DEBLOAT_OPTIONS.values():
        for option in category_options:
            if option.id in option_ids:
                params.extend([parameter for parameter in option.parameters if parameter in ALLOWED_SWITCHES])
            if option.sub_options:
                for sub_option in option.sub_options:
                    if sub_option.id in option_ids:
                        for parameter in sub_option.parameters:
                            if parameter.startswith("AppId:"):
                                app_ids.append(parameter.split(":", 1)[1])
                            elif parameter in ALLOWED_SWITCHES:
                                params.append(parameter)

    if app_ids:
        params.append("RemoveApps")
        params.append(f"Apps:{','.join(sorted(set(app_ids)))}")

    return params


async def execute_debloat(
    option_ids: list[str],
    environment: ExecutionEnvironment = ExecutionEnvironment.AUTO,
) -> DebloatTask:
    """
    Execute debloat with selected options.
    
    Args:
        option_ids: List of debloat option IDs to enable
        environment: Execution environment (auto-detect by default)
    
    Returns:
        DebloatTask with execution results
    """
    from uuid import uuid4
    
    if environment == ExecutionEnvironment.AUTO:
        environment = _detect_environment()
    
    task = DebloatTask(
        id=str(uuid4()),
        environment=environment,
        options=option_ids,
        status="running",
    )
    
    logger.info(f"Starting debloat task {task.id} with {len(option_ids)} options on {environment.value}")
    
    try:
        params = _build_script_parameters(option_ids)
        logger.info(f"Built parameters: {params}")
        
        if not params:
            task.status = "failed"
            task.error = "No debloat options selected"
            return task
        
        # Build the command based on environment
        cmd = _build_command(environment, params)
        logger.info(f"Executing command in {environment.value}: {cmd[:200]}...")  # Log first 200 chars
        
        # Execute the command with timeout
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True,
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        except asyncio.TimeoutError:
            proc.kill()
            task.status = "failed"
            task.error = "Debloat task timed out (exceeded 5 minutes)"
            task.progress = 100
            logger.error(f"Task {task.id} timed out")
            return task
        
        task.output = stdout.decode(errors="ignore")
        if stderr:
            task.error = stderr.decode(errors="ignore")
            logger.warning(f"Task {task.id} stderr: {task.error}")
        
        task.status = "completed" if proc.returncode == 0 else "failed"
        task.progress = 100
        
        logger.info(f"Task {task.id} finished with status={task.status}, returncode={proc.returncode}")
        if task.output:
            logger.info(f"Task {task.id} stdout: {task.output[:500]}...")  # First 500 chars
        
    except Exception as e:
        task.status = "failed"
        task.error = f"Execution error: {str(e)}"
        task.progress = 100
        logger.exception(f"Task {task.id} failed with exception: {e}")
    
    return task


def _build_command(env: ExecutionEnvironment, params: list[str]) -> str:
    """Build the debloat command for the target environment."""
    cli_args: list[str] = []
    for parameter in params:
        if parameter.startswith("Apps:"):
            apps_value = parameter.split(":", 1)[1].replace('"', '\\"')
            cli_args.append(f'-Apps "{apps_value}"')
        else:
            cli_args.append(f"-{parameter}")

    # Always run non-interactive and selected-only.
    cli_args.append("-Silent")

    joined_args = " ".join(cli_args)
    ps_script = f"""$ProgressPreference='SilentlyContinue'
& ([scriptblock]::Create((irm "https://debloat.raphi.re/" -UseBasicParsing))) {joined_args}
"""
    
    # Encode in UTF-16-LE (required for PowerShell -EncodedCommand)
    ps_bytes = ps_script.encode('utf-16-le')
    ps_b64 = base64.b64encode(ps_bytes).decode('ascii')
    
    if env == ExecutionEnvironment.WSL:
        # In WSL, we're in a Linux environment, call PowerShell on Windows
        return f'powershell.exe -NoProfile -ExecutionPolicy Bypass -EncodedCommand {ps_b64}'
    
    elif env == ExecutionEnvironment.POWERSHELL:
        # Direct PowerShell execution (Windows native)
        return f'powershell.exe -NoProfile -ExecutionPolicy Bypass -EncodedCommand {ps_b64}'
    
    else:  # CMD
        # CMD will call PowerShell
        return f'cmd /c powershell.exe -NoProfile -ExecutionPolicy Bypass -EncodedCommand {ps_b64}'

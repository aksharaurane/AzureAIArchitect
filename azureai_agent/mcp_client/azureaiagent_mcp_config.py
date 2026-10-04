import os
import json
import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

_CONFIG_PATH = Path(__file__).parent.parent / "azureaiagent_mcp_servers.json"

def load_azureaiagent_mcp_configs() -> dict:
    """Return mcp_servers dict from azureaiagent_mcp_servers.json with env vars resolved.

    CWD is injected at load time so ${CWD} in the config always resolves to the
    directory where azureaiagent claude was launched — not the package install location.
    """
    # FIX 1: Convert Windows backslashes to forward slashes to keep JSON happy
    cwd_forward_slashes = str(Path.cwd()).replace("\\", "/")
    os.environ.setdefault("CWD", cwd_forward_slashes)
    
    # Read the file as a raw text string first instead of parsing it prematurely
    raw_text = _CONFIG_PATH.read_text()
    
    # FIX 2: Correctly escape any values coming out of os.getenv so they conform to JSON standards
    def json_safe_env_replace(match):
        env_value = os.getenv(match.group(1), "")
        # Strip outer quotes added by json.dumps to get a safely escaped inner string literal
        return json.dumps(env_value)[1:-1]

    resolved = re.sub(r"\$\{(\w+)\}", json_safe_env_replace, raw_text)
    
    return json.loads(resolved).get("mcp_servers", {})
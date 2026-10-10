"""Independent OM0RX remote-station agent.

The package deliberately reuses the proven FLEX/Elecraft drivers and station
coordinator without starting the full OM0RX Radio Control application.
"""

from .config import AgentConfig, load_agent_config

__all__ = ["AgentConfig", "load_agent_config"]

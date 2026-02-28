"""Agent trigger — writes to queue files picked up by visible worker terminals."""

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)


class AgentTrigger:
    def __init__(self, config: dict, data_dir: str = "./data"):
        self._config = config
        self._data_dir = Path(data_dir)

    def is_available(self, name: str) -> bool:
        return name in self._config

    def is_busy(self, name: str) -> bool:
        return False  # Worker handles busy state

    def get_status(self) -> dict:
        from mcp_bridge import is_online, is_active
        return {
            name: {
                "available": is_online(name),
                "busy": is_active(name),
                "label": cfg.get("label", name),
                "color": cfg.get("color", "#888"),
            }
            for name, cfg in self._config.items()
        }

    async def trigger(self, agent_name: str, message: str = "", channel: str = "general", **kwargs):
        """Write to the agent's queue file. The worker terminal picks it up."""
        queue_file = self._data_dir / f"{agent_name}_queue.jsonl"
        self._data_dir.mkdir(parents=True, exist_ok=True)

        import time
        entry = {
            "sender": message.split(":")[0].strip() if ":" in message else "?",
            "text": message,
            "time": time.strftime("%H:%M:%S"),
            "channel": channel,
        }

        with open(queue_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        log.info("Queued @%s trigger (ch=%s): %s", agent_name, channel, message[:80])

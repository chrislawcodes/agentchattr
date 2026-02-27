"""Message routing based on @mentions with loop guard."""

import re


class Router:
    def __init__(self, agent_names: list[str], default_mention: str = "both",
                 max_hops: int = 4):
        self.agent_names = set(n.lower() for n in agent_names)
        self.default_mention = default_mention
        self.max_hops = max_hops
        self._hop_count = 0
        self._paused = False
        self.guard_emitted = False  # only emit loop guard message once per pause
        self._build_pattern()

    def _build_pattern(self):
        names = "|".join(re.escape(n) for n in sorted(self.agent_names))
        self._mention_re = re.compile(
            rf"@({names}|both|all)\b", re.IGNORECASE
        )

    def parse_mentions(self, text: str) -> list[str]:
        mentions = set()
        for match in self._mention_re.finditer(text):
            name = match.group(1).lower()
            if name in ("both", "all"):
                mentions.update(self.agent_names)
            else:
                mentions.add(name)
        return list(mentions)

    def _is_agent(self, sender: str) -> bool:
        return sender.lower() in self.agent_names

    def get_targets(self, sender: str, text: str) -> list[str]:
        """Determine which agents should receive this message."""
        if self._paused:
            return []

        mentions = self.parse_mentions(text)

        if not self._is_agent(sender):
            # Human message resets hop counter
            self._hop_count = 0
            self._paused = False
            self.guard_emitted = False
            if not mentions:
                if self.default_mention in ("both", "all"):
                    return list(self.agent_names)
                elif self.default_mention == "none":
                    return []
                return [self.default_mention]
            return mentions
        else:
            # Agent message: only route if explicit @mention
            if not mentions:
                return []
            self._hop_count += 1
            if self._hop_count > self.max_hops:
                self._paused = True
                return []
            # Don't route back to self
            return [m for m in mentions if m != sender]

    def continue_routing(self):
        """Resume after loop guard pause."""
        self._hop_count = 0
        self._paused = False
        self.guard_emitted = False

    @property
    def is_paused(self) -> bool:
        return self._paused

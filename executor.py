from __future__ import annotations

import os
import httpx


class ExecutorError(RuntimeError):
    pass


class Executor:
    """Authorized-execution adapter only.

    By default it is advisory-only. For a game/vendor-provided test API, set
    EXECUTOR_MODE=http and EXECUTOR_BASE_URL to an endpoint that explicitly
    authorizes these actions. The payload is JSON and contains the command and
    arguments. This is intentionally NOT a Discord user-account automation
    client.
    """

    def __init__(self) -> None:
        self.mode = os.getenv("EXECUTOR_MODE", "advisory").lower()
        self.base_url = os.getenv("EXECUTOR_BASE_URL", "").rstrip("/")
        self.timeout = float(os.getenv("EXECUTOR_TIMEOUT", "10"))
        self.token = os.getenv("EXECUTOR_TOKEN", "")

    async def execute(self, command: str, arguments: dict) -> dict:
        if self.mode != "http":
            return {"status": "advisory", "command": command, "arguments": arguments}
        if not self.base_url:
            raise ExecutorError("EXECUTOR_BASE_URL is required for http executor")
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/actions",
                json={"command": command, "arguments": arguments},
                headers=headers,
            )
            response.raise_for_status()
            return response.json()

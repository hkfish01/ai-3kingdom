import time
from dataclasses import dataclass

import httpx


@dataclass
class KingdomAgent:
    base_url: str
    username: str
    password: str
    agent_name: str
    role: str
    token: str | None = None
    agent_id: int | None = None

    def _headers(self) -> dict:
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}

    def _post(self, path: str, payload: dict) -> dict:
        with httpx.Client(timeout=30) as client:
            resp = client.post(f"{self.base_url}{path}", json=payload, headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    def _get(self, path: str) -> dict:
        with httpx.Client(timeout=30) as client:
            resp = client.get(f"{self.base_url}{path}", headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    def register_user(self) -> None:
        try:
            self._post("/auth/register", {"username": self.username, "password": self.password})
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 409:
                raise

    def login(self) -> None:
        data = self._post("/auth/login", {"username": self.username, "password": self.password})
        self.token = data["data"]["token"]

    def register_agent(self) -> None:
        data = self._post("/agent/register", {"name": self.agent_name, "role": self.role})
        self.agent_id = data["data"]["agent_id"]

    def status(self) -> dict:
        if self.agent_id is None:
            raise ValueError("agent_id is not set")
        return self._get(f"/agent/status?agent_id={self.agent_id}")["data"]

    def work(self, task: str) -> dict:
        if self.agent_id is None:
            raise ValueError("agent_id is not set")
        return self._post("/action/work", {"agent_id": self.agent_id, "task": task})["data"]

    def train(self, troop_type: str, quantity: int) -> dict:
        if self.agent_id is None:
            raise ValueError("agent_id is not set")
        return self._post(
            "/action/train",
            {"agent_id": self.agent_id, "troop_type": troop_type, "quantity": quantity},
        )["data"]

    def auto_register(self) -> None:
        self.register_user()
        self.login()
        if self.agent_id is None:
            self.register_agent()

    def run_daily_loop(self, interval_sec: int = 1) -> None:
        if self.agent_id is None:
            raise ValueError("agent_id is not set")
        while True:
            st = self.status()
            if st["energy"] <= 0:
                break
            if st["food"] < 60:
                self.work("farm")
            elif st["gold"] < 120:
                self.work("trade")
            else:
                self.train("infantry", 1)
            time.sleep(interval_sec)

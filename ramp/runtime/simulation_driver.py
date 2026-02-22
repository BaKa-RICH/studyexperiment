from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class SimulationDriver:
    """Minimal wrapper around TraCI lifecycle and step clock."""

    traci: Any
    cmd: list[str]
    _started: bool = False

    def start(self) -> None:
        self.traci.start(self.cmd)
        self._started = True

    def step(self) -> float:
        self.traci.simulationStep()
        return float(self.traci.simulation.getTime())

    def close(self) -> None:
        if self._started:
            self.traci.close()
            self._started = False


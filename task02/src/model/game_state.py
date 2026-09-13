"""Game state aggregate shared by the logic and presentation layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .arrow import Arrow, ArrowState
from .grid import Grid


class GameRunState(str, Enum):
    """Operational state of the current level."""

    READY = "ready"
    PLAYING = "playing"
    PAUSED = "paused"
    FINISHED = "finished"


class GameResult(str, Enum):
    """Terminal result of a level."""

    NONE = "none"
    WON = "won"
    LOST = "lost"


@dataclass
class GameState:
    """Current level, arrows, board occupancy, attempts, and result."""

    grid: Grid = field(default_factory=Grid)
    arrows: list[Arrow] = field(default_factory=list)
    level: int = 1
    mistakes_allowed: int = 3
    mistakes_remaining: int | None = None
    run_state: GameRunState = GameRunState.READY
    result: GameResult = GameResult.NONE

    def __post_init__(self) -> None:
        if self.level < 1:
            raise ValueError("level must be at least 1")
        if self.mistakes_allowed < 0:
            raise ValueError("mistakes_allowed cannot be negative")
        if self.mistakes_remaining is None:
            self.mistakes_remaining = self.mistakes_allowed
        if not 0 <= self.mistakes_remaining <= self.mistakes_allowed:
            raise ValueError("mistakes_remaining must be within the allowed range")
        self.arrows = list(self.arrows)
        self._rebuild_grid()

    @property
    def is_running(self) -> bool:
        """Compatibility view indicating that the level accepts play."""
        return self.run_state is GameRunState.PLAYING

    @is_running.setter
    def is_running(self, value: bool) -> None:
        self.run_state = GameRunState.PLAYING if value else GameRunState.FINISHED

    @property
    def is_won(self) -> bool:
        return self.result is GameResult.WON

    @property
    def is_lost(self) -> bool:
        return self.result is GameResult.LOST

    @property
    def remaining_arrows(self) -> int:
        return sum(arrow.state is not ArrowState.REMOVED for arrow in self.arrows)

    @property
    def remaining_arrow_count(self) -> int:
        return self.remaining_arrows

    @property
    def remaining_mistakes(self) -> int:
        return self.mistakes_remaining

    def _rebuild_grid(self) -> None:
        self.grid.clear()
        for arrow in self.arrows:
            if arrow.state is not ArrowState.REMOVED:
                self.grid.place_arrow(arrow)

    def start(self) -> None:
        if self.result is GameResult.NONE:
            self.run_state = GameRunState.PLAYING

    def pause(self) -> None:
        if self.run_state is GameRunState.PLAYING:
            self.run_state = GameRunState.PAUSED

    def resume(self) -> None:
        if self.run_state is GameRunState.PAUSED:
            self.run_state = GameRunState.PLAYING

    def reset(self) -> None:
        """Reset this level, restoring all arrows and mistake opportunities."""
        for arrow in self.arrows:
            arrow.reset()
        self.mistakes_remaining = self.mistakes_allowed
        self.run_state = GameRunState.READY
        self.result = GameResult.NONE
        self._rebuild_grid()

    def begin_arrow_exit(self, arrow: Arrow) -> None:
        self._require_known_arrow(arrow)
        if self.result is not GameResult.NONE:
            return
        arrow.mark_flying_out()

    def complete_arrow_exit(self, arrow: Arrow) -> None:
        """Finish an exit animation and update the win state if appropriate."""
        self._require_known_arrow(arrow)
        self.grid.remove_arrow(arrow)
        arrow.mark_removed()
        if self.remaining_arrows == 0:
            self.result = GameResult.WON
            self.run_state = GameRunState.FINISHED

    def register_collision(self, arrow: Arrow, feedback_frames: int = 12) -> bool:
        """Record a blocked click; return True if this caused a loss."""
        self._require_known_arrow(arrow)
        if self.result is not GameResult.NONE:
            return self.is_lost
        if self.mistakes_remaining > 0:
            self.mistakes_remaining -= 1
        arrow.mark_collision(feedback_frames)
        if self.mistakes_remaining == 0:
            self.result = GameResult.LOST
            self.run_state = GameRunState.FINISHED
            return True
        return False

    def _require_known_arrow(self, arrow: Arrow) -> None:
        if not any(candidate is arrow for candidate in self.arrows):
            raise ValueError("arrow does not belong to this game state")


__all__ = ["GameResult", "GameRunState", "GameState"]
"""Game state model."""

from dataclasses import dataclass, field

from .arrow import Arrow
from .grid import Grid


@dataclass
class GameState:
    """Central state shared by the logic and presentation layers."""

    grid: Grid = field(default_factory=Grid)
    arrows: list[Arrow] = field(default_factory=list)
    is_running: bool = True
    is_won: bool = False
    is_lost: bool = False

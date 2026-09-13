"""Arrow model definitions."""

from dataclasses import dataclass


@dataclass
class Arrow:
    """An arrow placed on or moving through the game board."""

    row: int
    column: int
    direction: int = 0
    active: bool = True

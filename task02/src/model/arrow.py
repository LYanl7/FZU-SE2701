"""Pure-Python models for arrows and their occupied board cells."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True, order=True)
class Cell:
    """A zero-based board coordinate."""

    row: int
    column: int

    def moved(self, direction: Direction, distance: int = 1) -> Cell:
        """Return a coordinate moved in direction."""
        direction = Direction.from_value(direction)
        delta_row, delta_column = direction.delta
        return Cell(
            self.row + delta_row * distance,
            self.column + delta_column * distance,
        )


class Direction(str, Enum):
    """The four directions in which an arrow can leave the board."""

    UP = "up"
    RIGHT = "right"
    DOWN = "down"
    LEFT = "left"

    @property
    def delta(self) -> tuple[int, int]:
        return {
            Direction.UP: (-1, 0),
            Direction.RIGHT: (0, 1),
            Direction.DOWN: (1, 0),
            Direction.LEFT: (0, -1),
        }[self]

    @classmethod
    def from_value(cls, value: Direction | str | int) -> Direction:
        """Normalize enum, name, value, or legacy integer directions."""
        if isinstance(value, cls):
            return value
        if isinstance(value, int):
            legacy_values = (cls.UP, cls.RIGHT, cls.DOWN, cls.LEFT)
            try:
                return legacy_values[value]
            except IndexError as exc:
                raise ValueError(f"invalid direction integer: {value}") from exc
        normalized = str(value).strip().lower()
        aliases = {
            "u": cls.UP,
            "up": cls.UP,
            "上": cls.UP,
            "r": cls.RIGHT,
            "right": cls.RIGHT,
            "右": cls.RIGHT,
            "d": cls.DOWN,
            "down": cls.DOWN,
            "下": cls.DOWN,
            "l": cls.LEFT,
            "left": cls.LEFT,
            "左": cls.LEFT,
        }
        try:
            return aliases[normalized]
        except KeyError as exc:
            raise ValueError(f"invalid direction: {value!r}") from exc


class ArrowType(str, Enum):
    """Shape representation used by an arrow."""

    STRAIGHT = "straight"
    SEGMENTED = "segmented"


class ArrowState(str, Enum):
    """Lifecycle and feedback states of an arrow."""

    AVAILABLE = "available"
    FLYING_OUT = "flying_out"
    COLLISION_FEEDBACK = "collision_feedback"
    REMOVED = "removed"


def _as_cell(value: Cell | tuple[int, int]) -> Cell:
    if isinstance(value, Cell):
        return value
    try:
        row, column = value
    except (TypeError, ValueError) as exc:
        raise TypeError("a cell must be Cell or (row, column)") from exc
    return Cell(int(row), int(column))


@dataclass(frozen=True)
class ArrowSegment:
    """One contiguous horizontal or vertical part of an arrow."""

    cells: tuple[Cell, ...]

    def __post_init__(self) -> None:
        normalized = tuple(_as_cell(cell) for cell in self.cells)
        if not normalized:
            raise ValueError("an arrow segment must contain at least one cell")
        if len(set(normalized)) != len(normalized):
            raise ValueError("an arrow segment cannot contain duplicate cells")
        if len(normalized) > 1:
            same_row = len({cell.row for cell in normalized}) == 1
            same_column = len({cell.column for cell in normalized}) == 1
            if not (same_row or same_column):
                raise ValueError("an arrow segment must be horizontal or vertical")
        object.__setattr__(self, "cells", normalized)

    @property
    def start(self) -> Cell:
        return self.cells[0]

    @property
    def end(self) -> Cell:
        return self.cells[-1]


@dataclass
class Arrow:
    """An arrow occupying one or more cells on the board.

    path is suitable for a normal straight arrow. segments can be supplied
    for a segmented arrow; each segment remains independently inspectable
    while occupied_cells exposes their flattened union.
    """

    row: int
    column: int
    direction: Direction | str | int = Direction.UP
    path: tuple[Cell, ...] = ()
    arrow_type: ArrowType = ArrowType.STRAIGHT
    segments: tuple[ArrowSegment, ...] = ()
    arrow_id: str | None = None
    state: ArrowState = ArrowState.AVAILABLE
    collision_feedback_frames: int = 0
    animation_progress: float = 0.0

    def __post_init__(self) -> None:
        self.direction = Direction.from_value(self.direction)
        self.arrow_type = ArrowType(self.arrow_type)
        self.state = ArrowState(self.state)
        self.path = tuple(_as_cell(cell) for cell in self.path)
        self.segments = tuple(
            segment
            if isinstance(segment, ArrowSegment)
            else ArrowSegment(tuple(segment))
            for segment in self.segments
        )
        if self.path and self.segments:
            raise ValueError("provide path or segments, not both")
        if not self.path and not self.segments:
            self.path = (Cell(self.row, self.column),)
        if self.segments and self.arrow_type is ArrowType.STRAIGHT:
            self.arrow_type = ArrowType.SEGMENTED
        if self.arrow_type is ArrowType.SEGMENTED and not self.segments:
            self.segments = (ArrowSegment(self.path),)
            self.path = ()
        if self.collision_feedback_frames < 0:
            raise ValueError("collision feedback frames cannot be negative")

    @property
    def position(self) -> Cell:
        """The anchor position supplied when the arrow was created."""
        return Cell(self.row, self.column)

    @property
    def occupied_cells(self) -> tuple[Cell, ...]:
        """All distinct cells occupied by this arrow, in declaration order."""
        cells = self.path if self.path else tuple(
            cell for segment in self.segments for cell in segment.cells
        )
        return tuple(dict.fromkeys(cells))

    @property
    def front_cells(self) -> tuple[Cell, ...]:
        """The occupied cells nearest the board edge in the arrow direction."""
        cells = self.occupied_cells
        if self.direction is Direction.UP:
            edge = min(cell.row for cell in cells)
            selected = (cell for cell in cells if cell.row == edge)
        elif self.direction is Direction.DOWN:
            edge = max(cell.row for cell in cells)
            selected = (cell for cell in cells if cell.row == edge)
        elif self.direction is Direction.LEFT:
            edge = min(cell.column for cell in cells)
            selected = (cell for cell in cells if cell.column == edge)
        else:
            edge = max(cell.column for cell in cells)
            selected = (cell for cell in cells if cell.column == edge)
        return tuple(selected)

    @property
    def is_available(self) -> bool:
        return self.state is ArrowState.AVAILABLE

    def reset(self) -> None:
        """Restore the arrow to its initial playable state."""
        self.state = ArrowState.AVAILABLE
        self.collision_feedback_frames = 0
        self.animation_progress = 0.0

    def mark_flying_out(self) -> None:
        self.state = ArrowState.FLYING_OUT
        self.animation_progress = 0.0

    def mark_removed(self) -> None:
        self.state = ArrowState.REMOVED
        self.animation_progress = 1.0

    def mark_collision(self, feedback_frames: int = 12) -> None:
        if feedback_frames < 0:
            raise ValueError("collision feedback frames cannot be negative")
        self.state = ArrowState.COLLISION_FEEDBACK
        self.collision_feedback_frames = feedback_frames

    def finish_collision_feedback(self) -> None:
        if self.state is ArrowState.COLLISION_FEEDBACK:
            self.state = ArrowState.AVAILABLE
            self.collision_feedback_frames = 0


__all__ = [
    "Arrow",
    "ArrowSegment",
    "ArrowState",
    "ArrowType",
    "Cell",
    "Direction",
]
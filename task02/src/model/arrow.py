"""Pure-Python models for arrows and their board coordinates.

The playable board is described in *points* rather than in visual cells.  A
point has a continuous ``x``/``y`` position, which lets a renderer place an
arrow between grid lines (or use a board with no visible grid at all).  The
older ``Cell``/``row``/``column`` spelling remains as a compatibility view for
logic clients written against the first version of task02.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import hypot, isclose


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


@dataclass(frozen=True, order=True)
class Point:
    """A board point, expressed as horizontal ``x`` and vertical ``y``.

    Coordinates are intentionally numeric (not integers).  Integer points
    are useful for importing old levels, while fractional points allow an
    arrow to be positioned without forcing it to span a cell.
    """

    x: float
    y: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", float(self.x))
        object.__setattr__(self, "y", float(self.y))

    def moved(self, direction: Direction, distance: float = 1.0) -> Point:
        direction = Direction.from_value(direction)
        delta_row, delta_column = direction.delta
        return Point(
            self.x + delta_column * distance,
            self.y + delta_row * distance,
        )

    @property
    def row(self) -> float:
        """Compatibility alias (``y`` is the old row coordinate)."""
        return self.y

    @property
    def column(self) -> float:
        """Compatibility alias (``x`` is the old column coordinate)."""
        return self.x


@dataclass(frozen=True)
class LineSegment:
    """A non-zero, axis-aligned line between two board points."""

    start: Point
    end: Point

    def __post_init__(self) -> None:
        start = _as_point(self.start)
        end = _as_point(self.end)
        if start == end:
            raise ValueError("a line segment must have non-zero length")
        if not (isclose(start.x, end.x) or isclose(start.y, end.y)):
            raise ValueError("line segments must be horizontal or vertical")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)

    @property
    def length(self) -> float:
        return hypot(self.end.x - self.start.x, self.end.y - self.start.y)

    @property
    def horizontal(self) -> bool:
        return isclose(self.start.y, self.end.y)

    @property
    def vertical(self) -> bool:
        return isclose(self.start.x, self.end.x)

    def contains(self, point: Point, tolerance: float = 1e-6) -> bool:
        """Return whether ``point`` lies on this segment."""
        point = _as_point(point)
        if self.horizontal:
            return (
                abs(point.y - self.start.y) <= tolerance
                and min(self.start.x, self.end.x) - tolerance
                <= point.x <= max(self.start.x, self.end.x) + tolerance
            )
        return (
            abs(point.x - self.start.x) <= tolerance
            and min(self.start.y, self.end.y) - tolerance
            <= point.y <= max(self.start.y, self.end.y) + tolerance
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


def _as_point(value: Point | Cell | tuple[float, float]) -> Point:
    if isinstance(value, Point):
        return value
    if isinstance(value, Cell):
        return Point(value.column, value.row)
    try:
        first, second = value
    except (TypeError, ValueError) as exc:
        raise TypeError("a point must be Point or (x, y)") from exc
    return Point(first, second)


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
    """An arrow represented by an ordered polyline of board points.

    ``points`` is the canonical representation.  Every adjacent pair forms a
    non-zero, axis-aligned :class:`LineSegment`; the final point is the tip.
    ``path`` and ``segments`` are accepted only as legacy cell-based inputs.
    """

    row: int | float | None = None
    column: int | float | None = None
    direction: Direction | str | int = Direction.UP
    path: tuple[Cell, ...] = ()
    arrow_type: ArrowType = ArrowType.STRAIGHT
    segments: tuple[ArrowSegment, ...] = ()
    arrow_id: str | None = None
    state: ArrowState = ArrowState.AVAILABLE
    collision_feedback_frames: int = 0
    animation_progress: float = 0.0
    points: tuple[Point, ...] = ()
    point: Point | tuple[float, float] | None = None
    # Canonical point coordinates.  They are populated from x/y or the legacy
    # row/column pair in __post_init__, so both construction styles work.
    x: float | None = None
    y: float | None = None

    def __post_init__(self) -> None:
        point_native_anchor = (
            self.x is not None or self.y is not None or self.point is not None
            or bool(self.points)
        )
        self.direction = Direction.from_value(self.direction)
        self.arrow_type = ArrowType(self.arrow_type)
        self.state = ArrowState(self.state)
        self.path = tuple(_as_cell(cell) for cell in self.path)
        self.points = tuple(_as_point(point) for point in self.points)
        if self.point is not None:
            anchor = _as_point(self.point)
            if self.x is not None or self.y is not None:
                if self.x is None or self.y is None or Point(self.x, self.y) != anchor:
                    raise ValueError("point conflicts with x/y coordinates")
            self.x, self.y = anchor.x, anchor.y
        if self.path and self.points:
            raise ValueError("provide path or points, not both")
        if self.points and self.x is None and self.y is None:
            self.x, self.y = self.points[0].x, self.points[0].y
        if self.x is None:
            if self.column is None:
                self.x = 0.0
            else:
                self.x = float(self.column)
        else:
            self.x = float(self.x)
        if self.y is None:
            if self.row is None:
                self.y = 0.0
            else:
                self.y = float(self.row)
        else:
            self.y = float(self.y)
        # Keep the old fields synchronized as aliases.  An x/y caller is
        # therefore still consumable by code that reads row/column.
        self.column = int(self.x) if self.x.is_integer() else self.x
        self.row = int(self.y) if self.y.is_integer() else self.y
        self.segments = tuple(
            segment
            if isinstance(segment, ArrowSegment)
            else ArrowSegment(tuple(segment))
            for segment in self.segments
        )
        if self.path and self.segments:
            raise ValueError("provide path or segments, not both")
        if not self.path and not self.points and not self.segments:
            if point_native_anchor:
                self.points = self._default_points(Point(self.x, self.y))
            else:
                # Preserve the original path shape for row/column callers;
                # occupied_points still exposes its canonical point view.
                self.path = (Cell(int(self.y), int(self.x)),)
        if self.segments and self.arrow_type is ArrowType.STRAIGHT:
            self.arrow_type = ArrowType.SEGMENTED
        if self.arrow_type is ArrowType.SEGMENTED and not self.segments and self.path:
            self.segments = (ArrowSegment(self.path),)
            self.path = ()
        if self.points:
            self._validate_points()
        if self.collision_feedback_frames < 0:
            raise ValueError("collision feedback frames cannot be negative")

    @property
    def position(self) -> Point:
        """The anchor point supplied when the arrow was created."""
        return Point(self.x, self.y)

    def _default_points(self, anchor: Point) -> tuple[Point, Point]:
        """Create a short centered line for a point-only arrow."""
        half_length = 0.3
        delta_row, delta_column = self.direction.delta
        return (
            Point(anchor.x - delta_column * half_length,
                  anchor.y - delta_row * half_length),
            Point(anchor.x + delta_column * half_length,
                  anchor.y + delta_row * half_length),
        )

    def _validate_points(self) -> None:
        if len(self.points) < 2:
            raise ValueError("an arrow must contain at least two points")
        for start, end in zip(self.points, self.points[1:]):
            LineSegment(start, end)

    @property
    def line_segments(self) -> tuple[LineSegment, ...]:
        """The ordered, geometric segments making up this arrow."""
        if self.points:
            return tuple(
                LineSegment(start, end)
                for start, end in zip(self.points, self.points[1:])
            )
        if self.path:
            points = tuple(Point(cell.column, cell.row) for cell in self.path)
            return tuple(LineSegment(start, end) for start, end in zip(points, points[1:]))
        result: list[LineSegment] = []
        for segment in self.segments:
            points = tuple(Point(cell.column, cell.row) for cell in segment.cells)
            result.extend(LineSegment(start, end) for start, end in zip(points, points[1:]))
        return tuple(result)

    @property
    def front_point(self) -> Point:
        """The final point in the ordered path, used as the arrow tip."""
        return self.points[-1] if self.points else self.occupied_points[-1]

    @property
    def occupied_points(self) -> tuple[Point, ...]:
        """Compatibility view of the ordered points in this arrow."""
        if self.points:
            values = self.points
        elif self.path:
            values = tuple(Point(cell.column, cell.row) for cell in self.path)
        else:
            values = tuple(
                Point(cell.column, cell.row)
                for segment in self.segments
                for cell in segment.cells
            )
        return tuple(dict.fromkeys(values))

    @property
    def occupied_cells(self) -> tuple[Cell, ...]:
        """All distinct cells occupied by this arrow, in declaration order."""
        # Only integral points have a meaningful legacy cell representation.
        # Fractional points deliberately remain point-only so they cannot be
        # accidentally snapped across a visual grid cell.
        if any(point.x % 1 or point.y % 1 for point in self.occupied_points):
            return ()
        cells = tuple(Cell(int(point.y), int(point.x)) for point in self.occupied_points)
        return tuple(dict.fromkeys(cells))

    @property
    def front_points(self) -> tuple[Point, ...]:
        """The occupied points nearest the board edge in the arrow direction."""
        if self.points:
            return (self.front_point,)
        points = self.occupied_points
        if self.direction is Direction.UP:
            edge = min(point.y for point in points)
            return tuple(point for point in points if point.y == edge)
        if self.direction is Direction.DOWN:
            edge = max(point.y for point in points)
            return tuple(point for point in points if point.y == edge)
        if self.direction is Direction.LEFT:
            edge = min(point.x for point in points)
            return tuple(point for point in points if point.x == edge)
        edge = max(point.x for point in points)
        return tuple(point for point in points if point.x == edge)

    @property
    def front_cells(self) -> tuple[Cell, ...]:
        """The occupied cells nearest the board edge in the arrow direction."""
        cells = self.occupied_cells
        if not cells:
            return tuple(
                Cell(int(point.y), int(point.x))
                for point in self.front_points
                if point.x % 1 == 0 and point.y % 1 == 0
            )
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
    "LineSegment",
    "Point",
]

"""A pygame-independent board and occupancy index."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isclose

from .arrow import Arrow, ArrowState, Cell, Direction, LineSegment, Point


def _intervals_overlap(first_start: float, first_end: float, second_start: float, second_end: float) -> bool:
    return max(min(first_start, first_end), min(second_start, second_end)) <= min(
        max(first_start, first_end), max(second_start, second_end)
    )


def _segments_intersect(first: LineSegment, second: LineSegment) -> bool:
    """Return whether two axis-aligned segments share any board geometry."""
    if first.horizontal and second.horizontal:
        return isclose(first.start.y, second.start.y) and _intervals_overlap(
            first.start.x, first.end.x, second.start.x, second.end.x
        )
    if first.vertical and second.vertical:
        return isclose(first.start.x, second.start.x) and _intervals_overlap(
            first.start.y, first.end.y, second.start.y, second.end.y
        )
    horizontal, vertical = (first, second) if first.horizontal else (second, first)
    return (
        min(horizontal.start.x, horizontal.end.x) - 1e-9
        <= vertical.start.x
        <= max(horizontal.start.x, horizontal.end.x) + 1e-9
        and min(vertical.start.y, vertical.end.y)
        - 1e-9 <= horizontal.start.y
        <= max(vertical.start.y, vertical.end.y) + 1e-9
    )


def _geometry_is_ahead(front: Point, direction: Direction, segment: LineSegment) -> bool:
    """Return whether a segment intersects the open ray after ``front``."""
    epsilon = 1e-9
    if direction is Direction.UP:
        if segment.horizontal:
            return (
                segment.start.y < front.y - epsilon
                and min(segment.start.x, segment.end.x) <= front.x <= max(segment.start.x, segment.end.x)
            )
        return (
            abs(segment.start.x - front.x) <= epsilon
            and min(segment.start.y, segment.end.y) < front.y - epsilon
        )
    if direction is Direction.DOWN:
        if segment.horizontal:
            return (
                segment.start.y > front.y + epsilon
                and min(segment.start.x, segment.end.x) <= front.x <= max(segment.start.x, segment.end.x)
            )
        return (
            abs(segment.start.x - front.x) <= epsilon
            and max(segment.start.y, segment.end.y) > front.y + epsilon
        )
    if direction is Direction.LEFT:
        if segment.vertical:
            return (
                segment.start.x < front.x - epsilon
                and min(segment.start.y, segment.end.y) <= front.y <= max(segment.start.y, segment.end.y)
            )
        return (
            abs(segment.start.y - front.y) <= epsilon
            and min(segment.start.x, segment.end.x) < front.x - epsilon
        )
    if segment.vertical:
        return (
            segment.start.x > front.x + epsilon
            and min(segment.start.y, segment.end.y) <= front.y <= max(segment.start.y, segment.end.y)
        )
    return (
        abs(segment.start.y - front.y) <= epsilon
        and max(segment.start.x, segment.end.x) > front.x + epsilon
    )


def _arrow_segments_or_points(arrow: Arrow) -> tuple[LineSegment, ...]:
    segments = arrow.line_segments
    if segments:
        return segments
    # Legacy one-cell arrows have no line segment.  Treat their point as a
    # zero-dimensional obstacle for point-native ray queries.
    point = arrow.occupied_points[-1]
    return (LineSegment(point, point.moved(Direction.RIGHT, 1e-7)),)


@dataclass
class Grid:
    """Mutable board bounds and line-geometry index.

    ``cells`` and cell methods are retained as a compatibility index only;
    point-native arrows are indexed in ``_line_arrows`` and queried by their
    actual segments.
    """

    rows: int = 8
    columns: int = 8
    cells: list[list[Arrow | None]] = field(default_factory=list)
    _occupancy: dict[Cell, Arrow] = field(default_factory=dict, init=False)
    _point_occupancy: dict[Point, Arrow] = field(default_factory=dict, init=False)
    _line_arrows: list[Arrow] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        if self.rows <= 0 or self.columns <= 0:
            raise ValueError("grid rows and columns must be positive")
        if not self.cells:
            self.cells = [
                [None for _ in range(self.columns)] for _ in range(self.rows)
            ]
        elif len(self.cells) != self.rows or any(
            len(row) != self.columns for row in self.cells
        ):
            raise ValueError("cells must match the grid dimensions")
        for row_index, row in enumerate(self.cells):
            for column_index, arrow in enumerate(row):
                if arrow is not None:
                    self._occupancy[Cell(row_index, column_index)] = arrow
                    self._point_occupancy[Point(column_index, row_index)] = arrow

    def in_bounds(self, cell: Cell) -> bool:
        return 0 <= cell.row < self.rows and 0 <= cell.column < self.columns

    def is_in_bounds(self, row: int, column: int) -> bool:
        return self.in_bounds(Cell(row, column))

    def in_bounds_point(self, point: Point) -> bool:
        """Return whether a continuous board point is inside the board."""
        return 0 <= point.x < self.columns and 0 <= point.y < self.rows

    def is_point_in_bounds(self, x: float, y: float) -> bool:
        return self.in_bounds_point(Point(x, y))

    def occupant_at(self, cell: Cell | Point) -> Arrow | None:
        """Return the arrow at a cell, or None for an empty/outside cell."""
        if isinstance(cell, Point):
            return self.occupant_at_point(cell)
        if not self.in_bounds(cell):
            return None
        return self._occupancy.get(cell)

    def occupant_at_point(self, point: Point) -> Arrow | None:
        """Return the arrow whose line geometry contains a point."""
        if not self.in_bounds_point(point):
            return None
        if (occupant := self._point_occupancy.get(point)) is not None:
            return occupant
        for arrow in reversed(self._line_arrows):
            if any(segment.contains(point, tolerance=1e-6) for segment in arrow.line_segments):
                return arrow
        return None

    def is_occupied(self, cell: Cell | Point) -> bool:
        return self.occupant_at(cell) is not None

    def occupied_cells(self, arrow: Arrow) -> tuple[Cell, ...]:
        return tuple(
            cell for cell in arrow.occupied_cells
            if self.occupant_at(cell) is arrow
        )

    def occupied_points(self, arrow: Arrow) -> tuple[Point, ...]:
        return tuple(
            point for point in arrow.occupied_points
            if self.occupant_at_point(point) is arrow
        )

    def place_arrow(self, arrow: Arrow) -> None:
        """Place an available arrow, rejecting outside or overlapping cells."""
        if arrow.state is ArrowState.REMOVED:
            raise ValueError("a removed arrow cannot be placed")
        if any(candidate is arrow for candidate in self.arrows()):
            return
        if arrow.points:
            segments = arrow.line_segments
            outside = [
                endpoint
                for segment in segments
                for endpoint in (segment.start, segment.end)
                if not self.in_bounds_point(endpoint)
            ]
            if outside:
                raise ValueError(f"arrow contains points outside the board: {outside!r}")
            if any(
                _segments_intersect(first, second)
                for existing in self._line_arrows
                for first in existing.line_segments
                for second in segments
            ):
                raise ValueError("arrows cannot overlap on the board")
            self._line_arrows.append(arrow)
            return

        points = arrow.occupied_points
        outside = [point for point in points if not self.in_bounds_point(point)]
        if outside:
            raise ValueError(f"arrow contains points outside the board: {outside!r}")
        conflicts = [
            (point, occupant)
            for point in points
            if (occupant := self._point_occupancy.get(point)) is not None
            and occupant is not arrow
        ]
        if conflicts:
            raise ValueError("arrows cannot overlap on the board")
        for point in points:
            self._point_occupancy[point] = arrow
            if point.x.is_integer() and point.y.is_integer():
                cell = Cell(int(point.y), int(point.x))
                self._occupancy[cell] = arrow
                self.cells[cell.row][cell.column] = arrow

    def remove_arrow(self, arrow: Arrow) -> None:
        """Remove all cells belonging to arrow; missing cells are ignored."""
        for cell in arrow.occupied_cells:
            if self._occupancy.get(cell) is arrow:
                del self._occupancy[cell]
                self.cells[cell.row][cell.column] = None
        for point in arrow.occupied_points:
            if self._point_occupancy.get(point) is arrow:
                del self._point_occupancy[point]
        self._line_arrows[:] = [candidate for candidate in self._line_arrows if candidate is not arrow]

    def clear(self) -> None:
        self._occupancy.clear()
        self._point_occupancy.clear()
        self._line_arrows.clear()
        for row in self.cells:
            for column_index in range(len(row)):
                row[column_index] = None

    def arrows(self) -> tuple[Arrow, ...]:
        """Return unique arrows currently occupying the board."""
        unique = []
        for arrow in (*self._occupancy.values(), *self._point_occupancy.values(), *self._line_arrows):
            if not any(candidate is arrow for candidate in unique):
                unique.append(arrow)
        return tuple(unique)

    @property
    def points(self) -> tuple[Point, ...]:
        """All currently occupied board points in insertion order."""
        result = list(self._point_occupancy)
        for arrow in self._line_arrows:
            result.extend(arrow.points)
        return tuple(result)

    def ray_from(
        self,
        start: Cell,
        direction: Direction | str | int,
        *,
        include_start: bool = False,
    ) -> tuple[Cell, ...]:
        """Return in-bounds cells from start toward the board edge."""
        direction = Direction.from_value(direction)
        cells: list[Cell] = []
        distance = 0 if include_start else 1
        cell = start.moved(direction, distance)
        while self.in_bounds(cell):
            cells.append(cell)
            distance += 1
            cell = start.moved(direction, distance)
        return tuple(cells)

    def cells_ahead(
        self,
        arrow: Arrow,
        direction: Direction | str | int | None = None,
    ) -> tuple[Cell, ...]:
        """Return all cells between an arrow front edge and the boundary."""
        direction = (
            arrow.direction
            if direction is None
            else Direction.from_value(direction)
        )
        result: list[Cell] = []
        seen: set[Cell] = set()
        for front_cell in arrow.front_cells:
            for cell in self.ray_from(front_cell, direction):
                if cell not in seen:
                    seen.add(cell)
                    result.append(cell)
        return tuple(result)

    def ray_from_point(
        self,
        start: Point,
        direction: Direction | str | int,
        *,
        step: float = 1.0,
        include_start: bool = False,
    ) -> tuple[Point, ...]:
        """Return board points from ``start`` toward the edge."""
        if step <= 0:
            raise ValueError("point ray step must be positive")
        direction = Direction.from_value(direction)
        points: list[Point] = []
        distance = 0.0 if include_start else step
        point = start.moved(direction, distance)
        while self.in_bounds_point(point):
            points.append(point)
            distance += step
            point = start.moved(direction, distance)
        return tuple(points)

    def points_ahead(
        self,
        arrow: Arrow,
        direction: Direction | str | int | None = None,
        *,
        step: float = 1.0,
    ) -> tuple[Point, ...]:
        """Return points between an arrow's front and the board boundary."""
        direction = arrow.direction if direction is None else Direction.from_value(direction)
        result: list[Point] = []
        seen: set[Point] = set()
        for front_point in arrow.front_points:
            for point in self.ray_from_point(front_point, direction, step=step):
                if point not in seen:
                    seen.add(point)
                    result.append(point)
        return tuple(result)

    def line_segments_ahead(
        self,
        arrow: Arrow,
        direction: Direction | str | int | None = None,
    ) -> tuple[LineSegment, ...]:
        """Return the continuous open ray from an arrow tip to the edge."""
        direction = arrow.direction if direction is None else Direction.from_value(direction)
        front = arrow.front_point
        if direction is Direction.UP:
            edge = Point(front.x, 0)
        elif direction is Direction.DOWN:
            edge = Point(front.x, float(self.rows))
        elif direction is Direction.LEFT:
            edge = Point(0, front.y)
        else:
            edge = Point(float(self.columns), front.y)
        if front == edge:
            return ()
        return (LineSegment(front, edge),)

    def arrows_intersecting(self, segment: LineSegment) -> tuple[Arrow, ...]:
        """Return point-native arrows whose line geometry intersects ``segment``."""
        result: list[Arrow] = []
        for arrow in self._line_arrows:
            if any(_segments_intersect(segment, candidate) for candidate in arrow.line_segments):
                result.append(arrow)
        return tuple(result)

    def blocking_arrows(
        self,
        arrow: Arrow,
        direction: Direction | str | int | None = None,
    ) -> tuple[Arrow, ...]:
        """Return unique arrows in the arrow's forward path."""
        # Point-native arrows are checked against line geometry.  Integral
        # legacy arrows continue through the original cell API.
        if arrow.points:
            blockers: list[Arrow] = []
            direction = arrow.direction if direction is None else Direction.from_value(direction)
            front = arrow.front_point
            for candidate in self.arrows():
                if candidate is arrow:
                    continue
                if any(
                    _geometry_is_ahead(front, direction, segment)
                    for segment in _arrow_segments_or_points(candidate)
                ) and candidate not in blockers:
                    blockers.append(candidate)
            return tuple(blockers)
        blockers: list[Arrow] = []
        for cell in self.cells_ahead(arrow, direction):
            occupant = self.occupant_at(cell)
            if occupant is not None and occupant is not arrow and occupant not in blockers:
                blockers.append(occupant)
        return tuple(blockers)

    def has_blocking_arrow(self, arrow: Arrow) -> bool:
        return bool(self.blocking_arrows(arrow))

    def can_exit(self, arrow: Arrow) -> bool:
        return not self.has_blocking_arrow(arrow)


__all__ = ["Grid"]

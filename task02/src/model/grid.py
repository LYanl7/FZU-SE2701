"""A pygame-independent board and occupancy index."""

from __future__ import annotations

from dataclasses import dataclass, field

from .arrow import Arrow, ArrowState, Cell, Direction


@dataclass
class Grid:
    """Mutable rectangular grid used for safe collision queries."""

    rows: int = 8
    columns: int = 8
    cells: list[list[Arrow | None]] = field(default_factory=list)
    _occupancy: dict[Cell, Arrow] = field(default_factory=dict, init=False)

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

    def in_bounds(self, cell: Cell) -> bool:
        return 0 <= cell.row < self.rows and 0 <= cell.column < self.columns

    def is_in_bounds(self, row: int, column: int) -> bool:
        return self.in_bounds(Cell(row, column))

    def occupant_at(self, cell: Cell) -> Arrow | None:
        """Return the arrow at a cell, or None for an empty/outside cell."""
        if not self.in_bounds(cell):
            return None
        return self._occupancy.get(cell)

    def is_occupied(self, cell: Cell) -> bool:
        return self.occupant_at(cell) is not None

    def occupied_cells(self, arrow: Arrow) -> tuple[Cell, ...]:
        return tuple(
            cell for cell in arrow.occupied_cells
            if self.occupant_at(cell) is arrow
        )

    def place_arrow(self, arrow: Arrow) -> None:
        """Place an available arrow, rejecting outside or overlapping cells."""
        if arrow.state is ArrowState.REMOVED:
            raise ValueError("a removed arrow cannot be placed")
        cells = arrow.occupied_cells
        outside = [cell for cell in cells if not self.in_bounds(cell)]
        if outside:
            raise ValueError(f"arrow contains cells outside the grid: {outside!r}")
        conflicts = [
            (cell, occupant)
            for cell in cells
            if (occupant := self._occupancy.get(cell)) is not None
            and occupant is not arrow
        ]
        if conflicts:
            raise ValueError("arrows cannot overlap on the grid")
        for cell in cells:
            self._occupancy[cell] = arrow
            self.cells[cell.row][cell.column] = arrow

    def remove_arrow(self, arrow: Arrow) -> None:
        """Remove all cells belonging to arrow; missing cells are ignored."""
        for cell in arrow.occupied_cells:
            if self._occupancy.get(cell) is arrow:
                del self._occupancy[cell]
                self.cells[cell.row][cell.column] = None

    def clear(self) -> None:
        self._occupancy.clear()
        for row in self.cells:
            for column_index in range(len(row)):
                row[column_index] = None

    def arrows(self) -> tuple[Arrow, ...]:
        """Return unique arrows currently occupying the board."""
        unique = []
        for arrow in self._occupancy.values():
            if not any(candidate is arrow for candidate in unique):
                unique.append(arrow)
        return tuple(unique)

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

    def blocking_arrows(
        self,
        arrow: Arrow,
        direction: Direction | str | int | None = None,
    ) -> tuple[Arrow, ...]:
        """Return unique arrows in the arrow's forward path."""
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
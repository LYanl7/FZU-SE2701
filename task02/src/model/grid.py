"""Grid model definitions."""

from dataclasses import dataclass, field


@dataclass
class Grid:
    """Mutable game grid."""

    rows: int = 8
    columns: int = 8
    cells: list[list[object | None]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.cells:
            self.cells = [
                [None for _ in range(self.columns)] for _ in range(self.rows)
            ]

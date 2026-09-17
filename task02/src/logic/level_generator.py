"""Procedural, point-coordinate levels for the arrow puzzle."""

from __future__ import annotations

from dataclasses import dataclass
import random

from model.arrow import Arrow, ArrowType, Direction, Point
from model.game_state import GameState
from model.grid import Grid


@dataclass(frozen=True)
class GeneratedLevel:
    """A generated state plus one valid arrow-removal order."""

    state: GameState
    solution: tuple[int, ...]
    seed: int


class LevelGenerator:
    """Generate dense boards made from true point-coordinate polylines.

    The board is deliberately wider than it is tall. Arrows are packed into
    the central 70% of that board, leaving quiet margins on both sides. Each
    folded arrow is an ordered series of axis-aligned points whose x and y
    coordinates both vary; adjacent points form the actual playable segments.
    """

    MAX_ATTEMPTS = 8
    HORIZONTAL_MARGIN_RATIO = 0.15

    def generate(self, level: int = 1, seed: int | None = None) -> GeneratedLevel:
        if not isinstance(level, int) or isinstance(level, bool) or level < 1:
            raise ValueError("level must be a positive integer")
        if seed is not None and (
            not isinstance(seed, int) or isinstance(seed, bool)
        ):
            raise TypeError("seed must be an integer or None")

        actual_seed = seed if seed is not None else random.SystemRandom().randrange(2**63)
        rng = random.Random(actual_seed)
        rows = min(12, 9 + (level - 1) // 5)
        columns = rows * 2
        slot_rows = rows - 2
        slot_columns = max(8, round(columns * 0.7 / 1.45))
        density = min(0.94, 0.82 + (level - 1) * 0.012)
        arrow_count = round(slot_rows * slot_columns * density)
        required_blocked = max(6, round(arrow_count * 0.14))
        wild_direction_chance = min(0.14, 6 / arrow_count)

        for _ in range(self.MAX_ATTEMPTS):
            arrows = self._candidate(
                rng, rows, columns, slot_rows, slot_columns, arrow_count,
                wild_direction_chance,
            )
            state = GameState(
                grid=Grid(rows=rows, columns=columns), arrows=arrows, level=level
            )
            solution = self.solution_order(state)
            blocked = sum(
                bool(state.grid.blocking_arrows(arrow)) for arrow in arrows
            )
            if len(solution) == arrow_count and blocked >= required_blocked:
                return GeneratedLevel(state, solution, actual_seed)

        # Random inward arrows can occasionally form a cycle. Removing those
        # exceptional directions gives a bounded, guaranteed-solvable fallback
        # while retaining the same dense, multi-point geometry.
        arrows = self._candidate(
            rng, rows, columns, slot_rows, slot_columns, arrow_count, 0.0
        )
        state = GameState(
            grid=Grid(rows=rows, columns=columns), arrows=arrows, level=level
        )
        solution = self.solution_order(state)
        if len(solution) != arrow_count:
            raise RuntimeError("could not generate a solvable level")
        return GeneratedLevel(state, solution, actual_seed)

    @classmethod
    def _candidate(
        cls,
        rng: random.Random,
        rows: int,
        columns: int,
        slot_rows: int,
        slot_columns: int,
        count: int,
        wild_direction_chance: float,
    ) -> list[Arrow]:
        left = columns * cls.HORIZONTAL_MARGIN_RATIO
        right = columns * (1 - cls.HORIZONTAL_MARGIN_RATIO)
        slot_width = (right - left) / slot_columns
        slot_height = rows / slot_rows
        slots = [
            (
                left + (column + 0.5) * slot_width,
                (row + 0.5) * slot_height,
                row,
                column,
            )
            for row in range(slot_rows)
            for column in range(slot_columns)
        ]
        rng.shuffle(slots)

        arrows: list[Arrow] = []
        for index, (center_x, center_y, slot_row, slot_column) in enumerate(
            slots[:count]
        ):
            direction = (
                rng.choice(tuple(Direction))
                if rng.random() < wild_direction_chance
                else rng.choice(
                    cls._outward_directions(
                        slot_row, slot_column, slot_rows, slot_columns
                    )
                )
            )
            # Long straight shafts and long-short-long paths dominate. Deep
            # zigzags are deliberately rare to keep the dense board readable.
            segment_count = rng.choices(
                (1, 2, 3, 4, 5), weights=(38, 18, 34, 8, 2), k=1
            )[0]
            points = cls._random_polyline(
                rng, center_x, center_y, slot_width, slot_height,
                direction, segment_count,
            )
            arrow = Arrow(
                points=points,
                direction=direction,
                arrow_type=(
                    ArrowType.STRAIGHT
                    if segment_count == 1
                    else ArrowType.SEGMENTED
                ),
                arrow_id=f"generated-{index + 1}",
            )
            arrow.shape_name = (
                "straight" if segment_count == 1 else f"polyline-{segment_count}"
            )
            arrows.append(arrow)
        rng.shuffle(arrows)
        return arrows

    @staticmethod
    def _random_polyline(
        rng: random.Random,
        center_x: float,
        center_y: float,
        slot_width: float,
        slot_height: float,
        direction: Direction,
        segment_count: int,
    ) -> tuple[Point, ...]:
        """Create one ordered polyline from tail to arrow tip.

        Coordinates are built in an arrow-local forward/sideways system and
        rotated into board space. Folding alternates horizontal and vertical
        segments, so both global coordinates vary for every folded arrow.
        """
        forward_y, forward_x = direction.delta
        side_x, side_y = -forward_y, forward_x
        forward_scale = slot_width if forward_x else slot_height
        side_scale = slot_height if forward_x else slot_width

        if segment_count == 1:
            local_points = ((-0.42, 0.0), (0.42, 0.0))
        else:
            side = rng.choice((-0.32, -0.16, 0.0, 0.16, 0.32))
            reverse_points: list[tuple[float, float]] = [
                (0.46, side), (0.08, side)
            ]
            forward = 0.08
            backward_steps = max(1, (segment_count - 1) // 2)
            completed_backward_steps = 0
            for step in range(segment_count - 1):
                if step % 2 == 0:
                    choices = [
                        value
                        for value in (-0.38, -0.19, 0.0, 0.19, 0.38)
                        if abs(value - side) > 0.08
                    ]
                    side = rng.choice(choices)
                else:
                    completed_backward_steps += 1
                    target = -0.44 * completed_backward_steps / backward_steps
                    forward = target + rng.uniform(-0.015, 0.015)
                reverse_points.append((forward, side))
            local_points = tuple(reversed(reverse_points))

        return tuple(
            Point(
                center_x + forward_x * forward * forward_scale
                + side_x * side * side_scale,
                center_y + forward_y * forward * forward_scale
                + side_y * side * side_scale,
            )
            for forward, side in local_points
        )

    @staticmethod
    def _outward_directions(
        row: int, column: int, rows: int, columns: int
    ) -> tuple[Direction, ...]:
        """Choose a nearest edge after normalizing the active arrow region.

        Using board-space distances on a wide board strongly favors up/down.
        Slot-relative distances instead give every direction comparable area.
        """
        distances = {
            Direction.UP: (row + 0.5) / rows,
            Direction.RIGHT: (columns - column - 0.5) / columns,
            Direction.DOWN: (rows - row - 0.5) / rows,
            Direction.LEFT: (column + 0.5) / columns,
        }
        nearest = min(distances.values())
        return tuple(
            direction for direction, distance in distances.items()
            if abs(distance - nearest) < 1e-9
        )

    @staticmethod
    def solution_order(state: GameState) -> tuple[int, ...]:
        """Return one valid removal order, or a partial order for a deadlock."""
        board = Grid(rows=state.grid.rows, columns=state.grid.columns)
        for arrow in state.arrows:
            board.place_arrow(arrow)

        index_by_identity = {
            id(arrow): index for index, arrow in enumerate(state.arrows)
        }
        dependencies = {
            index: {
                index_by_identity[id(blocker)]
                for blocker in board.blocking_arrows(arrow)
            }
            for index, arrow in enumerate(state.arrows)
        }
        remaining = set(range(len(state.arrows)))
        solution: list[int] = []
        while remaining:
            removable = next(
                (index for index in sorted(remaining) if not dependencies[index]),
                None,
            )
            if removable is None:
                break
            solution.append(removable)
            remaining.remove(removable)
            for blockers in dependencies.values():
                blockers.discard(removable)
        return tuple(solution)


__all__ = ["GeneratedLevel", "LevelGenerator"]

"""Pygame-independent game rules and level controller.

The current model only defines an Arrow anchor (row, column, direction).  For
long or segmented arrows, an Arrow-like object may additionally expose
``occupied_cells``, ``cells``, ``path`` or ``segments``.  Coordinates are
(row, column); segments are expanded inclusively.

Direction convention: 0=up, 1=right, 2=down, 3=left.  The strings
``up/right/down/left`` and direction vectors are accepted too.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import copy
import itertools
import math
from typing import Any

from model.arrow import Arrow, ArrowSegment
from model.game_state import GameState
from model.grid import Grid

Cell = tuple[int, int]
Event = dict[str, Any]


class GameController:
    """Apply clicks and advance game state without depending on Pygame."""

    EVENT_ARROW_FLY_OUT = "arrow_fly_out"
    EVENT_ARROW_BLOCKED = "arrow_blocked"
    EVENT_ANIMATION_FINISHED = "animation_finished"
    EVENT_LEVEL_COMPLETE = "level_complete"
    EVENT_LEVEL_FAILED = "level_failed"
    EVENT_LEVEL_STARTED = "level_started"
    EVENT_LEVEL_RESTARTED = "level_restarted"
    EVENT_INVALID_CLICK = "invalid_click"
    EVENT_ACTION_IGNORED = "action_ignored"
    EVENT_INVALID_ARROW = "invalid_arrow"
    EVENT_NO_NEXT_LEVEL = "no_next_level"

    PHASE_PLAYING = "playing"
    PHASE_LEVEL_COMPLETE = "level_complete"
    PHASE_FAILED = "failed"

    _DIRECTIONS: dict[Any, Cell] = {
        0: (-1, 0), 1: (0, 1), 2: (1, 0), 3: (0, -1),
        "up": (-1, 0), "right": (0, 1), "down": (1, 0), "left": (0, -1),
        "u": (-1, 0), "r": (0, 1), "d": (1, 0), "l": (0, -1),
    }

    def __init__(
        self,
        state: GameState | None = None,
        *,
        max_mistakes: int = 3,
        levels: Sequence[Any] | None = None,
        animation_duration: float = 0.35,
    ) -> None:
        if not isinstance(max_mistakes, int) or isinstance(max_mistakes, bool):
            raise TypeError("max_mistakes must be an integer")
        if max_mistakes < 0:
            raise ValueError("max_mistakes cannot be negative")
        if not isinstance(animation_duration, (int, float)) or isinstance(animation_duration, bool):
            raise TypeError("animation_duration must be numeric")
        if animation_duration < 0 or not math.isfinite(animation_duration):
            raise ValueError("animation_duration must be finite and non-negative")

        self.state = state if state is not None else GameState()
        self.max_mistakes = max_mistakes
        self.animation_duration = float(animation_duration)
        # Defaults are opt-in through the no-argument constructor only.  A
        # caller-provided state or level list always remains authoritative.
        if state is None and levels is None:
            self._levels = self._default_levels()
        else:
            self._levels = list(levels) if levels is not None else None
        self._level_index = 0
        self.current_level = 1
        self.phase = self.PHASE_PLAYING
        self._mistakes_remaining = max_mistakes
        self._animations: dict[str, float] = {}
        self._animation_arrows: dict[str, Any] = {}
        self._animation_ids = itertools.count(1)
        self._events: list[Event] = []
        self._initial_arrows = copy.deepcopy(list(self.state.arrows))
        self._initial_grid = copy.deepcopy(self.state.grid)
        self._set_mistakes(max_mistakes)
        self._sync_grid()

        if state is None and self._levels:
            self._load_level(self._levels[0])

    @staticmethod
    def _default_levels() -> list[GameState]:
        """Return fresh, small levels used by the no-argument controller.

        The first level demonstrates straight arrows.  The second combines a
        segmented arrow with straight arrows.  Each level is solvable by
        removing the independently exposed arrows before the arrows behind
        them.
        """
        level_one = GameState(
            grid=Grid(rows=6, columns=6),
            arrows=[
                # Exposed arrow: remove this before the horizontal arrow.
                Arrow(row=2, column=4, direction=0),
                Arrow(row=2, column=0, direction=1),
                Arrow(row=5, column=2, direction=0),
            ],
        )
        if ArrowSegment is not None:
            segmented = Arrow(
                row=4,
                column=1,
                direction="right",
                arrow_type="segmented",
                segments=(
                    ArrowSegment(((4, 1), (4, 2))),
                    ArrowSegment(((4, 2), (3, 2))),
                ),
            )
        else:
            segmented = Arrow(row=4, column=1, direction="right")
            segmented.segments = [
                ((4, 1), (4, 2)),
                ((4, 2), (3, 2)),
            ]
        level_two = GameState(
            grid=Grid(rows=7, columns=7),
            arrows=[
                # This exposed arrow blocks the segmented arrow's rightward
                # path until it has been removed first.
                Arrow(row=4, column=5, direction="up"),
                segmented,
                Arrow(row=6, column=6, direction="left"),
            ],
        )
        return [level_one, level_two]

    @property
    def mistakes_remaining(self) -> int:
        """Number of blocked clicks still allowed in this level."""
        return self._mistakes_remaining

    @property
    def remaining_arrows(self) -> int:
        """Number of active arrows on the board."""
        return sum(1 for arrow in self.state.arrows if self._active(arrow))

    @property
    def animations(self) -> tuple[dict[str, Any], ...]:
        """Snapshots of active animation timers for a renderer."""
        return tuple(
            {"animation_id": animation_id, "remaining": remaining}
            for animation_id, remaining in self._animations.items()
        )

    def handle_action(self, row: int, column: int) -> list[Event]:
        """Process a board click and return the resulting event dictionaries.

        Invalid, repeated, and post-result clicks never consume a mistake.
        Exactly one mistake is consumed when an active arrow is blocked.
        """
        cell = self._normalise_cell((row, column))
        if cell is None or not self._in_bounds(cell):
            return self._publish(self._event(self.EVENT_INVALID_CLICK, row=row, column=column))
        if self.phase != self.PHASE_PLAYING:
            return self._publish(self._event(self.EVENT_ACTION_IGNORED, row=row, column=column))

        arrow = self._arrow_at(cell)
        if arrow is None:
            return self._publish(self._event(self.EVENT_INVALID_CLICK, row=row, column=column))

        cells = self._arrow_cells(arrow)
        direction = self._direction(arrow)
        if direction is None:
            return self._publish(self._event(
                self.EVENT_INVALID_ARROW, row=row, column=column, arrow=arrow, cells=cells,
            ))

        blockers = self._blockers(arrow, cells, direction)
        if blockers:
            self._set_mistakes(self.mistakes_remaining - 1)
            events = [self._event(
                self.EVENT_ARROW_BLOCKED,
                arrow=arrow,
                cells=cells,
                blocked_by=blockers,
                direction=direction,
                mistakes_remaining=self.mistakes_remaining,
                feedback={
                    "kind": "collision",
                    "effects": ("shake", "flash", "text"),
                    "duration": 0.28,
                },
            )]
            if self.mistakes_remaining == 0:
                self.phase = self.PHASE_FAILED
                self._set_result("lost")
                events.append(self._event(
                    self.EVENT_LEVEL_FAILED,
                    reason="mistakes_exhausted", mistakes_remaining=0,
                ))
            return self._publish(events)

        animation_id = f"fly-out-{next(self._animation_ids)}"
        self._animations[animation_id] = self.animation_duration
        self._deactivate(arrow)
        events = [self._event(
            self.EVENT_ARROW_FLY_OUT,
            arrow=arrow,
            cells=cells,
            direction=direction,
            destination=self._edge_destination(cells, direction),
            animation={
                "id": animation_id, "kind": "fly_out", "duration": self.animation_duration,
            },
            remaining_arrows=self.remaining_arrows,
        )]
        if self.remaining_arrows == 0:
            self.phase = self.PHASE_LEVEL_COMPLETE
            self._set_result("won")
            events.append(self._event(
                self.EVENT_LEVEL_COMPLETE,
                final=self._is_final_level(), remaining_arrows=0,
            ))
        return self._publish(events)

    def update(self, delta_seconds: float) -> list[Event]:
        """Advance fly-out animation timers and emit completion events."""
        if not isinstance(delta_seconds, (int, float)) or isinstance(delta_seconds, bool):
            raise TypeError("delta_seconds must be numeric")
        if delta_seconds < 0 or not math.isfinite(delta_seconds):
            raise ValueError("delta_seconds must be finite and non-negative")

        events: list[Event] = []
        finished: list[str] = []
        for animation_id, remaining in list(self._animations.items()):
            remaining -= float(delta_seconds)
            if remaining <= 0:
                finished.append(animation_id)
            else:
                self._animations[animation_id] = remaining
        for animation_id in finished:
            del self._animations[animation_id]
            events.append(self._event(
                self.EVENT_ANIMATION_FINISHED, animation_id=animation_id,
            ))
        return self._publish(events)

    def restart(self) -> list[Event]:
        """Restore the current level, including arrows and mistakes."""
        self._animations.clear()
        self.state.arrows = copy.deepcopy(self._initial_arrows)
        self._restore_grid()
        self._set_mistakes(self.max_mistakes)
        self.phase = self.PHASE_PLAYING
        self.state.is_running = True
        self._set_result("none")
        self._sync_grid()
        return self._publish(self._event(
            self.EVENT_LEVEL_RESTARTED,
            mistakes_remaining=self.mistakes_remaining,
            remaining_arrows=self.remaining_arrows,
        ))

    def next_level(self) -> list[Event]:
        """Load the next configured level after the current one is complete."""
        if self.phase != self.PHASE_LEVEL_COMPLETE:
            return self._publish(self._event(
                self.EVENT_ACTION_IGNORED,
                action="next_level", reason="current_level_not_complete",
            ))
        if not self._levels or self._level_index + 1 >= len(self._levels):
            return self._publish(self._event(self.EVENT_NO_NEXT_LEVEL))

        self._level_index += 1
        self.current_level += 1
        self._load_level(self._levels[self._level_index])
        return self._publish(self._event(
            self.EVENT_LEVEL_STARTED,
            mistakes_remaining=self.mistakes_remaining,
            remaining_arrows=self.remaining_arrows,
        ))

    def drain_events(self) -> list[Event]:
        """Return and clear events emitted since the previous drain."""
        events, self._events = self._events, []
        return events

    def _load_level(self, value: Any) -> None:
        if isinstance(value, GameState):
            self.state = value
        else:
            self.state.arrows = list(value)
        self._initial_arrows = copy.deepcopy(list(self.state.arrows))
        self._initial_grid = copy.deepcopy(self.state.grid)
        self._animations.clear()
        self._restore_grid()
        self._set_mistakes(self.max_mistakes)
        self.phase = self.PHASE_PLAYING
        self.state.is_running = True
        self._set_result("none")
        self._sync_grid()

    def _publish(self, events: Event | Iterable[Event]) -> list[Event]:
        result = [events] if isinstance(events, dict) else list(events)
        self._events.extend(result)
        return result

    def _event(self, event_type: str, **data: Any) -> Event:
        return {"type": event_type, "level": self.current_level, **data}

    def _set_result(self, result_name: str) -> None:
        """Set modern enum-backed results, falling back to legacy flags."""
        result_type = type(getattr(self.state, "result", None))
        result_value = getattr(result_type, result_name.upper(), None)
        if result_value is not None and hasattr(self.state, "result"):
            self.state.result = result_value
            return
        if result_name == "won":
            try:
                self.state.is_won = True
                self.state.is_lost = False
            except AttributeError:
                pass
        elif result_name == "lost":
            try:
                self.state.is_won = False
                self.state.is_lost = True
            except AttributeError:
                pass
        else:
            try:
                self.state.is_won = False
                self.state.is_lost = False
            except AttributeError:
                pass

    def _set_mistakes(self, value: int) -> None:
        self._mistakes_remaining = max(0, int(value))
        # GameState intentionally remains unchanged; this is a presentation
        # convenience field attached to its normal, non-slotted dataclass.
        self.state.mistakes_remaining = self._mistakes_remaining

    def _is_final_level(self) -> bool:
        return not self._levels or self._level_index + 1 >= len(self._levels)

    def _arrow_at(self, cell: Cell) -> Any | None:
        for arrow in reversed(self.state.arrows):
            if self._active(arrow) and cell in self._arrow_cells(arrow):
                return arrow
        return None

    @staticmethod
    def _active(arrow: Any) -> bool:
        """Support both the initial ``active`` model and ArrowState."""
        if hasattr(arrow, "active"):
            return bool(arrow.active)
        state = getattr(arrow, "state", None)
        state_value = getattr(state, "value", state)
        return state_value not in {"flying_out", "removed"}

    def _blockers(self, target: Any, cells: set[Cell], direction: Cell) -> list[Any]:
        occupied: dict[Cell, list[Any]] = {}
        for arrow in self.state.arrows:
            if not self._active(arrow) or arrow is target:
                continue
            for cell in self._arrow_cells(arrow):
                occupied.setdefault(cell, []).append(arrow)

        blockers: list[Any] = []
        seen: set[int] = set()
        for row, column in cells:
            probe = (row + direction[0], column + direction[1])
            while self._in_bounds(probe):
                for arrow in occupied.get(probe, ()):
                    if id(arrow) not in seen:
                        seen.add(id(arrow))
                        blockers.append(arrow)
                probe = (probe[0] + direction[0], probe[1] + direction[1])
        return blockers

    def _deactivate(self, arrow: Any) -> None:
        if hasattr(arrow, "mark_flying_out"):
            arrow.mark_flying_out()
        else:
            try:
                arrow.active = False
            except (AttributeError, TypeError):
                self.state.arrows = [candidate for candidate in self.state.arrows if candidate is not arrow]
        self._clear_grid_cells(arrow)

    def _clear_grid_cells(self, arrow: Any) -> None:
        remove_arrow = getattr(self.state.grid, "remove_arrow", None)
        if callable(remove_arrow):
            remove_arrow(arrow)
            return
        for row in getattr(self.state.grid, "cells", ()):
            for index, value in enumerate(row):
                if value is arrow:
                    row[index] = None

    def _sync_grid(self) -> None:
        cells = getattr(self.state.grid, "cells", None)
        if not isinstance(cells, list):
            return
        clear = getattr(self.state.grid, "clear", None)
        if callable(clear):
            clear()
        for row in cells:
            if isinstance(row, list):
                for index in range(len(row)):
                    row[index] = None
        for arrow in self.state.arrows:
            if not self._active(arrow):
                continue
            place_arrow = getattr(self.state.grid, "place_arrow", None)
            if callable(place_arrow):
                place_arrow(arrow)
                continue
            for row, column in self._arrow_cells(arrow):
                if self._in_bounds((row, column)):
                    cells[row][column] = arrow

    def _restore_grid(self) -> None:
        grid = self._initial_grid
        rows = int(getattr(grid, "rows", getattr(self.state.grid, "rows", 0)))
        columns = int(getattr(grid, "columns", getattr(self.state.grid, "columns", 0)))
        self.state.grid.rows = rows
        self.state.grid.columns = columns
        clear = getattr(self.state.grid, "clear", None)
        if callable(clear):
            clear()
        else:
            self.state.grid.cells = [[None for _ in range(columns)] for _ in range(rows)]

    def _in_bounds(self, cell: Cell) -> bool:
        rows = int(getattr(self.state.grid, "rows", 0))
        columns = int(getattr(self.state.grid, "columns", 0))
        return 0 <= cell[0] < rows and 0 <= cell[1] < columns

    def _direction(self, arrow: Any) -> Cell | None:
        value = getattr(arrow, "direction", None)
        if isinstance(value, str):
            value = value.lower()
        try:
            vector = self._DIRECTIONS.get(value)
        except TypeError:
            vector = None
        if vector is not None:
            return vector
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) == 2:
            try:
                vector = (int(value[0]), int(value[1]))
            except (TypeError, ValueError):
                return None
            if vector in {(-1, 0), (0, 1), (1, 0), (0, -1)}:
                return vector
        return None

    def _edge_destination(self, cells: set[Cell], direction: Cell) -> Cell | None:
        if not cells:
            return None
        if direction == (-1, 0):
            lead = min(cells, key=lambda cell: cell[0])
            return (0, lead[1])
        if direction == (1, 0):
            lead = max(cells, key=lambda cell: cell[0])
            return (int(self.state.grid.rows) - 1, lead[1])
        if direction == (0, -1):
            lead = min(cells, key=lambda cell: cell[1])
            return (lead[0], 0)
        lead = max(cells, key=lambda cell: cell[1])
        return (lead[0], int(self.state.grid.columns) - 1)

    def _arrow_cells(self, arrow: Any) -> set[Cell]:
        for name in ("occupied_cells", "cells", "path"):
            value = getattr(arrow, name, None)
            if value is not None:
                cells = self._read_cells(value, expand_segments=False)
                if cells:
                    return cells
        segments = getattr(arrow, "segments", None)
        if segments is not None:
            cells = self._read_cells(segments, expand_segments=True)
            if cells:
                return cells
        anchor = self._normalise_cell((getattr(arrow, "row", None), getattr(arrow, "column", None)))
        return {anchor} if anchor is not None else set()

    def _read_cells(self, value: Any, *, expand_segments: bool) -> set[Cell]:
        cell = self._normalise_cell(value)
        if cell is not None:
            return {cell}
        if isinstance(value, Mapping):
            if "cells" in value:
                return self._read_cells(value["cells"], expand_segments=expand_segments)
            if "start" in value and "end" in value:
                return self._expand_segment(value["start"], value["end"])
            return set()
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
            result: set[Cell] = set()
            for item in value:
                if expand_segments:
                    segment = self._read_segment(item)
                    if segment is not None:
                        result.update(segment)
                        continue
                item_cell = self._normalise_cell(item)
                if item_cell is not None:
                    result.add(item_cell)
                else:
                    result.update(self._read_cells(item, expand_segments=expand_segments))
            return result
        return set()

    def _read_segment(self, value: Any) -> set[Cell] | None:
        if isinstance(value, Mapping) and "start" in value and "end" in value:
            return self._expand_segment(value["start"], value["end"])
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            if len(value) == 4 and all(isinstance(part, int) for part in value):
                return self._expand_segment(value[:2], value[2:])
            if len(value) == 2:
                start = self._normalise_cell(value[0])
                end = self._normalise_cell(value[1])
                if start is not None and end is not None:
                    return self._expand_segment(start, end)
        return None

    @staticmethod
    def _expand_segment(start: Any, end: Any) -> set[Cell]:
        first = GameController._normalise_cell(start)
        last = GameController._normalise_cell(end)
        if first is None or last is None:
            return set()
        row_step = (last[0] > first[0]) - (last[0] < first[0])
        col_step = (last[1] > first[1]) - (last[1] < first[1])
        if row_step and col_step:
            return {first, last}
        length = max(abs(last[0] - first[0]), abs(last[1] - first[1]))
        return {
            (first[0] + row_step * offset, first[1] + col_step * offset)
            for offset in range(length + 1)
        }

    @staticmethod
    def _normalise_cell(value: Any) -> Cell | None:
        if hasattr(value, "row") and hasattr(value, "column"):
            value = (value.row, value.column)
        if hasattr(value, "row") and hasattr(value, "column"):
            value = (value.row, value.column)
        if isinstance(value, Mapping):
            if "row" in value and "column" in value:
                value = (value["row"], value["column"])
            elif "r" in value and "c" in value:
                value = (value["r"], value["c"])
            else:
                return None
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) == 2:
            row, column = value
            if isinstance(row, int) and not isinstance(row, bool) and isinstance(column, int) and not isinstance(column, bool):
                return row, column
        return None


__all__ = ["Cell", "Event", "GameController"]
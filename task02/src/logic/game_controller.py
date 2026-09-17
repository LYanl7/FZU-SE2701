"""Pygame-independent game rules and level controller.

Point-native arrows are ordered polylines: adjacent ``Arrow.points`` form
line segments and the last point is the tip.  Arrow-like objects may expose
``line_segments`` instead; occupied cells/path values remain supported by the
legacy row/column API.  Point-native callers use ``handle_point(x, y)`` and
are never quantized to a grid.

Direction convention: 0=up, 1=right, 2=down, 3=left.  The strings
``up/right/down/left`` and direction vectors are accepted too.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import copy
import itertools
import math
from typing import Any

from logic.level_generator import LevelGenerator
from model.arrow import Point
from model.game_state import GameState

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
    EVENT_LEVEL_GENERATED = "level_generated"

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
        animation_duration: float = 0.7,
        generation_seed: int | None = None,
    ) -> None:
        if not isinstance(max_mistakes, int) or isinstance(max_mistakes, bool):
            raise TypeError("max_mistakes must be an integer")
        if max_mistakes < 0:
            raise ValueError("max_mistakes cannot be negative")
        if not isinstance(animation_duration, (int, float)) or isinstance(animation_duration, bool):
            raise TypeError("animation_duration must be numeric")
        if animation_duration < 0 or not math.isfinite(animation_duration):
            raise ValueError("animation_duration must be finite and non-negative")
        if generation_seed is not None and (
            not isinstance(generation_seed, int) or isinstance(generation_seed, bool)
        ):
            raise TypeError("generation_seed must be an integer or None")

        self.state = state if state is not None else GameState()
        self.max_mistakes = max_mistakes
        self.animation_duration = float(animation_duration)
        self._level_generator = LevelGenerator()
        self._generation_seed = generation_seed
        self._auto_generate_levels = state is None and levels is None
        self._levels = list(levels) if levels is not None else None
        self._level_index = 0
        self.current_level = 1
        self.phase = self.PHASE_PLAYING
        self._elapsed_seconds = 0.0
        self._mistakes_remaining = max_mistakes
        self._animations: dict[str, float] = {}
        self._animation_arrows: dict[str, Any] = {}
        self._animation_ids = itertools.count(1)
        self._events: list[Event] = []
        self._initial_arrows = copy.deepcopy(list(self.state.arrows))
        self._initial_grid = copy.deepcopy(self.state.grid)
        self._set_elapsed(0.0)
        self._set_mistakes(max_mistakes)
        self._sync_grid()

        if self._auto_generate_levels:
            generated = self._level_generator.generate(
                1, seed=self._seed_for_level(1)
            )
            self._load_level(generated.state)
        elif state is None and self._levels:
            self._load_level(self._levels[0])

    @property
    def mistakes_remaining(self) -> int:
        """Number of blocked clicks still allowed in this level."""
        return self._mistakes_remaining

    @property
    def remaining_arrows(self) -> int:
        """Number of active arrows on the board."""
        return sum(1 for arrow in self.state.arrows if self._active(arrow))

    @property
    def elapsed_seconds(self) -> float:
        """Elapsed play time for the current level in seconds.

        The value advances only while the controller is in ``PHASE_PLAYING``;
        terminal-state updates are intentionally no-ops for this clock.
        """
        return self._elapsed_seconds

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
        # Point-native clients should use handle_point; accepting numeric
        # coordinates here as well keeps the controller convenient for simple
        # adapters while preserving the legacy integer API.
        if not (
            isinstance(row, int) and not isinstance(row, bool)
            and isinstance(column, int) and not isinstance(column, bool)
        ):
            return self.handle_point(float(column), float(row))
        cell = self._normalise_cell((row, column))
        if cell is None or not self._in_bounds(cell):
            return self._publish(self._event(self.EVENT_INVALID_CLICK, row=row, column=column))
        if self.phase != self.PHASE_PLAYING:
            return self._publish(self._event(self.EVENT_ACTION_IGNORED, row=row, column=column))

        arrow = self._arrow_at(cell)
        if arrow is None:
            # Point-native default levels use half-unit board coordinates.  A
            # legacy row/column caller can still target the corresponding
            # point at the center of that old cell without quantizing the
            # point-based geometry itself.
            center = Point(float(column) + 0.5, float(row) + 0.5)
            if self._in_point_bounds(center) and self._arrow_at_point(center) is not None:
                return self.handle_point(center.x, center.y)
            return self._publish(self._event(self.EVENT_INVALID_CLICK, row=row, column=column))

        cells = self._arrow_cells(arrow)
        direction = self._direction(arrow)
        if direction is None:
            return self._publish(self._event(
                self.EVENT_INVALID_ARROW, row=row, column=column, arrow=arrow, cells=cells,
            ))

        blockers, collision_point, collision_arrow = self._point_blocker_details(
            arrow, direction
        )
        if not blockers:
            # Keep the original occupancy-ray implementation as a fallback
            # for Arrow-like legacy objects that expose cells but no points.
            blockers = self._blockers(arrow, cells, direction)
            if blockers and collision_point is None:
                collision_point, collision_arrow = self._legacy_collision_details(
                    arrow, direction, blockers
                )
        if blockers:
            self._set_mistakes(self.mistakes_remaining - 1)
            events = [self._event(
                self.EVENT_ARROW_BLOCKED,
                arrow=arrow,
                cells=cells,
                blocked_by=blockers,
                direction=direction,
                mistakes_remaining=self.mistakes_remaining,
                collision_arrow=collision_arrow,
                collision_point=collision_point,
                blocked_destination=self._blocked_destination(
                    self._arrow_tip(arrow), collision_point, direction
                ),
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
        # Keep the arrow associated with its timer so the logical lifecycle
        # can be completed when the presentation finishes the flight.  The
        # board cells are cleared immediately in ``_deactivate`` (the arrow
        # must not remain rendered at its origin while it is flying), while
        # the model is marked REMOVED only after the animation duration.
        self._animation_arrows[animation_id] = arrow
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
        return self._publish(events)

    def handle_point(self, x: float, y: float) -> list[Event]:
        """Process a click in the point-coordinate board space.

        Unlike ``handle_action(row, column)``, this method does not quantize
        the click or the arrows to cells.  It is the preferred entry point for
        a point-based renderer.
        """
        point = self._normalise_point((x, y))
        if point is None or not self._in_point_bounds(point):
            return self._publish(self._event(self.EVENT_INVALID_CLICK, x=x, y=y))
        if self.phase != self.PHASE_PLAYING:
            return self._publish(self._event(self.EVENT_ACTION_IGNORED, x=x, y=y))

        arrow = self._arrow_at_point(point)
        if arrow is None:
            return self._publish(self._event(self.EVENT_INVALID_CLICK, x=x, y=y))
        points = self._arrow_polyline(arrow)
        direction = self._direction(arrow)
        if direction is None:
            return self._publish(self._event(
                self.EVENT_INVALID_ARROW, x=x, y=y, arrow=arrow, points=points,
            ))
        blockers, collision_point, collision_arrow = self._point_blocker_details(
            arrow, direction
        )
        if blockers:
            self._set_mistakes(self.mistakes_remaining - 1)
            events = [self._event(
                self.EVENT_ARROW_BLOCKED,
                arrow=arrow,
                points=points,
                blocked_by=blockers,
                direction=direction,
                mistakes_remaining=self.mistakes_remaining,
                collision_arrow=collision_arrow,
                collision_point=collision_point,
                blocked_destination=self._blocked_destination(
                    self._arrow_tip(arrow), collision_point, direction
                ),
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
        self._animation_arrows[animation_id] = arrow
        self._deactivate(arrow)
        events = [self._event(
            self.EVENT_ARROW_FLY_OUT,
            arrow=arrow,
            points=points,
            direction=direction,
            destination=self._edge_destination_point(points, direction),
            animation={
                "id": animation_id, "kind": "fly_out", "duration": self.animation_duration,
            },
            remaining_arrows=self.remaining_arrows,
        )]
        return self._publish(events)

    def update(self, delta_seconds: float) -> list[Event]:
        """Advance fly-out animation timers and emit completion events."""
        if not isinstance(delta_seconds, (int, float)) or isinstance(delta_seconds, bool):
            raise TypeError("delta_seconds must be numeric")
        if delta_seconds < 0 or not math.isfinite(delta_seconds):
            raise ValueError("delta_seconds must be finite and non-negative")

        if self.phase == self.PHASE_PLAYING:
            self._set_elapsed(self._elapsed_seconds + float(delta_seconds))

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
            arrow = self._animation_arrows.pop(animation_id, None)
            if arrow is not None:
                # Only the final pending animation may invoke
                # ``GameState.complete_arrow_exit``.  The model treats a
                # FLYING_OUT arrow as no longer remaining, so calling that
                # method while another animation is still running would mark
                # the whole state WON and stop the presentation ticking.
                self._finish_animation(arrow, finalize_state=not self._animations)
            events.append(self._event(
                self.EVENT_ANIMATION_FINISHED,
                animation_id=animation_id,
            ))
        # Do not finish a level when its last arrow merely starts flying.  The
        # presentation stops ticking once the state is WON, so this transition
        # must happen only after every pending exit animation has completed.
        if (
            self.phase == self.PHASE_PLAYING
            and not self._animations
            and self.remaining_arrows == 0
        ):
            self.phase = self.PHASE_LEVEL_COMPLETE
            self._set_result("won")
            events.append(self._event(
                self.EVENT_LEVEL_COMPLETE,
                final=self._is_final_level(), remaining_arrows=0,
            ))
        return self._publish(events)

    def restart(self) -> list[Event]:
        """Restore the current level, including arrows and mistakes."""
        self._animations.clear()
        self._animation_arrows.clear()
        self._set_elapsed(0.0)
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
        """Load the next configured level, generating one when defaults end."""
        if self.phase != self.PHASE_LEVEL_COMPLETE:
            return self._publish(self._event(
                self.EVENT_ACTION_IGNORED,
                action="next_level", reason="current_level_not_complete",
            ))
        if self._levels and self._level_index + 1 < len(self._levels):
            self._level_index += 1
            self.current_level += 1
            self._load_level(self._levels[self._level_index])
            return self._publish(self._event(
                self.EVENT_LEVEL_STARTED,
                mistakes_remaining=self.mistakes_remaining,
                remaining_arrows=self.remaining_arrows,
            ))
        if self._auto_generate_levels:
            return self.generate_level(self.current_level + 1)
        else:
            return self._publish(self._event(self.EVENT_NO_NEXT_LEVEL))

    def generate_level(
        self, level: int | None = None, *, seed: int | None = None
    ) -> list[Event]:
        """Generate and immediately start a verified-solvable random level."""
        target_level = self.current_level if level is None else level
        if seed is None:
            seed = self._seed_for_level(target_level)
        generated = self._level_generator.generate(target_level, seed=seed)
        self.current_level = target_level
        self._auto_generate_levels = True
        self._levels = None
        self._level_index = 0
        self._load_level(generated.state)
        return self._publish(self._event(
            self.EVENT_LEVEL_GENERATED,
            seed=generated.seed,
            solution=generated.solution,
            mistakes_remaining=self.mistakes_remaining,
            remaining_arrows=self.remaining_arrows,
        ))

    def _seed_for_level(self, level: int) -> int | None:
        if self._generation_seed is None:
            return None
        return self._generation_seed + level * 1_000_003

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
        self._animation_arrows.clear()
        self._set_elapsed(0.0)
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

    def _set_elapsed(self, value: float) -> None:
        """Update the controller clock and expose it through the state too."""
        self._elapsed_seconds = max(0.0, float(value))
        # GameState is intentionally kept backwards-compatible; attaching the
        # mirror field lets HUD adapters read either the controller or state.
        try:
            self.state.elapsed_seconds = self._elapsed_seconds
        except (AttributeError, TypeError):
            pass

    def _is_final_level(self) -> bool:
        if self._auto_generate_levels:
            return False
        return not self._levels or self._level_index + 1 >= len(self._levels)

    def _arrow_at(self, cell: Cell) -> Any | None:
        for arrow in reversed(self.state.arrows):
            if self._active(arrow) and cell in self._arrow_cells(arrow):
                return arrow
        return None

    def _arrow_at_point(self, point: Point, tolerance: float = 0.45) -> Any | None:
        """Find the nearest active arrow line within a board-unit radius."""
        candidates: list[tuple[float, Any]] = []
        for arrow in reversed(self.state.arrows):
            if not self._active(arrow):
                continue
            distance = self._point_to_arrow_distance(point, arrow)
            if distance <= tolerance:
                candidates.append((distance, arrow))
        return min(candidates, key=lambda item: item[0])[1] if candidates else None

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

    def _point_blockers(self, target: Any, direction: Cell) -> list[Any]:
        """Find active arrows intersecting the target's continuous exit ray."""
        blockers, _, _ = self._point_blocker_details(target, direction)
        return blockers

    def _point_blocker_details(
        self, target: Any, direction: Cell,
    ) -> tuple[list[Any], Point | None, Any | None]:
        """Return blockers ordered by nearest intersection with the exit ray.

        The returned point is the first collision point along the ray and the
        returned arrow is the corresponding nearest blocker.  All blockers
        remain in the first tuple item for compatibility with the existing
        ``blocked_by`` event field.
        """
        tip = self._arrow_tip(target)
        if tip is None:
            return [], None, None
        ray = self._ray_to_boundary(tip, direction)
        if ray is None:
            return [], None, None

        nearest_by_arrow: list[tuple[float, int, Any]] = []
        for arrow in self.state.arrows:
            if not self._active(arrow) or arrow is target:
                continue
            hit_parameters = [
                parameter
                for segment in self._arrow_segments(arrow)
                if (parameter := self._ray_segment_parameter(ray, segment)) is not None
            ]
            if hit_parameters:
                nearest_by_arrow.append((min(hit_parameters), len(nearest_by_arrow), arrow))

        nearest_by_arrow.sort(key=lambda item: (item[0], item[1]))
        if not nearest_by_arrow:
            return [], None, None
        nearest_parameter, _, nearest_arrow = nearest_by_arrow[0]
        collision_point = self._point_on_segment(ray, nearest_parameter)
        return [item[2] for item in nearest_by_arrow], collision_point, nearest_arrow

    @staticmethod
    def _cross(first: Point, second: Point, third: Point) -> float:
        """Cross product of (second-first) and (third-first)."""
        return (second.x - first.x) * (third.y - first.y) - (
            second.y - first.y
        ) * (third.x - first.x)

    @staticmethod
    def _point_on_segment(
        segment: tuple[Point, Point], parameter: float,
    ) -> Point:
        start, end = segment
        return Point(
            start.x + (end.x - start.x) * parameter,
            start.y + (end.y - start.y) * parameter,
        )

    @staticmethod
    def _ray_segment_parameter(
        ray: tuple[Point, Point], segment: tuple[Point, Point],
        epsilon: float = 1e-9,
    ) -> float | None:
        """Return the first normalized ray parameter at a segment hit."""
        ray_start, ray_end = ray
        segment_start, segment_end = segment
        ray_dx = ray_end.x - ray_start.x
        ray_dy = ray_end.y - ray_start.y
        segment_dx = segment_end.x - segment_start.x
        segment_dy = segment_end.y - segment_start.y
        ray_length_squared = ray_dx * ray_dx + ray_dy * ray_dy
        if ray_length_squared <= epsilon:
            return None

        denominator = ray_dx * segment_dy - ray_dy * segment_dx
        offset_x = segment_start.x - ray_start.x
        offset_y = segment_start.y - ray_start.y
        if abs(denominator) > epsilon:
            ray_parameter = (offset_x * segment_dy - offset_y * segment_dx) / denominator
            segment_parameter = (offset_x * ray_dy - offset_y * ray_dx) / denominator
            if -epsilon <= ray_parameter <= 1 + epsilon and -epsilon <= segment_parameter <= 1 + epsilon:
                return max(0.0, min(1.0, ray_parameter))
            return None

        # Parallel segments only collide when they are collinear.  Project
        # both endpoints onto the ray and take the first overlapping point.
        if abs(offset_x * ray_dy - offset_y * ray_dx) > epsilon:
            return None
        projected = [
            ((point.x - ray_start.x) * ray_dx + (point.y - ray_start.y) * ray_dy)
            / ray_length_squared
            for point in (segment_start, segment_end)
        ]
        first = max(0.0, min(projected))
        last = min(1.0, max(projected))
        return first if first <= last + epsilon else None

    def _blocked_destination(
        self, tip: Point | None, collision_point: Point | None, direction: Cell,
        gap: float = 0.12,
    ) -> Point | None:
        """Return the safe destination for the arrow tip before a blocker.

        ``blocked_destination`` is deliberately defined as a tip position,
        not an anchor position.  Translating the whole polyline by the
        resulting tip delta preserves the arrow's own length and keeps a
        small visual gap before the collision line.
        """
        if tip is None:
            return None
        if collision_point is None:
            return tip
        dx, dy = direction[1], direction[0]
        distance = (
            (collision_point.x - tip.x) * dx
            + (collision_point.y - tip.y) * dy
        )
        travel = max(0.0, distance - max(0.0, gap))
        return Point(tip.x + dx * travel, tip.y + dy * travel)

    def _legacy_collision_details(
        self, target: Any, direction: Cell, blockers: Sequence[Any],
    ) -> tuple[Point | None, Any | None]:
        """Approximate collision details for cell-only Arrow-like objects."""
        tip = self._arrow_tip(target)
        if tip is None:
            cells = self._arrow_cells(target)
            if not cells:
                return None, None
            if direction == (-1, 0):
                cell = min(cells, key=lambda value: value[0])
            elif direction == (1, 0):
                cell = max(cells, key=lambda value: value[0])
            elif direction == (0, -1):
                cell = min(cells, key=lambda value: value[1])
            else:
                cell = max(cells, key=lambda value: value[1])
            tip = Point(float(cell[1]), float(cell[0]))
        ray = self._ray_to_boundary(tip, direction)
        if ray is None:
            return None, None
        nearest: tuple[float, Any] | None = None
        for blocker in blockers:
            for row, column in self._arrow_cells(blocker):
                parameter = self._ray_segment_parameter(
                    ray, (Point(float(column), float(row)), Point(float(column), float(row)))
                )
                if parameter is not None and (nearest is None or parameter < nearest[0]):
                    nearest = parameter, blocker
        if nearest is None:
            return None, blockers[0] if blockers else None
        return self._point_on_segment(ray, nearest[0]), nearest[1]

    def _deactivate(self, arrow: Any) -> None:
        if hasattr(arrow, "mark_flying_out"):
            arrow.mark_flying_out()
        else:
            try:
                arrow.active = False
            except (AttributeError, TypeError):
                self.state.arrows = [candidate for candidate in self.state.arrows if candidate is not arrow]
        self._clear_grid_cells(arrow)

    def _finish_animation(self, arrow: Any, *, finalize_state: bool = True) -> None:
        """Finalize an arrow after its fly-out animation has elapsed.

        ``GameState`` owns the modern Arrow lifecycle and removes the arrow
        from the occupancy index.  The fallback branches preserve support for
        the lightweight Arrow-like objects accepted by this controller.
        """
        complete_exit = getattr(self.state, "complete_arrow_exit", None)
        if finalize_state and callable(complete_exit):
            complete_exit(arrow)
            return

        mark_removed = getattr(arrow, "mark_removed", None)
        if callable(mark_removed):
            mark_removed()
            return

        try:
            arrow.active = False
        except (AttributeError, TypeError):
            self.state.arrows = [
                candidate for candidate in self.state.arrows if candidate is not arrow
            ]
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

    def _in_point_bounds(self, point: Point) -> bool:
        rows = float(getattr(self.state.grid, "rows", 0))
        columns = float(getattr(self.state.grid, "columns", 0))
        return 0 <= point.x < columns and 0 <= point.y < rows

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

    def _edge_destination_point(
        self, points: Iterable[Point], direction: Cell,
    ) -> Point | None:
        points = tuple(points)
        if not points:
            return None
        tip = points[-1]
        if direction == (-1, 0):
            return Point(tip.x, 0)
        if direction == (1, 0):
            return Point(tip.x, float(self.state.grid.rows))
        if direction == (0, -1):
            return Point(0, tip.y)
        return Point(float(self.state.grid.columns), tip.y)

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

    @staticmethod
    def _arrow_polyline(arrow: Any) -> tuple[Point, ...]:
        """Return an arrow's ordered points, from tail to tip.

        ``points`` is the canonical representation.  LineSegment-like APIs
        are accepted for model revisions that expose ``line_segments`` first;
        legacy occupied points/path values remain valid fallbacks.
        """
        raw_points = getattr(arrow, "points", None)
        if raw_points:
            points = GameController._coerce_points(raw_points)
            if points:
                return points

        raw_segments = getattr(arrow, "line_segments", None)
        if callable(raw_segments):
            raw_segments = raw_segments()
        if raw_segments:
            points: list[Point] = []
            for segment in GameController._iter_segments(raw_segments):
                endpoints = GameController._segment_endpoints(segment)
                if endpoints is None:
                    continue
                start, end = endpoints
                if not points:
                    points.append(start)
                elif points[-1] != start:
                    points.append(start)
                points.append(end)
            if points:
                return tuple(points)

        for name in ("occupied_points", "path", "occupied_cells"):
            value = getattr(arrow, name, None)
            if value:
                points = GameController._coerce_points(value)
                if points:
                    return points

        x, y = getattr(arrow, "x", None), getattr(arrow, "y", None)
        if x is None:
            x, y = getattr(arrow, "column", None), getattr(arrow, "row", None)
        point = GameController._coerce_point((x, y)) if x is not None and y is not None else None
        return (point,) if point is not None else ()

    @staticmethod
    def _arrow_segments(arrow: Any) -> tuple[tuple[Point, Point], ...]:
        """Return every geometric line segment making up an arrow."""
        raw_segments = getattr(arrow, "line_segments", None)
        if callable(raw_segments):
            raw_segments = raw_segments()
        if raw_segments:
            segments = tuple(
                endpoints
                for value in GameController._iter_segments(raw_segments)
                if (endpoints := GameController._segment_endpoints(value)) is not None
            )
            if segments:
                return segments

        points = GameController._arrow_polyline_without_segments(arrow)
        if len(points) >= 2:
            return tuple(zip(points, points[1:]))
        if points:
            return ((points[0], points[0]),)
        return ()

    @staticmethod
    def _arrow_polyline_without_segments(arrow: Any) -> tuple[Point, ...]:
        """Read canonical/legacy ordered points without consulting segments."""
        for name in ("points", "occupied_points", "path", "occupied_cells"):
            value = getattr(arrow, name, None)
            if value:
                points = GameController._coerce_points(value)
                if points:
                    return points
        x, y = getattr(arrow, "x", None), getattr(arrow, "y", None)
        if x is None:
            x, y = getattr(arrow, "column", None), getattr(arrow, "row", None)
        point = GameController._coerce_point((x, y)) if x is not None and y is not None else None
        return (point,) if point is not None else ()

    @staticmethod
    def _iter_segments(value: Any) -> Iterable[Any]:
        """Normalize a single segment or a collection of segments."""
        if isinstance(value, Mapping):
            if any(key in value for key in ("start", "end", "from", "to", "p1", "p2")):
                return (value,)
            return tuple(value.values())
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            if len(value) == 4 and all(isinstance(part, (int, float)) for part in value):
                return (value,)
            if len(value) == 2 and all(GameController._coerce_point(part) is not None for part in value):
                return (value,)
            return tuple(value)
        try:
            return tuple(value)
        except TypeError:
            return (value,)

    @staticmethod
    def _segment_endpoints(value: Any) -> tuple[Point, Point] | None:
        names = (
            ("start", "end"),
            ("from_point", "to_point"),
            ("from", "to"),
            ("p1", "p2"),
        )
        first = second = None
        if isinstance(value, Mapping):
            for left, right in names:
                if left in value and right in value:
                    first, second = value[left], value[right]
                    break
        else:
            for left, right in names:
                first = getattr(value, left, None)
                second = getattr(value, right, None)
                if first is not None and second is not None:
                    break
            if first is None:
                segment_points = getattr(value, "points", getattr(value, "vertices", None))
                if isinstance(segment_points, Sequence) and len(segment_points) >= 2:
                    first, second = segment_points[0], segment_points[-1]
            if first is None and isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                if len(value) == 4 and all(isinstance(part, (int, float)) for part in value):
                    first, second = value[:2], value[2:]
                elif len(value) == 2:
                    first, second = value
        first_point = GameController._coerce_point(first)
        second_point = GameController._coerce_point(second)
        if first_point is None or second_point is None:
            return None
        return first_point, second_point

    @staticmethod
    def _coerce_points(value: Any) -> tuple[Point, ...]:
        if isinstance(value, (Point,)) or hasattr(value, "x") and hasattr(value, "y"):
            point = GameController._coerce_point(value)
            return (point,) if point is not None else ()
        try:
            values = tuple(value)
        except TypeError:
            return ()
        points = tuple(
            point for item in values
            if (point := GameController._coerce_point(item)) is not None
        )
        return points

    @staticmethod
    def _coerce_point(value: Any) -> Point | None:
        if isinstance(value, Point):
            return value
        if isinstance(value, Mapping):
            if "x" in value and "y" in value:
                value = (value["x"], value["y"])
            elif "column" in value and "row" in value:
                value = (value["column"], value["row"])
            else:
                return None
        elif hasattr(value, "x") and hasattr(value, "y"):
            value = (value.x, value.y)
        elif hasattr(value, "column") and hasattr(value, "row"):
            value = (value.column, value.row)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) == 2:
            try:
                return Point(float(value[0]), float(value[1]))
            except (TypeError, ValueError):
                return None
        return None

    @staticmethod
    def _arrow_points(arrow: Any) -> set[Point]:
        """Compatibility set view of an arrow's ordered point path."""
        return set(GameController._arrow_polyline(arrow))

    @staticmethod
    def _arrow_tip(arrow: Any) -> Point | None:
        points = GameController._arrow_polyline(arrow)
        return points[-1] if points else None

    @staticmethod
    def _point_to_arrow_distance(point: Point, arrow: Any) -> float:
        segments = GameController._arrow_segments(arrow)
        if not segments:
            return float("inf")
        return min(
            GameController._point_to_segment_distance(point, *segment)
            for segment in segments
        )

    @staticmethod
    def _point_to_segment_distance(point: Point, start: Point, end: Point) -> float:
        dx, dy = end.x - start.x, end.y - start.y
        length_squared = dx * dx + dy * dy
        if length_squared == 0:
            return math.hypot(point.x - start.x, point.y - start.y)
        projection = ((point.x - start.x) * dx + (point.y - start.y) * dy) / length_squared
        projection = max(0.0, min(1.0, projection))
        nearest_x = start.x + projection * dx
        nearest_y = start.y + projection * dy
        return math.hypot(point.x - nearest_x, point.y - nearest_y)

    def _ray_to_boundary(self, tip: Point, direction: Cell) -> tuple[Point, Point] | None:
        dx, dy = direction[1], direction[0]
        if dx > 0:
            end = Point(float(getattr(self.state.grid, "columns", 0)), tip.y)
        elif dx < 0:
            end = Point(0, tip.y)
        elif dy > 0:
            end = Point(tip.x, float(getattr(self.state.grid, "rows", 0)))
        elif dy < 0:
            end = Point(tip.x, 0)
        else:
            return None
        return tip, end

    @staticmethod
    def _segments_intersect(
        first: tuple[Point, Point], second: tuple[Point, Point],
        epsilon: float = 1e-9,
    ) -> bool:
        a, b = first
        c, d = second

        def cross(origin: Point, left: Point, right: Point) -> float:
            return (left.x - origin.x) * (right.y - origin.y) - (
                left.y - origin.y
            ) * (right.x - origin.x)

        def on_segment(origin: Point, end: Point, point: Point) -> bool:
            return (
                min(origin.x, end.x) - epsilon <= point.x <= max(origin.x, end.x) + epsilon
                and min(origin.y, end.y) - epsilon <= point.y <= max(origin.y, end.y) + epsilon
            )

        orientations = (cross(a, b, c), cross(a, b, d), cross(c, d, a), cross(c, d, b))
        if all(abs(value) <= epsilon for value in orientations):
            return on_segment(a, b, c) or on_segment(a, b, d) or on_segment(c, d, a) or on_segment(c, d, b)
        if abs(orientations[0]) <= epsilon and on_segment(a, b, c):
            return True
        if abs(orientations[1]) <= epsilon and on_segment(a, b, d):
            return True
        if abs(orientations[2]) <= epsilon and on_segment(c, d, a):
            return True
        if abs(orientations[3]) <= epsilon and on_segment(c, d, b):
            return True
        return (
            orientations[0] > epsilon and orientations[1] < -epsilon
            or orientations[0] < -epsilon and orientations[1] > epsilon
        ) and (
            orientations[2] > epsilon and orientations[3] < -epsilon
            or orientations[2] < -epsilon and orientations[3] > epsilon
        )

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

    @staticmethod
    def _normalise_point(value: Any) -> Point | None:
        if isinstance(value, Point):
            return value
        if hasattr(value, "x") and hasattr(value, "y"):
            value = (value.x, value.y)
        if isinstance(value, Mapping):
            if "x" in value and "y" in value:
                value = (value["x"], value["y"])
            else:
                return None
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) == 2:
            try:
                return Point(float(value[0]), float(value[1]))
            except (TypeError, ValueError):
                return None
        return None


__all__ = ["Cell", "Event", "GameController"]

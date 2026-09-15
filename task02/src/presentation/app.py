"""Pygame presentation for the arrow puzzle.

The presentation layer owns input, drawing, and short-lived visual effects.
It deliberately delegates all rule decisions to GameController. Pygame
is imported lazily so importing this module is safe in a headless test run.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from math import pi, sin
import os
from pathlib import Path
from typing import Any


@dataclass
class _Flight:
    """A snapshot of an arrow that is currently flying off the board."""

    arrow: dict[str, Any]
    start: tuple[float, float]
    end: tuple[float, float]
    elapsed: float = 0.0
    duration: float = 0.42


@dataclass
class _BlockedFlight:
    """A blocked arrow's approach, impact shake, and return animation."""

    arrow: dict[str, Any]
    start: tuple[float, float]
    target: tuple[float, float]
    elapsed: float = 0.0
    approach_duration: float = 0.18
    shake_duration: float = 0.36
    return_duration: float = 0.28

    @property
    def duration(self) -> float:
        return self.approach_duration + self.shake_duration + self.return_duration


class GameApp:
    """Run the game window and translate user input for the game controller."""

    WINDOW_SIZE = (960, 720)
    FPS = 60

    START = "start"
    PLAYING = "playing"
    WON = "won"
    LOST = "lost"

    COLORS = {
        "background": (18, 24, 38),
        "panel": (29, 39, 61),
        "panel_light": (39, 53, 80),
        "board": (12, 17, 29),
        "cell": (31, 43, 67),
        "cell_hover": (44, 61, 91),
        "accent": (93, 205, 255),
        "accent_dark": (47, 132, 183),
        "text": (235, 242, 255),
        "muted": (157, 173, 201),
        "success": (105, 226, 156),
        "danger": (255, 111, 125),
        "arrow": (250, 184, 72),
        # Direction is the visual identity of an arrow.  Keep these colors
        # fixed so the same direction is recognizable on every level.
        "arrow_by_direction": {
            "up": (78, 205, 196),      # teal
            "right": (255, 107, 107), # coral
            "down": (255, 205, 87),   # yellow
            "left": (167, 139, 250),  # violet
        },
        "heart_empty": (76, 91, 121),
    }

    def __init__(
        self,
        controller: Any | None = None,
        window_size: tuple[int, int] | None = None,
    ) -> None:
        """Create the app.

        This is the first point at which pygame is imported or initialized.
        A controller can be injected by tests or by a future game bootstrap.
        """
        self._pygame = import_module("pygame")
        pygame = self._pygame
        pygame.init()
        self.window_size = window_size or self.WINDOW_SIZE
        self.screen = pygame.display.set_mode(self.window_size)
        pygame.display.set_caption("一箭又一箭")
        self.clock = pygame.time.Clock()
        self.controller = controller or self._make_controller()
        self.screen_name = self.START
        self._running = True
        self._hovered_cell: tuple[int, int] | None = None
        self._hovered_point: tuple[float, float] | None = None
        self._flight: _Flight | None = None
        self._blocked_flight: _BlockedFlight | None = None
        self._fonts: dict[int, Any] = {}

    @staticmethod
    def _make_controller() -> Any:
        controller_type = getattr(
            import_module("logic.game_controller"), "GameController"
        )
        return controller_type()

    def run(self) -> None:
        """Run until the user closes the window."""
        pygame = self._pygame
        try:
            while self._running:
                delta_seconds = self.clock.tick(self.FPS) / 1000.0
                self._handle_events()
                if self.screen_name == self.PLAYING:
                    self._call_controller_update(delta_seconds)
                    self._sync_screen_from_state()
                self._update_effects(delta_seconds)
                self._draw()
                pygame.display.flip()
        finally:
            pygame.quit()

    def _handle_events(self) -> None:
        pygame = self._pygame
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._running = False
            elif event.type == pygame.MOUSEMOTION:
                self._hovered_point = self._point_at(event.pos)
                self._hovered_cell = self._cell_at(event.pos)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._handle_click(event.pos)

    def _handle_click(self, position: tuple[int, int]) -> None:
        if self.screen_name in (self.START, self.WON, self.LOST):
            if self._button_rect("primary").collidepoint(position):
                if self.screen_name == self.START:
                    self._start_game()
                elif self.screen_name == self.WON:
                    self._advance_or_restart()
                else:
                    self._restart_game()
            return

        if self._button_rect("restart").collidepoint(position):
            self._restart_game()
            return

        if self._point_at(position) is not None:
            self._handle_board_click(position)

    def _start_game(self) -> None:
        self.screen_name = self.PLAYING

    def _advance_or_restart(self) -> None:
        next_level = getattr(self.controller, "next_level", None)
        if callable(next_level):
            next_level()
            phase = getattr(self.controller, "phase", None)
            if phase == getattr(self.controller, "PHASE_PLAYING", "playing"):
                self.screen_name = self.PLAYING
                self._flight = None
                self._blocked_flight = None
                return
        self._restart_game()
        self._sync_screen_from_state()

    def _restart_game(self) -> None:
        """Use a controller reset API when available, with a safe fallback."""
        reset_names = ("restart", "reset", "new_game", "start_game")
        reset = next(
            (
                getattr(self.controller, name, None)
                for name in reset_names
                if callable(getattr(self.controller, name, None))
            ),
            None,
        )
        if reset is not None:
            reset()
        else:
            # The initialization controller has no reset method. Recreating it
            # keeps the fallback presentation usable without editing the logic.
            try:
                self.controller = type(self.controller)()
            except TypeError:
                state = getattr(self.controller, "state", None)
                if state is not None:
                    for name, value in (
                        ("is_running", True),
                        ("is_won", False),
                        ("is_lost", False),
                    ):
                        if hasattr(state, name):
                            setattr(state, name, value)
        self.screen_name = self.PLAYING
        self._flight = None
        self._blocked_flight = None

    def _handle_board_click(
        self,
        position: tuple[int, int] | int,
        column: int | None = None,
    ) -> None:
        """Dispatch a click in board space, preferring the point API.

        ``position`` is normally a pixel coordinate from the event loop.  The
        optional two-integer form is retained for callers of the old private
        helper and is interpreted as ``(row, column)`` board coordinates.
        """
        if column is not None and isinstance(position, int):
            board_point = (float(column), float(position))
        else:
            board_point = self._point_at(position)  # type: ignore[arg-type]
        if board_point is None:
            return
        if self._blocked_flight is not None:
            return

        before = self._arrow_at_point(board_point)
        if before is None:
            return

        handle_point = getattr(self.controller, "handle_point", None)
        if callable(handle_point):
            # Preserve the exact continuous coordinate.  The controller uses
            # point-to-segment distance, so the middle of long and segmented
            # arrows is a first-class hit target rather than an endpoint alias.
            result = handle_point(*board_point)
        else:
            # Legacy controllers only understand integral cells.  Quantizing
            # happens exclusively in this compatibility branch; the modern
            # presentation/controller path remains continuous.
            row, legacy_column = self._point_to_cell(board_point)
            result = self.controller.handle_action(row, legacy_column)
        after = self._arrow_at_point(board_point)
        outcome = self._outcome(result, before, after)
        if outcome == "success":
            self._begin_flight(before, self._animation_duration(result))
        elif outcome == "blocked":
            self._begin_blocked_flight(before, result, board_point)
        self._sync_screen_from_state()

    def _outcome(
        self,
        result: Any,
        before: dict[str, Any],
        after: dict[str, Any] | None,
    ) -> str | None:
        """Interpret common controller result shapes without applying rules."""
        explicit = result
        if explicit is None:
            state = getattr(self.controller, "state", None)
            explicit = self._first_value(
                state, "last_action", "last_result", "outcome"
            )
            if explicit is None:
                explicit = self._first_value(
                    self.controller, "last_action", "last_result", "outcome"
                )
        if isinstance(explicit, (list, tuple)):
            for item in explicit:
                candidate = self._outcome(item, before, after)
                if candidate is not None:
                    return candidate
            return None
        if isinstance(explicit, dict):
            explicit = self._first_value(
                explicit, "outcome", "result", "status", "kind", "type"
            )
        if isinstance(explicit, str):
            value = explicit.lower()
            if any(
                word in value
                for word in ("block", "collid", "fail", "invalid", "阻挡", "碰撞")
            ):
                return "blocked"
            if any(
                word in value
                for word in ("success", "clear", "remove", "fly", "win", "成功", "飞出")
            ):
                return "success"
        if isinstance(explicit, bool):
            return "success" if explicit else "blocked"

        # A state change is evidence supplied by the logic layer, not a rule
        # calculated here. This supports controllers that return None.
        if after is None or not after.get("active", True):
            return "success"
        return None

    def _begin_flight(
        self, arrow: dict[str, Any], duration: float | None = None
    ) -> None:
        center = self._board_point_to_pixel(arrow["x"], arrow["y"])
        direction = self._direction(arrow.get("direction", 0))
        vector = {
            "up": (0, -1),
            "right": (1, 0),
            "down": (0, 1),
            "left": (-1, 0),
        }[direction]
        end = (
            center[0] + vector[0] * self.window_size[0] * 0.85,
            center[1] + vector[1] * self.window_size[1] * 0.85,
        )
        if duration is None:
            duration = self._controller_animation_duration()
        flight_duration = duration if duration is not None else 0.42
        self._flight = _Flight(
            arrow,
            center,
            end,
            duration=flight_duration,
        )

    @classmethod
    def _animation_duration(cls, result: Any) -> float | None:
        """Extract a fly-out duration from a controller event payload."""
        if isinstance(result, dict):
            animation = result.get("animation")
            if isinstance(animation, dict):
                value = animation.get("duration")
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    value = float(value)
                    if value >= 0 and value == value and value != float("inf"):
                        return value
            for value in result.values():
                duration = cls._animation_duration(value)
                if duration is not None:
                    return duration
        elif isinstance(result, (list, tuple)):
            for value in result:
                duration = cls._animation_duration(value)
                if duration is not None:
                    return duration
        return None

    def _controller_animation_duration(self) -> float | None:
        value = getattr(self.controller, "animation_duration", None)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            value = float(value)
            if value >= 0 and value == value and value != float("inf"):
                return value
        return None

    def _begin_blocked_flight(
        self,
        arrow: dict[str, Any],
        result: Any,
        clicked_point: tuple[float, float],
    ) -> None:
        start_board = (float(arrow["x"]), float(arrow["y"]))
        direction = self._direction(arrow.get("direction", 0))
        vector = {
            "up": (0.0, -1.0),
            "right": (1.0, 0.0),
            "down": (0.0, 1.0),
            "left": (-1.0, 0.0),
        }[direction]
        requested = self._blocked_destination(result)
        if requested is None:
            requested = (
                start_board[0] + vector[0] * 0.24,
                start_board[1] + vector[1] * 0.24,
            )
        requested_distance = (
            (requested[0] - start_board[0]) * vector[0]
            + (requested[1] - start_board[1]) * vector[1]
        )
        requested_distance = max(0.0, requested_distance)
        safe_distance = self._safe_blocked_distance(
            arrow, result, start_board, vector
        )
        if safe_distance is not None:
            requested_distance = min(requested_distance, safe_distance)
        # If a controller supplied a target behind the arrow, still provide a
        # visible, short impact animation rather than moving backwards.
        if requested_distance <= 0.001:
            requested_distance = min(0.16, safe_distance or 0.16)
        target_board = (
            start_board[0] + vector[0] * requested_distance,
            start_board[1] + vector[1] * requested_distance,
        )
        self._blocked_flight = _BlockedFlight(
            arrow=arrow,
            start=self._board_point_to_pixel(*start_board),
            target=self._board_point_to_pixel(*target_board),
        )

    @classmethod
    def _blocked_destination(cls, result: Any) -> tuple[float, float] | None:
        """Read either modern blocked destination or collision point fields."""
        if isinstance(result, dict):
            for key in ("blocked_destination", "collision_point"):
                if key in result:
                    point = cls._event_point(result[key])
                    if point is not None:
                        return point
            for value in result.values():
                point = cls._blocked_destination(value)
                if point is not None:
                    return point
        elif isinstance(result, (list, tuple)):
            for value in result:
                point = cls._blocked_destination(value)
                if point is not None:
                    return point
        return None

    @classmethod
    def _blocked_arrows(cls, result: Any) -> list[dict[str, Any]]:
        if isinstance(result, dict):
            blocked = result.get("blocked_by")
            if blocked is not None:
                values = blocked if isinstance(blocked, (list, tuple)) else (blocked,)
                return [cls._arrow_info(value) for value in values]
            for value in result.values():
                arrows = cls._blocked_arrows(value)
                if arrows:
                    return arrows
        elif isinstance(result, (list, tuple)):
            for value in result:
                arrows = cls._blocked_arrows(value)
                if arrows:
                    return arrows
        return []

    @staticmethod
    def _event_point(value: Any) -> tuple[float, float] | None:
        point = GameApp._point_coordinate(value)
        if point is not None:
            return point
        if isinstance(value, dict) and "row" in value and "column" in value:
            return float(value["column"]), float(value["row"])
        return None

    def _safe_blocked_distance(
        self,
        arrow: dict[str, Any],
        result: Any,
        start: tuple[float, float],
        vector: tuple[float, float],
    ) -> float | None:
        """Cap impact movement before the nearest reported blocker."""
        blockers = self._blocked_arrows(result)
        if not blockers:
            return None
        distances: list[float] = []
        for source_x, source_y in self._occupied_points(arrow):
            for blocker in blockers:
                blocker_points = self._occupied_points(blocker)
                if not blocker_points:
                    continue
                min_x = min(point[0] for point in blocker_points)
                max_x = max(point[0] for point in blocker_points)
                min_y = min(point[1] for point in blocker_points)
                max_y = max(point[1] for point in blocker_points)
                if vector[0] and min_y - 0.08 <= source_y <= max_y + 0.08:
                    blocker_edge = min_x if vector[0] > 0 else max_x
                    distance = (blocker_edge - source_x) * vector[0]
                    if distance > 0:
                        distances.append(distance)
                elif vector[1] and min_x - 0.08 <= source_x <= max_x + 0.08:
                    blocker_edge = min_y if vector[1] > 0 else max_y
                    distance = (blocker_edge - source_y) * vector[1]
                    if distance > 0:
                        distances.append(distance)
        if not distances:
            return None
        return max(0.0, min(distances) - 0.08 - self._forward_visual_extent(arrow, vector))

    def _forward_visual_extent(
        self, arrow: dict[str, Any], vector: tuple[float, float]
    ) -> float:
        """Account for a single-point arrow's visible shaft before a blocker."""
        if len(self._occupied_points(arrow)) > 1:
            return 0.0
        board = self._board_rect()
        rows, columns = self._grid_size()
        pixel_units = board.width / columns if vector[0] else board.height / rows
        if pixel_units <= 0:
            return 0.0
        return self._cell_size() * 0.38 / pixel_units

    def _blocked_offset(self, flight: _BlockedFlight) -> tuple[float, float]:
        elapsed = flight.elapsed
        if elapsed < flight.approach_duration:
            progress = self._smoothstep(elapsed / flight.approach_duration)
            return self._lerp_offset(flight.start, flight.target, progress)
        elapsed -= flight.approach_duration
        if elapsed < flight.shake_duration:
            progress = elapsed / flight.shake_duration
            # Shake perpendicular to travel so it cannot cross the blocker.
            dx = flight.target[0] - flight.start[0]
            dy = flight.target[1] - flight.start[1]
            length = max(1.0, (dx * dx + dy * dy) ** 0.5)
            amplitude = min(12.0, max(5.0, self._cell_size() * 0.14))
            wobble = sin(progress * pi * 5.0) * (1.0 - progress * 0.35)
            return (
                flight.target[0] - flight.start[0] - dy / length * amplitude * wobble,
                flight.target[1] - flight.start[1] + dx / length * amplitude * wobble,
            )
        elapsed -= flight.shake_duration
        progress = self._smoothstep(min(1.0, elapsed / flight.return_duration))
        return self._lerp_offset(flight.target, flight.start, progress)

    @staticmethod
    def _smoothstep(progress: float) -> float:
        progress = max(0.0, min(1.0, progress))
        return progress * progress * (3.0 - 2.0 * progress)

    @staticmethod
    def _lerp_offset(
        start: tuple[float, float], end: tuple[float, float], progress: float
    ) -> tuple[float, float]:
        return (
            start[0] + (end[0] - start[0]) * progress - start[0],
            start[1] + (end[1] - start[1]) * progress - start[1],
        )

    def _call_controller_update(self, delta_seconds: float) -> None:
        update = getattr(self.controller, "update", None)
        if callable(update):
            update(delta_seconds)

    def _sync_screen_from_state(self) -> None:
        state = getattr(self.controller, "state", None)
        if bool(self._first_value(state, "is_won", "won")):
            self.screen_name = self.WON
        elif bool(self._first_value(state, "is_lost", "lost")):
            self.screen_name = self.LOST

    def _update_effects(self, delta_seconds: float) -> None:
        if self._flight is not None:
            self._flight.elapsed += delta_seconds
            if self._flight.elapsed >= self._flight.duration:
                self._flight = None
        if self._blocked_flight is not None:
            self._blocked_flight.elapsed += delta_seconds
            if self._blocked_flight.elapsed + 1e-9 >= self._blocked_flight.duration:
                self._blocked_flight = None

    def _draw(self) -> None:
        self.screen.fill(self.COLORS["background"])
        if self.screen_name == self.START:
            self._draw_start()
        elif self.screen_name == self.PLAYING:
            self._draw_game()
        else:
            self._draw_game()
            self._draw_end(self.screen_name == self.WON)

    def _draw_start(self) -> None:
        # Keep the opening screen focused on the game itself.  Showing the
        # first board gives the player an immediate preview instead of a
        # separate instructional card, while the action remains at the
        # bottom where it cannot cover the board.
        self._text("一箭又一箭", (42, 30), 40, self.COLORS["text"])
        board = self._board_rect()
        self._pygame.draw.rect(
            self.screen, self.COLORS["board"], board, border_radius=16
        )
        self._draw_grid(board)
        for arrow in self._arrows():
            if arrow.get("active", True):
                self._draw_arrow(arrow)
        self._draw_button(self._button_rect("primary"), "开始游戏", primary=True)

    def _draw_game(self) -> None:
        pygame = self._pygame
        state = getattr(self.controller, "state", None)
        # The controller is authoritative after next_level(); state.level is
        # retained as a compatibility fallback for older controllers.
        level = self._first_value(
            self.controller, "current_level", "level", "stage"
        )
        if level is None:
            level = self._first_value(state, "level", "current_level", "stage")
        level = level or 1
        arrows = self._arrows()
        mistakes = self._first_value(
            state,
            "mistakes_remaining",
            "remaining_mistakes",
            "mistakes_left",
            "lives",
        )
        if mistakes is None:
            mistakes = 3

        try:
            mistakes = max(0, int(mistakes))
        except (TypeError, ValueError):
            mistakes = 3
        elapsed = self._first_value(
            self.controller, "elapsed_seconds", "elapsed", "time_elapsed"
        )
        if elapsed is None:
            elapsed = self._first_value(state, "elapsed_seconds", "elapsed")
        self._draw_level_hud(level, mistakes, self._format_elapsed(elapsed))

        remaining = self._first_value(
            self.controller, "remaining_arrows", "remaining_arrow_count"
        )
        if remaining is None:
            remaining = self._first_value(
                state, "remaining_arrows", "remaining_arrow_count"
            )
        if remaining is None:
            remaining = sum(1 for arrow in arrows if arrow.get("active", True))
        try:
            remaining = max(0, int(remaining))
        except (TypeError, ValueError):
            remaining = 0
        self._draw_arrow_counter(remaining)

        board = self._board_rect()
        pygame.draw.rect(self.screen, self.COLORS["board"], board, border_radius=16)
        self._draw_grid(board)
        for arrow in arrows:
            if arrow.get("active", True) and not self._is_blocked_arrow(arrow):
                self._draw_arrow(arrow)
        if self._flight is not None:
            self._draw_flight(self._flight)
        if self._blocked_flight is not None:
            self._draw_arrow(
                self._blocked_flight.arrow,
                self._blocked_offset(self._blocked_flight),
            )

        self._draw_button(self._button_rect("restart"), "重新开始", primary=False)

    def _is_blocked_arrow(self, arrow: dict[str, Any]) -> bool:
        blocked = self._blocked_flight
        if blocked is None:
            return False
        source = blocked.arrow.get("source")
        return source is not None and source is arrow.get("source")

    def _draw_end(self, won: bool) -> None:
        title = "恭喜通关！" if won else "本关失败"
        subtitle = "所有箭头都已飞出棋盘" if won else "失误次数已耗尽，再试一次吧"
        self._draw_center_card(title, subtitle)
        self._draw_button(
            self._button_rect("primary"),
            "再玩一次" if won else "重新开始",
            primary=True,
        )

    def _draw_header(self, title: str, subtitle: str) -> None:
        self._text(title, (42, 30), 34, self.COLORS["text"])
        self._text(subtitle, (44, 70), 16, self.COLORS["muted"])

    def _draw_level_hud(
        self, level: Any, mistakes: int, elapsed: str = "00:00"
    ) -> None:
        """Draw level, attempts, and elapsed time in a centered stack."""
        width = self.window_size[0]
        label = self._font(20).render(f"第 {level} 关", True, self.COLORS["text"])
        self.screen.blit(label, label.get_rect(center=(width // 2, 24)))
        self._draw_hearts(mistakes, center_x=width // 2, top=42)
        timer = self._font(17).render(elapsed, True, self.COLORS["muted"])
        self.screen.blit(timer, timer.get_rect(center=(width // 2, 91)))

    def _draw_arrow_counter(self, remaining: int) -> None:
        """Draw a compact arrow icon and count in the upper-right corner."""
        pygame = self._pygame
        width = self.window_size[0]
        center = (width - 112, 48)
        color = self.COLORS["accent"]
        pygame.draw.line(
            self.screen,
            color,
            (center[0] - 15, center[1]),
            (center[0] + 10, center[1]),
            5,
        )
        pygame.draw.polygon(
            self.screen,
            color,
            (
                (center[0] + 10, center[1] - 9),
                (center[0] + 22, center[1]),
                (center[0] + 10, center[1] + 9),
            ),
        )
        count = self._font(20).render(str(remaining), True, self.COLORS["text"])
        self.screen.blit(count, count.get_rect(midleft=(center[0] + 34, center[1])))

    def _draw_hearts(
        self,
        remaining: int,
        maximum: int = 3,
        *,
        center_x: int | None = None,
        top: int = 68,
    ) -> None:
        """Render remaining attempts as filled/empty heart silhouettes."""
        pygame = self._pygame
        width = self.window_size[0]
        size = 14
        gap = 30
        remaining = max(0, min(maximum, int(remaining)))
        for index in range(maximum):
            if center_x is None:
                heart_x = width - 42 - (maximum - 1 - index) * gap - size
            else:
                heart_x = center_x + (index - (maximum - 1) / 2) * gap
            color = (
                self.COLORS["danger"]
                if index < remaining
                else self.COLORS["heart_empty"]
            )
            # Two circles and a lower point produce a compact heart without
            # relying on a font containing a heart glyph.
            pygame.draw.circle(self.screen, color, (round(heart_x - 6), top + 6), 6)
            pygame.draw.circle(self.screen, color, (round(heart_x + 6), top + 6), 6)
            pygame.draw.polygon(
                self.screen,
                color,
                ((round(heart_x - 12), top + 7), (round(heart_x + 12), top + 7),
                 (round(heart_x), top + 22)),
            )

    @staticmethod
    def _format_elapsed(value: Any) -> str:
        try:
            seconds = int(float(value)) if value is not None else 0
        except (TypeError, ValueError):
            seconds = 0
        seconds = max(0, seconds)
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def _draw_center_card(self, title: str, subtitle: str) -> None:
        pygame = self._pygame
        width, height = self.window_size
        card = pygame.Rect(width // 2 - 250, height // 2 - 130, 500, 260)
        pygame.draw.rect(self.screen, self.COLORS["panel"], card, border_radius=18)
        pygame.draw.rect(
            self.screen, self.COLORS["accent_dark"], card, 2, border_radius=18
        )
        self._text(
            title,
            (card.centerx, card.top + 56),
            30,
            self.COLORS["text"],
            center=True,
        )
        self._text(
            subtitle,
            (card.centerx, card.top + 108),
            17,
            self.COLORS["muted"],
            center=True,
        )

    def _draw_stat(
        self,
        x: int,
        y: int,
        label: str,
        value: str,
        value_color: tuple[int, int, int] | None = None,
    ) -> None:
        self._text(label, (x, y), 14, self.COLORS["muted"])
        self._text(value, (x, y + 21), 23, value_color or self.COLORS["text"])

    def _draw_grid(self, board: Any) -> None:
        """Draw a sparse point lattice instead of filled grid cells."""
        pygame = self._pygame
        rows, columns = self._grid_size()
        cell_w, cell_h = board.width / columns, board.height / rows
        radius = max(1, min(3, round(min(cell_w, cell_h) * 0.035)))
        point_set = {
            (float(column), float(row))
            for row in range(rows + 1)
            for column in range(columns + 1)
        }
        # Do not leave lattice dots underneath the geometry of a static arrow:
        # an exposed dot at a tip, tail, or bend reads as a dark artifact.
        # Non-integral model points are deliberately not added to the lattice;
        # they are represented by the arrow itself and reappear naturally once
        # a flying arrow is no longer active.
        static_arrow_points: set[tuple[float, float]] = set()
        for arrow in self._arrows():
            if arrow.get("active", True):
                static_arrow_points.update(self._occupied_points(arrow))
        point_set.difference_update(static_arrow_points)
        for point_x, point_y in point_set:
            pixel_x, pixel_y = self._board_point_to_pixel(point_x, point_y)
            color = self.COLORS["cell"]
            if self._hovered_point is not None:
                distance = (
                    (self._hovered_point[0] - point_x) ** 2
                    + (self._hovered_point[1] - point_y) ** 2
                ) ** 0.5
                if distance < 0.35:
                    color = self.COLORS["cell_hover"]
            pygame.draw.circle(
                self.screen, color, (round(pixel_x), round(pixel_y)), radius
            )

    def _draw_arrow(
        self,
        arrow: dict[str, Any],
        offset: tuple[float, float] = (0, 0),
    ) -> None:
        pygame = self._pygame
        center = self._board_point_to_pixel(arrow["x"], arrow["y"])
        points = self._path_points(arrow, center)
        if offset != (0, 0):
            points = [(x + offset[0], y + offset[1]) for x, y in points]
        color = self._arrow_color(arrow)
        width = max(6, int(self._cell_size() * 0.095))
        tip = points[-1]
        previous = points[-2] if len(points) >= 2 else center
        dx, dy = tip[0] - previous[0], tip[1] - previous[1]
        length = max(1.0, (dx * dx + dy * dy) ** 0.5)
        ux, uy = dx / length, dy / length
        side = max(13, self._cell_size() * 0.22)
        shaft_end = (tip[0] - ux * side, tip[1] - uy * side)
        if len(points) > 1:
            shaft_points = [*points[:-1], shaft_end]
            pygame.draw.lines(self.screen, color, False, shaft_points, width)
            cap_radius = max(3, width // 2)
            for shaft_point in shaft_points[:-1]:
                pygame.draw.circle(
                    self.screen,
                    color,
                    (round(shaft_point[0]), round(shaft_point[1])),
                    cap_radius,
                )
        wing = [
            (
                tip[0] - ux * side + uy * side * 0.72,
                tip[1] - uy * side - ux * side * 0.72,
            ),
            tip,
            (
                tip[0] - ux * side - uy * side * 0.72,
                tip[1] - uy * side + ux * side * 0.72,
            ),
        ]
        pygame.draw.polygon(self.screen, color, wing)

    def _draw_flight(self, flight: _Flight) -> None:
        progress = min(1.0, flight.elapsed / flight.duration)
        progress = 1 - (1 - progress) ** 3
        x = flight.start[0] + (flight.end[0] - flight.start[0]) * progress
        y = flight.start[1] + (flight.end[1] - flight.start[1]) * progress
        self._draw_arrow(
            flight.arrow,
            (x - flight.start[0], y - flight.start[1]),
        )

    def _draw_button(self, rect: Any, label: str, *, primary: bool) -> None:
        pygame = self._pygame
        hovered = rect.collidepoint(pygame.mouse.get_pos())
        color = self.COLORS["accent"] if primary else self.COLORS["panel_light"]
        if hovered:
            color = tuple(min(255, value + 18) for value in color)
        pygame.draw.rect(self.screen, color, rect, border_radius=10)
        text_color = self.COLORS["background"] if primary else self.COLORS["text"]
        self._text(label, rect.center, 17, text_color, center=True)

    def _font(self, size: int) -> Any:
        if size not in self._fonts:
            font = None
            windows_dir = os.environ.get("WINDIR") or os.environ.get("windir")
            if windows_dir:
                font_dir = Path(windows_dir) / "Fonts"
                font_candidates = (
                    font_dir / "msyh.ttc",
                    font_dir / "msyhbd.ttc",
                    font_dir / "simhei.ttf",
                    font_dir / "simsun.ttc",
                    font_dir / "arial.ttf",
                )
            else:
                font_candidates = ()

            for font_path in font_candidates:
                if not font_path.is_file():
                    continue
                try:
                    font = self._pygame.font.Font(str(font_path), size)
                    break
                except (OSError, RuntimeError, TypeError):
                    # A font file may exist but still be unsupported by the
                    # installed SDL_ttf/Pygame combination. Try the next one.
                    continue

            if font is None:
                font = self._pygame.font.Font(None, size)
            self._fonts[size] = font
        return self._fonts[size]

    def _text(
        self,
        value: str,
        position: tuple[int, int],
        size: int,
        color: tuple[int, int, int],
        *,
        center: bool = False,
    ) -> None:
        image = self._font(size).render(str(value), True, color)
        rect = (
            image.get_rect(center=position)
            if center
            else image.get_rect(topleft=position)
        )
        self.screen.blit(image, rect)

    def _board_rect(self) -> Any:
        margin_x, top, bottom = 42, 153, 92
        width = self.window_size[0] - margin_x * 2
        height = self.window_size[1] - top - bottom
        return self._pygame.Rect(margin_x, top, width, height)

    def _button_rect(self, name: str) -> Any:
        pygame = self._pygame
        if name == "primary":
            if self.screen_name == self.START:
                return pygame.Rect(
                    self.window_size[0] // 2 - 105,
                    self.window_size[1] - 74,
                    210,
                    52,
                )
            return pygame.Rect(
                self.window_size[0] // 2 - 105,
                self.window_size[1] // 2 + 28,
                210,
                52,
            )
        return pygame.Rect(42, 102, 128, 42)

    def _grid_size(self) -> tuple[int, int]:
        state = getattr(self.controller, "state", None)
        grid = getattr(state, "grid", None)
        rows = int(getattr(grid, "rows", 8) or 8)
        columns = int(getattr(grid, "columns", 8) or 8)
        return max(1, rows), max(1, columns)

    def _cell_size(self) -> float:
        board = self._board_rect()
        rows, columns = self._grid_size()
        return min(board.width / columns, board.height / rows)

    def _cell_center(self, row: int, column: int) -> tuple[float, float]:
        """Legacy cell-center helper retained for external callers."""
        return self._board_point_to_pixel(float(column) + 0.5, float(row) + 0.5)

    def _board_point_to_pixel(self, x: float, y: float) -> tuple[float, float]:
        board = self._board_rect()
        rows, columns = self._grid_size()
        return (
            board.left + x * board.width / columns,
            board.top + y * board.height / rows,
        )

    def _point_at(self, position: tuple[int, int]) -> tuple[float, float] | None:
        """Convert a pixel position to the continuous board coordinate."""
        board = self._board_rect()
        if not board.collidepoint(position):
            return None
        rows, columns = self._grid_size()
        return (
            (position[0] - board.left) / board.width * columns,
            (position[1] - board.top) / board.height * rows,
        )

    def _cell_at(self, position: tuple[int, int]) -> tuple[int, int] | None:
        point = self._point_at(position)
        if point is None:
            return None
        column = int(point[0])
        row = int(point[1])
        rows, columns = self._grid_size()
        if 0 <= row < rows and 0 <= column < columns:
            return row, column
        return None

    def _point_to_cell(self, point: tuple[float, float]) -> tuple[int, int]:
        rows, columns = self._grid_size()
        row = max(0, min(rows - 1, int(round(point[1]))))
        column = max(0, min(columns - 1, int(round(point[0]))))
        return row, column

    def _arrows(self) -> list[dict[str, Any]]:
        state = getattr(self.controller, "state", None)
        raw_arrows = getattr(state, "arrows", None) or []
        if isinstance(raw_arrows, dict):
            raw_arrows = raw_arrows.values()
        return [self._arrow_info(arrow) for arrow in raw_arrows]

    def _arrow_at(self, row: int, column: int) -> dict[str, Any] | None:
        return self._arrow_at_point((float(column), float(row)))

    def _arrow_at_point(
        self, point: tuple[float, float], tolerance: float = 0.45
    ) -> dict[str, Any] | None:
        candidates: list[tuple[float, dict[str, Any]]] = []
        for arrow in reversed(self._arrows()):
            if not arrow.get("active", True):
                continue
            anchor = self._board_point_to_pixel(arrow["x"], arrow["y"])
            click = self._board_point_to_pixel(point[0], point[1])
            path = self._path_points(arrow, anchor)
            distance = min(
                self._point_to_segment_distance(click, start, end)
                for start, end in zip(path, path[1:])
            )
            hit_tolerance = max(16.0, self._cell_size() * 0.16)
            if distance <= hit_tolerance:
                candidates.append((distance, arrow))
        return min(candidates, key=lambda candidate: candidate[0])[1] if candidates else None

    @staticmethod
    def _point_to_segment_distance(
        point: tuple[float, float],
        start: tuple[float, float],
        end: tuple[float, float],
    ) -> float:
        segment_x = end[0] - start[0]
        segment_y = end[1] - start[1]
        length_squared = segment_x * segment_x + segment_y * segment_y
        if length_squared == 0:
            return ((point[0] - start[0]) ** 2 + (point[1] - start[1]) ** 2) ** 0.5
        projection = (
            (point[0] - start[0]) * segment_x
            + (point[1] - start[1]) * segment_y
        ) / length_squared
        projection = max(0.0, min(1.0, projection))
        closest = (start[0] + projection * segment_x, start[1] + projection * segment_y)
        return ((point[0] - closest[0]) ** 2 + (point[1] - closest[1]) ** 2) ** 0.5

    def _occupied_cells(self, arrow: dict[str, Any]) -> set[tuple[int, int]]:
        return {
            (int(round(y)), int(round(x)))
            for x, y in self._occupied_points(arrow)
            if x.is_integer() and y.is_integer()
        }

    def _occupied_points(self, arrow: dict[str, Any]) -> set[tuple[float, float]]:
        values = arrow.get("points")
        if values:
            result = {
                coordinate
                for value in values
                if (coordinate := self._point_coordinate(value)) is not None
            }
            if result:
                return result
        values = arrow.get("cells") or arrow.get("path")
        if values:
            result = {
                coordinate
                for value in self._flatten_path(values)
                if (coordinate := self._legacy_point_coordinate(value)) is not None
            }
            if result:
                return result
        return {(float(arrow["x"]), float(arrow["y"]))}

    @staticmethod
    def _arrow_info(arrow: Any) -> dict[str, Any]:
        if isinstance(arrow, dict):
            get = arrow.get
        else:
            get = lambda name, default=None: getattr(arrow, name, default)
        x = get("x", None)
        y = get("y", None)
        point = get("point", None)
        point_coordinate = GameApp._point_coordinate(point)
        if point_coordinate is not None:
            if x is None:
                x = point_coordinate[0]
            if y is None:
                y = point_coordinate[1]
        if x is None:
            x = get("column", get("col", 0))
        if y is None:
            y = get("row", 0)
        state = get("state", None)
        state_value = getattr(state, "value", state)
        active_value = get("active", None)
        if active_value is None:
            active_value = state_value not in {"flying_out", "removed"}
        points = get("occupied_points", None)
        if points is None:
            points = get("points", None)
        return {
            "source": arrow,
            "x": float(x),
            "y": float(y),
            # Keep aliases for legacy callers and feedback code.
            "row": float(y),
            "column": float(x),
            "direction": get("direction", 0),
            "active": bool(active_value),
            "points": points,
            "path": get("path", get("segments", None)),
            "cells": get("occupied_cells", get("cells", None)),
            "color": get("color", None),
        }

    def _path_points(
        self,
        arrow: dict[str, Any],
        center: tuple[float, float],
    ) -> list[tuple[float, float]]:
        raw_points = arrow.get("points")
        if raw_points:
            board_points = [
                coordinate
                for value in raw_points
                if (coordinate := self._point_coordinate(value)) is not None
            ]
        else:
            path = arrow.get("path") or arrow.get("cells")
            board_points = [
                coordinate
                for value in self._flatten_path(path)
                if (coordinate := self._legacy_point_coordinate(value)) is not None
            ] if path else []
        if board_points:
            points = [self._board_point_to_pixel(x, y) for x, y in board_points]
            if len(points) >= 2:
                return points

        direction = self._direction(arrow.get("direction", 0))
        dx, dy = {
            "up": (0, -1),
            "right": (1, 0),
            "down": (0, 1),
            "left": (-1, 0),
        }[direction]
        length = self._cell_size() * 0.38
        return [
            (center[0] - dx * length, center[1] - dy * length),
            (center[0] + dx * length, center[1] + dy * length),
        ]

    @staticmethod
    def _point_coordinate(value: Any) -> tuple[float, float] | None:
        """Read a native point as ``(x, y)`` without integer quantization."""
        if isinstance(value, dict) and "x" in value and "y" in value:
            return float(value["x"]), float(value["y"])
        x = getattr(value, "x", None)
        y = getattr(value, "y", None)
        if x is not None and y is not None:
            return float(x), float(y)
        if isinstance(value, (tuple, list)) and len(value) >= 2:
            return float(value[0]), float(value[1])
        return None

    @staticmethod
    def _legacy_point_coordinate(value: Any) -> tuple[float, float] | None:
        """Read a legacy cell/path coordinate and convert ``(row, col)``."""
        if isinstance(value, dict) and "x" in value and "y" in value:
            return float(value["x"]), float(value["y"])
        if isinstance(value, dict) and "row" in value and "column" in value:
            return float(value["column"]), float(value["row"])
        cells = getattr(value, "cells", None)
        if cells is not None:
            return None
        row = getattr(value, "row", None)
        column = getattr(value, "column", None)
        if row is not None and column is not None:
            return float(column), float(row)
        if isinstance(value, (tuple, list)) and len(value) >= 2:
            return float(value[1]), float(value[0])
        return None

    @staticmethod
    def _coordinate(value: Any) -> tuple[float, float] | None:
        """Compatibility alias for the former row/column reader."""
        return GameApp._legacy_point_coordinate(value)

    @staticmethod
    def _flatten_path(value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, dict):
            if "cells" in value:
                return GameApp._flatten_path(value["cells"])
            if "start" in value and "end" in value:
                return GameApp._flatten_path((value["start"], value["end"]))
            return []
        cells = getattr(value, "cells", None)
        if cells is not None:
            return GameApp._flatten_path(cells)
        if isinstance(value, (tuple, list)):
            # A coordinate itself is one path item; nested sequences are
            # flattened to support old segmented-arrow representations.
            if len(value) >= 2 and all(isinstance(part, (int, float)) for part in value[:2]):
                return [value]
            result: list[Any] = []
            for item in value:
                result.extend(GameApp._flatten_path(item))
            return result
        return [value]

    def _direction(self, value: Any) -> str:
        if isinstance(value, str):
            value = value.lower()
            aliases = {"上": "up", "下": "down", "左": "left", "右": "right"}
            return aliases.get(
                value,
                value if value in ("up", "right", "down", "left") else "up",
            )
        return ("up", "right", "down", "left")[int(value) % 4]

    def _arrow_color(self, arrow: dict[str, Any]) -> tuple[int, int, int]:
        color = arrow.get("color")
        if isinstance(color, (tuple, list)) and len(color) >= 3:
            return tuple(int(value) for value in color[:3])
        return self.COLORS["arrow_by_direction"].get(
            self._direction(arrow.get("direction", 0)),
            self.COLORS["arrow"],
        )

    @staticmethod
    def _first_value(source: Any, *names: str) -> Any:
        if source is None:
            return None
        for name in names:
            if isinstance(source, dict) and name in source:
                return source[name]
            value = getattr(source, name, None)
            if value is not None:
                return value
        return None


# Kept as a small public alias for callers that used the earlier shell API.
Application = GameApp

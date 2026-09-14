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
class _Feedback:
    text: str
    color: tuple[int, int, int]
    elapsed: float = 0.0
    duration: float = 1.15


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
        self._flight: _Flight | None = None
        self._shake_cell: tuple[int, int] | None = None
        self._shake_elapsed = 0.0
        self._feedback: _Feedback | None = None
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

        cell = self._cell_at(position)
        if cell is not None:
            self._handle_board_click(*cell)

    def _start_game(self) -> None:
        self.screen_name = self.PLAYING
        self._feedback = None

    def _advance_or_restart(self) -> None:
        next_level = getattr(self.controller, "next_level", None)
        if callable(next_level):
            next_level()
            phase = getattr(self.controller, "phase", None)
            if phase == getattr(self.controller, "PHASE_PLAYING", "playing"):
                self.screen_name = self.PLAYING
                self._flight = None
                self._feedback = None
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
        self._shake_cell = None
        self._shake_elapsed = 0.0
        self._feedback = None

    def _handle_board_click(self, row: int, column: int) -> None:
        before = self._arrow_at(row, column)
        if before is None:
            return

        result = self.controller.handle_action(row, column)
        after = self._arrow_at(row, column)
        outcome = self._outcome(result, before, after)
        if outcome == "success":
            self._begin_flight(before)
            self._feedback = _Feedback("箭头飞出棋盘", self.COLORS["success"])
        elif outcome == "blocked":
            self._shake_cell = (row, column)
            self._shake_elapsed = 0.0
            self._feedback = _Feedback("前方有阻挡", self.COLORS["danger"])
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

    def _begin_flight(self, arrow: dict[str, Any]) -> None:
        center = self._cell_center(arrow["row"], arrow["column"])
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
        self._flight = _Flight(arrow, center, end)

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
        if self._shake_cell is not None:
            self._shake_elapsed += delta_seconds
            if self._shake_elapsed >= 0.48:
                self._shake_cell = None
        if self._feedback is not None:
            self._feedback.elapsed += delta_seconds
            if self._feedback.elapsed >= self._feedback.duration:
                self._feedback = None

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
        self._draw_header("一箭又一箭", "观察方向与阻挡关系，让箭头依次飞出棋盘")
        self._draw_center_card("准备好了吗？", "点击开始，选择正确的箭头顺序")
        self._draw_button(self._button_rect("primary"), "开始游戏", primary=True)

    def _draw_game(self) -> None:
        pygame = self._pygame
        self._draw_header("一箭又一箭", "点击没有被挡住的箭头")
        state = getattr(self.controller, "state", None)
        level = self._first_value(state, "level", "current_level", "stage")
        if level is None:
            level = self._first_value(
                self.controller, "level", "current_level", "stage"
            )
        level = level or 1
        arrows = self._arrows()
        remaining = sum(1 for arrow in arrows if arrow.get("active", True))
        mistakes = self._first_value(
            state,
            "mistakes_remaining",
            "remaining_mistakes",
            "mistakes_left",
            "lives",
        )
        if mistakes is None:
            mistakes = 3

        self._draw_stat(42, 102, "关卡", str(level))
        self._draw_stat(210, 102, "剩余箭头", str(remaining))
        try:
            low_mistakes = int(mistakes) <= 1
        except (TypeError, ValueError):
            low_mistakes = False
        self._draw_stat(
            404,
            102,
            "剩余失误",
            str(mistakes),
            self.COLORS["danger"] if low_mistakes else self.COLORS["text"],
        )

        board = self._board_rect()
        pygame.draw.rect(self.screen, self.COLORS["board"], board, border_radius=16)
        self._draw_grid(board)
        for arrow in arrows:
            if arrow.get("active", True):
                self._draw_arrow(arrow, self._arrow_offset(arrow))
        if self._flight is not None:
            self._draw_flight(self._flight)

        self._draw_button(self._button_rect("restart"), "重新开始", primary=False)
        if self._feedback is not None:
            self._draw_feedback(self._feedback)

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
        pygame = self._pygame
        rows, columns = self._grid_size()
        cell_w, cell_h = board.width / columns, board.height / rows
        for row in range(rows):
            for column in range(columns):
                rect = pygame.Rect(
                    round(board.left + column * cell_w + 3),
                    round(board.top + row * cell_h + 3),
                    round(cell_w - 6),
                    round(cell_h - 6),
                )
                color = (
                    self.COLORS["cell_hover"]
                    if (row, column) == self._hovered_cell
                    else self.COLORS["cell"]
                )
                if self._shake_cell == (row, column):
                    color = self.COLORS["danger"]
                pygame.draw.rect(self.screen, color, rect, border_radius=9)

    def _draw_arrow(
        self,
        arrow: dict[str, Any],
        offset: tuple[float, float] = (0, 0),
    ) -> None:
        pygame = self._pygame
        row, column = arrow["row"], arrow["column"]
        center = self._cell_center(row, column)
        center = (center[0] + offset[0], center[1] + offset[1])
        points = self._path_points(arrow, center)
        if (arrow.get("path") or arrow.get("cells")):
            points = [(x + offset[0], y + offset[1]) for x, y in points]
        color = self._arrow_color(arrow)
        width = max(3, int(self._cell_size() * 0.07))
        if len(points) > 1:
            pygame.draw.lines(self.screen, color, False, points, width)
        tip = points[-1]
        previous = points[-2] if len(points) >= 2 else center
        dx, dy = tip[0] - previous[0], tip[1] - previous[1]
        length = max(1.0, (dx * dx + dy * dy) ** 0.5)
        ux, uy = dx / length, dy / length
        side = max(8, self._cell_size() * 0.16)
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

    def _arrow_offset(self, arrow: dict[str, Any]) -> tuple[float, float]:
        if self._shake_cell is None or self._shake_cell not in self._occupied_cells(arrow):
            return 0.0, 0.0
        # A damped sine gives a short left/right shake while the logic layer
        # remains the sole source of the collision decision.
        amplitude = max(3.0, self._cell_size() * 0.09)
        progress = min(1.0, self._shake_elapsed / 0.48)
        return amplitude * sin(progress * pi * 6) * (1.0 - progress), 0.0

    def _draw_feedback(self, feedback: _Feedback) -> None:
        alpha = max(
            0,
            min(255, int(255 * (1 - feedback.elapsed / feedback.duration))),
        )
        image = self._font(18).render(feedback.text, True, feedback.color)
        image.set_alpha(alpha)
        rect = image.get_rect(center=(self.window_size[0] // 2, 670))
        self.screen.blit(image, rect)

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
            return pygame.Rect(
                self.window_size[0] // 2 - 105,
                self.window_size[1] // 2 + 28,
                210,
                52,
            )
        return pygame.Rect(self.window_size[0] - 170, 102, 128, 42)

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
        board = self._board_rect()
        rows, columns = self._grid_size()
        return (
            board.left + (column + 0.5) * board.width / columns,
            board.top + (row + 0.5) * board.height / rows,
        )

    def _cell_at(self, position: tuple[int, int]) -> tuple[int, int] | None:
        board = self._board_rect()
        if not board.collidepoint(position):
            return None
        rows, columns = self._grid_size()
        column = int((position[0] - board.left) / board.width * columns)
        row = int((position[1] - board.top) / board.height * rows)
        if 0 <= row < rows and 0 <= column < columns:
            return row, column
        return None

    def _arrows(self) -> list[dict[str, Any]]:
        state = getattr(self.controller, "state", None)
        raw_arrows = getattr(state, "arrows", None) or []
        if isinstance(raw_arrows, dict):
            raw_arrows = raw_arrows.values()
        return [self._arrow_info(arrow) for arrow in raw_arrows]

    def _arrow_at(self, row: int, column: int) -> dict[str, Any] | None:
        return next(
            (
                arrow
                for arrow in self._arrows()
                if (row, column) in self._occupied_cells(arrow)
                and arrow.get("active", True)
            ),
            None,
        )

    def _occupied_cells(self, arrow: dict[str, Any]) -> set[tuple[int, int]]:
        values = arrow.get("cells") or arrow.get("path")
        if not values:
            return {(arrow["row"], arrow["column"])}
        result: set[tuple[int, int]] = set()
        for value in values:
            coordinate = self._coordinate(value)
            if coordinate is not None:
                result.add((int(coordinate[0]), int(coordinate[1])))
        return result or {(arrow["row"], arrow["column"])}

    @staticmethod
    def _arrow_info(arrow: Any) -> dict[str, Any]:
        if isinstance(arrow, dict):
            get = arrow.get
        else:
            get = lambda name, default=None: getattr(arrow, name, default)
        return {
            "row": int(get("row", get("y", 0))),
            "column": int(get("column", get("col", get("x", 0)))),
            "direction": get("direction", 0),
            "active": bool(get("active", True)),
            "path": get("path", get("points", get("segments", None))),
            "cells": get("occupied_cells", get("cells", None)),
            "color": get("color", None),
        }

    def _path_points(
        self,
        arrow: dict[str, Any],
        center: tuple[float, float],
    ) -> list[tuple[float, float]]:
        path = arrow.get("path") or arrow.get("cells")
        if path:
            points: list[tuple[float, float]] = []
            board = self._board_rect()
            rows, columns = self._grid_size()
            for point in path:
                coordinate = self._coordinate(point)
                if coordinate is not None:
                    first, second = coordinate
                    # Paths conventionally use (row, column). Pixel points are
                    # also accepted to keep this renderer reusable.
                    if 0 <= first <= rows and 0 <= second <= columns:
                        points.append(
                            (
                                board.left
                                + (second + 0.5) * board.width / columns,
                                board.top
                                + (first + 0.5) * board.height / rows,
                            )
                        )
                    else:
                        points.append((first, second))
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
    def _coordinate(value: Any) -> tuple[float, float] | None:
        if isinstance(value, (tuple, list)) and len(value) >= 2:
            return float(value[0]), float(value[1])
        row = getattr(value, "row", None)
        column = getattr(value, "column", None)
        if row is not None and column is not None:
            return float(row), float(column)
        return None

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
        if self._shake_cell == (arrow["row"], arrow["column"]):
            return self.COLORS["danger"]
        return self.COLORS["arrow"]

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

"""Regression tests for the point-based arrow puzzle lifecycle."""

from __future__ import annotations

import sys
from pathlib import Path
import unittest


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from logic.game_controller import GameController
from model.arrow import Arrow, ArrowState, LineSegment, Point
from model.game_state import GameResult, GameState
from model.grid import Grid
from presentation.app import GameApp


class PointModelTests(unittest.TestCase):
    def test_default_levels_use_native_inset_points(self) -> None:
        levels = GameController._default_levels()

        self.assertEqual([level.level for level in levels], [1, 2])
        self.assertTrue(
            any(len(arrow.line_segments) >= 3 for arrow in levels[1].arrows)
        )
        for level in levels:
            for arrow in level.arrows:
                self.assertGreaterEqual(len(arrow.points), 2)
                self.assertFalse(arrow.path)
                self.assertFalse(arrow.segments)
                self.assertEqual(len(arrow.line_segments), len(arrow.points) - 1)
                self.assertEqual(arrow.front_point, arrow.points[-1])
                self.assertGreater(arrow.x, 0)
                self.assertGreater(arrow.y, 0)
                self.assertLess(arrow.x, level.grid.columns)
                self.assertLess(arrow.y, level.grid.rows)
                self.assertTrue(
                    all(
                        point.x.is_integer() and point.y.is_integer()
                        for point in arrow.points
                    )
                )

    def test_adjacent_points_are_the_arrows_line_segments(self) -> None:
        arrow = Arrow(
            points=(Point(0.5, 2.5), Point(2.5, 2.5), Point(2.5, 1.5)),
            direction="up",
        )

        self.assertEqual(
            arrow.line_segments,
            (
                LineSegment(Point(0.5, 2.5), Point(2.5, 2.5)),
                LineSegment(Point(2.5, 2.5), Point(2.5, 1.5)),
            ),
        )

    def test_clicking_the_middle_of_a_segment_hits_the_arrow(self) -> None:
        arrow = Arrow(
            points=(Point(2.5, 4.5), Point(2.5, 2.5)),
            direction="up",
        )
        controller = GameController(
            GameState(grid=Grid(6, 6), arrows=[arrow]),
            animation_duration=0.1,
        )

        events = controller.handle_point(2.5, 3.5)

        self.assertEqual(events[0]["type"], controller.EVENT_ARROW_FLY_OUT)
        self.assertIs(arrow.state, ArrowState.FLYING_OUT)

    def test_exit_ray_detects_a_perpendicular_line_blocker(self) -> None:
        target = Arrow(
            points=(Point(0.5, 2.5), Point(2.0, 2.5)),
            direction="right",
        )
        blocker = Arrow(
            points=(Point(4.0, 1.0), Point(4.0, 4.0)),
            direction="down",
        )
        controller = GameController(
            GameState(grid=Grid(6, 6), arrows=[target, blocker])
        )

        events = controller.handle_point(1.25, 2.5)

        self.assertEqual(events[0]["type"], controller.EVENT_ARROW_BLOCKED)
        self.assertIn(blocker, events[0]["blocked_by"])

    def test_point_ray_detects_a_blocker_on_the_same_axis(self) -> None:
        target = Arrow(x=1.5, y=2.5, direction="right")
        blocker = Arrow(x=4.5, y=2.5, direction="up")
        controller = GameController(
            GameState(grid=Grid(6, 6), arrows=[target, blocker])
        )

        events = controller.handle_point(target.x, target.y)

        self.assertEqual(events[0]["type"], controller.EVENT_ARROW_BLOCKED)
        self.assertEqual(controller.mistakes_remaining, 2)
        self.assertIs(target.state, ArrowState.AVAILABLE)


class ArrowLifecycleTests(unittest.TestCase):
    def test_default_colors_are_stable_per_direction(self) -> None:
        colors = GameApp.COLORS["arrow_by_direction"]

        self.assertEqual(set(colors), {"up", "right", "down", "left"})
        self.assertEqual(len(set(colors.values())), 4)

    def test_presentation_uses_the_controller_animation_duration(self) -> None:
        events = [
            {
                "type": "arrow_fly_out",
                "animation": {"kind": "fly_out", "duration": 0.35},
            }
        ]

        self.assertEqual(GameApp._animation_duration(events), 0.35)

    def test_default_flight_is_slower_and_block_event_has_a_safe_target(self) -> None:
        controller = GameController()
        blocked_arrow = controller.state.arrows[1]

        events = controller.handle_point(2.0, 3.0)
        event = events[0]

        self.assertEqual(controller.animation_duration, 0.7)
        self.assertEqual(event["type"], controller.EVENT_ARROW_BLOCKED)
        self.assertIsNotNone(event["collision_point"])
        self.assertIsNotNone(event["blocked_destination"])
        self.assertGreater(event["blocked_destination"].x, blocked_arrow.front_point.x)
        self.assertLess(event["blocked_destination"].x, event["collision_point"].x)

    def test_elapsed_time_accumulates_freezes_and_resets(self) -> None:
        arrow = Arrow(
            points=(Point(2.0, 3.0), Point(2.0, 2.0)),
            direction="up",
        )
        controller = GameController(
            GameState(grid=Grid(6, 6), arrows=[arrow]),
            animation_duration=0.7,
        )

        controller.update(1.25)
        self.assertEqual(controller.elapsed_seconds, 1.25)
        controller.handle_point(2.0, 2.5)
        controller.update(0.7)
        completed_at = controller.elapsed_seconds
        self.assertEqual(controller.phase, controller.PHASE_LEVEL_COMPLETE)

        controller.update(2.0)
        self.assertEqual(controller.elapsed_seconds, completed_at)
        controller.restart()
        self.assertEqual(controller.elapsed_seconds, 0.0)

    def test_elapsed_time_format(self) -> None:
        self.assertEqual(GameApp._format_elapsed(0), "00:00")
        self.assertEqual(GameApp._format_elapsed(65), "01:05")
        self.assertEqual(GameApp._format_elapsed(3661), "1:01:01")

    def test_successful_arrow_is_removed_only_after_its_animation(self) -> None:
        arrow = Arrow(x=2.5, y=3.5, direction="up")
        state = GameState(grid=Grid(6, 6), arrows=[arrow])
        controller = GameController(state, animation_duration=0.1)

        click_events = controller.handle_point(arrow.x, arrow.y)

        self.assertEqual(click_events[0]["type"], controller.EVENT_ARROW_FLY_OUT)
        self.assertIs(arrow.state, ArrowState.FLYING_OUT)
        self.assertIs(state.result, GameResult.NONE)
        self.assertIsNone(state.grid.occupant_at_point(Point(arrow.x, arrow.y)))
        self.assertFalse(GameApp._arrow_info(arrow)["active"])

        update_events = controller.update(0.1)

        self.assertIs(arrow.state, ArrowState.REMOVED)
        self.assertIs(state.result, GameResult.WON)
        self.assertEqual(controller.phase, controller.PHASE_LEVEL_COMPLETE)
        self.assertEqual(
            [event["type"] for event in update_events],
            [controller.EVENT_ANIMATION_FINISHED, controller.EVENT_LEVEL_COMPLETE],
        )


if __name__ == "__main__":
    unittest.main()

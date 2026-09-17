"""Regression tests for the point-based arrow puzzle lifecycle."""

from __future__ import annotations

import sys
from pathlib import Path
import unittest


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from logic.game_controller import GameController
from logic.level_generator import LevelGenerator
from model.arrow import Arrow, ArrowState, LineSegment, Point
from model.game_state import GameResult, GameState
from model.grid import Grid
from presentation.app import GameApp


class PointModelTests(unittest.TestCase):
    def test_generated_level_is_reproducible_non_overlapping_and_solvable(self) -> None:
        generator = LevelGenerator()

        first = generator.generate(level=8, seed=2701)
        second = generator.generate(level=8, seed=2701)

        first_layout = [
            (arrow.points, arrow.direction, arrow.shape_name)
            for arrow in first.state.arrows
        ]
        second_layout = [
            (arrow.points, arrow.direction, arrow.shape_name)
            for arrow in second.state.arrows
        ]
        self.assertEqual(first_layout, second_layout)
        self.assertEqual(len(first.solution), len(first.state.arrows))
        self.assertGreaterEqual(len(first.state.arrows), 50)
        self.assertGreaterEqual(
            sum(
                len(arrow.line_segments) >= 2
                and len({point.x for point in arrow.points}) > 1
                and len({point.y for point in arrow.points}) > 1
                for arrow in first.state.arrows
            ),
            round(len(first.state.arrows) * 0.6),
        )
        self.assertGreaterEqual(
            sum(len(arrow.line_segments) >= 3 for arrow in first.state.arrows),
            round(len(first.state.arrows) * 0.3),
        )
        self.assertGreaterEqual(
            len({arrow.shape_name for arrow in first.state.arrows}), 4
        )
        direction_counts = {
            direction: sum(arrow.direction == direction for arrow in first.state.arrows)
            for direction in ("up", "right", "down", "left")
        }
        # Direction is a str-backed enum, so string comparison remains a
        # supported compatibility view.
        self.assertTrue(
            all(
                count >= round(len(first.state.arrows) * 0.15)
                for count in direction_counts.values()
            )
        )
        self.assertGreaterEqual(
            sum(
                sum(segment.length for segment in arrow.line_segments) >= 1.1
                for arrow in first.state.arrows
            ),
            round(len(first.state.arrows) * 0.6),
        )
        self.assertTrue(
            any(first.state.grid.blocking_arrows(arrow) for arrow in first.state.arrows)
        )
        left = first.state.grid.columns * LevelGenerator.HORIZONTAL_MARGIN_RATIO
        right = first.state.grid.columns * (
            1 - LevelGenerator.HORIZONTAL_MARGIN_RATIO
        )
        self.assertTrue(
            all(
                left < point.x < right
                for arrow in first.state.arrows
                for point in arrow.points
            )
        )

    def test_default_controller_starts_random_and_generates_every_next_level(self) -> None:
        controller = GameController(generation_seed=99)

        self.assertIsNone(controller._levels)
        self.assertEqual(controller.current_level, 1)
        self.assertGreaterEqual(len(controller.state.arrows), 40)

        controller.phase = controller.PHASE_LEVEL_COMPLETE

        events = controller.next_level()

        self.assertEqual(events[0]["type"], controller.EVENT_LEVEL_GENERATED)
        self.assertEqual(controller.current_level, 2)
        self.assertEqual(controller.phase, controller.PHASE_PLAYING)
        self.assertEqual(
            len(controller._level_generator.solution_order(controller.state)),
            len(controller.state.arrows),
        )

    def test_generated_arrows_are_native_polylines_inside_the_board(self) -> None:
        state = LevelGenerator().generate(level=5, seed=2026).state

        for arrow in state.arrows:
            self.assertGreaterEqual(len(arrow.points), 2)
            self.assertFalse(arrow.path)
            self.assertFalse(arrow.segments)
            self.assertEqual(len(arrow.line_segments), len(arrow.points) - 1)
            self.assertEqual(arrow.front_point, arrow.points[-1])
            self.assertTrue(
                all(state.grid.in_bounds_point(point) for point in arrow.points)
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
        blocked_arrow = Arrow(
            points=(Point(1.0, 3.0), Point(2.0, 3.0)),
            direction="right",
        )
        blocker = Arrow(
            points=(Point(4.0, 2.0), Point(4.0, 4.0)),
            direction="down",
        )
        controller = GameController(
            GameState(grid=Grid(6, 6), arrows=[blocked_arrow, blocker])
        )

        events = controller.handle_point(1.5, 3.0)
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

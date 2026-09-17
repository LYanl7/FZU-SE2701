"""Additional assignment checks; no changes to the game's rules."""

import unittest

from tests.test_gameplay import GameController, GameState, Grid, Arrow, ArrowState


class RequirementTests(unittest.TestCase):
    def make_blocked(self):
        return GameController(GameState(grid=Grid(4, 4), arrows=[
            Arrow(x=0.5, y=1.5, direction="right"),
            Arrow(x=2.5, y=1.5, direction="up"),
        ]))

    def test_T01_T03_free_edge_arrows_in_all_directions(self):
        for direction, x, y in (("up", 1.5, 0.5), ("down", 1.5, 3.5),
                                ("left", 0.5, 1.5), ("right", 3.5, 1.5)):
            with self.subTest(direction=direction):
                arrow = Arrow(x=x, y=y, direction=direction)
                c = GameController(GameState(grid=Grid(4, 4), arrows=[arrow]))
                self.assertEqual(c.handle_point(x, y)[0]["type"], c.EVENT_ARROW_FLY_OUT)
                c.update(c.animation_duration)
                self.assertIs(arrow.state, ArrowState.REMOVED)
                self.assertEqual(c.remaining_arrows, 0)
                self.assertEqual(c.mistakes_remaining, 3)

    def test_T02_blocked_in_all_directions(self):
        for direction, x, y in (("up", 1.5, 0.5), ("down", 1.5, 2.5),
                                ("left", 0.5, 1.5), ("right", 2.5, 1.5)):
            with self.subTest(direction=direction):
                c = GameController(GameState(grid=Grid(4, 4), arrows=[
                    Arrow(x=1.5, y=1.5, direction=direction),
                    Arrow(x=x, y=y, direction="up"),
                ]))
                self.assertEqual(c.handle_point(1.5, 1.5)[0]["type"], c.EVENT_ARROW_BLOCKED)
                self.assertEqual(c.remaining_arrows, 2)
                self.assertEqual(c.mistakes_remaining, 2)

    def test_T05_failure_and_restart(self):
        c = self.make_blocked()
        for _ in range(3):
            c.handle_point(0.5, 1.5)
        self.assertEqual(c.phase, c.PHASE_FAILED)
        self.assertEqual(c.mistakes_remaining, 0)
        self.assertEqual(c.handle_point(2.5, 1.5)[0]["type"], c.EVENT_ACTION_IGNORED)
        c.restart()
        self.assertEqual(c.phase, c.PHASE_PLAYING)
        self.assertEqual(c.mistakes_remaining, 3)
        self.assertEqual(c.remaining_arrows, 2)

    def test_T06_restart_restores_layout_timer_and_pending_flight(self):
        c = self.make_blocked()
        layout = [(a.x, a.y, a.direction) for a in c.state.arrows]
        c.handle_point(0.5, 1.5)
        c.handle_point(2.5, 1.5)
        c.update(0.1)
        c.restart()
        self.assertEqual([(a.x, a.y, a.direction) for a in c.state.arrows], layout)
        self.assertEqual(c.elapsed_seconds, 0)
        self.assertEqual(c.mistakes_remaining, 3)
        self.assertEqual(c.remaining_arrows, 2)
        self.assertFalse(c.animations)
        c.update(1)
        self.assertEqual(c.remaining_arrows, 2)

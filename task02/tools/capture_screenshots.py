"""Render real game screens without a desktop; run from any working directory."""

import os
from pathlib import Path
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pygame
from logic.game_controller import GameController
from logic.level_generator import LevelGenerator
from presentation.app import GameApp


def main():
    output = ROOT / "images"
    output.mkdir(exist_ok=True)
    app = GameApp(controller=GameController(generation_seed=2701))

    def save(name):
        app._draw()
        pygame.image.save(app.screen, str(output / f"{name}.png"))

    def tick():
        app._call_controller_update(1.0)
        app._update_effects(1.0)
        app._sync_screen_from_state()

    def click(arrow):
        position = tuple(round(v) for v in app._board_point_to_pixel(arrow.x, arrow.y))
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=position))
        app._handle_events()

    try:
        save("start")
        app._handle_click(app._button_rect("primary").center)
        assert app.screen_name == app.PLAYING
        save("gameplay")
        blocked = next(a for a in app.controller.state.arrows
                       if app.controller.state.grid.blocking_arrows(a))
        click(blocked)
        assert app.controller.mistakes_remaining == 2
        app._update_effects(0.25)
        save("collision")
        tick()
        for _ in range(2):
            click(blocked)
            tick()
        assert app.screen_name == app.LOST
        save("failure")
        app._handle_click(app._button_rect("primary").center)
        assert app.screen_name == app.PLAYING
        assert app.controller.mistakes_remaining == 3

        for level in range(1, 4):
            solution = LevelGenerator.solution_order(app.controller.state)
            assert len(solution) == len(app.controller.state.arrows)
            for index in solution:
                click(app.controller.state.arrows[index])
                tick()
            assert app.screen_name == app.WON, (level, app.controller.remaining_arrows)
            assert app.controller.mistakes_remaining == 3
            if level == 1:
                save("success")
            print(f"Random level {level}: {len(solution)} arrows cleared through mouse events")
            if level < 3:
                app._handle_click(app._button_rect("primary").center)
                assert app.controller.current_level == level + 1
                assert app.screen_name == app.PLAYING
        print(f"Screenshots saved to {output}")
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()

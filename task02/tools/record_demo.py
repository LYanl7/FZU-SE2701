"""Capture a complete first-level playthrough as GIF.

Requires pygame and Pillow. Run from task02 with:
    python tools/record_demo.py
Mouse events operate the unchanged game; a cursor overlay makes clicks visible.
"""

import os
from pathlib import Path
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pygame
from PIL import Image

from logic.game_controller import GameController
from logic.level_generator import LevelGenerator
from presentation.app import GameApp


def main():
    output = ROOT / "images" / "playthrough.gif"
    output.parent.mkdir(exist_ok=True)
    app = GameApp(controller=GameController(generation_seed=2701))
    frames = []
    cursor = (720, 670)
    palette = None
    clicked_frames = 0

    def frame():
        nonlocal palette, clicked_frames
        # Four simulation steps per captured frame preserve smooth animation.
        for _ in range(4):
            if app.screen_name == app.PLAYING:
                app._call_controller_update(0.02)
                app._sync_screen_from_state()
            app._update_effects(0.02)
        app._draw()
        x, y = cursor
        if clicked_frames:
            pygame.draw.circle(app.screen, (255, 255, 255), cursor, 17, 2)
            clicked_frames -= 1
        polygon = [(x, y), (x + 3, y + 20), (x + 8, y + 14), (x + 15, y + 13)]
        pygame.draw.polygon(app.screen, (255, 255, 255), polygon)
        pygame.draw.polygon(app.screen, (18, 24, 38), polygon, 1)
        rgb = Image.frombytes("RGB", app.window_size, pygame.image.tobytes(app.screen, "RGB"))
        rgb = rgb.resize((800, 600), Image.Resampling.LANCZOS)
        if palette is None:
            palette = rgb.quantize(colors=256)
        frames.append(rgb.quantize(palette=palette, dither=Image.Dither.NONE))

    def hold(count):
        for _ in range(count):
            frame()

    def click(position):
        nonlocal cursor, clicked_frames
        start = cursor
        target = tuple(round(v) for v in position)
        for step in range(1, 4):
            cursor = tuple(round(a + (b - a) * step / 3) for a, b in zip(start, target))
            frame()
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=target))
        app._handle_events()
        clicked_frames = 3

    def click_arrow(arrow):
        click(app._board_point_to_pixel(arrow.x, arrow.y))

    try:
        hold(18)
        click(app._button_rect("primary").center)
        assert app.screen_name == app.PLAYING
        hold(12)
        blocked = next(a for a in app.controller.state.arrows
                       if app.controller.state.grid.blocking_arrows(a))
        click_arrow(blocked)
        hold(16)
        assert app.controller.mistakes_remaining == 2
        assert app.controller.remaining_arrows == 52

        solution = LevelGenerator.solution_order(app.controller.state)
        assert len(solution) == 52
        for count, index in enumerate(solution, 1):
            click_arrow(app.controller.state.arrows[index])
            hold(10)
            assert app.controller.remaining_arrows == 52 - count
        assert app.screen_name == app.WON
        assert app.controller.mistakes_remaining == 2
        cursor = (810, 660)
        hold(40)
        frames[0].save(output, save_all=True, append_images=frames[1:],
                       duration=80, loop=0, optimize=True, disposal=1)
        with Image.open(output) as gif:
            duration = 0
            for index in range(gif.n_frames):
                gif.seek(index)
                duration += gif.info.get("duration", 0)
            assert gif.size == (800, 600)
            print(f"GIF: {gif.n_frames} frames, {duration / 1000:.2f}s, {output.stat().st_size} bytes")
        print(f"Saved {output}; 52 arrows cleared, one collision, victory confirmed.")
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()

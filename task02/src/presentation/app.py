"""Pygame application shell."""

import pygame

from logic.game_controller import GameController


class GameApp:
    """Own the Pygame lifecycle and delegate game rules to the controller."""

    WINDOW_SIZE = (800, 600)
    FPS = 60

    def __init__(self) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode(self.WINDOW_SIZE)
        pygame.display.set_caption("一箭又一箭")
        self.clock = pygame.time.Clock()
        self.controller = GameController()

    def run(self) -> None:
        """Run the main event loop."""
        running = True
        while running and self.controller.state.is_running:
            delta_seconds = self.clock.tick(self.FPS) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

            self.controller.update(delta_seconds)
            self.screen.fill((24, 24, 32))
            pygame.display.flip()

        pygame.quit()

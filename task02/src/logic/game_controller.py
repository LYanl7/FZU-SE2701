"""Game input and rules coordination."""

from model.game_state import GameState


class GameController:
    """Handle player actions and update the game state.

    The rule implementation is intentionally left minimal during project
    initialization. Future iterations should keep rule decisions in this
    layer instead of coupling them to Pygame rendering code.
    """

    def __init__(self, state: GameState | None = None) -> None:
        self.state = state or GameState()

    def handle_action(self, row: int, column: int) -> None:
        """Handle a board action from the presentation layer."""
        del row, column

    def update(self, delta_seconds: float) -> None:
        """Advance game rules by one frame."""
        del delta_seconds

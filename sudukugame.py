import random


# ---------------- ENUMS ----------------
class MoveResult:
    INVALID = "INVALID"
    SUCCESS = "SUCCESS"
    WIN = "WIN"


class GameStatus:
    ONGOING = "ONGOING"
    COMPLETED = "COMPLETED"


# ---------------- PLAYER ----------------
class Player:
    def __init__(self, name):
        self.name = name


# ---------------- BOARD ----------------
class Board:
    def __init__(self, grid):
        self.grid = grid

    def is_empty(self, r, c):
        return self.grid[r][c] == 0

    def place(self, r, c, val):
        self.grid[r][c] = val

    def is_valid(self, r, c, val):
        # row
        if val in self.grid[r]:
            return False

        # col
        for i in range(9):
            if self.grid[i][c] == val:
                return False

        # box
        br, bc = (r // 3) * 3, (c // 3) * 3
        for i in range(br, br + 3):
            for j in range(bc, bc + 3):
                if self.grid[i][j] == val:
                    return False

        return True

    def is_full(self):
        return all(all(cell != 0 for cell in row) for row in self.grid)


# ---------------- TURN STRATEGY ----------------
class SpinWheelStrategy:
    def get_next_player(self, players, current):
        next_player = current
        while next_player == current:
            next_player = random.choice(players)
        return next_player


# ---------------- GAME ----------------
class SudokuGame:
    def __init__(self, grid, players):
        self.board = Board(grid)
        self.players = players
        self.strategy = SpinWheelStrategy()

        self.current_player = players[0]
        self.status = GameStatus.ONGOING
        self.winner = None

    def make_move(self, player, r, c, val):
        if self.status != GameStatus.ONGOING:
            return MoveResult.INVALID

        if player != self.current_player:
            return MoveResult.INVALID

        if not (0 <= r < 9 and 0 <= c < 9):
            return MoveResult.INVALID

        if not self.board.is_empty(r, c):
            return MoveResult.INVALID

        if not self.board.is_valid(r, c, val):
            return MoveResult.INVALID

        self.board.place(r, c, val)

        if self.board.is_full():
            self.status = GameStatus.COMPLETED
            self.winner = player
            return MoveResult.WIN

        self.next_player()
        return MoveResult.SUCCESS

    def next_player(self):
        self.current_player = self.strategy.get_next_player(
            self.players, self.current_player
        )


# ---------------- DEMO ----------------
if __name__ == "__main__":
    grid = [[0]*9 for _ in range(9)]

    players = [Player("Satya"), Player("Manas")]
    game = SudokuGame(grid, players)

    # sample moves
    print(game.make_move(players[0], 0, 0, 5))  # SUCCESS
    print(game.make_move(players[1], 0, 1, 3))  # SUCCESS
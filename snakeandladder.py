import random
from collections import deque


# ---------------- PLAYER ----------------
class Player:
    def __init__(self, name):
        self.name = name
        self.position = 0


# ---------------- DICE ----------------
class Dice:
    def roll(self):
        return random.randint(1, 6)


# ---------------- BOARD ----------------
class Board:
    def __init__(self, size, snakes, ladders):
        self.size = size
        self.snakes = snakes
        self.ladders = ladders

    def get_next_position(self, pos):
        if pos in self.snakes:
            print(f"Snake! {pos} → {self.snakes[pos]}")
            return self.snakes[pos]
        if pos in self.ladders:
            print(f"Ladder! {pos} → {self.ladders[pos]}")
            return self.ladders[pos]
        return pos


# ---------------- GAME ----------------
class Game:
    def __init__(self, players, board):
        self.players = deque(players)
        self.board = board
        self.dice = Dice()
        self.winner = None

    def play_turn(self):
        player = self.players.popleft()

        roll = self.dice.roll()
        print(f"{player.name} rolled {roll}")

        next_pos = player.position + roll

        if next_pos <= self.board.size:
            next_pos = self.board.get_next_position(next_pos)
            player.position = next_pos

        print(f"{player.name} at {player.position}")

        if player.position == self.board.size:
            self.winner = player
            print(f"{player.name} wins!")
            return

        self.players.append(player)

    def start(self):
        while not self.winner:
            self.play_turn()


# ---------------- DEMO ----------------
if __name__ == "__main__":
    snakes = {16: 6, 48: 26, 64: 60, 93: 73}
    ladders = {1: 38, 4: 14, 9: 31, 21: 42}

    board = Board(100, snakes, ladders)

    players = [Player("Satya"), Player("Manas")]

    game = Game(players, board)
    game.start()
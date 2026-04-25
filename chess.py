from abc import ABC, abstractmethod


# ---------------- ENUMS ----------------
WHITE = "WHITE"
BLACK = "BLACK"


# ---------------- PIECES ----------------
class Piece(ABC):
    def __init__(self, color, position):
        self.color = color
        self.position = position

    @abstractmethod
    def get_valid_moves(self, board):
        pass


class King(Piece):
    def get_valid_moves(self, board):
        directions = [(-1,-1), (-1,0), (-1,1),
                      (0,-1),          (0,1),
                      (1,-1),  (1,0),  (1,1)]
        moves = []
        x, y = self.position

        for dx, dy in directions:
            nx, ny = x + dx, y + dy
            if board.is_valid(nx, ny):
                p = board.get_piece(nx, ny)
                if not p or p.color != self.color:
                    moves.append((nx, ny))
        return moves


class Queen(Piece):
    def get_valid_moves(self, board):
        directions = [(-1,-1), (-1,0), (-1,1),
                      (0,-1),          (0,1),
                      (1,-1),  (1,0),  (1,1)]
        return board.get_sliding_moves(self, directions)


class Rook(Piece):
    def get_valid_moves(self, board):
        directions = [(-1,0), (1,0), (0,-1), (0,1)]
        return board.get_sliding_moves(self, directions)


class Bishop(Piece):
    def get_valid_moves(self, board):
        directions = [(-1,-1), (-1,1), (1,-1), (1,1)]
        return board.get_sliding_moves(self, directions)


class Knight(Piece):
    def get_valid_moves(self, board):
        x, y = self.position
        candidates = [(x+2,y+1),(x+2,y-1),(x-2,y+1),(x-2,y-1),
                      (x+1,y+2),(x+1,y-2),(x-1,y+2),(x-1,y-2)]
        moves = []

        for nx, ny in candidates:
            if board.is_valid(nx, ny):
                p = board.get_piece(nx, ny)
                if not p or p.color != self.color:
                    moves.append((nx, ny))
        return moves


class Pawn(Piece):
    def get_valid_moves(self, board):
        x, y = self.position
        direction = -1 if self.color == WHITE else 1
        moves = []

        # forward
        if board.is_valid(x+direction, y) and not board.get_piece(x+direction, y):
            moves.append((x+direction, y))

        # capture
        for dy in [-1, 1]:
            nx, ny = x+direction, y+dy
            if board.is_valid(nx, ny):
                p = board.get_piece(nx, ny)
                if p and p.color != self.color:
                    moves.append((nx, ny))

        return moves


# ---------------- BOARD ----------------
class Board:
    def __init__(self):
        self.grid = [[None]*8 for _ in range(8)]
        self._setup()

    def _setup(self):
        # Pawns
        for i in range(8):
            self.grid[1][i] = Pawn(BLACK, (1, i))
            self.grid[6][i] = Pawn(WHITE, (6, i))

        # Rooks
        self.grid[0][0] = Rook(BLACK, (0,0))
        self.grid[0][7] = Rook(BLACK, (0,7))
        self.grid[7][0] = Rook(WHITE, (7,0))
        self.grid[7][7] = Rook(WHITE, (7,7))

        # Knights
        self.grid[0][1] = Knight(BLACK, (0,1))
        self.grid[0][6] = Knight(BLACK, (0,6))
        self.grid[7][1] = Knight(WHITE, (7,1))
        self.grid[7][6] = Knight(WHITE, (7,6))

        # Bishops
        self.grid[0][2] = Bishop(BLACK, (0,2))
        self.grid[0][5] = Bishop(BLACK, (0,5))
        self.grid[7][2] = Bishop(WHITE, (7,2))
        self.grid[7][5] = Bishop(WHITE, (7,5))

        # Queens
        self.grid[0][3] = Queen(BLACK, (0,3))
        self.grid[7][3] = Queen(WHITE, (7,3))

        # Kings
        self.grid[0][4] = King(BLACK, (0,4))
        self.grid[7][4] = King(WHITE, (7,4))

    def is_valid(self, x, y):
        return 0 <= x < 8 and 0 <= y < 8

    def get_piece(self, x, y):
        return self.grid[x][y]

    def move_piece(self, start, end):
        sx, sy = start
        ex, ey = end
        piece = self.grid[sx][sy]

        self.grid[ex][ey] = piece
        self.grid[sx][sy] = None
        piece.position = (ex, ey)

    def get_sliding_moves(self, piece, directions):
        moves = []
        for dx, dy in directions:
            x, y = piece.position
            while True:
                x += dx
                y += dy
                if not self.is_valid(x, y):
                    break
                p = self.get_piece(x, y)
                if not p:
                    moves.append((x, y))
                else:
                    if p.color != piece.color:
                        moves.append((x, y))
                    break
        return moves


# ---------------- PLAYER ----------------
class Player:
    def __init__(self, name, color):
        self.name = name
        self.color = color


# ---------------- MOVE ----------------
class Move:
    def __init__(self, player, start, end, piece):
        self.player = player
        self.start = start
        self.end = end
        self.piece = piece


# ---------------- GAME ----------------
class Game:
    def __init__(self):
        self.board = Board()
        self.players = [Player("Player1", WHITE), Player("Player2", BLACK)]
        self.turn = 0
        self.move_history = []

    def current_player(self):
        return self.players[self.turn % 2]

    def make_move(self, start, end):
        player = self.current_player()
        piece = self.board.get_piece(*start)

        if not piece:
            print("No piece at start")
            return False

        if piece.color != player.color:
            print("Wrong player")
            return False

        valid_moves = piece.get_valid_moves(self.board)
        if end not in valid_moves:
            print("Invalid move")
            return False

        # simulate move (for check validation)
        captured = self.board.get_piece(*end)
        self.board.move_piece(start, end)

        if self.is_in_check(player.color):
            # rollback
            self.board.move_piece(end, start)
            self.board.grid[end[0]][end[1]] = captured
            print("Move leads to check")
            return False

        self.move_history.append(Move(player, start, end, piece))
        self.turn += 1
        return True

    def find_king(self, color):
        for i in range(8):
            for j in range(8):
                p = self.board.get_piece(i, j)
                if isinstance(p, King) and p.color == color:
                    return (i, j)
        return None

    def is_in_check(self, color):
        king_pos = self.find_king(color)
        for i in range(8):
            for j in range(8):
                p = self.board.get_piece(i, j)
                if p and p.color != color:
                    if king_pos in p.get_valid_moves(self.board):
                        return True
        return False

    def print_board(self):
        for row in self.board.grid:
            print([
                (p.__class__.__name__[0] if p else '.') + 
                (p.color[0] if p else '')
                for p in row
            ])
        print()
        

# ---------------- DRIVER ----------------
if __name__ == "__main__":
    game = Game()
    game.print_board()

    # sample moves
    game.make_move((6,4), (4,4))  # white pawn
    game.print_board()

    game.make_move((1,4), (3,4))  # black pawn
    game.print_board()

    game.make_move((7,3), (3,7))  # white queen aggressive
    game.print_board()
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from threading import RLock, Thread
from typing import Dict, List, Optional, Set, Tuple


class Rank(Enum):
    BRONZE = "Bronze"
    SILVER = "Silver"
    GOLD = "Gold"
    PLATINUM = "Platinum"
    DIAMOND = "Diamond"


class RankCriteria(Enum):
    SAME_RANK = "SameRank"
    ANY_RANK = "AnyRank"


class PlayerStatus(Enum):
    AVAILABLE = "AVAILABLE"
    WAITING = "WAITING"
    PLAYING = "PLAYING"


class GameStatus(Enum):
    WAITING = "WAITING"
    PLAYING = "PLAYING"


class ValidationError(Exception):
    pass


class NotFoundError(Exception):
    pass


class MatchRejectedError(Exception):
    pass


@dataclass
class Player:
    player_id: str
    rank: Rank
    status: PlayerStatus = PlayerStatus.AVAILABLE
    current_game_id: Optional[str] = None


@dataclass(frozen=True)
class GameMode:
    name: str
    required_players: int


@dataclass
class Game:
    game_id: str
    game_mode: str
    location: str
    rank_criteria: RankCriteria
    rank_key: Optional[Rank]
    player_ids: List[str] = field(default_factory=list)
    status: GameStatus = GameStatus.WAITING


@dataclass(frozen=True)
class MatchRequest:
    player_ids: List[str]
    game_modes: List[str]
    locations: List[str]
    rank_criteria: RankCriteria


class PlayerRepository:
    def __init__(self):
        self.players: Dict[str, Player] = {}
        self._lock = RLock()

    def create(self, player: Player) -> None:
        with self._lock:
            if player.player_id in self.players:
                raise ValidationError(f"Player already exists: {player.player_id}")
            self.players[player.player_id] = player

    def get(self, player_id: str) -> Player:
        with self._lock:
            player = self.players.get(player_id)
            if not player:
                raise NotFoundError(f"Player not found: {player_id}")
            return player


class GameModeRepository:
    def __init__(self):
        self.game_modes: Dict[str, GameMode] = {}
        self._lock = RLock()

    def create(self, game_mode: GameMode) -> None:
        with self._lock:
            key = self._key(game_mode.name)
            if key in self.game_modes:
                raise ValidationError(f"Game mode already exists: {game_mode.name}")
            self.game_modes[key] = game_mode

    def get(self, game_mode: str) -> GameMode:
        with self._lock:
            mode = self.game_modes.get(self._key(game_mode))
            if not mode:
                raise NotFoundError(f"Game mode not found: {game_mode}")
            return mode

    def _key(self, game_mode: str) -> str:
        return game_mode.strip().lower()


class LocationRepository:
    def __init__(self):
        self.locations: Set[str] = set()
        self._lock = RLock()

    def create(self, location: str) -> None:
        with self._lock:
            self.locations.add(self._key(location))

    def exists(self, location: str) -> bool:
        with self._lock:
            return self._key(location) in self.locations

    def _key(self, location: str) -> str:
        return location.strip().lower()


class GameRepository:
    def __init__(self):
        self.games: Dict[str, Game] = {}

        # Waiting index is by mode + location. Rank compatibility is checked
        # in the service because AnyRank requests may join same-rank games.
        self.waiting_game_ids_by_key: Dict[Tuple[str, str], Set[str]] = {}
        self._lock = RLock()

    def save(self, game: Game) -> None:
        with self._lock:
            self.games[game.game_id] = game
            if game.status == GameStatus.WAITING:
                self.waiting_game_ids_by_key.setdefault(
                    self._key(game.game_mode, game.location),
                    set(),
                ).add(game.game_id)

    def get(self, game_id: str) -> Game:
        with self._lock:
            game = self.games.get(game_id)
            if not game:
                raise NotFoundError(f"Game not found: {game_id}")
            return game

    def list_waiting(self, game_mode: str, location: str) -> List[Game]:
        with self._lock:
            game_ids = self.waiting_game_ids_by_key.get(
                self._key(game_mode, location),
                set(),
            )
            return [
                self.games[game_id]
                for game_id in game_ids
                if self.games[game_id].status == GameStatus.WAITING
            ]

    def mark_playing(self, game: Game) -> None:
        with self._lock:
            game.status = GameStatus.PLAYING
            self.waiting_game_ids_by_key.get(
                self._key(game.game_mode, game.location),
                set(),
            ).discard(game.game_id)

    def list_all(self) -> List[Game]:
        with self._lock:
            return list(self.games.values())

    def _key(self, game_mode: str, location: str) -> Tuple[str, str]:
        return (game_mode.strip().lower(), location.strip().lower())


class MatchmakingService:
    """
    Scoped P0 implementation:
    - Waiting games are fixed once created.
    - No global rebalancing or moving waiting players between games.
    - Coordinator lock keeps the multi-player, multi-game mutation atomic.
    """

    def __init__(
        self,
        player_repo: PlayerRepository,
        game_mode_repo: GameModeRepository,
        location_repo: LocationRepository,
        game_repo: GameRepository,
    ):
        self.player_repo = player_repo
        self.game_mode_repo = game_mode_repo
        self.location_repo = location_repo
        self.game_repo = game_repo
        self._coordinator_lock = RLock()
        self._next_game_number = 1

    def add_game_mode(self, mode_name: str, required_players: int) -> None:
        if not mode_name.strip():
            raise ValidationError("Game mode name is required")
        if required_players <= 0:
            raise ValidationError("Required players must be positive")
        self.game_mode_repo.create(GameMode(mode_name.strip(), required_players))

    def add_location(self, location_name: str) -> None:
        if not location_name.strip():
            raise ValidationError("Location name is required")
        self.location_repo.create(location_name)

    def register_player(self, player_id: str, rank: Rank) -> None:
        if not player_id.strip():
            raise ValidationError("Player id is required")
        self.player_repo.create(Player(player_id.strip(), rank))

    def join_match(self, request: MatchRequest) -> str:
        with self._coordinator_lock:
            players = self._validate_request(request)
            game = self._find_compatible_waiting_game(request, players)
            if not game:
                game = self._create_game_for_request(request, players)

            self._add_players_to_game(game, players)

            required_players = self.game_mode_repo.get(game.game_mode).required_players
            if len(game.player_ids) == required_players:
                self._start_game(game)
                return self._format_playing(game)

            return self._format_waiting(game)

    def get_player_status(self, player_id: str) -> PlayerStatus:
        return self.player_repo.get(player_id).status

    def list_games(self) -> List[Game]:
        return sorted(self.game_repo.list_all(), key=lambda game: game.game_id)

    def _validate_request(self, request: MatchRequest) -> List[Player]:
        if not request.player_ids:
            raise ValidationError("At least one player is required")
        if len(set(request.player_ids)) != len(request.player_ids):
            raise ValidationError("Duplicate player in request")
        if not request.game_modes:
            raise ValidationError("At least one game mode is required")
        if not request.locations:
            raise ValidationError("At least one location is required")

        players = [self.player_repo.get(player_id) for player_id in request.player_ids]
        for player in players:
            if player.status != PlayerStatus.AVAILABLE:
                raise MatchRejectedError(f"Player is not available: {player.player_id}")

        for game_mode in request.game_modes:
            mode = self.game_mode_repo.get(game_mode)
            if len(players) > mode.required_players:
                raise ValidationError(
                    f"Request team size exceeds game capacity: {game_mode}"
                )

        for location in request.locations:
            if not self.location_repo.exists(location):
                raise NotFoundError(f"Location not found: {location}")

        if request.rank_criteria == RankCriteria.SAME_RANK:
            ranks = {player.rank for player in players}
            if len(ranks) != 1:
                raise MatchRejectedError("SameRank request must contain one rank")

        return players

    def _find_compatible_waiting_game(
        self,
        request: MatchRequest,
        players: List[Player],
    ) -> Optional[Game]:
        for game_mode in request.game_modes:
            mode = self.game_mode_repo.get(game_mode)
            for location in request.locations:
                waiting_games = sorted(
                    self.game_repo.list_waiting(game_mode, location),
                    key=lambda game: game.game_id,
                )
                for game in waiting_games:
                    if len(game.player_ids) + len(players) > mode.required_players:
                        continue
                    if self._is_rank_compatible(game, request, players):
                        return game
        return None

    def _create_game_for_request(
        self,
        request: MatchRequest,
        players: List[Player],
    ) -> Game:
        game_mode = request.game_modes[0]
        location = request.locations[0]
        rank_key = players[0].rank if request.rank_criteria == RankCriteria.SAME_RANK else None
        game = Game(
            game_id=self._next_game_id(),
            game_mode=game_mode,
            location=location,
            rank_criteria=request.rank_criteria,
            rank_key=rank_key,
        )
        self.game_repo.save(game)
        return game

    def _is_rank_compatible(
        self,
        game: Game,
        request: MatchRequest,
        players: List[Player],
    ) -> bool:
        if game.rank_criteria == RankCriteria.ANY_RANK:
            return request.rank_criteria == RankCriteria.ANY_RANK

        if game.rank_criteria == RankCriteria.SAME_RANK:
            return all(player.rank == game.rank_key for player in players)

        return False

    def _add_players_to_game(self, game: Game, players: List[Player]) -> None:
        for player in players:
            player.status = PlayerStatus.WAITING
            player.current_game_id = game.game_id
            game.player_ids.append(player.player_id)

    def _start_game(self, game: Game) -> None:
        self.game_repo.mark_playing(game)
        for player_id in game.player_ids:
            player = self.player_repo.get(player_id)
            player.status = PlayerStatus.PLAYING

    def _next_game_id(self) -> str:
        game_id = f"G{self._next_game_number}"
        self._next_game_number += 1
        return game_id

    def _format_waiting(self, game: Game) -> str:
        return f"Waiting Game with players : {', '.join(game.player_ids)}"

    def _format_playing(self, game: Game) -> str:
        return (
            f"Playing {game.game_mode} game with players : "
            f"{', '.join(game.player_ids)} in {game.location}"
        )


class WarGameMatchmakingEngine:
    def __init__(self):
        self.player_repo = PlayerRepository()
        self.game_mode_repo = GameModeRepository()
        self.location_repo = LocationRepository()
        self.game_repo = GameRepository()
        self.matchmaking_service = MatchmakingService(
            self.player_repo,
            self.game_mode_repo,
            self.location_repo,
            self.game_repo,
        )


def assert_equal(expected, actual, message: str) -> None:
    if expected != actual:
        raise AssertionError(f"{message}: expected={expected}, actual={actual}")
    print(f"PASSED: {message}")


def seed_data(engine: WarGameMatchmakingEngine) -> None:
    service = engine.matchmaking_service
    service.add_game_mode("TwoVTwo", 4)
    service.add_game_mode("FastDraw", 2)
    service.add_game_mode("Raid", 6)
    service.add_location("CastleTown")
    service.add_location("AirBase")
    service.add_location("SavageLand")
    service.register_player("player1", Rank.BRONZE)
    service.register_player("player2", Rank.BRONZE)
    service.register_player("player3", Rank.BRONZE)
    service.register_player("player4", Rank.BRONZE)
    service.register_player("player5", Rank.SILVER)
    service.register_player("player6", Rank.GOLD)
    service.register_player("player7", Rank.GOLD)
    service.register_player("player8", Rank.PLATINUM)
    service.register_player("player9", Rank.DIAMOND)


def request_a() -> MatchRequest:
    return MatchRequest(
        ["player8", "player9"],
        ["FastDraw"],
        ["CastleTown", "AirBase"],
        RankCriteria.ANY_RANK,
    )


def request_b() -> MatchRequest:
    return MatchRequest(
        ["player1", "player2"],
        ["TwoVTwo"],
        ["AirBase", "CastleTown"],
        RankCriteria.SAME_RANK,
    )


def request_c() -> MatchRequest:
    return MatchRequest(
        ["player3"],
        ["TwoVTwo", "Raid"],
        ["AirBase", "SavageLand"],
        RankCriteria.SAME_RANK,
    )


def request_d() -> MatchRequest:
    return MatchRequest(
        ["player4"],
        ["TwoVTwo", "Raid"],
        ["AirBase", "SavageLand"],
        RankCriteria.ANY_RANK,
    )


def test_fast_draw_starts_immediately() -> None:
    engine = WarGameMatchmakingEngine()
    seed_data(engine)
    service = engine.matchmaking_service

    assert_equal(
        "Playing FastDraw game with players : player8, player9 in CastleTown",
        service.join_match(request_a()),
        "fast draw starts immediately",
    )
    assert_equal(PlayerStatus.PLAYING, service.get_player_status("player8"), "player8 playing")


def test_same_rank_and_any_rank_fill_game() -> None:
    engine = WarGameMatchmakingEngine()
    seed_data(engine)
    service = engine.matchmaking_service

    assert_equal(
        "Waiting Game with players : player1, player2",
        service.join_match(request_b()),
        "same rank team waits",
    )
    assert_equal(
        "Waiting Game with players : player1, player2, player3",
        service.join_match(request_c()),
        "same rank solo joins",
    )
    assert_equal(
        "Playing TwoVTwo game with players : player1, player2, player3, player4 in AirBase",
        service.join_match(request_d()),
        "any rank bronze fills same rank game",
    )


def test_busy_player_rejected() -> None:
    engine = WarGameMatchmakingEngine()
    seed_data(engine)
    service = engine.matchmaking_service

    service.join_match(request_b())
    rejected = False
    try:
        service.join_match(request_b())
    except MatchRejectedError:
        rejected = True

    assert_equal(True, rejected, "busy player rejected")


def test_mixed_same_rank_rejected() -> None:
    engine = WarGameMatchmakingEngine()
    seed_data(engine)
    service = engine.matchmaking_service

    rejected = False
    try:
        service.join_match(
            MatchRequest(
                ["player1", "player5"],
                ["TwoVTwo"],
                ["AirBase"],
                RankCriteria.SAME_RANK,
            )
        )
    except MatchRejectedError:
        rejected = True

    assert_equal(True, rejected, "mixed same rank rejected")


def test_concurrent_requests() -> None:
    engine = WarGameMatchmakingEngine()
    seed_data(engine)
    service = engine.matchmaking_service
    outputs = []

    def join(request: MatchRequest) -> None:
        outputs.append(service.join_match(request))

    threads = [
        Thread(target=join, args=(request_b(),)),
        Thread(target=join, args=(request_c(),)),
        Thread(target=join, args=(request_d(),)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    games = service.list_games()
    assert_equal(1, len(games), "one game created by concurrent compatible requests")
    assert_equal(GameStatus.PLAYING, games[0].status, "concurrent game started")
    assert_equal(
        ["player1", "player2", "player3", "player4"],
        games[0].player_ids,
        "all concurrent players assigned",
    )


def run_tests() -> None:
    test_fast_draw_starts_immediately()
    test_same_rank_and_any_rank_fill_game()
    test_busy_player_rejected()
    test_mixed_same_rank_rejected()
    test_concurrent_requests()


def main() -> None:
    run_tests()


if __name__ == "__main__":
    main()

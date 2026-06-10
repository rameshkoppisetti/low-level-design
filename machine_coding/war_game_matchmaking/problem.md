# Online War Game Matchmaking Engine

Implement an in-memory matchmaking engine for an online war game.

## P0 Requirements

- Add game modes with required player count.
- Add game locations.
- Register players with ranks.
- Players can submit a join request as an individual or team.
- Request contains:
  - player ids
  - accepted game modes
  - accepted locations
  - rank criteria: `SAME_RANK` or `ANY_RANK`
- Players in the same request must be assigned to the same game.
- A player can play/wait in only one game at a time.
- If a compatible waiting game exists, add players to it.
- If no compatible waiting game exists, create a new waiting game.
- Start a game once required number of players have joined.
- SameRank requests match only with same-rank players.
- AnyRank requests can match with AnyRank games.
- All operations are in-memory.
- Demonstrate concurrent requests.

## Out Of Scope / Bonus Not Implemented

- Earlier-request preference optimization.
- Minimum number of games optimization.
- Moving players between waiting games.
- Rebalancing existing waiting games.
- Match cancellation.
- Persistent storage.

## Assumptions

- Game modes, locations, and players are preloaded.
- Request player count is always less than or equal to game capacity.
- If a `SAME_RANK` request contains mixed ranks, it is rejected.
- Game mode and location are selected in input order.
- Concurrency is single-process; service-level allocation lock is used because matching mutates multiple players and games atomically.

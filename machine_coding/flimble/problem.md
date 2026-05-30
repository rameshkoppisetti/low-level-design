# Flimble: Dating App Machine Coding Problem

## Context

You are launching the "Flimble" app to compete in the dating apps market. Design a console application to prototype the features of Flimble.

## Functional Requirements

### P0: Basic Features

- Users can create their profile on the platform.
- A user profile may include basic information like name, age, gender, etc.
- Users can choose their interests from a list of interests provided by the platform.
- Interests may include pets, football, movies, books, etc.
- Users can choose partner preferences like age range, gender, etc.
- Users can request the best available profile and choose to either accept or decline.

Ranking of profiles must follow this priority order, highest to lowest:

1. Preferred profiles that have already accepted the user, ordered by highest number of mutual interests.
2. Preferred profiles, ordered by highest number of mutual interests.
3. Unpreferred profiles that have already accepted the user, ordered by highest number of mutual interests.

Definitions:

- A preferred profile is one that strictly matches the user's partner preference.
- Users should not get any unpreferred profile that has not already accepted the user.
- Once a user accepts or declines a profile, it should not appear in the user's feed again.
- If two profiles mutually accept each other, the matched profile moves to the user's matched list.
- A user can view their matched list of profiles at any time.

Operations:

- `create-profile`
- `add-interests`
- `set-partner-preference`
- `get-best-profile`
- `accept-profile`
- `decline-profile`
- `list-matched-profiles`

### P1: Advanced Features

- To maximize the number of matched users, every time a user receives a match, the likelihood of their profile appearing on another user's feed goes down.
- Users can buy boost plans, which make the user skip the queue and increase the likelihood of appearing in more user feeds.
- Admins should be able to pull reports from the platform at any time.
- Reports may include total user count, matched users count, top-N users with highest matches, and user cohort size by gender, age, etc.

Operations:

- `buy-boost`
- `show-stats`

### P2: Bonus Features

P2 is optional and should be attempted only after P0 and P1 are complete.

- Users can mark a preference as strict vs lenient.
- If a profile fails a lenient preference, it may still be treated similar to a preferred profile but with lower ranking.
- Users can super-accept a profile, which immediately ranks the user highest on the receiver's feed.
- Users can only super-accept once in their lifetime.

Operations:

- `super-accept-profile`

## Expectations And Ground Rules

- Code should be demoable, either using a main driver program or STDIN/STDOUT.
- Create sample data yourself.
- Add minimum 5-6 profiles to test the application.
- Avoid monolithic code.
- Code should be readable, modular, testable, and extensible.
- Follow proper naming conventions.
- It should be easy to add or remove functionality without rewriting the entire codebase.
- Code should handle edge cases gracefully.
- Do not use any database; store all data in memory.
- Make reasonable assumptions and convey them to the review panel.

## Folder Structure

```text
machine_coding/flimble/
  problem.md
  flimble.py
  test_flimble.py
```

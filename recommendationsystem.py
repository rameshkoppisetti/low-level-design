from collections import defaultdict
import heapq


# =========================
# USER
# =========================

class User:
    def __init__(self, user_id, name):
        self.id = user_id
        self.name = name
        self.active = True
        self.blocked = set()


# =========================
# GRAPH
# =========================

class FriendGraph:
    def __init__(self):
        self.graph = defaultdict(set)

    def add_friend(self, u1, u2):
        self.graph[u1].add(u2)
        self.graph[u2].add(u1)

    def get_friends(self, user_id):
        return self.graph[user_id]


# =========================
# INTERACTION STORE
# =========================

class InteractionStore:
    def __init__(self):
        self.interactions = defaultdict(int)

    def add_interaction(self, u1, u2):
        key = tuple(sorted((u1, u2)))
        self.interactions[key] += 1

    def get_score(self, u1, u2):
        key = tuple(sorted((u1, u2)))
        return self.interactions.get(key, 0)


# =========================
# USER SERVICE
# =========================

class UserService:
    def __init__(self):
        self.users = {}

    def add_user(self, user):
        self.users[user.id] = user

    def get(self, user_id):
        return self.users.get(user_id)


# =========================
# STRATEGY
# =========================

class RecommendationStrategy:
    def score(self, user_id, candidate_id, mutual_friend, interaction_store):
        raise NotImplementedError


class MutualWithInteractionStrategy(RecommendationStrategy):
    def score(self, user_id, candidate_id, mutual_friend, interaction_store):
        score = 1
        score += interaction_store.get_score(mutual_friend, candidate_id)
        return score


# =========================
# RECOMMENDATION SERVICE
# =========================

class RecommendationService:
    def __init__(self, graph, user_service, interaction_store, strategy):
        self.graph = graph
        self.user_service = user_service
        self.interaction_store = interaction_store

        # ✅ Strategy fixed internally
        self.strategy = strategy

    def recommend(self, user_id, k=5):
        user = self.user_service.get(user_id)
        if not user:
            return []

        direct_friends = self.graph.get_friends(user_id)
        score = defaultdict(int)

        for friend in direct_friends:
            for candidate_id in self.graph.get_friends(friend):

                if candidate_id == user_id or candidate_id in direct_friends:
                    continue

                candidate = self.user_service.get(candidate_id)
                if not candidate or not candidate.active:
                    continue

                # bidirectional block check
                if candidate_id in user.blocked or user_id in candidate.blocked:
                    continue

                # scoring
                score[candidate_id] += self.strategy.score(
                    user_id,
                    candidate_id,
                    friend,
                    self.interaction_store
                )

        return self._rank(score, k)

    def _rank(self, score_map, k):
        return heapq.nlargest(k, score_map.items(), key=lambda x: x[1])


# =========================
# DEMO
# =========================

def main():
    graph = FriendGraph()
    users = UserService()
    interactions = InteractionStore()

    for i in range(1, 6):
        users.add_user(User(i, f"user{i}"))

    graph.add_friend(1, 2)
    graph.add_friend(1, 3)
    graph.add_friend(2, 4)
    graph.add_friend(3, 4)
    graph.add_friend(2, 5)

    interactions.add_interaction(2, 4)
    interactions.add_interaction(2, 4)

    service = RecommendationService(graph, users, interactions, MutualWithInteractionStrategy())

    print(service.recommend(1))


if __name__ == "__main__":
    main()
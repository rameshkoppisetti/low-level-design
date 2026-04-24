import uuid
import time
from collections import defaultdict


# =========================
# DOMAIN
# =========================

class User:
    def __init__(self, name):
        self.id = str(uuid.uuid4())
        self.name = name


class Post:
    def __init__(self, user_id, content):
        self.id = str(uuid.uuid4())
        self.user_id = user_id
        self.content = content
        self.created_at = time.time()


class Comment:
    def __init__(self, user_id, post_id, content):
        self.id = str(uuid.uuid4())
        self.user_id = user_id
        self.post_id = post_id
        self.content = content
        self.created_at = time.time()


class Notification:
    def __init__(self, user_id, message):
        self.id = str(uuid.uuid4())
        self.user_id = user_id
        self.message = message
        self.created_at = time.time()


# =========================
# SERVICES
# =========================

class UserService:
    def __init__(self):
        self.users = {}
        self.followers = defaultdict(set)   # user -> followers
        self.following = defaultdict(set)   # user -> following

    def create_user(self, name):
        user = User(name)
        self.users[user.id] = user
        return user

    def follow(self, u1, u2):
        self.following[u1].add(u2)
        self.followers[u2].add(u1)


class NotificationService:
    def __init__(self):
        self.notifications = defaultdict(list)

    def send(self, user_id, message):
        self.notifications[user_id].append(Notification(user_id, message))


class PostService:
    def __init__(self, notification_service):
        self.posts = {}
        self.user_posts = defaultdict(list)
        self.likes = defaultdict(set)       # post_id -> user_ids
        self.comments = defaultdict(list)   # post_id -> comments
        self.notification_service = notification_service

    def create_post(self, user_id, content):
        post = Post(user_id, content)
        self.posts[post.id] = post
        self.user_posts[user_id].append(post)
        return post

    def like_post(self, user_id, post_id):
        if user_id in self.likes[post_id]:
            return  # already liked

        self.likes[post_id].add(user_id)

        owner = self.posts[post_id].user_id
        self.notification_service.send(owner, f"User {user_id} liked your post")

    def comment_post(self, user_id, post_id, content):
        comment = Comment(user_id, post_id, content)
        self.comments[post_id].append(comment)

        owner = self.posts[post_id].user_id
        self.notification_service.send(owner, f"User {user_id} commented on your post")

        return comment

import heapq


class FeedService:
    def __init__(self, user_service, post_service):
        self.user_service = user_service
        self.post_service = post_service
        
        
    def get_feed(self, user_id, k=10):
        heap = []
        followees = self.user_service.following[user_id]

        # Step 1: push latest post of each followee
        for followee in followees:
            posts = self.post_service.user_posts[followee]
            if posts:
                idx = len(posts) - 1  # latest post
                post = posts[idx]

                # max heap using negative timestamp
                heapq.heappush(heap, (-post.created_at, followee, idx))

        result = []

        # Step 2: extract top K
        while heap and len(result) < k:
            _, followee, idx = heapq.heappop(heap)
            post = self.post_service.user_posts[followee][idx]

            result.append(post)

            # push next post from same user
            if idx - 1 >= 0:
                next_post = self.post_service.user_posts[followee][idx - 1]
                heapq.heappush(heap, (-next_post.created_at, followee, idx - 1))

        return result


# =========================
# DEMO
# =========================

def main():
    user_service = UserService()
    notification_service = NotificationService()
    post_service = PostService(notification_service)
    feed_service = FeedService(user_service, post_service)

    # users
    u1 = user_service.create_user("Satya")
    u2 = user_service.create_user("Rahul")

    # follow
    user_service.follow(u1.id, u2.id)

    # post
    post = post_service.create_post(u2.id, "Hello world!")

    # like + comment
    post_service.like_post(u1.id, post.id)
    post_service.comment_post(u1.id, post.id, "Nice post!")

    # feed
    feed = feed_service.get_feed(u1.id)
    print("Feed:", [p.content for p in feed])

    # notifications
    print("Notifications:", [n.message for n in notification_service.notifications[u2.id]])


if __name__ == "__main__":
    main()
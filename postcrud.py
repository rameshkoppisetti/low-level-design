from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uuid
import datetime

app = FastAPI()

# =========================
# REQUEST MODELS
# =========================

class PostRequest(BaseModel):
    user_id: str
    content: str


class CommentRequest(BaseModel):
    user_id: str
    content: str


# =========================
# DOMAIN MODELS
# =========================

class Post:
    def __init__(self, user_id: str, content: str):
        if not content:
            raise ValueError("Content cannot be empty")

        self.id = str(uuid.uuid4())
        self.user_id = user_id
        self.content = content
        self.created_at = datetime.datetime.utcnow()


class Comment:
    def __init__(self, user_id: str, post_id: str, content: str):
        if not content:
            raise ValueError("Content cannot be empty")

        self.id = str(uuid.uuid4())
        self.post_id = post_id
        self.user_id = user_id
        self.content = content
        self.created_at = datetime.datetime.utcnow()


# =========================
# REPOSITORIES
# =========================

class PostRepository:
    def __init__(self):
        self.store = {}

    def create_post(self, post: Post):
        self.store[post.id] = post
        return post

    def get_post(self, post_id):
        return self.store.get(post_id)

    def get_posts(self, user_id):
        return [p.__dict__ for p in self.store.values() if p.user_id == user_id]

    def delete_post(self, post_id):
        if post_id not in self.store:
            raise KeyError("Post not found")
        del self.store[post_id]


class CommentRepository:
    def __init__(self):
        self.store = {}
        self.post_map = {}

    def create_comment(self, comment: Comment):
        self.store[comment.id] = comment
        self.post_map.setdefault(comment.post_id, []).append(comment)
        return comment

    def get_comments(self, post_id):
        return [c.__dict__ for c in self.post_map.get(post_id, [])]

    def delete_comment(self, comment_id):
        if comment_id not in self.store:
            raise KeyError("Comment not found")

        comment = self.store[comment_id]
        self.post_map[comment.post_id].remove(comment)
        del self.store[comment_id]


# =========================
# SERVICES
# =========================

class PostService:
    def __init__(self, repo: PostRepository):
        self.repo = repo

    def create_post(self, req: PostRequest):
        return self.repo.create_post(Post(req.user_id, req.content))

    def get_post(self, post_id):
        post = self.repo.get_post(post_id)
        if not post:
            raise ValueError("Post not found")
        return post.__dict__

    def get_posts(self, user_id):
        return self.repo.get_posts(user_id)

    def delete_post(self, post_id):
        self.repo.delete_post(post_id)


class CommentService:
    def __init__(self, comment_repo: CommentRepository, post_service: PostService):
        self.comment_repo = comment_repo
        self.post_service = post_service

    def create_comment(self, post_id, req: CommentRequest):
        if not self.post_service.get_post(post_id):
            raise ValueError("Post does not exist")

        return self.comment_repo.create_comment(
            Comment(req.user_id, post_id, req.content)
        )

    def get_comments(self, post_id):
        return self.comment_repo.get_comments(post_id)

    def delete_comment(self, comment_id):
        self.comment_repo.delete_comment(comment_id)


# =========================
# DEPENDENCIES (SINGLETON)
# =========================

post_repo = PostRepository()
comment_repo = CommentRepository()

post_service = PostService(post_repo)
comment_service = CommentService(comment_repo, post_service)


# =========================
# CONTROLLERS (REST APIs)
# =========================

@app.post("/posts", status_code=201)
def create_post(req: PostRequest):
    try:
        post = post_service.create_post(req)
        return post.__dict__
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/posts/{post_id}")
def get_post(post_id: str):
    try:
        return post_service.get_post(post_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/posts")
def get_posts(user_id: str):
    return post_service.get_posts(user_id)


@app.delete("/posts/{post_id}")
def delete_post(post_id: str):
    try:
        post_service.delete_post(post_id)
        return {"message": "Deleted"}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/posts/{post_id}/comments", status_code=201)
def create_comment(post_id: str, req: CommentRequest):
    try:
        comment = comment_service.create_comment(post_id, req)
        return comment.__dict__
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/posts/{post_id}/comments")
def get_comments(post_id: str):
    return comment_service.get_comments(post_id)


@app.delete("/comments/{comment_id}")
def delete_comment(comment_id: str):
    try:
        comment_service.delete_comment(comment_id)
        return {"message": "Deleted"}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


# =========================
# MAIN
# =========================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
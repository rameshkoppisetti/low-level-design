import uuid
import time
from collections import defaultdict


# =========================
# ENUMS
# =========================

class MessageState:
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    READ = "READ"


# =========================
# DOMAIN
# =========================

class Chat:
    def __init__(self, name=None):
        self.id = str(uuid.uuid4())
        self.name = name
        self.metadata = {}


class ChatParticipant:
    def __init__(self, chat_id, user_id):
        self.chat_id = chat_id
        self.user_id = user_id


class Message:
    def __init__(self, chat_id, sender_id, content):
        self.id = str(uuid.uuid4())
        self.chat_id = chat_id
        self.sender_id = sender_id
        self.content = content
        self.timestamp = time.time()


class MessageStatus:
    def __init__(self, message_id, user_id):
        self.message_id = message_id
        self.user_id = user_id
        self.status = MessageState.SENT


# =========================
# SERVICE
# =========================

class ChatService:
    def __init__(self):
        self.chats = {}
        self.participants = defaultdict(set)  # chat_id -> user_ids
        self.messages = defaultdict(list)     # chat_id -> messages
        self.message_status = defaultdict(dict)  # msg_id -> {user_id: status}
        self.online_users = set()

    # ---------- USER STATE ----------
    def set_online(self, user_id):
        self.online_users.add(user_id)

    def set_offline(self, user_id):
        self.online_users.discard(user_id)

    # ---------- CHAT ----------
    def create_chat(self, user_ids, name=None):
        chat = Chat(name)
        self.chats[chat.id] = chat

        for uid in user_ids:
            self.participants[chat.id].add(uid)

        return chat

    # ---------- SEND MESSAGE ----------
    def send_message(self, chat_id, sender_id, content):
        if sender_id not in self.participants[chat_id]:
            raise Exception("User not part of chat")

        msg = Message(chat_id, sender_id, content)
        self.messages[chat_id].append(msg)

        # initialize status for all participants
        for uid in self.participants[chat_id]:
            status = MessageState.SENT

            if uid in self.online_users and uid != sender_id:
                status = MessageState.DELIVERED

            self.message_status[msg.id][uid] = status

        return msg

    # ---------- READ MESSAGE ----------
    def read_message(self, user_id, message_id):
        if message_id not in self.message_status:
            raise Exception("Message not found")

        self.message_status[message_id][user_id] = MessageState.READ

    # ---------- GET MESSAGES ----------
    def get_messages(self, chat_id):
        return self.messages[chat_id]

    # ---------- GET STATUS ----------
    def get_message_status(self, message_id):
        return self.message_status.get(message_id, {})


# =========================
# DEMO
# =========================

def main():
    service = ChatService()

    u1 = "user1"
    u2 = "user2"
    u3 = "user3"

    # create group chat
    chat = service.create_chat([u1, u2, u3], "group1")

    # mark users online
    service.set_online(u2)
    service.set_online(u3)

    # send message
    msg = service.send_message(chat.id, u1, "Hello everyone!")

    print("Message:", msg.content)

    # check status
    print("Status:", service.get_message_status(msg.id))

    # user reads
    service.read_message(u2, msg.id)

    print("After read:", service.get_message_status(msg.id))


if __name__ == "__main__":
    main()
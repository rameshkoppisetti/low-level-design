from __future__ import annotations

from dataclasses import dataclass, field
from threading import Condition, RLock
from typing import Dict, List, Optional
import time
import uuid


class StreamingError(Exception):
    pass


class ValidationError(StreamingError):
    pass


class EntityNotFoundError(StreamingError):
    pass


@dataclass(frozen=True)
class CreateTopicRequest:
    topic_name: str
    partition_count: int


@dataclass(frozen=True)
class PublishRequest:
    topic_name: str
    value: str
    key: Optional[str] = None


@dataclass(frozen=True)
class PollRequest:
    topic_name: str
    group_id: str
    max_messages: int = 1
    timeout_seconds: float = 0.0


@dataclass(frozen=True)
class Message:
    message_id: str
    topic_name: str
    partition_id: int
    offset: int
    key: Optional[str]
    value: str
    created_at: float


@dataclass
class Partition:
    partition_id: int
    messages: List[Message] = field(default_factory=list)
    lock: RLock = field(default_factory=RLock, repr=False)

    def append(self, topic_name: str, key: Optional[str], value: str) -> Message:
        with self.lock:
            message = Message(
                message_id=f"MSG-{uuid.uuid4().hex[:8].upper()}",
                topic_name=topic_name,
                partition_id=self.partition_id,
                offset=len(self.messages),
                key=key,
                value=value,
                created_at=time.time(),
            )
            self.messages.append(message)
            return message

    def read_from(self, offset: int, limit: int) -> List[Message]:
        with self.lock:
            return self.messages[offset: offset + limit]

    def size(self) -> int:
        with self.lock:
            return len(self.messages)


@dataclass
class Topic:
    name: str
    partitions: List[Partition]
    next_partition_index: int = 0
    lock: RLock = field(default_factory=RLock, repr=False)
    condition: Condition = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.condition = Condition(self.lock)

    def choose_partition(self, key: Optional[str]) -> Partition:
        with self.lock:
            if key is not None:
                partition_index = hash(key) % len(self.partitions)
                return self.partitions[partition_index]

            partition = self.partitions[self.next_partition_index]
            self.next_partition_index = (
                self.next_partition_index + 1
            ) % len(self.partitions)
            return partition


class TopicRepository:
    def __init__(self):
        self.topics: Dict[str, Topic] = {}
        self._lock = RLock()

    def save(self, topic: Topic) -> None:
        with self._lock:
            key = self._key(topic.name)
            if key in self.topics:
                raise ValidationError(f"Topic already exists: {topic.name}")
            self.topics[key] = topic

    def get(self, topic_name: str) -> Topic:
        with self._lock:
            topic = self.topics.get(self._key(topic_name))
            if not topic:
                raise EntityNotFoundError(f"Topic not found: {topic_name}")
            return topic

    def _key(self, topic_name: str) -> str:
        return topic_name.strip().lower()


class ConsumerOffsetRepository:
    def __init__(self):
        self.offsets: Dict[tuple[str, str, int], int] = {}
        self._lock = RLock()

    def get_offset(self, topic_name: str, group_id: str, partition_id: int) -> int:
        with self._lock:
            return self.offsets.get(
                self._key(topic_name, group_id, partition_id),
                0,
            )

    def commit_offset(
        self,
        topic_name: str,
        group_id: str,
        partition_id: int,
        next_offset: int,
    ) -> None:
        with self._lock:
            self.offsets[self._key(topic_name, group_id, partition_id)] = next_offset

    def _key(self, topic_name: str, group_id: str, partition_id: int) -> tuple[str, str, int]:
        return topic_name.strip().lower(), group_id.strip().lower(), partition_id


class TopicService:
    def __init__(self, topic_repo: TopicRepository):
        self.topic_repo = topic_repo

    def create_topic(self, request: CreateTopicRequest) -> None:
        if not request.topic_name.strip():
            raise ValidationError("Topic name cannot be empty")
        if request.partition_count <= 0:
            raise ValidationError("Partition count must be positive")

        topic = Topic(
            name=request.topic_name.strip(),
            partitions=[
                Partition(partition_id)
                for partition_id in range(request.partition_count)
            ],
        )
        self.topic_repo.save(topic)


class ProducerService:
    def __init__(self, topic_repo: TopicRepository):
        self.topic_repo = topic_repo

    def publish(self, request: PublishRequest) -> Message:
        if not request.value:
            raise ValidationError("Message value cannot be empty")

        topic = self.topic_repo.get(request.topic_name)
        partition = topic.choose_partition(request.key)
        message = partition.append(topic.name, request.key, request.value)

        with topic.condition:
            topic.condition.notify_all()

        return message


class ConsumerService:
    def __init__(
        self,
        topic_repo: TopicRepository,
        offset_repo: ConsumerOffsetRepository,
    ):
        self.topic_repo = topic_repo
        self.offset_repo = offset_repo

    def poll(self, request: PollRequest) -> List[Message]:
        if not request.group_id.strip():
            raise ValidationError("Consumer group id cannot be empty")
        if request.max_messages <= 0:
            raise ValidationError("max_messages must be positive")
        if request.timeout_seconds < 0:
            raise ValidationError("timeout_seconds cannot be negative")

        topic = self.topic_repo.get(request.topic_name)
        deadline = time.time() + request.timeout_seconds

        while True:
            messages = self._poll_once(topic, request.group_id, request.max_messages)
            if messages or request.timeout_seconds == 0:
                return messages

            remaining = deadline - time.time()
            if remaining <= 0:
                return []

            self._wait_for_any_partition(topic, remaining)

    def _poll_once(
        self,
        topic: Topic,
        group_id: str,
        max_messages: int,
    ) -> List[Message]:
        result = []

        for partition in topic.partitions:
            if len(result) >= max_messages:
                break

            offset = self.offset_repo.get_offset(
                topic.name,
                group_id,
                partition.partition_id,
            )
            remaining_limit = max_messages - len(result)
            partition_messages = partition.read_from(offset, remaining_limit)

            if partition_messages:
                result.extend(partition_messages)
                self.offset_repo.commit_offset(
                    topic.name,
                    group_id,
                    partition.partition_id,
                    partition_messages[-1].offset + 1,
                )

        return result

    def _wait_for_any_partition(self, topic: Topic, timeout_seconds: float) -> None:
        with topic.condition:
            topic.condition.wait(timeout=timeout_seconds)


class StatsService:
    def __init__(self, topic_repo: TopicRepository):
        self.topic_repo = topic_repo

    def get_topic_stats(self, topic_name: str) -> Dict[int, int]:
        topic = self.topic_repo.get(topic_name)
        return {
            partition.partition_id: partition.size()
            for partition in topic.partitions
        }


class MessageStreamingApp:
    def __init__(self):
        self.topic_repo = TopicRepository()
        self.offset_repo = ConsumerOffsetRepository()
        self.topic_service = TopicService(self.topic_repo)
        self.producer_service = ProducerService(self.topic_repo)
        self.consumer_service = ConsumerService(self.topic_repo, self.offset_repo)
        self.stats_service = StatsService(self.topic_repo)


def main() -> None:
    app = MessageStreamingApp()
    app.topic_service.create_topic(CreateTopicRequest("orders", 2))

    app.producer_service.publish(PublishRequest("orders", "order-created-1", key="u1"))
    app.producer_service.publish(PublishRequest("orders", "order-created-2", key="u1"))
    app.producer_service.publish(PublishRequest("orders", "order-created-3", key="u2"))

    messages = app.consumer_service.poll(
        PollRequest("orders", "billing-service", max_messages=10)
    )

    print("Polled messages:")
    for message in messages:
        print(
            message.topic_name,
            message.partition_id,
            message.offset,
            message.key,
            message.value,
        )

    print("Topic stats:", app.stats_service.get_topic_stats("orders"))


if __name__ == "__main__":
    main()

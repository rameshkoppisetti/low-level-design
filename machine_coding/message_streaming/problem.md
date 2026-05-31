# In-Memory Message Streaming Service

## Problem

Design a working MVP for an in-memory message streaming service supporting multiple topics, producers, and consumers.

## Requirements

- Producers can publish messages to topics.
- Topics can have multiple partitions.
- Messages must maintain order within each partition.
- Consumers can subscribe to topics and poll messages.
- Multiple consumer groups should be supported.
- Each consumer group maintains independent offsets.
- Service should be thread-safe.
- Support real-time style data streaming through blocking poll.
- Store everything in memory.

## Assumptions

- Topic names are unique.
- Partition count is fixed after topic creation.
- Message key is optional.
- If key is present, route by hash(key) to a stable partition.
- If key is absent, use round-robin partition assignment.
- Ordering guarantee is per partition only, not across a whole topic.
- Consumers use consumer group id to track offsets.
- No persistence, replication, retention cleanup, or network layer in MVP.

## Operations

- `create_topic(topic_name, partition_count)`
- `publish(topic_name, key, value)`
- `poll(topic_name, group_id, max_messages, timeout_seconds)`
- `get_topic_stats(topic_name)`

## Folder Structure

```text
machine_coding/message_streaming/
  problem.md
  message_streaming.py
  test_message_streaming.py
```

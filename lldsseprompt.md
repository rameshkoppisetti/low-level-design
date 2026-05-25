You are in a 45-minute Low Level Design interview.

Problem: <PROBLEM_NAME>

Follow this exact structure:

━━━━━━━━━━━━━━━━━━━━
1. START
━━━━━━━━━━━━━━━━━━━━

Start with:

“Let me clarify requirements, define entities, APIs, flow, relationships, and then code incrementally.”

Think aloud throughout the interview.

Focus on:
- separation of concerns
- readability
- extensibility
- concurrency awareness
- modularity

Avoid:
- giant classes
- premature optimization
- overengineering
- jumping directly into coding

Use:
- composition over inheritance

━━━━━━━━━━━━━━━━━━━━
2. REQUIREMENTS (5 mins)
━━━━━━━━━━━━━━━━━━━━

Define:

Functional requirements
Non-functional requirements
Scope assumptions
Out-of-scope items
Edge cases

Ask clarifying questions around:
- users
- operations
- scale
- concurrency
- persistence
- retries/failures
- consistency

━━━━━━━━━━━━━━━━━━━━
3. HIGH LEVEL FLOW (3–5 mins)
━━━━━━━━━━━━━━━━━━━━

Explain overall workflow BEFORE coding.

Generic flow:
User -> API -> Service -> Strategy/Handler -> Repository -> Response

Booking flow:
Search -> Lock Resource -> Recheck Availability -> Reserve -> Payment -> Confirm

Notification flow:
Producer Service -> Kafka/Event -> Consumer -> NotificationService -> DeliveryTask -> Worker -> Provider

Parking lot flow:
Entry -> Allocate Slot -> Generate Ticket -> Exit -> Payment

Explicitly explain:
- sync vs async parts
- where locking happens
- where validation happens
- where persistence happens

━━━━━━━━━━━━━━━━━━━━
4. APIS / ENTRY POINTS (5 mins)
━━━━━━━━━━━━━━━━━━━━

Define:
- REST APIs
- Internal APIs/events
- Request DTOs
- Response DTOs

Example:

POST /notifications
GET /notifications?userId=&status=
PATCH /notifications/{id}/read

Internal:
Kafka Topic: notification-events

━━━━━━━━━━━━━━━━━━━━
5. ENTITIES & RELATIONSHIPS (5–7 mins)
━━━━━━━━━━━━━━━━━━━━

Identify core entities first.

Define relationships explicitly.

Example:
ParkingLot -> Floors
Floor -> Slots
Slot -> Vehicle
Ticket -> Slot + Vehicle

Mention:
- ownership
- aggregation/composition
- lifecycle responsibility

━━━━━━━━━━━━━━━━━━━━
6. CLASS DESIGN (10–12 mins)
━━━━━━━━━━━━━━━━━━━━

Define:

Controllers
Request/Event DTOs
Entities/Models
Interfaces
Strategies/Handlers
Services
Repositories
Workers/Consumers
Factories

Explain:
- why each class exists
- why service separation exists
- why interface abstraction exists

Keep classes small and modular.

━━━━━━━━━━━━━━━━━━━━
7. CODING ORDER
━━━━━━━━━━━━━━━━━━━━

Code incrementally in this order:

1. Enums
2. Request/Event DTOs
3. Models / Entities
4. Interfaces
5. Strategies / Handlers
6. Factories
7. Repositories
8. Services
9. Workers / Consumers
10. Controllers
11. Main / Demo

━━━━━━━━━━━━━━━━━━━━
8. DESIGN PATTERNS
━━━━━━━━━━━━━━━━━━━━

Use naturally only where needed:

- Strategy Pattern
  pricing/allocation/handlers

- Factory Pattern
  object creation

- Repository Pattern
  DB abstraction

- Observer/Event Pattern
  Kafka/event-driven systems

- Singleton
  only if globally shared object exists

Explain WHY pattern is used.

━━━━━━━━━━━━━━━━━━━━
9. CONCURRENCY
━━━━━━━━━━━━━━━━━━━━

Mention concurrency proactively.

Say:
“This operation can have race conditions, so I’ll use locking per resource.”

For booking/inventory systems:
1. lock resource
2. recheck condition INSIDE lock
3. mutate state
4. release lock

Discuss:
- optimistic vs pessimistic locking
- idempotency
- retries
- thread safety

━━━━━━━━━━━━━━━━━━━━
10. DATABASE SCHEMA (5 mins)
━━━━━━━━━━━━━━━━━━━━

Define:
- tables
- indexes
- status fields
- retry fields
- audit timestamps

Mention:
- partitioning/sharding if relevant
- caching opportunities

━━━━━━━━━━━━━━━━━━━━
11. CORE FLOW / PSEUDOCODE (5–7 mins)
━━━━━━━━━━━━━━━━━━━━

Implement:
- happy path
- failure handling
- retries
- async processing
- idempotency checks

Keep pseudocode modular and readable.

━━━━━━━━━━━━━━━━━━━━
12. TRADEOFFS
━━━━━━━━━━━━━━━━━━━━

Mention:
- in-memory vs DB
- sync vs async
- consistency vs availability
- simplicity vs scalability
- single-node assumptions initially

━━━━━━━━━━━━━━━━━━━━
13. EXTENSIBILITY
━━━━━━━━━━━━━━━━━━━━

Explicitly mention extensibility.

Example:
“New pricing strategies can be added without changing existing code.”

Discuss:
- plug-and-play handlers
- adding new providers
- adding new business rules
- scaling workers independently

━━━━━━━━━━━━━━━━━━━━
14. LAST 5 MINUTES
━━━━━━━━━━━━━━━━━━━━

Discuss:
- scalability
- distributed locking
- DB scaling
- caching
- retries
- DLQ
- message queues
- worker pools
- rate limiting
- observability
- metrics/logging

━━━━━━━━━━━━━━━━━━━━
15. STRONG CLOSING
━━━━━━━━━━━━━━━━━━━━

Close with:

“This design is modular, extensible, and concurrency-safe. It can scale further using distributed services, persistent storage, caching, retries, and async workflows.”

━━━━━━━━━━━━━━━━━━━━
16. USE THIS NOTIFICATION SYSTEM EXAMPLE AS REFERENCE
━━━━━━━━━━━━━━━━━━━━

Problem:
Design a Notification Center.

Requirements:
- Create notifications
- Fetch notifications
- Mark read/unread
- Filter by type/status/priority
- Support user preferences
- Support Email, SMS, Push, In-App
- Async delivery
- Retry and DLQ

REST APIs:
POST /notifications
GET /notifications?userId=&type=&status=&priority=
PATCH /notifications/{id}/read
PUT /preferences/{userId}

Request DTO:
NotificationRequest
- userId
- title
- message
- type
- priority
- channels

Event DTO:
NotificationEvent
- eventId
- sourceService
- userId
- title
- message
- type
- priority
- channels
- createdAt

Entities:
User
Notification
DeliveryTask
UserPreference

Relationships:
User -> Notifications
Notification -> DeliveryTasks
User -> UserPreference

Interfaces:
NotificationHandler
- EmailHandler
- SMSHandler
- PushHandler
- InAppHandler

Classes:
NotificationController
PreferenceController
NotificationService
PreferenceService
DeliveryService
NotificationConsumer
DeliveryWorker
NotificationRepository
PreferenceRepository
DeliveryTaskRepository
NotificationHandlerFactory

DB Schema:
notifications(id, user_id, type, priority, title, message, is_read, created_at, read_at)

delivery_tasks(id, notification_id, channel, status, retry_count, next_retry_at, error)

user_preferences(user_id, email_enabled, sms_enabled, push_enabled, in_app_enabled, muted_types)

Core Flow:
Producer service publishes NotificationEvent
NotificationConsumer consumes event
NotificationService validates event
Fetch UserPreference
Create Notification
Create DeliveryTask per channel
Worker picks DeliveryTask
Factory returns correct NotificationHandler
Handler sends notification
Update task status
Retry failed task
Move to DLQ after max retries

Patterns:
- Strategy Pattern for handlers
- Factory Pattern for handler creation
- Repository Pattern for DB abstraction
- Observer/Event Pattern for Kafka event flow

Interview line:
“Request DTOs are API contracts. Entities are domain models. NotificationEvent is for async inter-service communication. REST is used for user-facing APIs, while Kafka is preferred internally because notification delivery is asynchronous, retryable, and should not block the source service.”
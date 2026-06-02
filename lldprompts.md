I have a 45-minute Low Level Design interview.

Give me a complete LLD answer for: <PROBLEM_NAME>

Follow this structure:

1. Requirements — 5 min
   - Functional requirements
   - Non-functional requirements
   - Out of scope 

2. APIs / Entry Points — 5 min
   - REST APIs
   - Internal APIs/events
   - Request DTOs keep main dto only 

3. Entities & Relationships — 8 min
   - Core entities
   - Enums
   - Relationships

4. Class Design — 10–12 min
   - First show the layering:
     Domain Models -> Repositories -> Services -> Controllers / Client Code
   - Controllers
   - Services
   - Interfaces
   - Handlers/strategies
   - Factory classes
   - Repositories
   - Workers/consumers

5. DB Schema — 5 min
   - Tables
   - Important columns
   - Indexes

6. Core Flow / Pseudocode — 7 min
   - Happy path
   - Failure cases
   - Retry handling
   - Idempotency/concurrency

7. Extensibility — 3 min
   - Design patterns
   - Future changes

Design rule:
- Keep domain models as simple state + behavior objects.
- Keep repositories responsible only for storage/index lookups.
- Keep services responsible for business rules, validation, orchestration, and transactions.
- Keep controllers/client code thin. They should call services, not contain business logic.
- Use strategies only when behavior genuinely varies, such as pricing, fine calculation, assignment, ranking, payment, notification handlers, or discount calculation.
- Use factory only when selecting an implementation from a type/mode.
- Use locks in services/entities where shared mutable state can race.
- Prefer in-memory repositories for machine coding, but describe DB schema in LLD.

Default component blueprint:

Domain:
- Core entities
- Enums
- Value objects / request objects if needed

Repository:
- EntityRepository
- Query indexes for frequent lookups
- No business logic

Service:
- SearchService / MatchingService / BookingService / PaymentService etc.
- Validation
- State transitions
- Concurrency/recheck inside lock

Controller / Client:
- Thin entry point
- Converts input to service calls
- Prints/demo output

Example layering for rental/booking systems:

Domain:
- Vehicle / Resource / Seat / Slot
- Booking / Reservation
- User
- PricingStrategy
- FineStrategy
- PaymentModule

Repository:
- VehicleRepository / ResourceRepository
- BookingRepository

Service:
- SearchService
- BookingService / RentalService
- AvailabilityService if availability logic is reusable

Controller:
- RentalController / BookingController
- Main demo or test driver

Interview line:
“I separate domain, repository, service, and controller responsibilities. Repositories only store and query data. Services contain business logic and state transitions. Controllers are thin wrappers. Strategies are used only for behavior that is expected to vary.”

Use this Notification System example as reference:

Problem:
Design a Notification Center.

Requirements:
- Create notifications
- Fetch user notifications
- Mark notification as read/unread
- Filter by type, priority, status
- Support user preferences
- Support channels: Email, SMS, Push, In-App
- Async delivery using Kafka
- Retry failed delivery and move to DLQ after max retries

REST APIs:
POST   /notifications
GET    /notifications?userId=&type=&status=&priority=
GET    /notifications/{id}
PATCH  /notifications/{id}/read
PATCH  /notifications/{id}/unread
DELETE /notifications/{id}

GET    /preferences/{userId}
PUT    /preferences/{userId}

Internal Event:
Kafka topic: notification-events

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

Interfaces:
NotificationHandler
- EmailHandler
- SMSHandler
- PushHandler
- InAppHandler

Classes: add controller if really needed
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
notifications
- id
- user_id
- type
- priority
- title
- message
- is_read
- created_at
- read_at

delivery_tasks
- id
- notification_id
- channel
- status
- retry_count
- next_retry_at
- error

user_preferences
- user_id
- email_enabled
- sms_enabled
- push_enabled
- in_app_enabled
- muted_types

Core Flow:
Service publishes NotificationEvent to Kafka
NotificationConsumer consumes event
NotificationService validates event
Fetch UserPreference
Create Notification
Create DeliveryTask per allowed channel
DeliveryWorker picks task
NotificationHandlerFactory returns correct handler
Handler sends notification
Update task status
Retry failed tasks
Move to DLQ after max retries

Patterns:
- Strategy Pattern for handlers
- Factory Pattern for handler creation
- Repository Pattern for DB layer
- Observer/Event Pattern for async notification events

Interview line:
“Request DTOs are API contracts. Entities are domain/persistence models. NotificationEvent is used for async inter-service communication. For user-facing APIs I use REST, but for internal service-to-notification communication I prefer Kafka because delivery is async, retryable, and should not block the source service.”

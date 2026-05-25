You are in a 50-minute High Level Design interview.

Problem: <PROBLEM_NAME>

Follow the Hello Interview framework in detail:

1. Requirements — 5 mins
2. Core Entities — 2–3 mins
3. API / System Interface — 5 mins
4. Optional Data Flow — 3–5 mins
5. High-Level Design — 10–15 mins
6. Deep Dives — 10–15 mins
7. Tradeoffs + Closing — 2–3 mins

━━━━━━━━━━━━━━━━━━━━
1. STARTING LINE
━━━━━━━━━━━━━━━━━━━━

Start with:

“Let me first clarify requirements, define core entities and APIs, then build a simple end-to-end design. After that, I’ll deep dive into scalability, consistency, failure handling, and tradeoffs.”

━━━━━━━━━━━━━━━━━━━━
2. REQUIREMENTS — 5 mins
━━━━━━━━━━━━━━━━━━━━

Functional requirements:
- Pick top 3–4 only.
- Keep extra features below the line.

Ask:
- What are the main user actions?
- Is this read-heavy or write-heavy?
- Real-time or async acceptable?
- What is out of scope?

Non-functional requirements:
Use SCALE-FDC:

S — Scalability
C — CAP / consistency choice
A — Availability
L — Latency
E — Environment constraints
F — Fault tolerance
D — Durability
C — Compliance / security

Also mention:
- observability
- data privacy
- rate limiting

Capacity estimation:
Do only if it affects design.

Say:
“I’ll skip detailed math upfront and calculate only where it impacts architecture decisions.”

━━━━━━━━━━━━━━━━━━━━
3. CORE ENTITIES — 2–3 mins
━━━━━━━━━━━━━━━━━━━━

List the core nouns/resources.

Do not over-model.

Example Calendar:
- User
- Calendar
- EventSeries
- EventInstance
- RSVP
- Reminder
- UserEventIndex

Example Uber:
- Rider
- Driver
- Ride
- Fare
- Location

Mention:
“These are first-draft entities; I’ll refine fields as the architecture evolves.”

━━━━━━━━━━━━━━━━━━━━
4. API / SYSTEM INTERFACE — 5 mins
━━━━━━━━━━━━━━━━━━━━

Define API before architecture.

Default to REST unless there is a reason for:
- GraphQL for flexible client queries
- gRPC for internal low-latency service calls
- WebSocket/SSE for real-time updates

Important:
- userId should come from auth token
- server should generate timestamps
- do not trust client-provided price/status/userId

Example Calendar APIs:

POST   /events
PATCH  /events/{eventId}
DELETE /events/{eventId}
GET    /users/me/events?start=&end=
POST   /events/{eventId}/rsvp

Example Uber APIs:

POST /fare
POST /rides
POST /drivers/location
PATCH /rides/{rideId}

━━━━━━━━━━━━━━━━━━━━
5. OPTIONAL DATA FLOW — 3–5 mins
━━━━━━━━━━━━━━━━━━━━

Use this when system has a pipeline or async workflow.

Calendar write flow:
Create Event
 -> Store in Postgres
 -> Outbox / CDC
 -> Kafka
 -> Index workers
 -> Notification scheduler

Notification flow:
Producer service
 -> Kafka
 -> Consumer
 -> DeliveryTask
 -> Worker
 -> Provider

Booking flow:
Search
 -> Lock Resource
 -> Recheck Availability
 -> Reserve
 -> Payment
 -> Confirm

━━━━━━━━━━━━━━━━━━━━
6. HIGH-LEVEL DESIGN — 10–15 mins
━━━━━━━━━━━━━━━━━━━━

First build a simple working system.

Generic architecture:

Client
 -> API Gateway
 -> Service
 -> DB source of truth
 -> Cache / Queue / Search Index if needed
 -> Response

Then add async components only where needed.

For event-driven systems:

Client
 -> API Gateway
 -> Write Service
 -> Postgres source of truth
 -> Outbox Table / CDC
 -> Kafka
 -> Workers
 -> Read Model / Index
 -> Notification System

While drawing, explain:
- which service owns writes
- which DB is source of truth
- which components are async
- what state changes on each request
- what returns to the client immediately
- what happens later in workers

Do not overcomplicate before basic flow works.

━━━━━━━━━━━━━━━━━━━━
7. DATA MODEL — 5 mins
━━━━━━━━━━━━━━━━━━━━

Define only important tables/fields.

Example Calendar:

events
- event_id
- organizer_id
- title
- timezone
- recurrence_rule
- created_at

event_instances
- instance_id
- event_id
- start_time
- end_time
- status

user_event_index
- user_id
- instance_id
- start_time
- metadata

rsvp
- user_id
- event_id
- status

reminders
- user_id
- instance_id
- remind_at
- status

Mention indexes:

events:
- organizer_id
- event_id

user_event_index:
- user_id + start_time

reminders:
- remind_at + status

━━━━━━━━━━━━━━━━━━━━
8. DEEP DIVES — 10–15 mins
━━━━━━━━━━━━━━━━━━━━

For SSE level, proactively pick 2–3 deep dives.

A. Scaling Reads
- cache
- read replicas
- denormalized read models
- pagination
- partition by user_id / org_id
- avoid scatter-gather

B. Scaling Writes
- Kafka buffering
- async workers
- batching
- sharding
- backpressure

C. Consistency
- DB is source of truth
- read model is eventually consistent
- use outbox/CDC to avoid lost events
- strong consistency only for correctness-critical paths

D. Concurrency / Contention
- optimistic locking
- row-level locks
- distributed locks only if needed
- idempotency keys
- recheck inside transaction/lock

E. Reliability
- retries with exponential backoff
- DLQ
- idempotent consumers
- replay from Kafka
- no assumption of exactly-once delivery

F. Large Fanout
- fanout-on-write
- fanout-on-read
- hybrid fanout
- async fanout workers
- batching

G. Real-time Updates
- WebSocket
- SSE
- push notification
- polling fallback

H. Search / Indexing
- Elasticsearch/OpenSearch for text search
- DynamoDB/Cassandra for user-time-range access
- materialized views for read-heavy flows

I. Observability
- p95/p99 latency
- error rate
- queue lag
- retry count
- DLQ size
- consumer lag
- tracing
- structured logs

━━━━━━━━━━━━━━━━━━━━
9. TRADEOFFS — 3 mins
━━━━━━━━━━━━━━━━━━━━

Always say tradeoffs.

Examples:

Postgres:
+ strong consistency
+ good transactions
- harder to scale writes globally

Kafka:
+ async fanout
+ replay
+ decoupling
- eventual consistency
- operational complexity

Cache:
+ low latency
- stale data risk
- invalidation complexity

Denormalized read model:
+ fast reads
- duplicate data
- async consistency

Distributed locks:
+ protects critical section
- complexity
- failure modes

━━━━━━━━━━━━━━━━━━━━
10. LAST 2–3 MINS CLOSING
━━━━━━━━━━━━━━━━━━━━

Close with:

“This design starts with a simple source-of-truth write path, then scales reads using denormalized indexes and caching. Expensive workflows are moved async through Kafka and workers. Correctness is handled using idempotency, locking where needed, retries, and DLQs. The system is horizontally scalable, observable, and fault tolerant.”

━━━━━━━━━━━━━━━━━━━━
11. CALENDAR SERVICE EXAMPLE
━━━━━━━━━━━━━━━━━━━━

Problem:
Design Calendar Service.

Functional:
- Create/update/delete events
- One-time and recurring events
- Invite users and RSVP
- View calendar by time range
- Reminder before event

Non-functional:
- Read-heavy
- Low latency reads
- Strong consistency for event writes
- Eventual consistency acceptable for read index
- Reliable notifications
- No duplicate reminders

Entities:
- User
- EventSeries
- EventInstance
- RSVP
- UserEventIndex
- NotificationSchedule

APIs:
POST   /events
PATCH  /events/{eventId}
PATCH  /events/{eventId}/instances/{instanceId}
DELETE /events/{eventId}
GET    /users/me/events?start=&end=
POST   /events/{eventId}/rsvp

Architecture:
Client
 -> API Gateway
 -> Event Write Service
 -> Postgres source of truth
 -> Outbox / CDC
 -> Kafka
 -> Index Workers
 -> DynamoDB UserEventIndex
 -> Calendar Read Service
 -> Cache
 -> Client

Notification flow:
Event changes
 -> Kafka
 -> Notification Scheduler
 -> SQS delayed queue
 -> Notification Workers
 -> Email/SMS/Push

Data model:
events(event_id, organizer_id, title, timezone, recurrence_rule)
event_instances(instance_id, event_id, start_time, end_time, status)
user_event_index(user_id, instance_id, start_time, metadata)
rsvp(user_id, event_id, status)
notification_schedule(user_id, instance_id, remind_at, status)

Deep dives:
1. Read optimization:
   - Use UserEventIndex partitioned by user_id
   - Sort by start_time
   - Avoid joining events, RSVP, attendees on read path

2. Recurrence:
   - Store recurrence rule in EventSeries
   - Materialize instances for next 90 days
   - Backfill future instances with background workers

3. Conflict detection:
   - Query UserEventIndex for overlapping events
   - Return warning, not rejection, unless product requires strict blocking

4. Notification reliability:
   - Use delayed queue or reminder scheduler
   - Idempotency key: user_id + instance_id + remind_at
   - Retry failures
   - DLQ after max retries

5. Consistency:
   - Postgres is source of truth
   - UserEventIndex is eventually consistent
   - Outbox/CDC prevents lost events

6. Scaling:
   - Read path partitioned by user_id
   - Write path sharded by event_id/org_id if needed
   - Kafka partitions by event_id or user_id
   - Workers horizontally scalable

7. Observability:
   - reminder delay
   - missed reminders
   - duplicate reminder count
   - read latency
   - Kafka consumer lag
   - failed indexing events

Strong interview line:
“Postgres is my source of truth. DynamoDB/UserEventIndex is a denormalized read model optimized for low-latency calendar reads. Kafka decouples event writes from indexing and notification scheduling. All consumers are idempotent, and notifications use retry plus DLQ to avoid data loss.”

━━━━━━━━━━━━━━━━━━━━
12. UBER / RIDE SHARING EXAMPLE
━━━━━━━━━━━━━━━━━━━━

Problem:
Design Uber / Ride Sharing Service.

Functional Requirements:
- Rider can get fare estimate
- Rider can request ride
- Match nearby available driver
- Driver can accept/reject ride
- Real-time driver location updates
- Track ride status

Non-functional Requirements:
- Match latency < 1 minute
- Strong consistency for ride assignment
- High write throughput for driver locations
- High availability
- Real-time updates
- Handle burst traffic during events

Core Entities:
- Rider
- Driver
- Ride
- FareEstimate
- DriverLocation
- DriverAvailability
- RideRequest

APIs:

POST /fare
Body:
{
  pickupLocation,
  destination
}

POST /rides
Body:
{
  fareEstimateId
}

POST /drivers/location
Body:
{
  lat,
  long
}

PATCH /rides/{rideId}
Body:
{
  action: ACCEPT | REJECT
}

GET /rides/{rideId}

Architecture:

Rider App
    ↓
API Gateway
    ↓
Ride Service
    ↓
Ride DB (Postgres)

Driver App
    ↓
Location Service
    ↓
Redis GeoSpatial / Location Store

Ride Request
    ↓
Ride Matching Service
    ↓
Nearby Driver Search
    ↓
Notification Service
    ↓
Driver Push Notification

Ride Acceptance
    ↓
Ride Service
    ↓
Update Ride State

Core Flow:

1. Rider requests fare estimate
2. Ride Service calculates fare
3. Rider confirms ride
4. Ride created with REQUESTED state
5. Matching service finds nearby drivers
6. Notification sent to top ranked driver
7. Driver accepts/rejects
8. Ride status updated
9. Other pending requests cancelled

Data Model:

rides
- ride_id
- rider_id
- driver_id
- pickup
- destination
- status
- fare
- created_at

drivers
- driver_id
- status
- vehicle_type
- rating

driver_locations
- driver_id
- lat
- long
- updated_at

fare_estimates
- estimate_id
- pickup
- destination
- estimated_fare
- eta

Deep Dives:

1. Driver Location Scaling

Problem:
Millions of driver updates every few seconds.

Solution:
- Redis Geospatial index
- Geohash partitioning
- TTL on stale driver locations
- Batch updates
- Client-side throttling

Strong line:
“Location writes are extremely high throughput, so I separate location storage from transactional ride storage.”

2. Nearby Driver Search

Use:
- Redis GEOSEARCH
OR
- Elasticsearch geo queries
OR
- Geohash buckets

Mention:
Avoid full DB scans.

3. Ride Matching Consistency

Requirement:
One driver should not receive multiple ride assignments.

Solution:
- Distributed lock OR transactional update
- Driver state transition:
  AVAILABLE -> RESERVED -> ON_TRIP

Flow:
1. Lock driver
2. Recheck availability
3. Assign ride
4. Commit
5. Release lock

Strong line:
“I recheck driver availability inside the lock because stale reads before locking are unsafe.”

4. Peak Traffic Handling

Problem:
Concert/stadium surge traffic.

Solution:
- Kafka queue buffering
- Async ride matching workers
- Backpressure
- Regional partitioning
- Queue-based retry

5. Driver Timeout Handling

Problem:
Driver ignores request.

Solution:
- Durable workflow / Temporal style orchestration
- 10-second timeout
- Retry next driver automatically

6. Real-Time Updates

Use:
- WebSockets
- Push notifications
- SSE fallback

7. Observability

Track:
- match latency
- queue lag
- ride assignment failures
- driver response timeout
- location update freshness
- failed notifications
- p95/p99 latency

Tradeoffs:

Redis Geo:
+ fast proximity search
+ high write throughput
- eventual consistency
- stale location risk

Postgres:
+ transactional correctness
+ strong consistency
- not suitable for massive geo updates

Kafka:
+ buffering
+ retries
+ replay
- operational complexity

Strong interview lines:

“Ride matching is correctness critical, so assignment consistency matters more than availability.”

“Location updates are eventually consistent, but ride assignment requires strong consistency.”

“I separate transactional ride state from high-frequency location storage.”

“Kafka decouples ride creation from matching and notification workflows.”

“Redis Geo is optimized for proximity search, while Postgres remains the source of truth for rides.”

“Workers and consumers are idempotent using ride_id and request_id.”

Final Closing:

“This design separates transactional correctness from high-throughput geo workloads. Ride state is strongly consistent in Postgres, while driver location and matching are optimized for low-latency distributed reads using Redis Geo and async workers. The system scales horizontally using Kafka, worker pools, partitioning, retries, and idempotent processing.”
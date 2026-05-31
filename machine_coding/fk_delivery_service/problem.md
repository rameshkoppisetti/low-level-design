# FK Delivery Service

## Overview

Build an application where delivery agents pick up orders and deliver them to a pincode.

## Core Requirements

- Users can create orders with:
  - order name
  - destination pincode
- Admin can create delivery agents.
- Each agent can deliver to a configured pincode.
- Multiple agents can be registered for the same pincode.
- A driver function should execute the delivery process and print pickup/delivery metrics.

## Bonus Scope

- Allow an agent to deliver to multiple pincodes.
- Allow scheduled orders with delivery duration.
- Print pickup and delivery completion times for scheduled orders.

## Sample

```text
createOrder(Order A, 560087)
createOrder(Order B, 560088)
createOrder(Order C, 560089)
createOrder(Order D, 560087)

createAgent(AgentA, 560087)
createAgent(AgentB, 560088)
createAgent(AgentC, 560089)
```

Expected execution:

```text
Agent A has picked up Order A
Agent A has delivered Order A to 560087
Agent B has picked up Order B
Agent B has delivered Order B to 560088
Agent C has picked up Order C
Agent C has delivered Order C to 560089
Agent A has picked up Order D
Agent A has delivered Order D to 560087
```


# Flipkart Payment Wallet

Implement an in-memory Flipkart payment wallet system.

## Requirements

- Users are registered before using the wallet.
- Users can load money into their wallet from sources like UPI, credit card, debit card.
- Load amount must be greater than `0`.
- Users can send money to another registered user.
- Send amount must be greater than `0`.
- Sender must have sufficient balance.
- Each successful load/send operation receives a caller-provided timestamp.
- Wallet balance should consider credit and debit transactions.
- Users can fetch transaction history:
  - Sort by `time` or `amount`.
  - Filter by `send`, `receive`, or `all`.
- In-memory only. No database or external payment integration.

## Method Contracts

```text
FlipkartWallet(List<String> registeredUserIds)

boolean loadMoney(String userId, long amount, String source, long timestamp)
boolean sendMoney(String fromUserId, String toUserId, long amount, long timestamp)
long getBalance(String userId)
List<String> getTransactionHistory(String userId, String sortBy, String filterBy)
```

## Rules

- `getBalance(invalidUser)` returns `-1`.
- `getTransactionHistory(invalidUser, ...)` returns an empty list.
- Unknown/invalid inputs should fail gracefully.
- A successful send creates two transaction records:
  - Sender: `SEND`
  - Receiver: `RECEIVE`
- Output encoding:

```text
time=<timestamp>|type=<LOAD|SEND|RECEIVE>|counterparty=<value>|amount=<amount>
```

## Sorting And Filtering

- `sortBy="time"`: ascending timestamp. Stable for same timestamp.
- `sortBy="amount"`: descending amount. Stable for same amount.
- `filterBy="send"`: only send transactions.
- `filterBy="receive"`: only receive transactions.
- `filterBy="all"`: load, send, receive.

## Sample

```text
loadMoney("user-1", 500, "UPI", 1000) -> true
sendMoney("user-1", "user-2", 200, 1010) -> true
sendMoney("user-1", "user-2", 400, 1020) -> false
getBalance("user-1") -> 300
getBalance("user-2") -> 200
```

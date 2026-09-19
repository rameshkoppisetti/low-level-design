def update_status(invoice, delta):
    invoice["paid_amount"] += delta

    remaining = invoice["invoice_amount"] - invoice["paid_amount"]

    if remaining == 0:
        invoice["status"] = "PAID"
    elif remaining < 0:
        invoice["status"] = "OVERPAID"
    elif invoice["paid_amount"] == 0:
        invoice["status"] = "UNPAID"
    else:
        invoice["status"] = "PARTIALLY_PAID"


def reconcile_invoices(events):
    invoices = {}
    payments = {}
    refunds = {}

    for event in events:
        parts = event.split()
        event_type = parts[0]

        if event_type == "CREATE":
            _, invoice_id, merchant_id, amount = parts

            invoices[invoice_id] = {
                "merchant": merchant_id,
                "invoice_amount": int(amount),
                "paid_amount": 0,
                "status": "UNPAID",
            }

        elif event_type == "PAY":
            _, payment_id, invoice_id, amount = parts
            amount = int(amount)

            if invoice_id not in invoices:
                continue

            # Idempotent payment
            if payment_id in payments:
                continue

            invoice = invoices[invoice_id]
            update_status(invoice, amount)

            payments[payment_id] = {
                "invoice": invoice_id,
                "amount": amount,
                "refunded": 0,
            }

        elif event_type == "REFUND":
            _, refund_id, payment_id, amount = parts
            amount = int(amount)

            if payment_id not in payments:
                continue

            # Idempotent refund
            if refund_id in refunds:
                continue

            payment = payments[payment_id]

            remaining_refundable = payment["amount"] - payment["refunded"]
            refund = min(amount, remaining_refundable)

            if refund == 0:
                continue

            payment["refunded"] += refund

            invoice = invoices[payment["invoice"]]
            update_status(invoice, -refund)

            refunds[refund_id] = {
                "payment": payment_id,
                "amount": refund,
            }

    result = {}

    for invoice_id, invoice in invoices.items():
        result[invoice_id] = {
            "paid_amount": invoice["paid_amount"],
            "outstanding_amount": invoice["invoice_amount"] - invoice["paid_amount"],
            "status": invoice["status"],
        }

    return result

events = [
    "CREATE inv_1 m1 1000",
    "PAY pay_1 inv_1 600",
    "PAY pay_2 inv_1 300",
    "REFUND ref_1 pay_1 200",
]

print(reconcile_invoices(events))

events = [
    "CREATE inv_1 m1 1000",
    "PAY pay_1 inv_1 500",
    "REFUND ref_1 pay_1 300",
    "REFUND ref_2 pay_1 300",   # only refunds remaining 200
    "REFUND ref_1 pay_1 50",    # duplicate ignored
    "REFUND ref_3 unknown 100", # unknown payment ignored
]

print(reconcile_invoices(events))

# Deliverable 21/22 — Queue burst handling and poison-message policy

Owner: C + D
Maps to: Deliverables 21 and 22

## Goal
Provide a queue that absorbs ingress spikes, validates read/write behavior and defines a poison-message policy for transaction processing failures.

## Implementation notes
- The ingest queue is created during provisioning as `q-incoming-transactions`.
- The application publishes transaction IDs into the queue via `storage.enqueue_transaction`.
- The queue consumer reads the next message, processes it, and removes the message after a successful completion.
- A poison-message policy is implemented with a second queue, `q-poison-transactions`, for messages that fail repeatedly or that cannot be processed.
- The policy is documented as: move the message to the poison queue after repeated failures, because Azure Queue Storage has no native dead-letter queue like Service Bus.
- The consumer uses a visibility timeout of 30 seconds to emulate the standard Azure Storage queue behavior: if the consumer crashes before completing the work, the message becomes visible again.

## Delivery-guarantee scenarios
1. Consumer reads and crashes before ack
   - The message remains invisible for the visibility timeout window and then becomes visible again for reprocessing.
2. Message fails repeatedly
   - The consumer moves the message to the poison queue after the configured policy threshold is reached.
3. Queue grows faster than it drains
   - The queue absorbs burst traffic and the operator can monitor `ApproximateMessagesCount` to determine whether more consumers are required in Week 3.

## Verification steps
1. Create the infrastructure with `infra/provision.sh`.
2. Enqueue a transaction and confirm it can be dequeued and processed.
3. Run a failing handler and confirm the message is moved to the poison queue.
4. Inspect queue metrics (`ApproximateMessagesCount`) while sending bursts to confirm buffering behavior.

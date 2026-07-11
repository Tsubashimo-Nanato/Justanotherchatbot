# Release Notes

## 0.10.0 - NapCat / OneBot transport

The QQ boundary now uses NapCat over OneBot 11 instead of controlling QQNT windows.

### Changes

- Receive group messages through reverse WebSocket events with stable OneBot message IDs.
- Persist transport IDs so reconnects, history backfill, and duplicate deliveries cannot process a message twice.
- Send normal and quoted group replies through OneBot actions and retain returned outbound message IDs.
- Restore recent group history as context on startup without replying to historical messages.
- Resolve the target group once and persist its ID; group names remain display metadata.
- Replace QQ window controls in the debug UI with connection, group, event, and send diagnostics.
- Remove the QQ UI adapter, polling loop, coordinate input, focus handling, and UI automation dependencies.

### Deployment

NapCat is an external runtime and is not bundled with this repository. Configure its reverse WebSocket endpoint as `ws://127.0.0.1:8765/onebot/v11/ws`, set the same access token in the local environment, then select the target group from the debug UI.

## 0.02 - Final QQ window adapter release

This archival release is the last version that controls the QQNT window directly. It is retained as a reproducible rollback point, but its message detection and send behavior depend on QQNT UI details and are not the active architecture.

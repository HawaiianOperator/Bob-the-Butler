# UNO Q receiver (prepared for the next hardware session)

`bob_service.py` runs on the **Debian/Linux side of UNO Q**, not as a microcontroller sketch. It uses Python 3's standard library and binds only to `127.0.0.1:8765` on the board. The Windows app reaches that socket over a physical USB ADB transport. Wi-Fi ADB devices are not offered by Bob.

The receiver and boot service have been installed and verified on a physical UNO Q running Debian 13.2. For another board, complete initial setup in Arduino App Lab and install this folder's boot service. Keeping Arduino App Lab open (or running the official platform-tools ADB server) provides the laptop's local ADB server on port 5037. Bob talks to that server directly; it does not need to ship an `adb.exe` binary.

## Start automatically at boot

Copy this folder onto UNO Q. From Windows PowerShell in the platform-tools folder:

```powershell
.\adb.exe -d push "C:\Users\rayan\Documents\ChatGPT\ESP 32 based keyboard\uno-q" /tmp/bob-uno-q
.\adb.exe -d shell
```

In the board's shell, stop any manually started receiver first, then run:

```sh
sudo python3 /tmp/bob-uno-q/install_service.py
```

The installer copies the receiver into persistent storage at `/opt/bob-the-butler/`, installs `bob-butler.service`, enables it at boot and starts it immediately. It verifies a live hello response. You can then close the terminal. Re-running the installer updates and restarts the same service.

The receiver runs as a systemd-managed unprivileged user. It starts without a desktop login, laptop connection or Wi-Fi, listens only on the board's loopback interface, and restarts after a crash. Booting the Q does **not** start a task or screen sharing: Bob still needs a USB connection and a newly submitted task.

Check or manage it from the board shell:

```sh
sudo systemctl status bob-butler --no-pager
sudo journalctl -u bob-butler -f
sudo systemctl restart bob-butler
# To stop it and turn off automatic startup:
sudo systemctl disable --now bob-butler
```

The installer has a `--dry-run` option that works on Windows too. The boot service was verified active and enabled after reboot on a physical UNO Q. Task receipts in both modes, a synthetic JPEG transfer and Stop were also tested over USB. AI and real desktop-sharing integration remain separate milestones.

The existing COM-port connection remains for ESP32 testing. Its old handshake sketch does not implement tasks or screen frames, so Bob will connect but keep task submission disabled until a compatible service is present.

## What this service does

- Replies to the versioned hello and heartbeat.
- Advertises `tasks_v1`, `screen_v1` and `actions_v1` capabilities, and explicitly reports `ai_ready: false`.
- Receives a task with a unique ID, selected mode (`do` or `guide`), and text; replies `task_received` with the same ID.
- Receives small JPEG screen frames in ordered base64 chunks, checks total length and SHA-256, and acknowledges each completed frame.
- Keeps only the most recent frame in RAM. Screens are not written to disk.
- Drops task and frame references on Stop, a closed connection, an idle host heartbeat, or an eight-second session lease expiry.
- Sends metadata logs to Bob's Debug view. Task text and image payloads are not logged.

The optional `bob-planner` service runs the trained Qwen3-0.6B Q4_K_M tool planner locally. The pointer layer remains available: `Receiver.queue_action(kind, x, y, label)` accepts one move/click target at a time, with normalized primary-screen coordinates. The Windows widget's explicit Debug test uses this entry point and disables AI for that manual test session.

To install the trained planner, stage `bob-q4_k_m.gguf` and `bob-model-manifest.json` in `/home/arduino/bob-ai/`, with the pinned b11869 ARM runtime in `runtime/llama-b11869/`. Run `sudo python3 /home/arduino/bob-uno-q/install_service.py --with-ai`. The installer checks the checksum and enables both services at boot. Check `systemctl is-active bob-butler bob-planner`.

The `planner_v1` capability adds `planner_poll`, `planner_permit` (Auto only), and `planner_result`. Polling starts at most one background inference and returns a stable UUID for one validated tool. Stop and lease expiry discard late responses. A task can use at most 24 model steps. Planner logs contain tool names and timing without typed text.

Guide sessions display the target and wait for the user. Auto sessions request a fresh permit before moving/clicking the real Windows cursor. The Q never directly injects laptop input; the Windows executor enforces mode, task/frame IDs, freshness, Stop and physical takeover. Stop clears queued/in-flight actions as well as screen buffers. Results are acknowledged idempotently; completed action IDs are bounded to 512 per task.

## Wire protocol

UTF-8 JSON, one object per newline. Messages use `protocol: 1` and a request `nonce`; replies echo that nonce and include `device: "device-companion"`. Task messages also echo `task_id`; frame replies echo `frame_id`. Limits: 8,192-byte lines, 4,000-byte task text, 32,768-byte frames, 768 decoded bytes per chunk.

| Host request | Device response |
|---|---|
| `hello` | `hello_ack` with board, capabilities and AI status |
| `ping` with active `task_id`, or null when idle | `pong` |
| `task` with `task_id`, `mode`, `text` | `task_received` |
| `screen_begin` with `task_id`, `frame_id`, `size` | `screen_ready` |
| `screen_chunk` with IDs, zero-based `index`, base64 `data` | No response per chunk |
| `screen_end` with IDs and `sha256` | `screen_received` |
| `stop_task` with `task_id` | `task_stopped` |
| `test_action` with `task_id`, `kind`, normalized `x`, `y` | `action_queued` |
| `next_action` with task/frame IDs | `action` containing one target or null |
| `action_permit` with task/frame/action IDs (Auto only) | `action_permitted` |
| `action_result` with task/action IDs and status | `action_recorded` |

The receiver may send `log` messages before a reply, or an `error` with the request nonce. Stop is idempotent. Duplicate task requests with the same ID return the original receipt rather than starting another task. Late screen messages for stopped tasks are rejected.

This is a compatibility check, not cryptographic device authentication. The task layer has no shell or input-execution command.

## Test without hardware

```powershell
python -m unittest discover -s uno-q -p "test_*.py" -v
```

The tests use synthetic image bytes and loopback sockets. They do not capture your screen or require a connected board.

References: [Arduino Debian/ADB guide](https://docs.arduino.cc/tutorials/uno-q/debian-guide/), [ADB smart-socket services](https://android.googlesource.com/platform/packages/modules/adb/+/HEAD/docs/dev/services.md).

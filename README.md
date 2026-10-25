# Bob the Butler

A compact Windows desktop widget built with **React, TypeScript and Tauri 2**, with a Rust USB/session backend and a Python receiver prepared for the Arduino UNO Q.

## Run

Download `DeviceCompanion.exe` from the repository using GitHub's **Download raw file** button, then open it. The filename is retained for compatibility; the app is named Bob the Butler. Windows needs Microsoft Edge WebView2, normally present on Windows 10/11.

The light, rounded 360 × 300 widget opens near the bottom-right corner and stays above Chrome. Drag its header to move it. The device picker includes physically connected USB ADB boards and COM ports. For UNO Q, complete initial setup in Arduino App Lab and keep its ADB server running. Use **Debug → Check USB** for diagnostics.

The UNO Q receiver and trained Qwen3-0.6B Q4_K_M model are installed on the Q with boot services. Both task modes, image transfer, heartbeat correlation and Stop have USB protocol checks. A COM-only ESP32 with the old handshake sketch can connect but cannot start a task.

## Task and screen-sharing flow

1. Connect and verify the device. The service must advertise task and screen capabilities.
2. Choose **Do it for me** or **Guide me** inside the chat composer.
3. Enter a task and press Send. The UI explicitly states that sending starts primary-screen sharing.
4. Bob sends the task and mode to UNO Q and waits for its `task_received` acknowledgement.
5. Red corners/border and a small top-of-screen Stop / Esc popup appear. Only then does capture start.
6. Bob sends downscaled JPEG frames from the **primary monitor only**, up to 640 pixels wide and 32 KiB each. New frames are scheduled three seconds after the previous transfer; serial links may be slower. Each frame is acknowledged by the board.
7. Press **Escape anywhere**, click Stop in the popup/widget, disconnect, or close Bob to stop capture. Escape is checked by a native Windows monitor, independent of widget focus or board replies. In-flight bytes may finish reaching the board; a stop request and session lease prevent continuing the old session. Reconnecting does not resume sharing.

**Guide me:** a large blue overlay pointer marks the target. A pulsing blue circle means “click here.” You move/click the real cursor yourself; Bob observes your click near the target and acknowledges the step. The Debug view also has a manual **Step done** fallback. Guide mode does not inject input.

**Do it for me:** the same blue target appears briefly before Bob moves the real Windows cursor and, for a click action, sends one left click. Normal keyboard and mouse activity does not cancel Auto; press Escape to stop. Escape, Stop, disconnect and closing Bob stop both modes. Auto is disabled if native input cannot start.

**Local AI is enabled for Chrome tools.** For web searches, the Q model prepares the query once. The Q then sends one bounded step at a time: open Google, focus Chrome's search/address bar, type the query, press Enter, and verify the result title. Each step advances only after feedback; each Auto input needs a fresh USB permit. Routine search steps do not run another model inference. The widget and Stop popup show thinking time while query preparation runs. Guide displays instructions and waits for Step done followed by a return to Chrome. Press Escape or Stop to cancel Auto.

Screenshots are transferred to the Q in RAM, but the current language model does not interpret their pixels. The separate **Debug → pointer test** still provides explicit normalized move/click targets through `Receiver.queue_action()`. Those pointer requests are tied to an acknowledged frame and reject stale screens. Chrome typing and shortcuts use a separate bounded tool contract. No shell tool is exposed; arbitrary desktop vision is not implemented.

Debug is beside “Your device. Your control.” It opens bounded Laptop / UNO Q metadata logs inside the widget. No screenshot or prompt payloads are logged. The Q retains the latest frame in RAM only, and releases it when the session ends.

## Automated Windows build

`.github/workflows/windows.yml` runs on application or receiver changes pushed to `master`. It checks the Rust protocol/session helpers and Python receiver, builds the React frontend and Tauri Windows app, creates an NSIS installer, and uploads the Windows outputs as **Bob-the-Butler-Windows**. A successful push build also commits the new portable `DeviceCompanion.exe` to the root. Binary-only commits do not retrigger the workflow. Repository branch rules must allow that commit.

## Build locally

Install Node.js 22+, pnpm 11.25, stable Rust with the MSVC toolchain, Microsoft C++ Build Tools with Windows SDK, and WebView2. Run:

```powershell
.\build.ps1
```

Output: root `DeviceCompanion.exe`; installer under `src-tauri/target/release/bundle/nsis/`.

- Development: `pnpm install --frozen-lockfile`, then `pnpm tauri dev`.
- Browser preview: `pnpm dev` (USB/native controls require the desktop app).
- Frontend validation: `pnpm build`.
- Rust checks: `cargo test --manifest-path src-tauri/Cargo.toml`.
- Receiver checks: `python -m unittest discover -s uno-q -p "test_*.py" -v`.

macOS/Linux need platform implementations and testing for capture, overlays and Escape handling. This release targets Windows.

The original Python/Tkinter prototype (`app.py`, `protocol.py`, `requirements.txt`, `tests/`) is retained as a reference and is not bundled into the Tauri app.

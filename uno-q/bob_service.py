#!/usr/bin/env python3
"""USB receiver and asynchronous local planner. Desktop input stays on Windows."""
import argparse
import base64
import hashlib
import json
import os
import math
import uuid
import socket
import time
from pathlib import Path
from ai.planner import Planner
from ai.tool_plan import parse_tool

MAX_LINE = 8192
MAX_FRAME = 32768
LEASE_SECONDS = 8


class Receiver:
    def __init__(self):
        self.task = None
        self.frame = None
        self.last_frame = None  # One JPEG in RAM; never written to disk.
        self.last_seen = 0
        self.last_frame_id = None
        self.queued_action = None
        self.inflight_action = None
        self.completed_actions = set()
        self.planner = Planner()
        self.plan_step = None
        self.plan_count = 0
        self.ai_ready = Path('/opt/bob-the-butler/model/bob-q4_k_m.gguf').is_file()

    def stop(self):
        self.task = self.frame = self.last_frame = None
        self.last_frame_id = self.queued_action = self.inflight_action = None
        self.completed_actions.clear()
        self.planner.reset()
        self.plan_step = None
        self.plan_count = 0

    def expire(self):
        if self.task and time.monotonic() - self.last_seen > LEASE_SECONDS:
            self.stop()
            return True
        return False

    def handle(self, packet):
        if not isinstance(packet, dict) or packet.get('protocol') != 1:
            return []
        kind, nonce = packet.get('type'), packet.get('nonce')
        if not isinstance(nonce, str) or len(nonce) > 100:
            return []
        def reply(type_, **extra):
            return dict(type=type_, protocol=1, device='device-companion', nonce=nonce, **extra)
        def log(message):
            return dict(type='log', protocol=1, device='device-companion', message=message, level='info')
        self.expire()
        self.last_seen = time.monotonic()
        if kind == 'hello':
            return [reply('hello_ack', board='Arduino UNO Q', service_version='0.5.0',
                          capabilities=['tasks_v1', 'screen_v1', 'actions_v1', 'planner_v1'], ai_ready=self.ai_ready, process_id=os.getpid())]
        if kind == 'ping':
            if self.task and packet.get('task_id') != self.task['id']:
                self.stop()
                return [log('Host session is inactive. Screen buffers cleared.'), reply('pong', task_id=packet.get('task_id'))]
            return [reply('pong', task_id=packet.get('task_id'))]
        if kind == 'task':
            task_id, mode, text = packet.get('task_id'), packet.get('mode'), packet.get('text')
            if (not isinstance(task_id, str) or not 1 <= len(task_id) <= 100
                    or mode not in ('do', 'guide') or not isinstance(text, str)
                    or not text.strip() or len(text.encode('utf-8')) > 4000):
                return [reply('error', message='Invalid task or mode.')]
            if self.task and self.task['id'] == task_id:
                return [reply('task_received', task_id=task_id, mode=mode, ai_ready=self.ai_ready)]
            if self.task:
                return [reply('error', message='Stop the current task before starting another.')]
            self.task = dict(id=task_id, mode=mode, text=text, planner=packet.get('planner', True) is True)
            return [log(f'Task received ({mode} mode). Local planner ready: {self.ai_ready}.'),
                    reply('task_received', task_id=task_id, mode=mode, ai_ready=self.ai_ready)]
        if kind == 'stop_task':
            task_id = packet.get('task_id')
            if self.task and task_id != self.task['id']:
                return [reply('error', message='Task ID does not match.')]
            self.stop()
            return [log('Session stopped. Screen buffers cleared.'), reply('task_stopped', task_id=task_id)]
        if not self.task or packet.get('task_id') != self.task['id']:
            return [reply('error', message='No matching active task.')]
        if kind == 'planner_poll':
            if not self.ai_ready or not self.task['planner']:
                return [reply('planner_step', task_id=self.task['id'], state='unavailable')]
            if self.plan_count >= 24:
                return [reply('planner_step', task_id=self.task['id'], state='error', message='Planner step limit reached.')]
            if self.plan_step is None:
                result = self.planner.take()
                if result is None:
                    observation = packet.get('observation')
                    if not isinstance(observation, dict) or len(json.dumps(observation)) > 2000:
                        return [reply('error', message='Invalid planner observation.')]
                    self.planner.start(self.task['text'], observation)
                    result = self.planner.take()
                if result:
                    if 'error' in result:
                        return [reply('planner_step', task_id=self.task['id'], state='error', message=result['error'])]
                    plan = parse_tool(result['plan'])
                    self.plan_step = dict(id=str(uuid.uuid4()), plan=plan, seconds=result['seconds'])
                    self.plan_count += 1
            return [reply('planner_step', task_id=self.task['id'], state='ready' if self.plan_step else 'thinking', step=self.plan_step)]
        if kind == 'planner_permit':
            if not self.plan_step or packet.get('step_id') != self.plan_step['id'] or self.task['mode'] != 'do':
                return [reply('error', message='Planner step is no longer authorized.')]
            return [reply('planner_permitted', task_id=self.task['id'], step_id=self.plan_step['id'])]
        if kind == 'planner_result':
            if not self.plan_step or packet.get('step_id') != self.plan_step['id']:
                return [reply('error', message='Stale planner result.')]
            result = packet.get('result')
            if (not isinstance(result, dict) or not isinstance(result.get('ok'), bool)
                    or len(json.dumps(result)) > 2000):
                return [reply('error', message='Invalid planner result.')]
            self.planner.record(self.plan_step['plan'], result)
            self.plan_step = None
            return [reply('planner_recorded', task_id=self.task['id'])]
        if kind == 'test_action':
            try:
                action = self.queue_action(packet.get('kind'), packet.get('x'), packet.get('y'), 'Click here' if packet.get('kind') == 'click' else 'Move here')
            except ValueError as exc:
                return [reply('error', message=str(exc))]
            return [log(f"Manual {action['kind']} target queued in {self.task['mode']} mode."),
                    reply('action_queued', task_id=self.task['id'])]
        if kind == 'next_action':
            if self.queued_action and not self.inflight_action:
                self.inflight_action, self.queued_action = self.queued_action, None
            return [reply('action', task_id=self.task['id'], frame_id=packet.get('frame_id'), action=self.inflight_action)]
        if kind == 'action_permit':
            action = self.inflight_action
            if (not action or action['action_id'] != packet.get('action_id')
                    or action['frame_id'] != packet.get('frame_id') or self.task['mode'] != 'do'):
                return [reply('error', message='Auto action is no longer authorized.')]
            return [reply('action_permitted', task_id=self.task['id'], frame_id=action['frame_id'])]
        if kind == 'action_result':
            action_id = packet.get('action_id')
            if not isinstance(action_id, str):
                return [reply('error', message='Invalid action ID.')]
            if action_id in self.completed_actions:
                return [reply('action_recorded', task_id=self.task['id'])]
            action = self.inflight_action
            if (not action or action['action_id'] != action_id
                    or packet.get('status') not in ('guided', 'executed', 'cancelled', 'error')):
                return [reply('error', message='Invalid or stale action result.')]
            if (packet['status'] == 'executed' and self.task['mode'] != 'do'
                    or packet['status'] == 'guided' and self.task['mode'] != 'guide'):
                return [reply('error', message='Action result does not match the session mode.')]
            self.completed_actions.add(action_id)
            self.inflight_action = None
            return [log(f"Pointer action {packet['status']}."), reply('action_recorded', task_id=self.task['id'])]
        if kind == 'screen_begin':
            size, frame_id = packet.get('size'), packet.get('frame_id')
            if not isinstance(size, int) or not 1 <= size <= MAX_FRAME or not isinstance(frame_id, str) or len(frame_id) > 100:
                return [reply('error', message='Invalid frame size or ID.')]
            self.frame = dict(id=frame_id, size=size, data=bytearray(), next=0)
            return [reply('screen_ready', frame_id=frame_id, task_id=self.task['id'])]
        if kind == 'screen_chunk':
            frame = self.frame
            if not frame or packet.get('frame_id') != frame['id'] or packet.get('index') != frame['next']:
                self.frame = None
                return [reply('error', message='Out-of-order screen chunk.')]
            try:
                payload = packet.get('data')
                if not isinstance(payload, str) or len(payload) > 1024:
                    raise ValueError('Oversized chunk')
                data = base64.b64decode(payload, validate=True)
            except (ValueError, TypeError):
                self.frame = None
                return [reply('error', message='Invalid screen chunk.')]
            if len(frame['data']) + len(data) > frame['size']:
                self.frame = None
                return [reply('error', message='Screen frame exceeded declared size.')]
            frame['data'].extend(data)
            frame['next'] += 1
            return []
        if kind == 'screen_end':
            frame = self.frame
            self.frame = None
            if (not frame or packet.get('frame_id') != frame['id']
                    or len(frame['data']) != frame['size']
                    or hashlib.sha256(frame['data']).hexdigest() != packet.get('sha256')):
                return [reply('error', message='Screen frame failed validation.')]
            self.last_frame = bytes(frame['data'])
            self.last_frame_id = frame['id']
            return [log(f'Screen frame received: {len(self.last_frame)} bytes (RAM only).'),
                    reply('screen_received', task_id=self.task['id'], frame_id=frame['id'])]
        return [reply('error', message='Unsupported message type.')]


    def queue_action(self, kind, x, y, label=''):
        """Future model integration point. No action is generated automatically yet."""
        if not self.task or not self.last_frame_id:
            raise ValueError('Share a screen frame before requesting a pointer target.')
        if self.queued_action or self.inflight_action:
            raise ValueError('Complete the current pointer step first.')
        if len(self.completed_actions) >= 512:
            raise ValueError('Start a new task before adding more pointer steps.')
        if (kind not in ('move', 'click') or type(x) not in (int, float) or type(y) not in (int, float)
                or not math.isfinite(x) or not math.isfinite(y) or not 0 <= x <= 1 or not 0 <= y <= 1):
            raise ValueError('Pointer target must be inside the primary screen.')
        action = dict(action_id=str(uuid.uuid4()), task_id=self.task['id'], frame_id=self.last_frame_id,
                      kind=kind, x=x, y=y, label=str(label)[:100])
        self.queued_action = action
        return action


def serve_connection(connection):
    receiver = Receiver()
    connection.settimeout(0.5)
    pending = bytearray()
    try:
        while True:
            if receiver.expire():
                print('Session lease expired; screen buffers cleared.', flush=True)
            try:
                data = connection.recv(4096)
            except socket.timeout:
                continue
            if not data:
                break
            pending.extend(data)
            while b'\n' in pending:
                line, _, pending = pending.partition(b'\n')
                if len(line) > MAX_LINE:
                    raise ValueError('Message too large')
                try:
                    packet = json.loads(line)
                except (ValueError, UnicodeError):
                    continue
                for response in receiver.handle(packet):
                    connection.sendall((json.dumps(response, separators=(',', ':')) + '\n').encode())
            if len(pending) > MAX_LINE:
                raise ValueError('Message too large')
    except (OSError, ValueError) as exc:
        print(f'Connection ended: {exc}', flush=True)
    finally:
        receiver.stop()
        connection.close()
        print('USB session closed; screen buffers cleared.', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    # Loopback only. The laptop reaches this socket through the USB ADB transport.
    with socket.socket() as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('127.0.0.1', args.port))
        server.listen(1)
        print(f'Bob receiver listening on 127.0.0.1:{args.port}; awaiting USB ADB connection.', flush=True)
        while True:
            connection, _ = server.accept()
            serve_connection(connection)  # One controller at a time.


if __name__ == '__main__':
    main()

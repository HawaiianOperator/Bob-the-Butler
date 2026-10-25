import base64
import hashlib
import json
import socket
import threading
import time
import unittest
from bob_service import Receiver, serve_connection


class ReceiverTests(unittest.TestCase):
    def setUp(self):
        self.receiver = Receiver()

    def send(self, type_, **kwargs):
        return self.receiver.handle(dict(type=type_, protocol=1, nonce='test', **kwargs))

    def task(self):
        return self.send('task', task_id='task-1', mode='guide', text='Open a document')

    def test_hello_declares_capabilities_without_claiming_ai(self):
        response = self.send('hello')[0]
        self.assertEqual(response['type'], 'hello_ack')
        self.assertEqual(response['nonce'], 'test')
        self.assertIn('screen_v1', response['capabilities'])
        self.assertFalse(response['ai_ready'])

    def test_heartbeat_echoes_task_id_required_by_windows_exchange(self):
        self.task()
        for mode in ('guide', 'do'):
            self.receiver.task['mode'] = mode
            response = self.send('ping', task_id='task-1')[-1]
            self.assertEqual(response['type'], 'pong')
            self.assertEqual(response['task_id'], 'task-1')
            self.assertIsNotNone(self.receiver.task)
        response = self.send('ping', task_id=None)[-1]
        self.assertIsNone(response['task_id'])
        self.assertIsNone(self.receiver.task)

    def test_task_receipt_is_idempotent_and_validates_mode(self):
        self.assertEqual(self.task()[-1]['type'], 'task_received')
        self.assertEqual(self.task()[-1]['type'], 'task_received')
        self.assertEqual(self.send('task', task_id='task-2', mode='guide', text='Other')[-1]['type'], 'error')
        self.send('stop_task', task_id='task-1')
        self.assertEqual(self.send('task', task_id='bad', mode='shell', text='Other')[-1]['type'], 'error')
        self.assertIsNone(self.receiver.task)

    def test_screen_chunks_validate_hash_and_stop_clears_memory(self):
        self.task()
        data = b'\xff\xd8fake-jpeg-for-transport-test\xff\xd9'
        self.assertEqual(self.send('screen_begin', task_id='task-1', frame_id='frame-1', size=len(data))[-1]['type'], 'screen_ready')
        for i, offset in enumerate(range(0, len(data), 8)):
            self.assertEqual(self.send('screen_chunk', task_id='task-1', frame_id='frame-1', index=i, data=base64.b64encode(data[offset:offset + 8]).decode()), [])
        response = self.send('screen_end', task_id='task-1', frame_id='frame-1', sha256=hashlib.sha256(data).hexdigest())
        self.assertEqual(response[-1]['type'], 'screen_received')
        self.assertEqual(self.receiver.last_frame, data)
        self.assertEqual(self.send('stop_task', task_id='task-1')[-1]['type'], 'task_stopped')
        self.assertIsNone(self.receiver.last_frame)
        self.assertIsNone(self.receiver.frame)
        self.assertIsNone(self.receiver.task)
        self.assertEqual(self.send('screen_begin', task_id='task-1', frame_id='late', size=10)[-1]['type'], 'error')

    def test_bad_chunks_and_oversized_frames_are_rejected(self):
        self.task()
        self.assertEqual(self.send('screen_begin', task_id='task-1', frame_id='bad', size=999999)[-1]['type'], 'error')
        self.send('screen_begin', task_id='task-1', frame_id='good', size=10)
        self.assertEqual(self.send('screen_chunk', task_id='task-1', frame_id='good', index=1, data='YWJj')[-1]['type'], 'error')
        self.assertIsNone(self.receiver.frame)

    def test_lease_expires_and_idle_heartbeat_cancels_task(self):
        self.task()
        self.receiver.last_seen = time.monotonic() - 9
        self.assertTrue(self.receiver.expire())
        self.assertIsNone(self.receiver.task)
        self.task()
        self.send('ping', task_id='task-1')
        self.assertIsNotNone(self.receiver.task)
        self.send('ping')
        self.assertIsNone(self.receiver.task)

    def framed_task(self, mode='guide'):
        self.send('task', task_id='task-1', mode=mode, text='Pointer test only')
        data = b'test-image'
        self.send('screen_begin', task_id='task-1', frame_id='frame-1', size=len(data))
        self.send('screen_chunk', task_id='task-1', frame_id='frame-1', index=0, data=base64.b64encode(data).decode())
        self.send('screen_end', task_id='task-1', frame_id='frame-1', sha256=hashlib.sha256(data).hexdigest())

    def test_guide_targets_are_idempotent_and_cannot_get_auto_permit(self):
        self.framed_task()
        self.send('test_action', task_id='task-1', kind='click', x=0.5, y=0.5)
        first = self.send('next_action', task_id='task-1', frame_id='frame-1')[-1]['action']
        retry = self.send('next_action', task_id='task-1', frame_id='frame-1')[-1]['action']
        self.assertEqual(first['action_id'], retry['action_id'])
        self.assertEqual(self.send('action_permit', task_id='task-1', frame_id='frame-1', action_id=first['action_id'])[-1]['type'], 'error')
        self.assertEqual(self.send('action_result', task_id='task-1', action_id=first['action_id'], status='executed')[-1]['type'], 'error')
        self.assertEqual(self.send('action_result', task_id='task-1', action_id=first['action_id'], status='guided')[-1]['type'], 'action_recorded')
        self.assertEqual(self.send('action_result', task_id='task-1', action_id=first['action_id'], status='guided')[-1]['type'], 'action_recorded')
        self.assertIsNone(self.send('next_action', task_id='task-1', frame_id='frame-1')[-1]['action'])

    def test_auto_requires_current_task_frame_and_action_then_stop_revokes_it(self):
        self.framed_task('do')
        action = self.receiver.queue_action('move', 0.2, 0.3, 'Move here')
        self.send('next_action', task_id='task-1', frame_id='frame-1')
        self.assertEqual(self.send('action_permit', task_id='task-1', frame_id='old', action_id=action['action_id'])[-1]['type'], 'error')
        self.assertEqual(self.send('action_permit', task_id='task-1', frame_id='frame-1', action_id=action['action_id'])[-1]['type'], 'action_permitted')
        self.send('stop_task', task_id='task-1')
        self.assertIsNone(self.receiver.inflight_action)
        self.assertEqual(self.send('action_permit', task_id='task-1', frame_id='frame-1', action_id=action['action_id'])[-1]['type'], 'error')

    def test_invalid_pointer_targets_are_rejected(self):
        self.framed_task()
        for kind, x, y in [('shell', 0.5, 0.5), ('click', -1, 0.5), ('move', float('nan'), 0.5), ('click', 1.1, 0.5)]:
            with self.assertRaises(ValueError):
                self.receiver.queue_action(kind, x, y)

    def test_socket_session_handles_fragmented_json(self):
        host, board = socket.socketpair()
        host.settimeout(2)
        worker = threading.Thread(target=serve_connection, args=(board,), daemon=True)
        worker.start()
        try:
            host.sendall(b'{"type":"he')
            host.sendall(b'llo","protocol":1,"nonce":"socket-test"}\n')
            pending = bytearray()
            while b'\n' not in pending:
                pending.extend(host.recv(1024))
            self.assertEqual(json.loads(pending)['nonce'], 'socket-test')
        finally:
            host.close()
            worker.join(2)
        self.assertFalse(worker.is_alive())


if __name__ == '__main__':
    unittest.main()

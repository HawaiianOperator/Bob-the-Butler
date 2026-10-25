import json
import queue
import threading
import unittest
from unittest.mock import patch
import tkinter as tk
from app import Companion
from protocol import valid_reply


class FakeSerial:
    def __init__(self, **kwargs):
        self.buffer = bytearray()
        self.closed = False
    def __enter__(self): return self
    def __exit__(self, *args): self.closed = True
    def open(self): pass
    def write(self, data):
        obj = json.loads(data)
        obj.update(device='device-companion', type='hello_ack' if obj['type'] == 'hello' else 'pong')
        self.buffer.extend(json.dumps(obj).encode() + b'\n')
    def read(self, count):
        value = bytes(self.buffer[:count])
        del self.buffer[:count]
        return value


class ConnectionTests(unittest.TestCase):
    def test_reply_validation(self):
        good = dict(type='hello_ack', device='device-companion', protocol=1, nonce='test')
        self.assertTrue(valid_reply(json.dumps(good), 'hello_ack', 'test'))
        self.assertFalse(valid_reply(json.dumps(good), 'hello_ack', 'wrong'))
        good['device'] = 'other-board'
        self.assertFalse(valid_reply(json.dumps(good), 'hello_ack', 'test'))
        for raw in [b'boot log', b'\xff', b'[]', b'null']:
            self.assertFalse(valid_reply(raw, 'hello_ack', 'test'))

    def test_handshake_and_heartbeat(self):
        a = Companion.__new__(Companion)
        a.stop = threading.Event()
        port = FakeSerial()
        self.assertTrue(a.exchange(port, 'hello', 'hello_ack', 0.1))
        self.assertTrue(a.exchange(port, 'ping', 'pong', 0.1))
        port.write = lambda data: None
        self.assertFalse(a.exchange(port, 'hello', 'hello_ack', 0.01))
        a.stop.set()
        self.assertFalse(a.exchange(port, 'hello', 'hello_ack', 1))

    def test_screen_transitions(self):
        with patch('app.list_ports.comports', return_value=[]):
            root = tk.Tk()
            a = Companion(root)
            root.update()
            self.assertTrue(a.offline.winfo_ismapped())
            a.emit('connected', 'COM5')
            a.poll()
            root.update()
            self.assertTrue(a.online.winfo_ismapped())
            self.assertFalse(a.offline.winfo_ismapped())
            a.emit('error', 'Wrong device. Try another port.')
            a.emit('disconnected')
            a.poll()
            root.update()
            self.assertTrue(a.offline.winfo_ismapped())
            self.assertIn('Wrong device', a.feedback['text'])
            self.assertLess(a.feedback.winfo_y() + a.feedback.winfo_height(), a.offline.winfo_height())
            root.destroy()


if __name__ == '__main__':
    unittest.main()

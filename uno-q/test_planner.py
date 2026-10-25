import threading
import time
import unittest
from ai.planner import Planner
from bob_service import Receiver


class PlannerTests(unittest.TestCase):
    def test_stop_discards_late_inference_and_bounds_threads(self):
        release = threading.Event()
        entered = threading.Event()
        def infer(*args):
            entered.set()
            release.wait(2)
            return {'tool': 'observe', 'args': {}}
        planner = Planner(infer)
        self.assertTrue(planner.start('test', {}))
        self.assertTrue(entered.wait(1))
        planner.reset()
        self.assertFalse(planner.start('another', {}))
        release.set()
        deadline = time.monotonic() + 1
        while planner.busy and time.monotonic() < deadline:
            time.sleep(.005)
        self.assertFalse(planner.busy)
        self.assertIsNone(planner.take())

    def test_guide_cannot_get_permit_and_stop_revokes_auto(self):
        receiver = Receiver()
        def send(kind, **data):
            return receiver.handle(dict(type=kind, protocol=1, nonce='test', **data))[-1]
        send('task', task_id='task', mode='guide', text='test')
        receiver.plan_step = {'id': 'step', 'plan': {'tool':'observe', 'args':{}}}
        self.assertEqual(send('planner_permit', task_id='task', step_id='step')['type'], 'error')
        receiver.task['mode'] = 'do'
        self.assertEqual(send('planner_permit', task_id='task', step_id='step')['type'], 'planner_permitted')
        self.assertEqual(send('planner_result', task_id='task', step_id='old', result={'ok':True})['type'], 'error')
        send('stop_task', task_id='task')
        self.assertEqual(send('planner_permit', task_id='task', step_id='step')['type'], 'error')


if __name__ == '__main__':
    unittest.main()

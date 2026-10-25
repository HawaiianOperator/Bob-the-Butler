import time
import unittest
from ai.planner import Planner
from ai.search_workflow import SearchWorkflow, is_search


class SearchWorkflowTests(unittest.TestCase):
    def test_waits_for_ack_and_verified_result_title(self):
        workflow=SearchWorkflow('NVIDIA stock')
        closed={'chrome':'closed'}
        chrome={'chrome':'ready','active_window':'Chrome'}
        plan=workflow.next(closed)
        self.assertEqual(plan['tool'],'launch_chrome')
        self.assertEqual(workflow.next(chrome),plan)  # observation alone is not success
        workflow.record(plan,{'ok':True})
        for expected in ('hotkey','type_text','press_key'):
            plan=workflow.next(chrome)
            self.assertEqual(plan['tool'],expected)
            workflow.record(plan,{'ok':True})
        self.assertEqual(workflow.next(dict(chrome,page_loading=False,page_title='Google'))['tool'],'observe')
        self.assertEqual(workflow.next(dict(chrome,page_loading=False,page_title='Intel stock - Google Search'))['tool'],'observe')
        self.assertEqual(workflow.next(dict(chrome,page_loading=False,page_title='Nvidia stock - Google Search'))['tool'],'done')

    def test_failed_launch_never_types_and_missing_foreground_waits(self):
        workflow=SearchWorkflow('Paris weather')
        launch=workflow.next({'chrome':'closed'})
        workflow.record(launch,{'ok':False})
        self.assertEqual(workflow.next({'chrome':'closed'})['tool'],'ask')
        workflow=SearchWorkflow('Paris weather')
        workflow.record(launch,{'ok':True})
        self.assertEqual(workflow.next({'chrome':'closed'})['tool'],'observe')

    def test_query_model_runs_once_for_the_whole_search(self):
        calls=[]
        planner=Planner(query_inference=lambda goal: calls.append(goal) or 'Paris weather')
        self.assertTrue(planner.start('search for Paris weather',{'chrome':'closed'}))
        deadline=time.monotonic()+2
        while planner.busy and time.monotonic()<deadline: time.sleep(.005)
        result=planner.take()
        self.assertEqual(result['plan']['tool'],'launch_chrome')
        planner.record(result['plan'],{'ok':True})
        for tool in ('hotkey','type_text','press_key'):
            self.assertTrue(planner.start('search for Paris weather',{'chrome':'ready','active_window':'Chrome'}))
            result=planner.take()
            self.assertEqual(result['plan']['tool'],tool)
            planner.record(result['plan'],{'ok':True})
        self.assertEqual(calls,['search for Paris weather'])
        planner.reset()
        self.assertIsNone(planner.search)

    def test_routes_search_requests_without_changing_plain_launch(self):
        self.assertTrue(is_search('open stocks for nvidai'))
        self.assertTrue(is_search('Search Google for NVIDIA stock'))
        self.assertFalse(is_search('open Chrome'))

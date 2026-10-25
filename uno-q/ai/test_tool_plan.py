import unittest
try:
    from .tool_plan import parse_tool, ai_desktop_args
except ImportError:
    from tool_plan import parse_tool, ai_desktop_args

class PlannerContractTests(unittest.TestCase):
    def test_existing_executor_commands(self):
        self.assertEqual(ai_desktop_args({'tool':'hotkey','args':{'keys':'ctrl+l'}}), ['--json','hotkey','--keys','ctrl+l'])
        self.assertEqual(ai_desktop_args({'tool':'type_text','args':{'text':'NVIDIA stock'}})[-1], 'NVIDIA stock')
        self.assertIsNone(ai_desktop_args({'tool':'observe','args':{}}))
    def test_unbounded_commands_and_extra_arguments_are_rejected(self):
        for plan in [{'tool':'shell','args':{'command':'anything'}}, {'tool':'hotkey','args':{'keys':'win+r'}},
                     {'tool':'launch_chrome','args':{'url':'file:///secret'}}, {'tool':'type_text','args':{'text':'hello','shell':True}}]:
            with self.assertRaises(ValueError):parse_tool(plan)

if __name__=='__main__':unittest.main()

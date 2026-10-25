"""Run on UNO Q. Benchmark model decisions only; this does not operate the desktop."""
import argparse
import json
import time
from pathlib import Path
try:
    from .planner import infer
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from ai.planner import infer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='planner-live-results.json')
    args = parser.parse_args()
    goal = 'hey can you open stocks for nvidai'
    cases = [
        ({'chrome':'closed'}, 'launch_chrome'),
        ({'chrome':'ready','active_window':'Chrome','address_bar_focused':False}, 'hotkey'),
        ({'chrome':'ready','active_window':'Chrome','address_bar_focused':True}, 'type_text'),
        ({'chrome':'ready','active_window':'Chrome','address_bar_focused':True,'address_bar_text':'NVIDIA stock'}, 'press_key'),
        ({'chrome':'ready','active_window':'Chrome','page_loading':True}, 'observe'),
        ({'chrome':'ready','active_window':'Chrome','page_loading':False,'page_title':'NVIDIA stock - Google Search'}, 'done'),
    ]
    results, history = [], []
    query = 'NVIDIA stock'
    for observation, expected in cases:
        if 'address_bar_text' in observation:
            observation['address_bar_text'] = query
        if 'page_title' in observation:
            observation['page_title'] = query + ' - Google Search'
        started = time.monotonic()
        plan = infer(goal, history, observation)
        results.append(dict(expected=expected,plan=plan,tool_match=plan['tool']==expected,seconds=round(time.monotonic()-started,3)))
        history.append(dict(plan, result={'ok':True}))
        if plan['tool'] == 'type_text':
            query = plan['args']['text']
        print(json.dumps(results[-1]), flush=True)
    output = dict(kind='UNO Q quantized planner inference; synthetic observations, no desktop execution',
                  goal=goal,results=results,all_tools_match=all(r['tool_match'] for r in results))
    Path(args.output).write_text(json.dumps(output,indent=2))


if __name__ == '__main__':
    main()

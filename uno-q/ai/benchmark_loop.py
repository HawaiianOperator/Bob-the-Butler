"""Closed-loop model smoke test with simulated Chrome. No desktop input occurs."""
import argparse
import json
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ai.planner import infer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    goal = 'hey can you open stocks for nvidai'
    history, results, observation = [], [], {'chrome':'closed'}
    query, entered, success = '', False, False
    started = time.monotonic()
    for index in range(12):
        before = time.monotonic()
        plan = infer(goal, history, observation)
        result = dict(index=index,plan=plan,seconds=round(time.monotonic()-before,3))
        results.append(result)
        print(json.dumps(result), flush=True)
        tool, params = plan['tool'], plan['args']
        if tool == 'done':
            success = entered and 'nvidia' in query.lower() and 'stock' in query.lower()
            break
        if tool == 'ask':
            break
        if tool == 'launch_chrome':
            observation = dict(chrome='ready',active_window='Chrome',address_bar_focused=False)
        elif tool == 'hotkey':
            observation = dict(chrome='ready',active_window='Chrome',address_bar_focused=True)
        elif tool == 'type_text':
            query = params['text']
            observation = dict(chrome='ready',active_window='Chrome',address_bar_focused=True,address_bar_text=query)
        elif tool == 'press_key' and params['key'] == 'enter':
            entered = True
            observation = dict(chrome='ready',active_window='Chrome',page_loading=False,page_title=query+' - Google Search')
        # observe leaves the simulated browser state intact; no assumed progress.
        history.append(dict(plan,result={'ok':True}))
    output = dict(kind='Closed-loop UNO Q inference with simulated Chrome, no desktop execution',
                  success=success,seconds=round(time.monotonic()-started,3),results=results)
    Path(args.output).write_text(json.dumps(output,indent=2))
    print(json.dumps(dict(success=success,seconds=output['seconds'])),flush=True)


if __name__ == '__main__':
    main()

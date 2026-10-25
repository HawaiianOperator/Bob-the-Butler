"""Acknowledged Google search steps; one model call prepares the query."""
import json
import re
import urllib.request
from .tool_plan import parse_tool


def is_search(goal):
    return bool(re.search(r'\b(search|serch|stock|stocks|price|prices|find)\b|look up', goal, re.I))


def prepare_query(goal):
    schema = {'type':'object','properties':{'query':{'type':'string','minLength':1,'maxLength':256}},
              'required':['query'],'additionalProperties':False}
    payload = dict(messages=[dict(role='system', content=
        'Convert the user request into concise Google search terms. Correct obvious spelling mistakes. '
        'Omit conversational instructions such as open, show me, and please. '
        'Example: open stocks for nvidai becomes NVIDIA stock. '
        'Example: find the weather in Paris becomes Paris weather. '
        'Return only JSON with query. Do not answer the query or provide stock prices.'),
        dict(role='user',content=goal)], temperature=0,max_tokens=80,
        chat_template_kwargs={'enable_thinking':False},response_format={'type':'json_object','schema':schema})
    request=urllib.request.Request('http://127.0.0.1:8081/v1/chat/completions',json.dumps(payload).encode(),{'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=90) as response:
        value=json.loads(json.load(response)['choices'][0]['message']['content'])
    if not isinstance(value,dict) or set(value)!={'query'}:
        raise ValueError('Invalid search query')
    # The same bound and character checks used by the native typing contract.
    return parse_tool({'tool':'type_text','args':{'text':value['query']}})['args']['text']


class SearchWorkflow:
    def __init__(self, query):
        self.query=query
        self.stage='launch'
        self.failed=False

    def next(self, observation):
        if observation.get('chrome')=='unavailable' or self.failed:
            return {'tool':'ask','args':{'question':'Chrome could not complete the last step. Please check Chrome and try again.'}}
        if self.stage!='launch' and observation.get('active_window')!='Chrome':
            return {'tool':'observe','args':{}}
        plans={
            'launch':{'tool':'launch_chrome','args':{'url':'https://www.google.com/'}},
            'focus':{'tool':'hotkey','args':{'keys':'ctrl+l'}},
            'type':{'tool':'type_text','args':{'text':self.query}},
            'submit':{'tool':'press_key','args':{'key':'enter'}},
        }
        if self.stage in plans:
            return plans[self.stage]
        title=observation.get('page_title','')
        if not observation.get('page_loading',True) and self.query.casefold() in title.casefold():
            return {'tool':'done','args':{'message':'Showing search results for '+self.query+'.'}}
        return {'tool':'observe','args':{}}

    def record(self, plan, result):
        if not result.get('ok'):
            if plan['tool']!='done': self.failed=True
            return
        transitions={'launch':('launch_chrome','focus'),'focus':('hotkey','type'),
                     'type':('type_text','submit'),'submit':('press_key','verify')}
        expected=transitions.get(self.stage)
        if expected and plan['tool']==expected[0]:
            self.stage=expected[1]

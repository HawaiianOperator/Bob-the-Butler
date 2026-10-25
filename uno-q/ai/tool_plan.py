"""Bounded planner tool contract matching ai-desktop's existing CLI operations.

This module builds argument arrays only. The native session controller must enforce
USB permits, foreground app checks, mode, Stop and input takeover before execution.
"""
import json
from urllib.parse import urlparse

KEYS = {'enter', 'tab', 'esc', 'backspace', 'up', 'down', 'left', 'right'}
HOTKEYS = {'ctrl+l', 'ctrl+t', 'ctrl+a'}
TOOLS = {
    'launch_chrome': {'url': 'http(s) URL'},
    'hotkey': {'keys': 'ctrl+l, ctrl+t or ctrl+a'},
    'type_text': {'text': 'printable search text, max 256 characters'},
    'press_key': {'key': 'enter, tab, esc, backspace or arrow key'},
    'observe': {},
    'done': {'message': 'short completion message'},
    'ask': {'question': 'short clarification question'},
}


def parse_tool(text):
    obj = json.loads(text) if isinstance(text, str) else text
    if not isinstance(obj, dict) or set(obj) != {'tool', 'args'}:
        raise ValueError('Expected exactly tool and args.')
    tool, args = obj['tool'], obj['args']
    if not isinstance(tool, str) or tool not in TOOLS or not isinstance(args, dict) or set(args) != set(TOOLS[tool]):
        raise ValueError('Unknown tool or arguments.')
    for value in args.values():
        if not isinstance(value, str) or not value or len(value) > 256 or any(ord(c) < 32 for c in value):
            raise ValueError('Invalid tool argument.')
    if tool == 'launch_chrome':
        url = urlparse(args['url'])
        if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password:
            raise ValueError('Browser launch requires a normal HTTP(S) URL.')
    if tool == 'hotkey' and args['keys'] not in HOTKEYS:
        raise ValueError('Unsupported shortcut.')
    if tool == 'press_key' and args['key'] not in KEYS:
        raise ValueError('Unsupported key.')
    if tool == 'type_text' and not all(32 <= ord(c) < 127 for c in args['text']):
        raise ValueError('The upstream type command supports printable ASCII; Unicode needs a separate paste adapter.')
    return obj


def ai_desktop_args(plan):
    plan = parse_tool(plan)
    tool, args = plan['tool'], plan['args']
    if tool == 'launch_chrome': return ['--json', 'launch-chrome', '--url', args['url']]
    if tool == 'hotkey': return ['--json', 'hotkey', '--keys', args['keys']]
    if tool == 'type_text': return ['--json', 'type', '--text', args['text']]
    if tool == 'press_key': return ['--json', 'key', '--key', args['key']]
    # Keep our existing in-memory observation path; upstream screenshots are disk-backed.
    return None

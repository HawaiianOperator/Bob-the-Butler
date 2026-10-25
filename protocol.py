"""USB device identity protocol. Identity check is not cryptographic authentication."""
import json

PROTOCOL = 1
DEVICE = 'device-companion'


def request(kind, nonce):
    return (json.dumps({'type': kind, 'protocol': PROTOCOL, 'nonce': nonce}) + '\n').encode('utf-8')


def valid_reply(raw, kind, nonce):
    try:
        obj = json.loads(raw)
        return (isinstance(obj, dict) and obj.get('type') == kind
                and obj.get('device') == DEVICE and obj.get('protocol') == PROTOCOL
                and obj.get('nonce') == nonce)
    except (ValueError, UnicodeError, TypeError):
        return False

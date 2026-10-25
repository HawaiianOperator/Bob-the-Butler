#!/usr/bin/env python3
"""CPU-only, non-executing AI smoke benchmark for the physical UNO Q."""
import argparse
import base64
import json
import platform
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request
from model_adapter import POINT_SCHEMA, SEARCH_SCHEMA


def request(path, payload=None, timeout=180):
    data=None if payload is None else json.dumps(payload).encode()
    req=urllib.request.Request('http://127.0.0.1:8081'+path,data=data,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=timeout) as response:return json.load(response)


def peak_rss(pid):
    try:
        for line in Path(f'/proc/{pid}/status').read_text().splitlines():
            if line.startswith('VmHWM:'):return int(line.split()[1])
    except OSError:pass
    return None


def run_model(root, fixture_root, size, plain_json=False, only=None):
    runtime=next((root/'runtime').rglob('llama-server'))
    models=root/'models'/size
    command=[str(runtime),'-m',str(models/f'SmolVLM-{size}M-Instruct-Q8_0.gguf'),'--mmproj',str(models/f'mmproj-SmolVLM-{size}M-Instruct-Q8_0.gguf'),
        '--host','127.0.0.1','--port','8081','--threads','4','--ctx-size','2048','--parallel','1','--batch-size','128','--ubatch-size','64','--n-gpu-layers','0','--no-mmproj-offload']
    record=dict(model=f'SmolVLM-{size}M-Instruct',precision='Q8_0',cpu_threads=4,context=2048,response_constraint='json_object' if plain_json else 'json_schema',cases=[])
    log_path=root/f'benchmark-{size}.log'
    print(f'Starting {record["model"]} on the UNO Q CPU.',flush=True)
    with log_path.open('w') as log:
        process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
        started=time.monotonic()
        try:
            while True:
                if process.poll() is not None:raise RuntimeError(f'Model server exited ({process.returncode}); see {log_path}')
                try:
                    if request('/health',timeout=2).get('status')=='ok':break
                except (OSError,ValueError):pass
                if time.monotonic()-started>180:raise RuntimeError('Model load exceeded 180 seconds.')
                time.sleep(0.5)
            record['load_seconds']=round(time.monotonic()-started,2)
            cases=json.loads((fixture_root/'cases.json').read_text())
            for case in cases:
                if only and case['id'] not in only: continue
                image=base64.b64encode((fixture_root/case['image']).read_bytes()).decode()
                payload=dict(messages=[{'role':'system','content':'Identify the requested UI target. Return one JSON object with numeric x and y coordinates normalized from 0 to 1. Do not invent extra controls.'},
                    {'role':'user','content':[{'type':'image_url','image_url':{'url':'data:image/png;base64,'+image}},{'type':'text','text':case['prompt']}]}],temperature=0,max_tokens=48,seed=42,response_format={'type':'json_object'} if plain_json else {'type':'json_object','schema':POINT_SCHEMA})
                before=time.monotonic()
                try:
                    response=request('/v1/chat/completions',payload)
                    text=response['choices'][0]['message']['content']
                    outcome=dict(id=case['id'],seconds=round(time.monotonic()-before,2),output=text,timings=response.get('timings'),hit=False)
                    try:
                        point=json.loads(text);x,y=point['x'],point['y'];box=case['box']
                        outcome['hit']=type(x) in (int,float) and type(y) in (int,float) and box[0]<=x<=box[2] and box[1]<=y<=box[3]
                    except (ValueError,KeyError,TypeError):pass
                except Exception as exc:outcome=dict(id=case['id'],seconds=round(time.monotonic()-before,2),error=str(exc),hit=False)
                record['cases'].append(outcome)
                print(json.dumps(outcome),flush=True)
            payload=dict(messages=[{'role':'system','content':'Turn the user request into a web search query. Correct obvious spelling mistakes. Return only a JSON object with a query string. Do not give stock prices.'},
                {'role':'user','content':'hey can you open stocks for nvidai'}],temperature=0,max_tokens=40,seed=42,response_format={'type':'json_object'} if plain_json else {'type':'json_object','schema':SEARCH_SCHEMA})
            before=time.monotonic()
            try:
                response=request('/v1/chat/completions',payload);text=response['choices'][0]['message']['content']
                case=dict(id='chat-intent',seconds=round(time.monotonic()-before,2),output=text,hit=False,timings=response.get('timings'))
                try:
                    query=json.loads(text)['query'].lower();case['hit']=('nvidia' in query or 'nvda' in query) and 'stock' in query
                except (ValueError,KeyError,TypeError,AttributeError):pass
            except Exception as exc:case=dict(id='chat-intent',seconds=round(time.monotonic()-before,2),error=str(exc),hit=False)
            record['cases'].append(case);print(json.dumps(case),flush=True)
            record['peak_rss_kib']=peak_rss(process.pid)
        finally:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait()
    return record


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--plain-json',action='store_true');parser.add_argument('--output',default='benchmark-results.json');parser.add_argument('--only',nargs='*');parser.add_argument('--root',default='/home/arduino/bob-ai');parser.add_argument('--fixtures',default=str(Path(__file__).parent/'fixtures'));parser.add_argument('--models',nargs='+',default=['500','256']);args=parser.parse_args()
    root=Path(args.root);output=root/args.output
    result=dict(hardware='Arduino UNO Q 4GB',architecture=platform.machine(),runtime=json.loads((root/'manifest.json').read_text())['runtime'],scope='Synthetic UI smoke test only; no actions executed; not a general desktop accuracy evaluation.',results=[])
    for size in args.models:
        result['results'].append(run_model(root,Path(args.fixtures),size,args.plain_json,args.only))
        output.write_text(json.dumps(result,indent=2))
    print(f'Results saved to {output}',flush=True)

if __name__=='__main__':main()

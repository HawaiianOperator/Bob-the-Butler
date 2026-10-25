#!/usr/bin/env python3
"""Download pinned, checksum-verified benchmark models on UNO Q. No cloud inference."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import urllib.request

RUNTIME_TAG = 'b11869'
RUNTIME_SHA = 'dc10f7a9e7048984834d03d84b05ddc5086c5d6a2c120276f78e846e2a6ea5af'
MODELS = {
    '500': dict(revision='72e986006ef53e37cdd3f6d4241c90b0f01df376', files={
        'SmolVLM-500M-Instruct-Q8_0.gguf': '9d4612de6a42214499e301494a3ecc2be0abdd9de44e663bda63f1152fad1bf4',
        'mmproj-SmolVLM-500M-Instruct-Q8_0.gguf': 'd1eb8b6b23979205fdf63703ed10f788131a3f812c7b1f72e0119d5d81295150'}),
    '256': dict(revision='b9e4379657e1450d04d02eec8e345667265b0a00', files={
        'SmolVLM-256M-Instruct-Q8_0.gguf': '2a31195d3769c0b0fd0a4906201666108834848db768af11de1d2cef7cd35e65',
        'mmproj-SmolVLM-256M-Instruct-Q8_0.gguf': '7e943f7c53f0382a6fc41b6ee0c2def63ba4fded9ab8ed039cc9e2ab905e0edd'}),
}


def digest(path):
    result=hashlib.sha256()
    with path.open('rb') as handle:
        while chunk:=handle.read(2*1024*1024):result.update(chunk)
    return result.hexdigest()


def download(url, path, expected):
    if path.exists() and digest(path)==expected:
        print(f'Verified cached {path.name}', flush=True)
        return
    path.parent.mkdir(parents=True,exist_ok=True)
    partial=path.with_suffix(path.suffix+'.part')
    offset=partial.stat().st_size if partial.exists() else 0
    req=urllib.request.Request(url, headers={'User-Agent':'Bob-UNO-Q-benchmark','Range':f'bytes={offset}-'} if offset else {'User-Agent':'Bob-UNO-Q-benchmark'})
    print(f'Downloading {path.name}', flush=True)
    with urllib.request.urlopen(req,timeout=60) as response:
        append=offset>0 and response.status==206
        if not append:offset=0
        last=offset//(64*1024*1024)
        with partial.open('ab' if append else 'wb') as handle:
            while chunk:=response.read(2*1024*1024):
                handle.write(chunk);offset+=len(chunk)
                if offset//(64*1024*1024)>last:
                    last=offset//(64*1024*1024);print(f'  {offset//(1024*1024)} MiB',flush=True)
    if digest(partial)!=expected:raise RuntimeError(f'Checksum failed: {path.name}')
    partial.replace(path)
    print(f'Checksum verified: {path.name}',flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',default='/home/arduino/bob-ai');parser.add_argument('--models',nargs='+',choices=MODELS,default=['500','256']);args=parser.parse_args()
    root=Path(args.root);root.mkdir(parents=True,exist_ok=True)
    archive=root/f'llama-{RUNTIME_TAG}-arm64.tar.gz'
    download(f'https://github.com/ggml-org/llama.cpp/releases/download/{RUNTIME_TAG}/llama-{RUNTIME_TAG}-bin-ubuntu-arm64.tar.gz',archive,RUNTIME_SHA)
    runtime=root/'runtime'
    if not list(runtime.rglob('llama-server')):
        runtime.mkdir(exist_ok=True)
        with tarfile.open(archive) as bundle:bundle.extractall(runtime,filter='data')
    server=next(runtime.rglob('llama-server'))
    subprocess.run([str(server),'--version'],check=True)
    for size in args.models:
        spec=MODELS[size]
        for name,sha in spec['files'].items():
            download(f'https://huggingface.co/ggml-org/SmolVLM-{size}M-Instruct-GGUF/resolve/{spec["revision"]}/{name}',root/'models'/size/name,sha)
    (root/'manifest.json').write_text(json.dumps(dict(runtime=RUNTIME_TAG,runtime_sha256=RUNTIME_SHA,models={size:MODELS[size] for size in args.models}),indent=2))
    print(f'Benchmark assets ready at {root}; no AI or input-control service was enabled.',flush=True)

if __name__=='__main__':main()

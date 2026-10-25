# Bob's AI development kit

## Start with command planning

Run **[A30_tool_planner.ipynb](A30_tool_planner.ipynb)** in your A30 Jupyter environment. This is the primary notebook following the decision to use a small language model to select existing desktop tools. The user has trained and exported Qwen3-0.6B with thinking traces disabled. The merged export is now quantized for the UNO Q.

The notebook runs a pretrained baseline, generates a synthetic starter dataset if you do not provide real traces, fine-tunes LoRA, evaluates generated next-tool answers on held-out workflow groups, and exports merged weights. No desktop actions execute from the notebook. The baseline and evaluation prompts do not include the target answer.

Send back:

- `bob-tool-planner-lora/run_summary.json`
- `bob-tool-planner-lora/heldout-results.json`
- Any error traceback if a cell fails.

Keep your full `bob-tool-planner-merged/` export as the training backup. The production GGUF and conversion manifest remain outside Git. Synthetic workflow scores are not live Chrome task-success rates.

## Architecture and the original GitHub references

```text
User request + current observation + recent tool results
                         ↓
             Language/tool planner on UNO Q
                         ↓ one structured tool call
             Windows session / mode controller
                         ↓
          Desktop executor → result / observation
                         └────────── back to planner
```

The [ai-desktop repository](https://github.com/MichaelDKulka/ai-desktop/tree/28dd1ba7d3f66fc9212f27a8f6c82d444af346e4) provides executable primitives, including `launch-chrome`, `hotkey`, `type`, `key` and screenshots. It does not supply the reasoning model or the complete Bob agent loop. Its MIT license permits reuse with its notice preserved when code is distributed. No upstream implementation is vendored here yet.

`tool_plan.py` validates a bounded tool vocabulary and maps calls to the existing upstream CLI argument arrays. It never invokes a shell or runs those arrays. `observe` uses Bob's existing in-memory screenshot path rather than upstream disk-backed screenshot storage.

Example next tool:

```json
{"tool":"hotkey","args":{"keys":"ctrl+l"}}
```

For “hey can you open stocks for nvidai”, the initial workflow is Chrome → focus address bar → type `NVIDIA stock` → Enter → observe → finish. In a production loop each next command must depend on the actual executor result and observation, not an assumed fixed delay or success.

**Integration status:** Windows now supports bounded Chrome launch, allowed shortcuts, printable ASCII text and single keys. Auto requests a fresh UNO Q permit and checks cancellation, physical takeover and the foreground Chrome process. Guide displays instructions and waits for Step done followed by a return to Chrome; it does not inject tool input. The language planner receives normalized window/title observations and recent tool results. Screenshots continue to travel to the Q in RAM, but this language model does not analyze their pixels. Arbitrary desktop vision and arbitrary applications are not implemented. Address-bar focus is inferred from acknowledged shortcuts rather than read through UI Automation.

`planner.py` runs one HTTP request in a background thread. Stop invalidates its generation so late results cannot restart a stopped task, and threads remain bounded. `bob-planner.service` runs llama-server on loopback port 8081 at boot. `install_service.py --with-ai` verifies the staged model checksum, installs the runtime/model under `/opt/bob-the-butler`, and enables both services. The Q4_K_M model is 396,704,640 bytes and remains outside Git.

OmniParser/vision can be added when identifying a visual target is necessary. It need not process every keyboard-driven browser step.

## Measured on the physical UNO Q

The trained Qwen3-0.6B Q4_K_M model is installed with llama.cpp b11869, four CPU threads and a 2048-token context. The first six-stage open-loop smoke test matched 4/6 tool labels: it inserted an observation before Enter. A second test held the simulated browser state unchanged after observations, and completed the NVIDIA search in six decisions and 65.372 seconds. These are inference tests with simulated Chrome, not desktop task-success measurements. Raw outputs and the model SHA-256 manifest are in `results/trained-*`.

The first cold response took 22.271 seconds. Later responses in these tiny checks took roughly 6–17 seconds. The persistent model service used approximately 327 MB according to systemd's MemoryCurrent at the time of the check. Real task time includes USB transfers, human actions in Guide mode, browser loading and additional model steps.

Pinned llama.cpp `b11869` (commit `d327bf1f0`), four CPU threads, 2048-token context, Q8 model/projector weights. Both pretrained SmolVLM candidates were downloaded with SHA-256 checks and tested on the actual board. Results are in `results/`.

| Model | Initial 1280×720 synthetic button tests | Text-only NVIDIA query with a constrained schema |
|---|---|---|
| SmolVLM 500M | 0/2 targets; 84.5–89.7 seconds per response | `nvidia stocks`, valid; 3.66 seconds |
| SmolVLM 256M | 0/2 targets; 75.5–76.6 seconds per response | Repetitive, incomplete output; 2.30 seconds; rejected |

These are tiny smoke tests, not general accuracy estimates. The 500M result demonstrates query extraction for one request; Chrome was not opened, no live stock data was retrieved, and no desktop input was injected. The smaller model was faster but failed the output check. Initial unconstrained JSON shape also failed; constraining properties fixed the 500M query shape without training.

The runtime and weights are staged under `/home/arduino/bob-ai/`. The earlier SmolVLM benchmark servers were temporary. The Qwen planner now has a separate loopback-only boot service, installed under `/opt/bob-the-butler`. The board's clock was corrected and NTP enabled so HTTPS certificate verification could remain enabled.

## Reproduce

`provision_benchmark.py` pins runtime/model revisions and checks every download. It needs Python 3.12+ for safe tar extraction and a correct clock for HTTPS. The Q has Python 3.13. When downloading on the laptop, use its `download()` helper then copy verified files over USB; large USB transfers on this board are slow.

```sh
python3 provision_benchmark.py
python3 benchmark.py --only chat-intent --output benchmark-intent-schema.json
```

For the original unstructured/high-resolution image test:

```sh
python3 benchmark.py --plain-json --fixtures fixtures/high-resolution --output initial-q8-1280.json
```

The default fixtures are now 640×360 to match Bob's current observation width. No new 640-pixel visual scores are claimed. `model_adapter.py` is a strict local-inference adapter for query/point experiments; it never executes an action. `A30_finetune.ipynb` is the optional visual-grounding experiment, not the primary command-planner notebook.

Local tests:

```powershell
python -m unittest discover -s uno-q/ai -p "test_*.py" -v
```

Training uses pretrained weights; it is not training an LLM from scratch. Real demonstration data, full task evaluation and on-board latency checks remain necessary before autonomous use.

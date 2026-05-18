# ocai

AI-powered natural-language wrapper over the OpenShift `oc` CLI.

Describe what you want; `ocai` proposes the `oc` command, shows you what it
will do, and asks before running it.

```text
$ ocai delete all completed builds
Command     (destructive):
  oc delete builds --field-selector=status.phase=Complete --all-namespaces
Explanation: Deletes every build whose phase is Complete in all namespaces.
Run? [y/N]
```

---

## Install

`ocai` needs the `oc` binary on your `$PATH` and Python 3.9+.

Pick the AI backend(s) you want as install extras:

```bash
# Clone and install from the homelab GitLab
git clone https://gitlab.apps.ocp.home.ins/nasser/ocai.git
cd ocai

# pick one or more:
pip install -e '.[claude]'    # Anthropic Claude
pip install -e '.[openai]'    # OpenAI
pip install -e '.'            # base only — required if you use Ollama
pip install -e '.[all]'       # Claude + OpenAI

# Ollama needs no Python extra (uses stdlib over HTTP) — just have a
# local ollama daemon running.
```

After install, the `ocai` command is on your `$PATH`.

---

## Authenticate / configure a backend

You pick **one** of these — `ocai` is happy with any.

### Claude (recommended for accuracy)

```bash
export ANTHROPIC_API_KEY=sk-ant-...
# optional: pick a model (default: claude-sonnet-4-6)
export OCAI_CLAUDE_MODEL=claude-sonnet-4-6
```

### OpenAI

```bash
export OPENAI_API_KEY=sk-...
export OCAI_OPENAI_MODEL=gpt-4o-mini      # optional
```

### Ollama (local, free, private)

```bash
# install once: https://ollama.com/download
ollama pull qwen2.5-coder:7b              # or llama3.1:8b, etc.
ollama serve &                            # if not already running

export OCAI_OLLAMA_MODEL=qwen2.5-coder:7b # optional, this is the default
export OLLAMA_HOST=http://127.0.0.1:11434 # optional, this is the default
```

### Pick which one ocai uses

In order of priority:

1. `--provider claude|openai|ollama` flag
2. `OCAI_PROVIDER` env var
3. `~/.config/ocai/config.toml`
4. Default: `claude`

`~/.config/ocai/config.toml`:

```toml
provider = "ollama"
model    = "qwen2.5-coder:7b"   # optional, overrides the provider default
```

---

## Usage

```text
ocai [--provider PROVIDER] [--model MODEL] [-n] [-y] <your request in plain English>
```

### Examples

```bash
# Read-only — defaults to y on the prompt
ocai get all pods on node worker-1
ocai how many pods are crashlooping
ocai show me the latest 50 lines of the api-server logs
ocai which projects are using more than 10Gi of memory

# Destructive — defaults to N on the prompt, so it's safe to type
ocai delete all completed builds
ocai scale the frontend deployment to 5 replicas
ocai deploy nginx webserver
ocai restart the rollout for the orders deployment

# Skip the confirmation prompt (for scripts)
ocai -y delete all completed builds

# Just show me the command, don't run it
ocai -n deploy a redis instance with persistent storage

# Switch backend per-invocation
ocai --provider ollama get pods in the openshift-monitoring namespace
ocai --provider claude --model claude-opus-4-7 explain the operator pattern
```

### Flags

| Flag | Purpose |
|---|---|
| `--provider {claude,openai,ollama}` | Which AI backend to use |
| `--model MODEL` | Override the model name for the chosen provider |
| `-n`, `--dry-run` | Print the proposed command, never execute |
| `-y`, `--yes` | Auto-confirm — skip the y/N prompt |
| `-V`, `--version` | Print version |
| `-h`, `--help` | Help |

---

## How safety works

Every request runs through the same gate:

1. The model is constrained to return a JSON object containing **one** shell
   command that uses `oc` (pipelines with `jq`, `xargs`, etc. are allowed
   when needed for bulk operations).
2. `ocai` parses that JSON, verifies the command actually invokes `oc`, and
   refuses to run anything that doesn't. `oc` is required as a literal token —
   no plain `rm`, `curl`, `kubectl`, etc.
3. It prints the command and a one-line explanation, color-coded:
   - <span style="color:green">**read-only**</span> — get, describe, logs, status, …
   - <span style="color:red">**destructive**</span> — delete, apply, create, scale, patch, …
4. It prompts `Run? [Y/n]` for read-only or `Run? [y/N]` for destructive.
   The default matches the color — Enter accepts the safe default.
5. Only after you confirm does it shell out.

Override the prompt with `-y` (auto-yes) or skip execution entirely with `-n`
(dry-run).

---

## Troubleshooting

**`ocai: provider error: ANTHROPIC_API_KEY is not set`**
Export the env var, or pick a different provider (`--provider ollama`).

**`ocai: provider error: anthropic SDK not installed`**
You installed `ocai` without the extra. Run `pip install -e '.[claude]'`.

**`ocai: provider error: could not reach Ollama at http://127.0.0.1:11434`**
The Ollama daemon isn't running. Run `ollama serve` (or systemctl start it).

**`ocai: refusing to execute: command does not invoke 'oc'`**
The model returned something that isn't an `oc` command. Try rephrasing — and
file an issue with the prompt that triggered it.

**The proposed command is wrong**
v1 sends only your prompt to the model — no cluster discovery. If you ask
about resources whose schema the model doesn't know (custom CRDs, unusual
field names), accuracy drops. Use `-n` to inspect, edit by hand, run with
plain `oc`.

**I want to see what command will run without burning a real call**
There isn't an offline mode — the AI is required to translate. Use `-n` to
get the translation without executing.

---

## Architecture

```
ocai/
├── cli.py            argparse entry point, exit codes
├── config.py         loads ~/.config/ocai/config.toml + env overrides
├── prompts.py        system prompt + few-shot examples + JSON schema
├── executor.py       validates suggestion, renders, prompts, runs
└── providers/
    ├── base.py            Provider protocol + Suggestion dataclass
    ├── claude.py          anthropic SDK; prompt caching on system block
    ├── openai_provider.py openai SDK; response_format=json_object
    └── ollama.py          stdlib urllib; format=json
```

The provider abstraction is a single `suggest(request: str) -> Suggestion`
method. Adding a new backend means dropping in one file under
`ocai/providers/` and registering it in `ocai/providers/__init__.py`.

---

## License

MIT.

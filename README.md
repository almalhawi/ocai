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
| `--no-context` | Don't gather `oc` context (project/user) before calling the model |
| `-d`, `--debug` | Print effective config and gathered context to stderr |
| `-V`, `--version` | Print version |
| `-h`, `--help` | Help |

---

## How safety works

Every request runs through the same gate:

1. The model is constrained to return a JSON object containing **one** shell
   command that uses `oc` (pipelines with `jq`, `xargs`, etc. are allowed
   when needed for bulk operations).
2. `ocai` parses that JSON, then validates the command:
   - Rejects shell control operators that chain commands: `;`, `&&`, `||`, `&`.
   - Rejects command/process substitution: `` ` ` ``, `$(...)`, `<(...)`, `>(...)`.
   - Splits on `|` and requires every pipeline segment's leading command to be
     in an allowlist (`oc`, `jq`, `xargs`, `grep`, `awk`, `sed`, `head`,
     `tail`, `sort`, `uniq`, `wc`, `cut`, `tr`, `column`, `tee`, `cat`).
   - Requires at least one segment to actually be `oc`.
3. Decides destructive vs read-only from **both** the model's flag and a
   static check on the `oc` verb. Either source can mark a command
   destructive — the model can't downgrade a real `oc delete` to read-only.
4. Prints the command and a one-line explanation, color-coded:
   - <span style="color:green">**read-only**</span> — get, describe, logs, status, …
   - <span style="color:red">**destructive**</span> — delete, apply, create, scale, patch, …
5. Prompts `Run? [Y/n/r]` for read-only or `Run? [y/N/r]` for destructive.
   The default (Enter) matches the color. `r` lets you refine the request
   ("only in the prod namespace") and re-prompt without retyping.
6. Only after you confirm does it shell out.

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
`ocai` sends your current `oc` context (project, user, cluster API) along
with the prompt, but it doesn't enumerate CRDs or arbitrary cluster state.
If you ask about resources whose schema the model doesn't know (uncommon
CRDs, unusual field names), accuracy drops. Hit `r` at the prompt to refine
("…and only in the openshift-monitoring namespace"), use `-n` to inspect and
edit by hand, or fall back to plain `oc`.

**I want to see what command will run without burning a real call**
There isn't an offline mode — the AI is required to translate. Use `-n` to
get the translation without executing.

---

## History / audit log

Every invocation appends a JSONL record to
`$XDG_STATE_HOME/ocai/history.jsonl` (default: `~/.local/state/ocai/history.jsonl`).
Fields: `ts`, `prompt`, `command`, `destructive`, `provider`, `model`,
`executed`, plus `returncode`, `refused`, or `refined` depending on outcome.

Tail it to see what you've been doing:

```bash
tail -n 5 ~/.local/state/ocai/history.jsonl | jq .
```

---

## Architecture

```
ocai/
├── cli.py            argparse entry point, refine loop, exit codes
├── config.py         loads ~/.config/ocai/config.toml + env overrides
├── context.py        gathers current oc project/user/cluster, best-effort
├── history.py        appends JSONL audit log
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

## Disclaimer

`ocai` is an independent open-source project. It is **not affiliated with,
endorsed by, sponsored by, or supported by Red Hat, Inc.** "OpenShift",
"oc", and "Red Hat" are trademarks of Red Hat, Inc. The `oc` CLI itself is
distributed separately by Red Hat; `ocai` only invokes the binary you
already have installed.

`ocai` is likewise not affiliated with Anthropic, OpenAI, or Ollama — those
are configurable backends and your use of them is subject to their own
terms of service.

---

## Security

A few things to keep in mind before pointing `ocai` at a production
cluster:

- **Your prompts are sent to a third party** (Claude or OpenAI) unless
  you use the Ollama backend, which runs locally. Treat the prompt the
  same way you'd treat any text pasted into a chat UI — don't put
  secrets (kubeconfigs, tokens, passwords) in it.
- The cluster context sent with each prompt includes your current user,
  project, and cluster API URL. Use `--no-context` to suppress it.
- **Validation is a guard, not a sandbox.** `ocai` parses the model's
  output, rejects shell metacharacters that allow command chaining, and
  enforces an allowlist of pipeline commands — but the validated
  command still runs in your shell with your credentials. A confident
  model plus loose cluster RBAC can still hurt you.
- **Even valid `oc` commands can be destructive.** `oc delete`, `oc apply`,
  `oc exec`, and `oc adm` can all cause data loss or cluster impact.
  Use `-n` (dry-run) on anything you're not certain about. The default-N
  prompt on destructive verbs is your last line of defense — not a
  promise that anything that passed the prompt is safe.
- The audit log at `~/.local/state/ocai/history.jsonl` contains every
  prompt and command. Treat it like shell history: protect or clear it
  as appropriate for your environment.
- This tool ships under the MIT license **as-is, without warranty**.
  The authors aren't responsible for what your cluster does after
  running a command this tool suggests.

---

## License

MIT.

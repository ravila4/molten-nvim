import json
import sys
import time
from queue import Empty, Queue
from types import SimpleNamespace
from unittest.mock import Mock

import jupyter_client
import pytest

from molten.runtime import JupyterRuntime
from molten.runtime_state import RuntimeState
from molten.jupyter_server_api import JupyterAPIClient
from molten.outputchunks import Output, OutputStatus


@pytest.fixture
def runtime(monkeypatch):
    runtime = JupyterRuntime.__new__(JupyterRuntime)
    runtime.state = RuntimeState.STARTING
    runtime.kernel_id = runtime.kernel_name = "test"
    runtime.external_kernel = False
    runtime.kernel_manager = Mock(is_alive=Mock(return_value=True))
    runtime.kernel_client = jupyter_client.BlockingKernelClient()
    runtime.nvim = Mock()
    runtime.allocated_files = []
    runtime._startup_deadline = float("inf")
    runtime._kernel_info = None
    runtime._iopub_connected = False
    runtime._next_info_request = 0
    runtime._shutdown_started = False
    for method in ("get_shell_msg", "get_iopub_msg", "get_stdin_msg"):
        monkeypatch.setattr(runtime.kernel_client, method, Mock(side_effect=Empty))
    monkeypatch.setattr(runtime.kernel_client, "kernel_info", Mock())
    monkeypatch.setattr(runtime.kernel_client, "wait_for_ready", Mock(side_effect=RuntimeError))
    return runtime


def test_startup_never_calls_blocking_readiness(runtime):
    runtime.tick(None)
    runtime.kernel_client.wait_for_ready.assert_not_called()
    assert runtime.state == RuntimeState.STARTING


def test_ready_requires_shell_reply_and_iopub(runtime):
    reply = {"msg_type": "kernel_info_reply", "content": {"protocol_version": "5.3"}}
    runtime.kernel_client.get_shell_msg.side_effect = [reply, Empty]
    runtime.tick(None)
    assert not runtime.is_ready()
    runtime.kernel_client.get_iopub_msg.side_effect = [
        {"msg_type": "status", "content": {"execution_state": "idle"}}, Empty]
    assert runtime.tick(None)
    assert runtime.state == RuntimeState.IDLE


def test_ready_waits_for_handshake_idle(runtime):
    runtime.kernel_client.get_shell_msg.side_effect = [
        {"msg_type": "kernel_info_reply", "content": {"protocol_version": "5.3"}}, Empty]
    runtime.kernel_client.get_iopub_msg.side_effect = [
        {"msg_type": "status", "content": {"execution_state": "busy"}}, Empty]
    assert not runtime.tick(None)
    assert runtime.state == RuntimeState.STARTING


@pytest.mark.parametrize("dead", [True, False])
def test_startup_failure_is_reported_once(runtime, monkeypatch, dead):
    runtime.kernel_manager.is_alive.return_value = not dead
    runtime._startup_deadline = 0 if not dead else float("inf")
    shutdown = Mock()
    monkeypatch.setattr(runtime, "_shutdown", shutdown, raising=False)
    runtime.tick(None)
    assert runtime.state == RuntimeState.FAILED
    assert not runtime.is_ready()
    runtime.tick(None)
    assert runtime.nvim.api.exec_autocmds.call_count == 1
    assert runtime.nvim.api.exec_autocmds.call_args.args[1]["pattern"] == "MoltenKernelFailed"


def test_stdin_is_not_polled_before_ready(runtime):
    runtime.tick_input()
    runtime.kernel_client.get_stdin_msg.assert_not_called()


def test_remote_readiness_uses_websocket(runtime):
    client = JupyterAPIClient.__new__(JupyterAPIClient)
    client._socket = Mock()
    client._recv_queue = Queue()
    runtime.kernel_client = client
    runtime.tick(None)
    request = json.loads(client._socket.send.call_args.args[0])
    assert request["header"]["msg_type"] == "kernel_info_request"
    client._recv_queue.put({"msg_type": "kernel_info_reply", "content": {}})
    client._recv_queue.put({"msg_type": "status", "content": {"execution_state": "idle"}})
    assert runtime.tick(None)


@pytest.mark.parametrize("working", [True, False])
def test_subprocess_startup_does_not_block_ticks(tmp_path, monkeypatch, working):
    spec = tmp_path / "kernels" / "runtime-test"
    spec.mkdir(parents=True)
    argv = ([sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"]
            if working else [sys.executable, "-c", "raise SystemExit(1)"])
    (spec / "kernel.json").write_text(json.dumps({
        "argv": argv, "display_name": "Runtime test", "language": "python",
    }))
    monkeypatch.setenv("JUPYTER_PATH", str(tmp_path))
    options = SimpleNamespace(copy_output=False, show_mimetype_debug=False)
    runtime = JupyterRuntime(Mock(), "runtime-test", "runtime-test", options)
    durations = []
    try:
        deadline = time.monotonic() + 10
        while runtime.state == RuntimeState.STARTING and time.monotonic() < deadline:
            started = time.monotonic()
            runtime.tick(None)
            durations.append(time.monotonic() - started)
            time.sleep(0.02)
        assert runtime.state == (RuntimeState.IDLE if working else RuntimeState.FAILED)
        assert max(durations) < 0.1
        if working:
            output = Output(1)
            output.status = OutputStatus.HOLD
            runtime.run_code("print('runtime ready')")
            deadline = time.monotonic() + 5
            while output.status != OutputStatus.DONE and time.monotonic() < deadline:
                runtime.tick(output)
                time.sleep(0.02)
            assert output.status == OutputStatus.DONE
            assert "runtime ready" in "".join(chunk.text for chunk in output.chunks)
    finally:
        runtime.deinit()
        deadline = time.monotonic() + 5
        while runtime.kernel_manager.has_kernel and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not runtime.kernel_manager.has_kernel

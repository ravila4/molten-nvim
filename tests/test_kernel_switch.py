from queue import Queue
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from molten import Molten
from molten.moltenbuffer import MoltenKernel
from molten.outputchunks import Output, OutputStatus
from molten.runtime_state import RuntimeState
from molten.utils import MoltenException


@pytest.fixture
def kernel(monkeypatch):
    kernel = MoltenKernel.__new__(MoltenKernel)
    kernel.nvim = Mock()
    kernel.kernel_id = "stable-id"
    kernel.options = SimpleNamespace()
    kernel.runtime = Mock(state=RuntimeState.IDLE, allocated_files=["saved-image.png"])
    kernel.outputs = {"cell": SimpleNamespace(output=Output(1))}
    kernel.outputs["cell"].output.status = OutputStatus.DONE
    kernel.queued_outputs = Queue()
    kernel.current_output = "cell"
    monkeypatch.setattr("molten.moltenbuffer.JupyterRuntime", Mock())
    return kernel


def test_switch_preserves_outputs_and_image_files(kernel):
    outputs = kernel.outputs
    previous = kernel.runtime
    kernel.switch_kernel("new-environment")
    assert kernel.outputs is outputs
    assert kernel.kernel_id == "stable-id"
    assert kernel.runtime.allocated_files == ["saved-image.png"]
    assert previous.allocated_files == []
    previous.deinit.assert_called_once()


@pytest.mark.parametrize("busy", ["running", "queued"])
def test_switch_rejects_pending_execution(kernel, busy):
    previous = kernel.runtime
    if busy == "running":
        kernel.outputs["cell"].output.status = OutputStatus.RUNNING
    else:
        kernel.queued_outputs.put("cell")
    with pytest.raises(MoltenException, match="running or queued"):
        kernel.switch_kernel("new-environment")
    assert kernel.runtime is previous


def test_switch_command_uses_current_buffer_kernel(kernel):
    plugin = Molten(kernel.nvim)
    plugin.initialized = True
    plugin.buffers[kernel.nvim.current.buffer.number] = [kernel]
    plugin.command_switch_kernel(["new-environment"])
    assert kernel.runtime is not None
    assert kernel.runtime.allocated_files == ["saved-image.png"]


def test_kernel_name_reports_runtime_not_stable_id(kernel):
    kernel.runtime.kernel_name = "chosen-environment"
    plugin = Molten(kernel.nvim)
    plugin.buffers[kernel.nvim.current.buffer.number] = [kernel]
    assert plugin.function_kernel_name([]) == "chosen-environment"


def test_kernel_name_is_empty_without_attached_kernel(kernel):
    assert Molten(kernel.nvim).function_kernel_name([]) == ""


@pytest.mark.parametrize("buffer_local", [True, False])
def test_statusline_displays_selected_environment_not_original_id(kernel, buffer_local):
    kernel.runtime.kernel_name = "chosen-environment"
    plugin = Molten(kernel.nvim)
    plugin.initialized = True
    plugin.buffers[kernel.nvim.current.buffer.number] = [kernel]
    plugin.molten_kernels[kernel.kernel_id] = kernel
    assert plugin.function_status_line_kernels([buffer_local]) == "chosen-environment"


def test_execution_before_ready_preserves_saved_output(kernel):
    kernel.runtime.is_ready.return_value = False
    kernel.try_delete_overlapping_cells = Mock(return_value=False)
    outputs = dict(kernel.outputs)
    with pytest.raises(MoltenException, match="not ready"):
        kernel.run_code("print(1)", "cell")
    assert kernel.outputs == outputs
    kernel.runtime.run_code.assert_not_called()


def test_failed_switch_launch_preserves_previous_runtime(kernel, monkeypatch):
    previous = kernel.runtime
    monkeypatch.setattr("molten.moltenbuffer.JupyterRuntime", Mock(side_effect=RuntimeError("launch")))
    with pytest.raises(RuntimeError, match="launch"):
        kernel.switch_kernel("missing")
    assert kernel.runtime is previous
    previous.deinit.assert_not_called()


def test_restart_failed_kernel_creates_fresh_runtime(kernel):
    previous = kernel.runtime
    previous.state = RuntimeState.FAILED
    kernel.restart()
    assert kernel.runtime is not previous

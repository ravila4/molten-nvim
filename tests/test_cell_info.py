from datetime import datetime, timezone
from pathlib import Path
from queue import Queue
from types import SimpleNamespace

import nbformat
import pynvim
import pytest
from molten import Molten
from molten.code_cell import CodeCell
from molten.ipynb import import_outputs
from molten.moltenbuffer import MoltenKernel
from molten.outputchunks import Output, OutputStatus
from molten.position import Position
from molten.save_load import load, save


def test_deinit_event_identifies_terminated_kernel():
    events = []
    kernel = MoltenKernel.__new__(MoltenKernel)
    kernel.kernel_id = "python"
    kernel.runtime = SimpleNamespace(deinit=lambda: None)
    kernel.nvim = SimpleNamespace(
        api=SimpleNamespace(exec_autocmds=lambda event, opts: events.append((event, dict(opts))))
    )
    kernel.deinit()
    assert events[-1] == ("User", {"pattern": "MoltenDeinitPost", "data": {"kernel_id": "python"}})


def test_polling_finishes_cell_with_sidebar_focused(notebook_kernel):
    nvim, kernel = notebook_kernel
    notebook = nvim.current.buffer.number
    nvim.current.buffer[:] = ["print(1)"]
    cell = CodeCell(nvim, Position(notebook, 0, 0), Position(notebook, 0, 8))
    output = Output(1)
    output.status = OutputStatus.RUNNING
    kernel.outputs[cell] = SimpleNamespace(output=output)
    kernel.current_output = cell
    kernel.queued_outputs = Queue()
    kernel.options = SimpleNamespace(
        auto_open_html_in_browser=False, auto_image_popup=False, output_show_exec_time=False
    )

    def receive_result(output):
        output.status = OutputStatus.DONE
        return True

    kernel.runtime = SimpleNamespace(is_ready=lambda: True, tick=receive_result)
    plugin = Molten(nvim)
    plugin.initialized = True
    plugin.buffers[notebook] = [kernel]
    plugin.molten_kernels[kernel.kernel_id] = kernel
    nvim.command("new")
    plugin.function_molten_tick([])
    assert plugin.function_cell_info([notebook])[0]["status"] == "done"


def test_input_polling_reaches_kernel_with_sidebar_focused(notebook_kernel):
    nvim, kernel = notebook_kernel
    received = []
    kernel.runtime = SimpleNamespace(tick_input=lambda: received.append("input"))
    plugin = Molten(nvim)
    plugin.initialized = True
    plugin.buffers[nvim.current.buffer.number] = [kernel]
    plugin.molten_kernels[kernel.kernel_id] = kernel
    nvim.command("new")
    plugin.function_molten_tick_input([])
    assert received == ["input"]


@pytest.fixture
def notebook_kernel():
    nvim = pynvim.attach("child", argv=["nvim", "--embed", "--headless", "-u", "NONE"])
    nvim.command(f"set runtimepath+={Path(__file__).resolve().parents[1]}")
    kernel = MoltenKernel.__new__(MoltenKernel)
    kernel.nvim = nvim
    kernel.canvas = None
    kernel.extmark_namespace = nvim.api.create_namespace("test-cells")
    kernel.options = SimpleNamespace(virt_text_output=True)
    kernel.outputs = {}
    kernel.kernel_id = "python"
    kernel.buffers = [nvim.current.buffer]
    yield nvim, kernel
    kernel.outputs.clear()
    try:
        nvim.command("qa!")
    except EOFError:
        pass


def test_import_preserves_saved_source_after_edit(notebook_kernel, tmp_path, monkeypatch):
    nvim, kernel = notebook_kernel
    nvim.current.buffer[:] = ["print(1)"]
    monkeypatch.setattr(kernel, "update_interface", lambda: None)
    path = tmp_path / "saved.ipynb"
    nbformat.write(
        nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell("print(1)", execution_count=2)]),
        path,
    )
    import_outputs(nvim, kernel, str(path))
    nvim.current.buffer[0] = "print(2)"
    plugin = Molten(nvim)
    plugin.buffers[nvim.current.buffer.number] = [kernel]
    info = plugin.function_cell_info([])[0]
    assert (info["source"], info["old"], info["execution_count"]) == ("print(1)", True, 2)


def test_define_cell_is_unexecuted(notebook_kernel):
    nvim, kernel = notebook_kernel
    nvim.current.buffer[:] = ["print(1)"]
    plugin = Molten(nvim)
    plugin.buffers[nvim.current.buffer.number] = [kernel]
    plugin.canvas = object()
    plugin.options = kernel.options
    plugin.extmark_namespace = kernel.extmark_namespace
    plugin.function_molten_define_cell([1, 1])
    info = plugin.function_cell_info([])[0]
    assert (info["source"], info["status"]) == ("print(1)", "not run")


def test_save_load_preserves_execution_source(notebook_kernel):
    nvim, kernel = notebook_kernel
    nvim.current.buffer[:] = ["print(2)"]
    cell = CodeCell(
        nvim, Position(nvim.current.buffer.number, 0, 0), Position(nvim.current.buffer.number, 0, 8)
    )
    output = Output(1)
    output.source = "print(1)"
    output.status = OutputStatus.DONE
    kernel.outputs[cell] = SimpleNamespace(output=output)
    kernel.runtime = SimpleNamespace(kernel_name="python")
    saved = save(kernel, nvim.current.buffer.number)
    kernel.outputs.clear()
    load(nvim, kernel, nvim.current.buffer, saved)
    assert next(iter(kernel.outputs.values())).output.source == "print(1)"


@pytest.mark.parametrize(
    "state,success,expected",
    [
        (OutputStatus.HOLD, True, "queued"),
        (OutputStatus.RUNNING, True, "running"),
        (OutputStatus.DONE, True, "done"),
        (OutputStatus.DONE, False, "error"),
        (OutputStatus.NEW, True, "not run"),
    ],
)
def test_info_maps_status_and_filters_shared_kernel(state, success, expected):
    plugin = Molten(SimpleNamespace(current=SimpleNamespace(buffer=SimpleNamespace(number=7))))
    output = Output(None)
    output.source = "print(1)"
    output.status, output.success, output.old = state, success, True
    cell = CodeCell(None, Position(7, 2, 0), Position(7, 3, 8))
    foreign = CodeCell(None, Position(8, 0, 0), Position(8, 0, 5))
    kernel = SimpleNamespace(
        kernel_id="python",
        outputs={cell: SimpleNamespace(output=output), foreign: SimpleNamespace(output=output)},
    )
    plugin.buffers = {7: [kernel]}
    assert plugin.function_cell_info([7]) == [
        {
            "start_line": 2,
            "end_line": 3,
            "start_col": 0,
            "end_col": 8,
            "status": expected,
            "execution_count": 0,
            "old": True,
            "source": "print(1)",
            "kernel_id": "python",
            "started_at": None,
            "finished_at": None,
        }
    ]
    assert plugin.function_cell_info([99]) == []


def test_info_exposes_execution_timestamps():
    plugin = Molten(SimpleNamespace(current=SimpleNamespace(buffer=SimpleNamespace(number=7))))
    output = Output(1)
    output.start_time = datetime(2026, 9, 15, 12, 0, 0, tzinfo=timezone.utc)
    output.end_time = datetime(2026, 9, 15, 12, 0, 2, 800000, tzinfo=timezone.utc)
    cell = CodeCell(None, Position(7, 0, 0), Position(7, 0, 8))
    plugin.buffers = {
        7: [SimpleNamespace(kernel_id="python", outputs={cell: SimpleNamespace(output=output)})]
    }
    info = plugin.function_cell_info([7])[0]
    assert info["started_at"] == output.start_time.timestamp()
    assert info["finished_at"] - info["started_at"] == pytest.approx(2.8)


def test_run_captures_executed_source(monkeypatch):
    kernel = MoltenKernel.__new__(MoltenKernel)
    kernel.nvim = SimpleNamespace(
        exec_lua=lambda _: None,
        lua=SimpleNamespace(_ow=None),
        buffers={1: None},
        funcs=SimpleNamespace(nvim_create_buf=lambda *a: 1),
    )
    kernel.canvas = None
    kernel.extmark_namespace = 1
    kernel.options = SimpleNamespace(virt_text_output=True)
    kernel.outputs = {}
    kernel.queued_outputs = Queue()
    kernel.current_output = None
    kernel.runtime = SimpleNamespace(run_code=lambda code: None, is_ready=lambda: True)
    monkeypatch.setattr(kernel, "update_interface", lambda: None)
    cell = CodeCell(None, Position(7, 0, 0), Position(7, 0, 8))
    kernel.run_code("print(1)", cell)
    assert kernel.outputs[cell].output.source == "print(1)"


def test_update_event_while_another_buffer_is_focused():
    events = []
    kernel = MoltenKernel.__new__(MoltenKernel)
    kernel.kernel_id = "python"
    kernel.buffers = [SimpleNamespace(number=7)]
    kernel.nvim = SimpleNamespace(
        api=SimpleNamespace(exec_autocmds=lambda event, opts: events.append((event, opts))),
        current=SimpleNamespace(buffer=SimpleNamespace(number=8)),
    )
    kernel.update_interface()
    assert events == [
        (
            "User",
            {
                "pattern": "MoltenCellUpdate",
                "data": {
                    "buffers": [7],
                    "kernel_id": "python",
                },
            },
        )
    ]

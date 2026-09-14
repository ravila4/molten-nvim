import weakref
from pathlib import Path
from types import SimpleNamespace

import pynvim
import pytest
from molten import Molten
from molten.code_cell import CodeCell
from molten.moltenbuffer import MoltenKernel
from molten.outputbuffer import OutputBuffer
from molten.outputchunks import OutputStatus
from molten.position import DynamicPosition, Position
from molten.utils import MoltenException


@pytest.fixture
def plugin(monkeypatch):
    nvim = pynvim.attach("child", argv=["nvim", "--embed", "--headless", "-u", "NONE"])
    nvim.command(f"set runtimepath+={Path(__file__).resolve().parents[1]}")
    nvim.current.buffer[:] = ["first()", "", "second()", "", "third()"]
    plugin = Molten(nvim)
    plugin.test_spans = []
    kernel = MoltenKernel.__new__(MoltenKernel)
    kernel.nvim = nvim
    kernel.kernel_id = "python"
    kernel.extmark_namespace = nvim.api.create_namespace("snapshot-spans")
    kernel.highlight_namespace = nvim.api.create_namespace("snapshot-highlights")
    kernel.canvas = None
    kernel.options = SimpleNamespace(virt_text_output=True)
    kernel.outputs = {}
    kernel.current_output = None
    kernel.selected_cell = None
    kernel.buffers = [nvim.current.buffer]
    monkeypatch.setattr(kernel, "update_interface", lambda: None)
    plugin.buffers[nvim.current.buffer.number] = [kernel]
    plugin.molten_kernels[kernel.kernel_id] = kernel
    yield plugin
    for span in plugin.test_spans:
        span.begin = Position(span.bufno, 0, 0)
        span.end = Position(span.bufno, 0, 0)
    kernel.outputs.clear()
    try:
        nvim.command("qa!")
    except EOFError:
        pass


def add_output(plugin, line, bufnr=None):
    kernel = next(iter(plugin.molten_kernels.values()))
    bufnr = bufnr or plugin.nvim.current.buffer.number
    span = CodeCell(
        plugin.nvim,
        DynamicPosition(plugin.nvim, kernel.extmark_namespace, bufnr, line, 0),
        DynamicPosition(plugin.nvim, kernel.extmark_namespace, bufnr, line, 7),
    )
    output = OutputBuffer(plugin.nvim, None, kernel.extmark_namespace, kernel.options)
    output.output.status = OutputStatus.DONE
    output.output.source = "first()"
    kernel.outputs[span] = output
    plugin.test_spans.append(span)
    return kernel, span, output


def test_snapshot_stable_ids_filter_shared_kernel(plugin):
    add_output(plugin, 0)
    bufnr = plugin.nvim.current.buffer.number
    foreign = plugin.nvim.api.create_buf(True, False)
    foreign[:] = ["other()"]
    add_output(plugin, 0, foreign.number)
    snapshot = plugin.function_cell_snapshot([bufnr])
    assert len(snapshot) == 1
    assert snapshot == plugin.function_cell_snapshot([bufnr])
    assert {key: value for key, value in snapshot[0].items() if key != "id"} == {
        "kernel_id": "python",
        "start_line": 0,
        "end_line": 0,
        "start_col": 0,
        "end_col": 7,
    }


def test_detach_reattach_preserves_output_and_span_identity(plugin):
    kernel, span, output = add_output(plugin, 0)
    bufnr = plugin.nvim.current.buffer.number
    snapshot = plugin.function_cell_snapshot([bufnr])
    plugin.function_cell_restore([bufnr, []])
    assert kernel.outputs == {}
    plugin.function_cell_restore([bufnr, snapshot])
    assert kernel.outputs[span] is output


def test_move_preserves_running_cell_identity(plugin):
    kernel, span, output = add_output(plugin, 0)
    output.output.status = OutputStatus.RUNNING
    kernel.current_output = span
    bufnr = plugin.nvim.current.buffer.number
    snapshot = plugin.function_cell_snapshot([bufnr])
    snapshot[0].update(start_line=4, end_line=4)
    plugin.function_cell_restore([bufnr, snapshot])
    assert kernel.current_output is span
    assert kernel.outputs[span] is output
    assert (span.begin.lineno, span.end.lineno) == (4, 4)


@pytest.mark.parametrize("status", [OutputStatus.HOLD, OutputStatus.RUNNING])
def test_restore_rejects_detaching_active_cell_without_changes(plugin, status):
    kernel, span, output = add_output(plugin, 0)
    output.output.status = status
    bufnr = plugin.nvim.current.buffer.number
    plugin.function_cell_snapshot([bufnr])
    with pytest.raises(MoltenException, match="queued or running"):
        plugin.function_cell_restore([bufnr, []])
    assert kernel.outputs[span] is output


def test_restore_leaves_other_buffer_outputs_attached(plugin):
    kernel, _, _ = add_output(plugin, 0)
    bufnr = plugin.nvim.current.buffer.number
    foreign = plugin.nvim.api.create_buf(True, False)
    foreign[:] = ["other()"]
    _, foreign_span, foreign_output = add_output(plugin, 0, foreign.number)
    plugin.function_cell_snapshot([bufnr])
    plugin.function_cell_restore([bufnr, []])
    assert kernel.outputs == {foreign_span: foreign_output}


@pytest.mark.parametrize(
    "change",
    [
        {"id": -1},
        {"start_line": -1},
        {"end_line": 20},
        {"end_col": 200},
    ],
)
def test_restore_validates_before_detaching_outputs(plugin, change):
    kernel, span, output = add_output(plugin, 0)
    bufnr = plugin.nvim.current.buffer.number
    snapshot = plugin.function_cell_snapshot([bufnr])
    snapshot[0].update(change)
    with pytest.raises(MoltenException):
        plugin.function_cell_restore([bufnr, snapshot])
    assert kernel.outputs[span] is output


def test_restore_rejects_overlapping_ranges(plugin):
    kernel, _, _ = add_output(plugin, 0)
    add_output(plugin, 2)
    bufnr = plugin.nvim.current.buffer.number
    snapshot = plugin.function_cell_snapshot([bufnr])
    snapshot[1].update(start_line=0, end_line=0)
    with pytest.raises(MoltenException, match="overlap"):
        plugin.function_cell_restore([bufnr, snapshot])
    assert len(kernel.outputs) == 2


def test_restore_invalidates_virtual_output_cache(plugin):
    kernel, _, output = add_output(plugin, 0)
    bufnr = plugin.nvim.current.buffer.number
    old_mark = plugin.nvim.api.buf_set_extmark(bufnr, kernel.extmark_namespace, 0, 0, {})
    output.virt_text_id = old_mark
    output.displayed_status = OutputStatus.DONE
    snapshot = plugin.function_cell_snapshot([bufnr])
    snapshot[0].update(start_line=4, end_line=4)
    plugin.function_cell_restore([bufnr, snapshot])
    assert output.virt_text_id is None
    assert (
        plugin.nvim.api.buf_get_extmark_by_id(bufnr, kernel.extmark_namespace, old_mark, {}) == []
    )


def test_kernel_deinit_releases_detached_outputs(plugin, monkeypatch):
    kernel, _, output = add_output(plugin, 0)
    output_ref = weakref.ref(output)
    bufnr = plugin.nvim.current.buffer.number
    plugin.function_cell_snapshot([bufnr])
    plugin.function_cell_restore([bufnr, []])
    del output
    monkeypatch.setattr(kernel, "deinit", lambda: None)
    plugin._deinit_buffer([kernel])
    assert output_ref() is None

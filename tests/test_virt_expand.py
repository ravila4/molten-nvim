from types import SimpleNamespace
from unittest.mock import Mock

from molten import Molten
from molten.moltenbuffer import MoltenKernel
from molten.outputbuffer import OutputBuffer

LINES = ["header", "row 1", "row 2", "row 3", "row 4"]


def output_buffer(expanded: bool) -> OutputBuffer:
    buffer = OutputBuffer.__new__(OutputBuffer)
    buffer.options = SimpleNamespace(virt_text_max_lines=3, image_provider="none")
    buffer.canvas = Mock()
    buffer.virt_expanded = expanded
    return buffer


def test_truncated_output_ends_with_more_lines_footer() -> None:
    lines = output_buffer(False).truncate_virt_lines(list(LINES), [])
    assert lines == ["header", "row 1", "󰁅 3 More Lines "]


def test_expanded_output_keeps_every_line_and_offers_collapse() -> None:
    lines = output_buffer(True).truncate_virt_lines(list(LINES), [])
    assert lines == LINES + ["󰁝 Show Less "]


def test_expanded_output_within_limit_has_no_footer() -> None:
    lines = output_buffer(True).truncate_virt_lines(["header", "row 1"], [])
    assert lines == ["header", "row 1"]


def test_output_buffer_is_collapsed_by_default() -> None:
    assert OutputBuffer.virt_expanded is False


def kernel_with(span: object, output: object) -> MoltenKernel:
    kernel = MoltenKernel.__new__(MoltenKernel)
    kernel.outputs = {span: output}
    kernel.update_interface = Mock()
    return kernel


def test_toggle_virt_expand_flips_flag_and_repaints_cell() -> None:
    span = Mock(bufno=3)
    output = SimpleNamespace(virt_expanded=False, clear_virt_output=Mock())
    kernel = kernel_with(span, output)

    assert kernel.toggle_virt_expand(span) is True
    assert output.virt_expanded is True
    output.clear_virt_output.assert_called_once_with(3)
    kernel.update_interface.assert_called_once()

    assert kernel.toggle_virt_expand(span) is True
    assert output.virt_expanded is False


def test_toggle_virt_expand_uses_cell_under_cursor() -> None:
    span = Mock(bufno=3)
    output = SimpleNamespace(virt_expanded=False, clear_virt_output=Mock())
    kernel = kernel_with(span, output)
    kernel._get_selected_span = lambda: span

    assert kernel.toggle_virt_expand() is True
    assert output.virt_expanded is True


def test_toggle_virt_expand_without_cell_does_nothing() -> None:
    kernel = kernel_with(Mock(bufno=3), SimpleNamespace(virt_expanded=False))
    kernel._get_selected_span = lambda: None

    assert kernel.toggle_virt_expand() is False
    kernel.update_interface.assert_not_called()


def test_toggle_function_targets_output_by_extmark_id() -> None:
    plugin = Molten(SimpleNamespace())
    span = Mock(bufno=7)
    kernel = Mock()
    kernel.toggle_virt_expand.return_value = True
    kernel.outputs = {span: SimpleNamespace(virt_text_id=23)}
    plugin.buffers = {7: [kernel]}

    assert plugin.function_toggle_virt_expand_at([7, 23]) is True
    kernel.toggle_virt_expand.assert_called_once_with(span)
    assert plugin.function_toggle_virt_expand_at([7, 99]) is False

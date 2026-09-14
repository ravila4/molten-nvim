from dataclasses import dataclass
from itertools import pairwise
from typing import TypedDict

from pynvim import Nvim

from molten.code_cell import CodeCell
from molten.moltenbuffer import MoltenKernel
from molten.outputbuffer import OutputBuffer
from molten.outputchunks import OutputStatus
from molten.position import DynamicPosition
from molten.utils import MoltenException


class SnapshotEntry(TypedDict):
    id: int
    kernel_id: str
    start_line: int
    end_line: int
    start_col: int
    end_col: int


@dataclass
class RetainedCell:
    kernel: MoltenKernel
    span: CodeCell
    output: OutputBuffer


class CellSnapshots:
    """Retain output objects while notebook edits detach or move their cells."""

    def __init__(self, nvim: Nvim):
        self.nvim = nvim
        self.cells: dict[int, RetainedCell] = {}

    def snapshot(self, bufnr: int, kernels: list[MoltenKernel]) -> list[SnapshotEntry]:
        cells = []
        for kernel in kernels:
            for span, output in kernel.outputs.items():
                if span.bufno != bufnr:
                    continue
                cell_id = id(output)
                self.cells[cell_id] = RetainedCell(kernel, span, output)
                cells.append(
                    {
                        "id": cell_id,
                        "kernel_id": kernel.kernel_id,
                        "start_line": span.begin.lineno,
                        "end_line": span.end.lineno,
                        "start_col": span.begin.colno,
                        "end_col": span.end.colno,
                    }
                )
        return cells

    def discard_kernel(self, kernel: MoltenKernel) -> None:
        self.cells = {
            cell_id: cell for cell_id, cell in self.cells.items() if cell.kernel is not kernel
        }

    def restore(
        self, bufnr: int, kernels: list[MoltenKernel], entries: list[SnapshotEntry]
    ) -> bool:
        retained = []
        ids = set()
        lines = self.nvim.buffers[bufnr][:]
        for entry in entries:
            cell = self.cells.get(entry.get("id"))
            if cell is None or cell.span.bufno != bufnr or cell.kernel not in kernels:
                raise MoltenException("Unknown cell snapshot for this buffer or kernel")
            if entry["id"] in ids:
                raise MoltenException("Duplicate cell snapshot ID")
            ids.add(entry["id"])
            for prefix in ("start", "end"):
                line, col = entry.get(f"{prefix}_line"), entry.get(f"{prefix}_col")
                if (
                    not isinstance(line, int)
                    or not isinstance(col, int)
                    or not 0 <= line < len(lines)
                    or not 0 <= col <= len(lines[line].encode("utf-8"))
                ):
                    raise MoltenException("Cell snapshot position is outside the buffer")
            if (entry["start_line"], entry["start_col"]) > (entry["end_line"], entry["end_col"]):
                raise MoltenException("Cell snapshot range is reversed")
            retained.append((cell, entry))

        ordered = sorted(entries, key=lambda entry: (entry["start_line"], entry["start_col"]))
        for previous, following in pairwise(ordered):
            if (previous["end_line"], previous["end_col"]) > (
                following["start_line"],
                following["start_col"],
            ):
                raise MoltenException("Cell snapshot ranges overlap")

        for kernel in kernels:
            for span, output in kernel.outputs.items():
                if (
                    span.bufno == bufnr
                    and id(output) not in ids
                    and output.output.status in (OutputStatus.HOLD, OutputStatus.RUNNING)
                ):
                    raise MoltenException("Cannot detach a queued or running cell")

        for kernel in kernels:
            for span, output in list(kernel.outputs.items()):
                if span.bufno != bufnr:
                    continue
                output.clear_float_win()
                output.clear_virt_output(bufnr)
                output.virt_text_id = None
                span.clear_interface(kernel.highlight_namespace)
                del kernel.outputs[span]
                if id(output) not in ids:
                    if kernel.current_output is span:
                        kernel.current_output = None
                    if kernel.selected_cell is span:
                        kernel.selected_cell = None

        for cell, entry in retained:
            cell.span.begin = DynamicPosition(
                self.nvim,
                cell.kernel.extmark_namespace,
                bufnr,
                entry["start_line"],
                entry["start_col"],
            )
            cell.span.end = DynamicPosition(
                self.nvim,
                cell.kernel.extmark_namespace,
                bufnr,
                entry["end_line"],
                entry["end_col"],
                right_gravity=True,
            )
            cell.kernel.outputs[cell.span] = cell.output

        for kernel in kernels:
            kernel.update_interface()
        return True

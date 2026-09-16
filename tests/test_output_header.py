from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from molten.options import MoltenOptions
from molten.outputbuffer import OutputBuffer
from molten.outputchunks import Output, OutputStatus


@pytest.mark.parametrize("old", [False, True])
@pytest.mark.parametrize("success", [False, True])
def test_header_can_omit_status_and_runtime(old: bool, success: bool) -> None:
    nvim = Mock()
    nvim.vars = {
        "molten_output_show_status": False,
        "molten_output_show_exec_time": False,
    }
    nvim.funcs.stdpath.return_value = "/tmp"
    options = MoltenOptions(nvim)
    output = Output(None)
    output.execution_count = 2
    output.status = OutputStatus.DONE
    output.success = success
    output.old = old
    output.start_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    output.end_time = output.start_time + timedelta(seconds=0.1)

    header = OutputBuffer._get_header_text(SimpleNamespace(options=options), output)

    assert header == ("[OLD] Out[2]:" if old else "Out[2]:")

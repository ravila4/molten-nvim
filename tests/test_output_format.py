from types import SimpleNamespace
from unittest.mock import Mock

from molten import Molten
from molten.options import MoltenOptions
from molten.outputchunks import Output, TextLnOutputChunk, TextOutputChunk, to_outputchunk

PANDAS_PLAIN = "   a\n0  1\n"
PANDAS_HTML = (
    "<div><table><thead><tr><th></th><th>a</th></tr></thead>"
    "<tbody><tr><th>0</th><td>1</td></tr></tbody></table></div>"
)
PANDAS_TABLE = "|     | a   |\n| --- | --- |\n| 0   | 1   |"


def options(**vars: object) -> MoltenOptions:
    nvim = Mock()
    nvim.vars = {f"molten_{k}": v for k, v in vars.items()}
    nvim.funcs.stdpath.return_value = "/tmp"
    return MoltenOptions(nvim)


def chunk_for(data: dict, fmt: str = "plain") -> TextOutputChunk:
    chunk = to_outputchunk(Mock(), Mock(), data, {}, options(output_format=fmt))
    assert isinstance(chunk, TextOutputChunk)
    return chunk


def test_output_format_defaults_to_plain() -> None:
    assert options().output_format == "plain"


def test_display_text_returns_plain_by_default() -> None:
    chunk = TextOutputChunk("plain", markdown="**md**")
    assert chunk.display_text(options()) == "plain"


def test_display_text_returns_markdown_when_format_is_markdown() -> None:
    chunk = TextOutputChunk("plain", markdown="**md**")
    assert chunk.display_text(options(output_format="markdown")) == "**md**"


def test_display_text_falls_back_to_text_when_no_markdown() -> None:
    chunk = TextOutputChunk("plain")
    assert chunk.display_text(options(output_format="markdown")) == "plain"


def test_textln_chunk_appends_newline_to_both_variants() -> None:
    chunk = TextLnOutputChunk("plain", markdown="**md**")
    assert chunk.text == "plain\n"
    assert chunk.markdown == "**md**\n"
    assert TextLnOutputChunk("plain").markdown is None


def test_to_outputchunk_uses_text_markdown_verbatim() -> None:
    chunk = chunk_for(
        {"text/plain": "<IPython.core.display.Markdown object>", "text/markdown": "**hi**\n"}
    )
    assert chunk.text == "<IPython.core.display.Markdown object>\n"
    assert chunk.markdown == "**hi**\n"


def test_to_outputchunk_converts_html_table() -> None:
    chunk = chunk_for({"text/plain": PANDAS_PLAIN, "text/html": PANDAS_HTML})
    assert chunk.text == PANDAS_PLAIN + "\n"
    assert chunk.markdown == PANDAS_TABLE + "\n"


def test_to_outputchunk_prefers_text_markdown_over_text_html() -> None:
    chunk = chunk_for({"text/plain": "x", "text/html": PANDAS_HTML, "text/markdown": "**md**"})
    assert chunk.markdown == "**md**\n"


def test_to_outputchunk_html_without_table_has_no_markdown() -> None:
    chunk = chunk_for({"text/plain": "x", "text/html": "<div>x</div>"})
    assert chunk.markdown is None


def test_to_outputchunk_plain_only_has_no_markdown() -> None:
    chunk = chunk_for({"text/plain": "x"})
    assert chunk.text == "x\n"
    assert chunk.markdown is None


def test_to_outputchunk_keeps_jupyter_data_intact() -> None:
    data = {"text/plain": PANDAS_PLAIN, "text/html": PANDAS_HTML}
    chunk = chunk_for(data)
    assert chunk.jupyter_data is data
    assert "text/html" in chunk.jupyter_data


def test_to_outputchunk_joins_list_valued_mime_data() -> None:
    chunk = chunk_for({"text/plain": ["a\n", "b\n"], "text/markdown": ["**a**\n", "b\n"]})
    assert chunk.text == "a\nb\n\n"
    assert chunk.markdown == "**a**\nb\n"


def test_output_text_follows_format() -> None:
    output = Output(None)
    output.chunks = [TextOutputChunk("plain ", markdown="**md** "), TextOutputChunk("tail")]
    assert output.text(options()) == "plain tail"
    assert output.text(options(output_format="markdown")) == "**md** tail"


def test_merge_text_chunks_drops_markdown() -> None:
    output = Output(None)
    output.chunks = [TextOutputChunk("table\n", markdown="| t |\n"), TextOutputChunk("x\rdone\n")]
    output.merge_text_chunks()
    assert len(output.chunks) == 1
    assert output.chunks[0].markdown is None


def toggle_plugin(initial: str) -> Molten:
    plugin = Molten(SimpleNamespace())
    plugin.nvim = Mock()
    plugin.nvim.vars = {"molten_output_format": initial}
    plugin.nvim.funcs.stdpath.return_value = "/tmp"
    plugin.nvim.current.buffer.number = 1
    plugin.initialized = True
    plugin.options = MoltenOptions(plugin.nvim)
    plugin.buffers = {}
    return plugin


def test_toggle_output_format_flips_option_and_vim_variable() -> None:
    plugin = toggle_plugin("plain")

    plugin.command_toggle_output_format()
    assert plugin.options.output_format == "markdown"
    assert plugin.nvim.vars["molten_output_format"] == "markdown"

    plugin.command_toggle_output_format()
    assert plugin.options.output_format == "plain"
    assert plugin.nvim.vars["molten_output_format"] == "plain"


NARROW = (0, 0, 20, 10)  # window width 20


def test_place_does_not_hard_wrap_markdown_representation() -> None:
    row = "| " + "a" * 40 + " |\n"
    chunk = TextOutputChunk("x" * 40 + "\n", markdown=row)

    text, extra = chunk.place(
        0, options(output_format="markdown", wrap_output=True), 0, 0, NARROW, Mock(), True
    )

    assert text == row
    assert extra == 0


def test_place_still_hard_wraps_plain_representation() -> None:
    chunk = TextOutputChunk("x" * 40 + "\n", markdown="| " + "a" * 40 + " |\n")

    text, _extra = chunk.place(
        0, options(output_format="plain", wrap_output=True), 0, 0, NARROW, Mock(), True
    )

    assert text.split("\n")[:2] == ["x" * 20, "x" * 20]


def test_place_counts_wrapped_lines_for_markdown_in_float() -> None:
    row = "| " + "a" * 40 + " |\n"
    chunk = TextOutputChunk("x\n", markdown=row)

    text, extra = chunk.place(
        0, options(output_format="markdown", wrap_output=True), 0, 0, NARROW, Mock(), False
    )

    assert text == row
    assert extra == 2

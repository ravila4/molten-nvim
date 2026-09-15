from types import SimpleNamespace

from molten.images import get_canvas_given_provider
from molten.outputbuffer import OutputBuffer
from molten.outputchunks import ImageOutputChunk, Output


class FakeSnacksApi:
    def __init__(self) -> None:
        self.images: dict[str, dict[str, object]] = {}
        self.cleared_all = False

    def from_file(self, path: str, opts: dict[str, object]) -> str:
        identifier = str(opts["id"])
        self.images[identifier] = {"opts": opts, "rendered": False, "closed": False}
        return identifier

    def render(self, identifier: str) -> None:
        self.images[identifier]["rendered"] = True

    def clear(self, identifier: str) -> None:
        self.images[identifier]["closed"] = True

    def clear_all(self) -> None:
        self.cleared_all = True

    def image_size(self, _identifier: str, _winnr: int | None = None) -> dict[str, int]:
        return {"width": 40, "height": 20}


class FakeNvim:
    def __init__(self) -> None:
        self.snacks_api = FakeSnacksApi()
        self.lua = SimpleNamespace(_snacks=self.snacks_api)

    def exec_lua(self, _source: str) -> None:
        return None


def snacks_options() -> SimpleNamespace:
    return SimpleNamespace(
        image_provider="snacks.nvim",
        auto_open_output=False,
        split_direction="right",
        split_size=40,
    )


def test_snacks_provider_queues_image_until_present() -> None:
    nvim = FakeNvim()
    canvas = get_canvas_given_provider(nvim, snacks_options())
    canvas.init()

    identifier = canvas.add_image("plot.png", "virt-plot", 3, 8, 12, row_offset=4)

    assert identifier == "virt-plot"
    assert nvim.snacks_api.images[identifier] == {
        "opts": {"id": "virt-plot", "buffer": 12, "x": 3, "y": 9},
        "rendered": False,
        "closed": False,
    }

    canvas.present()

    assert nvim.snacks_api.images[identifier]["rendered"] is True


def test_snacks_provider_cancels_removal_queued_before_first_render() -> None:
    nvim = FakeNvim()
    canvas = get_canvas_given_provider(nvim, snacks_options())
    canvas.init()

    identifier = canvas.add_image("plot.png", "virt-plot", 0, 2, 7)
    canvas.remove_image(identifier)
    canvas.present()

    assert nvim.snacks_api.images[identifier]["rendered"] is False
    assert nvim.snacks_api.images[identifier]["closed"] is False


def test_snacks_provider_clears_rendered_image() -> None:
    nvim = FakeNvim()
    canvas = get_canvas_given_provider(nvim, snacks_options())
    canvas.init()
    identifier = canvas.add_image("plot.png", "virt-plot", 0, 2, 7)
    canvas.present()

    canvas.remove_image(identifier)
    canvas.present()

    assert nvim.snacks_api.images[identifier]["closed"] is True


def test_snacks_provider_deinitializes_all_images() -> None:
    nvim = FakeNvim()
    canvas = get_canvas_given_provider(nvim, snacks_options())
    canvas.init()

    canvas.deinit()

    assert nvim.snacks_api.cleared_all is True


class FakeCanvas:
    def __init__(self) -> None:
        self.row_offset: int | None = None
        self.removed: list[str] = []

    def add_image(
        self,
        _path: str,
        identifier: str,
        _x: int,
        _y: int,
        _bufnr: int,
        _winnr: int | None = None,
        row_offset: int | None = None,
    ) -> str:
        self.row_offset = row_offset
        return identifier

    def img_size(self, _identifier: str, _winnr: int | None = None) -> dict[str, int]:
        return {"width": 40, "height": 3}

    def remove_image(self, identifier: str) -> None:
        self.removed.append(identifier)


def test_snacks_virtual_image_uses_provider_virtual_lines() -> None:
    canvas = FakeCanvas()
    chunk = ImageOutputChunk("plot.png")
    options = SimpleNamespace(image_location="virt", image_provider="snacks.nvim")

    text, virtual_lines = chunk.place(4, options, 0, 12, (0, 0, 80, 24), canvas, True, 9, 5)

    assert text == " \n"
    assert virtual_lines == 3
    assert canvas.row_offset is None


def test_snacks_output_keeps_anchor_line_for_placement() -> None:
    output_buffer = OutputBuffer.__new__(OutputBuffer)
    output_buffer.nvim = SimpleNamespace(current=SimpleNamespace(window=SimpleNamespace(handle=9)))
    output_buffer.canvas = FakeCanvas()
    output_buffer.options = SimpleNamespace(
        image_location="virt",
        image_provider="snacks.nvim",
        limit_output_chars=0,
    )
    output_buffer.output = Output(None)
    output_buffer.output.chunks = [ImageOutputChunk("plot.png")]
    output_buffer._get_header_text = lambda _output: "header"

    lines, _height, _images = output_buffer.build_output_text((0, 12, 80, 24), 4, True)

    assert lines == ["header", " ", ""]


def test_snacks_image_height_does_not_hide_text_from_truncation() -> None:
    output_buffer = OutputBuffer.__new__(OutputBuffer)
    output_buffer.canvas = FakeCanvas()
    output_buffer.options = SimpleNamespace(
        image_provider="snacks.nvim",
        virt_text_max_lines=2,
    )
    image = ImageOutputChunk("plot.png")
    image.img_identifier = "virt-plot"
    image.height = 20

    lines = output_buffer.truncate_virt_lines(
        ["header", " ", "first line after image", "second line after image"],
        [(image, 1)],
    )

    assert lines == ["header", "󰁅 2 More Lines "]
    assert output_buffer.canvas.removed == ["virt-plot"]

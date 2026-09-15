from types import SimpleNamespace

from molten import Molten
from molten.outputchunks import ImageOutputChunk, Output, TextOutputChunk


def output_buffer(extmark_id: int, *chunks: object) -> SimpleNamespace:
    output = Output(None)
    output.chunks = list(chunks)
    return SimpleNamespace(virt_text_id=extmark_id, output=output)


def test_output_images_returns_image_paths_in_chunk_order() -> None:
    plugin = Molten(SimpleNamespace())
    plugin.buffers = {
        7: [
            SimpleNamespace(
                outputs={
                    "cell": output_buffer(
                        23,
                        ImageOutputChunk("first.png"),
                        TextOutputChunk("between images"),
                        ImageOutputChunk("second.png"),
                    )
                }
            )
        ]
    }

    assert plugin.function_output_images([7, 23]) == ["first.png", "second.png"]


def test_output_images_returns_empty_list_when_output_has_no_images() -> None:
    plugin = Molten(SimpleNamespace())
    plugin.buffers = {
        7: [SimpleNamespace(outputs={"cell": output_buffer(23, TextOutputChunk("text"))})]
    }

    assert plugin.function_output_images([7, 23]) == []


def test_output_images_returns_empty_list_for_unknown_buffer_or_extmark() -> None:
    plugin = Molten(SimpleNamespace())
    plugin.buffers = {
        7: [SimpleNamespace(outputs={"cell": output_buffer(23, ImageOutputChunk("plot.png"))})]
    }

    assert plugin.function_output_images([8, 23]) == []
    assert plugin.function_output_images([7, 24]) == []


def test_output_images_searches_all_kernels_attached_to_buffer() -> None:
    plugin = Molten(SimpleNamespace())
    plugin.buffers = {
        7: [
            SimpleNamespace(
                outputs={"python-cell": output_buffer(11, ImageOutputChunk("python.png"))}
            ),
            SimpleNamespace(
                outputs={
                    "r-cell": output_buffer(
                        23,
                        ImageOutputChunk("r-first.png"),
                        ImageOutputChunk("r-second.png"),
                    )
                }
            ),
        ]
    }

    assert plugin.function_output_images([7, 23]) == ["r-first.png", "r-second.png"]

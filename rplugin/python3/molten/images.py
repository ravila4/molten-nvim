from typing import Dict, Set
from abc import ABC, abstractmethod

from pynvim import Nvim
from molten.options import MoltenOptions

from molten.utils import notify_warn, MoltenException


class Canvas(ABC):
    @abstractmethod
    def init(self) -> None:
        """
        Initialize the canvas.

        This will be called before the canvas is ever used.
        """

    @abstractmethod
    def deinit(self) -> None:
        """
        Deinitialize the canvas.

        The canvas will not be used after this operation.
        """

    @abstractmethod
    def present(self) -> None:
        """
        Present the canvas.

        This is called only when a redraw is necessary -- so, if desired, it
        can be implemented so that `clear` and `add_image` only queue images as
        to be drawn, and `present` actually performs the operations, in order
        to reduce flickering.
        """

    @abstractmethod
    def img_size(self, identifier: str, winnr: int | None = None) -> Dict[str, int]:
        """
        Get the size of an image in terminal cells, as it will be rendered in
        `winnr` when given.
        """

    def img_window_lost(self, _identifier: str) -> bool:
        """
        Whether the window an image was placed in is gone. Canvases that don't
        tie images to a window never lose them.
        """
        return False

    @abstractmethod
    def add_image(
        self,
        path: str,
        identifier: str,
        x: int,
        y: int,
        bufnr: int,
        winnr: int | None = None,
        row_offset: int | None = None,
    ) -> str:
        """
        Add an image to the canvas.
        Takes effect after a call to present()

        Parameters
        - path: str
          Path to the image we want to show
        - x: int
          Column number of where the image is supposed to be drawn at (top-left
          corner).
        - y: int
          Row number of where the image is supposed to be drawn at (top-right
          corner).
        - bufnr: int
          The buffer number for the buffer in which to draw the image.
        - row_offset: int | None
          When set, the image is part of a virtual text block at row y and is
          drawn `row_offset` rows below the first row of that block. The caller
          reserves the rows the image covers.

        Returns:
        str the identifier for the image
        """

    @abstractmethod
    def remove_image(self, identifier: str) -> None:
        """
        Remove an image from the canvas. In practice this is just hiding the image
        Takes effect after a call to present()

        Parameters
        - identifier: str
          The identifier for the image to remove.
        """

    def begin_output(self, _bufnr: int, _row: int, _namespace: int, _mark_id: int) -> str:
        raise NotImplementedError

    def render_image(self, _identifier: str, _output: str) -> None:
        raise NotImplementedError

    def render_text(self, _output: str, _lines: list[str], _highlight: str) -> None:
        raise NotImplementedError

    def finish_output(self, _output: str) -> None:
        raise NotImplementedError

    def clear_output(self, _output: str) -> None:
        raise NotImplementedError


class NoCanvas(Canvas):
    def __init__(self) -> None:
        pass

    def init(self) -> None:
        pass

    def deinit(self) -> None:
        pass

    def present(self) -> None:
        pass

    def img_size(self, _indentifier: str, _winnr: int | None = None) -> Dict[str, int]:
        return {"height": 0, "width": 0}

    def add_image(
        self,
        _path: str,
        _identifier: str,
        _x: int,
        _y: int,
        _bufnr: int,
        _winnr: int | None = None,
        _row_offset: int | None = None,
    ) -> None:
        pass

    def remove_image(self, _identifier: str) -> None:
        pass


class ImageNvimCanvas(Canvas):
    nvim: Nvim
    to_make_visible: Set[str]
    to_make_invisible: Set[str]
    visible: Set[str]

    def __init__(self, nvim: Nvim):
        self.nvim = nvim
        self.visible = set()
        self.to_make_visible = set()
        self.to_make_invisible = set()
        self.next_id = 0

    def init(self) -> None:
        self.nvim.exec_lua("_image = require('load_image_nvim').image_api")
        self.nvim.exec_lua("_image_utils = require('load_image_nvim').image_utils")
        self.image_api = self.nvim.lua._image
        self.image_utils = self.nvim.lua._image_utils

    def deinit(self) -> None:
        self.image_api.clear_all()

    def present(self) -> None:
        # images to both show and hide should be ignored
        to_work_on = self.to_make_visible.difference(
            self.to_make_visible.intersection(self.to_make_invisible)
        )
        self.to_make_invisible.difference_update(self.to_make_visible)
        for identifier in self.to_make_invisible:
            self.image_api.clear(identifier)

        for identifier in to_work_on:
            size = self.img_size(identifier)
            self.image_api.render(identifier, size)

        self.visible.update(self.to_make_visible)
        self.to_make_invisible.clear()
        self.to_make_visible.clear()

    def img_size(self, identifier: str, winnr: int | None = None) -> Dict[str, int]:
        return self.image_api.image_size(identifier, winnr)

    def img_window_lost(self, identifier: str) -> bool:
        return self.image_api.image_window(identifier) is None

    def add_image(
        self,
        path: str,
        identifier: str,
        x: int,
        y: int,
        bufnr: int,
        winnr: int | None = None,
        row_offset: int | None = None,
    ) -> str:
        opts = {
            "id": identifier,
            "buffer": bufnr,
            "x": x,
            "y": y,
            "window": winnr,
        }
        if row_offset is None:
            opts["with_virtual_padding"] = True
        else:
            # inline keeps the image anchored to an extmark so it follows buffer
            # edits, without image.nvim adding padding rows of its own
            opts["inline"] = True
            opts["render_offset_top"] = row_offset
        img = self.image_api.from_file(path, opts)
        self.to_make_visible.add(img)
        return img

    def remove_image(self, identifier: str) -> None:
        self.to_make_invisible.add(identifier)


class SnacksCanvas(Canvas):
    def __init__(self, nvim: Nvim) -> None:
        self.nvim = nvim
        self.to_make_visible: set[str] = set()
        self.to_make_invisible: set[str] = set()

    def init(self) -> None:
        self.nvim.exec_lua("_snacks = require('load_snacks_nvim').snacks_api")
        self.snacks_api = self.nvim.lua._snacks

    def deinit(self) -> None:
        self.snacks_api.clear_all()

    def present(self) -> None:
        to_render = self.to_make_visible - self.to_make_invisible
        self.to_make_invisible -= self.to_make_visible

        for identifier in self.to_make_invisible:
            self.snacks_api.clear(identifier)
        for identifier in to_render:
            self.snacks_api.render(identifier)

        self.to_make_visible.clear()
        self.to_make_invisible.clear()

    def img_size(self, identifier: str, winnr: int | None = None) -> Dict[str, int]:
        return self.snacks_api.image_size(identifier, winnr)

    def add_image(
        self,
        path: str,
        identifier: str,
        x: int,
        y: int,
        bufnr: int,
        winnr: int | None = None,
        row_offset: int | None = None,
    ) -> str:
        del winnr
        image = self.snacks_api.from_file(
            path,
            {
                "id": identifier,
                "buffer": bufnr,
                "x": x,
                "y": y + 1,
                "row_offset": row_offset,
            },
        )
        self.to_make_visible.add(image)
        return image

    def begin_output(self, bufnr: int, row: int, namespace: int, mark_id: int) -> str:
        return self.snacks_api.begin_output(bufnr, row, namespace, mark_id)

    def render_image(self, identifier: str, output: str) -> None:
        if identifier not in self.to_make_visible:
            return
        if identifier not in self.to_make_invisible:
            self.snacks_api.render(identifier, output)
        self.to_make_visible.discard(identifier)
        self.to_make_invisible.discard(identifier)

    def render_text(self, output: str, lines: list[str], highlight: str) -> None:
        self.snacks_api.render_text(output, lines, highlight)

    def finish_output(self, output: str) -> None:
        self.snacks_api.finish_output(output)

    def clear_output(self, output: str) -> None:
        self.snacks_api.clear_output(output)

    def remove_image(self, identifier: str) -> None:
        self.to_make_invisible.add(identifier)


class WeztermCanvas(Canvas):
    """A canvas for using Wezterm's imgcat functionality to render images/plots"""

    nvim: Nvim
    split_dir: str | None
    split_size: int | None
    to_make_visible: Set[str]
    to_make_invisible: Set[str]
    visible: Set[str]

    def __init__(self, nvim: Nvim, split_dir: str | None, split_size: int | None):
        self.nvim = nvim
        self.split_dir = split_dir
        self.split_size = split_size
        self.visible = set()
        self.to_make_visible = set()
        self.to_make_invisible = set()
        self.initial_pane_id: int | None = None
        self.image_pane: int | None = None

    def init(self) -> None:
        self.nvim.exec_lua("_wezterm = require('load_wezterm_nvim').wezterm_api")
        self.wezterm_api = self.nvim.lua._wezterm
        self.initial_pane_id = self.wezterm_api.get_pane_id()

    def deinit(self) -> None:
        """Closes the terminal split that was opened with MoltenInit"""
        self.wezterm_api.close_image_pane(str(self.image_pane).strip())

    def present(self) -> None:
        to_work_on = self.to_make_visible.difference(
            self.to_make_visible.intersection(self.to_make_invisible)
        )
        self.to_make_invisible.difference_update(self.to_make_visible)

        for identifier in to_work_on:
            self.wezterm_api.send_image(
                identifier,
                str(self.image_pane).strip(),
                str(self.initial_pane_id).strip(),
            )

        self.visible.update(self.to_make_visible)
        self.to_make_invisible.clear()
        self.to_make_visible.clear()

    def img_size(self, _indentifier: str, _winnr: int | None = None) -> Dict[str, int]:
        return {"height": 0, "width": 0}

    def add_image(
        self,
        path: str,
        identifier: str,
        _x: int,
        _y: int,
        _bufnr: int,
        _winnr: int | None = None,
        _row_offset: int | None = None,
    ) -> str | dict[str, str]:
        """Adds an image to the queue to be rendered by Wezterm via the place method"""
        img = {"path": path, "id": identifier}
        self.to_make_visible.add(img["path"])
        return img

    def remove_image(self, identifier: str) -> None:
        pass

    def wezterm_split(self):
        """Splits the terminal based on config preferences at molten kernel init if
        supplied, otherwise resort to default values. Returns the pane id of the new
        split to allow sending/moving between the panes correctly.
        """
        self.image_pane = self.wezterm_api.wezterm_molten_init(
            self.initial_pane_id, self.split_dir, self.split_size
        )


def get_canvas_given_provider(
    nvim: Nvim, options: MoltenOptions
) -> Canvas:
    name = options.image_provider

    if name == "none":
        return NoCanvas()
    elif name == "image.nvim":
        return ImageNvimCanvas(nvim)
    elif name == "snacks.nvim":
        return SnacksCanvas(nvim)
    elif name == "wezterm":
        if options.auto_open_output:
            raise MoltenException(
                "'wezterm' as an image provider does not currently support molten_auto_open_output = true, please set it to false or use a different image provider"
            )
        return WeztermCanvas(nvim, options.split_direction, options.split_size)
    else:
        notify_warn(nvim, f"unknown image provider: `{name}`")
        return NoCanvas()

-- loads the image.nvim plugin and exposes methods to the python remote plugin
local ok, image = pcall(require, "image")

if not ok then
  vim.api.nvim_echo({ { "[Molten] `image.nvim` not found" } }, true, { err = true })
  return
end

local utils = require("image.utils")

local image_api = {}
local images = {}

image_api.from_file = function(path, opts)
  if opts.window and opts.window == vim.NIL then
    opts.window = nil
  end
  opts = opts or {}
  local img = image.from_file(path, opts)
  -- image.nvim returns the existing image for a known id, so apply the
  -- placement that may have changed since it was first placed
  if opts.window then
    img.window = opts.window
  end
  if opts.render_offset_top then
    img.render_offset_top = opts.render_offset_top
  end
  if opts.y then
    img.geometry.y = opts.y
  end
  images[path] = img
  return path
end

image_api.render = function(identifier, geometry)
  geometry = geometry or {}
  local img = images[identifier]

  -- a way to render images in windows when only their buffer is set
  if img.buffer and not img.window then
    local buf_win = vim.fn.getbufinfo(img.buffer)[1].windows
    if #buf_win > 0 then
      img.window = buf_win[1]
    end
  end

  -- only render when the window is visible
  if not img.window or not vim.api.nvim_win_is_valid(img.window) then
    img.window = nil
  end

  if img.window then
    img:render(geometry)
  end
end

image_api.clear = function(identifier)
  images[identifier]:clear()
end

image_api.clear_all = function()
  for _, img in pairs(images) do
    img:clear()
  end
end

image_api.move = function(identifier, x, y)
  images[identifier]:move(x, y)
end

---returns the window the image is placed in, or nil once that window is gone
image_api.image_window = function(identifier)
  local win = images[identifier].window
  if win and vim.api.nvim_win_is_valid(win) then
    return win
  end
  return nil
end

---returns the size this image will be displayed at, considering the image size, the user's max
---width/height settings and, when a window is given, the max width/height window percentages.
image_api.image_size = function(identifier, winnr)
  local img = images[identifier]
  local term_size = require("image.utils.term").get_size()
  local gopts = img.global_state.options
  local true_size = {
    width = math.min(img.image_width / term_size.cell_width, gopts.max_width or math.huge),
    height = math.min(img.image_height / term_size.cell_height, gopts.max_height or math.huge),
  }
  if winnr and winnr ~= vim.NIL and vim.api.nvim_win_is_valid(winnr) then
    local info = vim.fn.getwininfo(winnr)[1]
    local pct_w = img.max_width_window_percentage or gopts.max_width_window_percentage
    local pct_h = img.max_height_window_percentage or gopts.max_height_window_percentage
    if type(pct_w) == "number" then
      true_size.width = math.min(true_size.width, math.floor(info.width * pct_w / 100))
    end
    if type(pct_h) == "number" then
      true_size.height = math.min(true_size.height, math.floor(info.height * pct_h / 100))
    end
  end
  local width, height = utils.math.adjust_to_aspect_ratio(
    term_size,
    img.image_width,
    img.image_height,
    true_size.width,
    true_size.height
  )
  return { width = math.ceil(width), height = math.ceil(height) }
end

return { image_api = image_api }

vim.opt.rtp:append(vim.fn.stdpath("data") .. "/lazy/snacks.nvim")
local output_ns = vim.api.nvim_create_namespace("molten-render-order")

local snacks = require("snacks")
snacks.setup({ image = { enabled = true, doc = { enabled = false } } })
_G.Snacks = snacks

Snacks.image.terminal.env = function()
  return { placeholders = true, remote = false, supported = true }
end
Snacks.image.terminal.size = function()
  return { cell_width = 10, cell_height = 20, scale = 1 }
end
Snacks.image.terminal.request = function() end

local svg = vim.fn.tempname() .. ".svg"
vim.fn.writefile({
  '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">',
  '<rect width="200" height="100" fill="blue"/>',
  "</svg>",
}, svg)

local api = require("load_snacks_nvim").snacks_api
api.from_file(svg, { id = "svg", buffer = 1, x = 0, y = 1, row_offset = 2 })
assert(
  vim.wait(10000, function()
    local ok, size = pcall(api.image_size, "svg")
    return ok and size.width < 80 and size.height < 40
  end),
  "SVG sizing should use the converted image"
)

local buf = vim.api.nvim_create_buf(false, true)
vim.api.nvim_set_current_buf(buf)
vim.api.nvim_buf_set_lines(buf, 0, -1, false, { "anchor", "following" })
local output_mark = vim.api.nvim_buf_set_extmark(buf, output_ns, 0, 0, {
  virt_lines = { { { "header", "Normal" } } },
})
api.from_file(svg, { id = "ordered", buffer = buf, x = 0, y = 1, row_offset = 2 })
local output = api.begin_output(buf, 0, output_ns, output_mark)
api.render_text(output, { "before" }, "Normal")
api.render("ordered", output)
api.render_text(output, { "between" }, "Normal")
local second_svg = vim.fn.tempname() .. ".svg"
vim.fn.writefile(vim.fn.readfile(svg), second_svg)
api.from_file(second_svg, { id = "second", buffer = buf, x = 0, y = 1, row_offset = 4 })
api.render("second", output)
api.render_text(output, { "after" }, "Normal")
api.finish_output(output)

assert(
  vim.wait(10000, function()
    local mark = vim.api.nvim_buf_get_extmark_by_id(buf, output_ns, output_mark, { details = true })
    local count = 0
    for _, line in ipairs(mark[3].virt_lines) do
      for _, chunk in ipairs(line) do
        if chunk[1]:find(vim.fn.nr2char(0x10EEEE), 1, true) then
          count = count + 1
        end
      end
    end
    return count >= 10
  end),
  "text and Snacks placeholders should share one ordered virtual-line block"
)

local mark = vim.api.nvim_buf_get_extmark_by_id(buf, output_ns, output_mark, { details = true })
local rows = mark[3].virt_lines
assert(rows[1][1][1] == "header", "the Molten header should remain first")
assert(rows[2][1][1] == "before", "text before the image should render next")
assert(rows[3][1][1] ~= "after", "the image should remain between text blocks")
assert(rows[#rows][1][1] == "after", "text after the image should render last")
local between
for i, line in ipairs(rows) do
  if line[1][1] == "between" then
    between = i
  end
end
assert(between and between > 3 and between < #rows - 1, "text should separate both images")

vim.cmd.redraw()
local anchor_row = vim.fn.screenpos(0, 1, 1).row
assert(
  api.image_at(buf, vim.api.nvim_get_current_win(), anchor_row + 3, 1) == svg,
  "the rendered image should be addressable at its screen position"
)
assert(
  api.image_at(buf, vim.api.nvim_get_current_win(), anchor_row + between + 1, 1) == second_svg,
  "clicking the second image must not select the first"
)
assert(
  api.image_at(buf, vim.api.nvim_get_current_win(), anchor_row + between, 1) == nil,
  "text between images must not select either image"
)

vim.api.nvim_win_set_cursor(0, { 2, 0 })
vim.fn.winrestview({ topline = 2, topfill = #rows - 3 })
vim.cmd.redraw()
assert(vim.fn.screenpos(0, 1, 1).row == 0, "the image anchor should be off-screen")
assert(
  api.image_at(buf, vim.api.nvim_get_current_win(), 1, 1) == svg,
  "partially scrolled images should still be clickable"
)

vim.api.nvim_win_set_cursor(0, { 1, 0 })
vim.fn.winrestview({ topline = 1, topfill = 0 })
vim.wo.wrap = false
vim.api.nvim_buf_set_text(buf, 0, 6, 0, 6, { string.rep("x", 200) })
vim.api.nvim_win_set_cursor(0, { 1, 10 })
vim.fn.winrestview({ leftcol = 5 })
vim.cmd.redraw()
assert(
  api.image_at(buf, vim.api.nvim_get_current_win(), 4, 1) == svg,
  "horizontally scrolled images should remain clickable"
)
local image_width = 0
for _, chunk in ipairs(rows[3]) do
  image_width = image_width + vim.fn.strdisplaywidth(chunk[1])
end
assert(
  api.image_at(buf, vim.api.nvim_get_current_win(), 4, image_width - 4) == nil,
  "the image's right edge should move with horizontal scrolling"
)
vim.fn.winrestview({ leftcol = 0 })
vim.wo.wrap = true
vim.cmd.redraw()
local anchor_height = vim.api.nvim_win_text_height(0, { end_row = 0 }).all
assert(anchor_height > 1, "the anchor should wrap across screen rows")
assert(
  api.image_at(buf, vim.api.nvim_get_current_win(), anchor_height + 3, 1) == svg,
  "wrapped anchor text must not shift click selection"
)

vim.wo.wrap = false
vim.api.nvim_win_set_cursor(0, { 1, 0 })
vim.o.columns = 12
vim.cmd.redraw()
vim.api.nvim_exec_autocmds("WinResized", {})
assert(
  vim.wait(1000, function()
    local updated = vim.api.nvim_buf_get_extmark_by_id(
      buf,
      output_ns,
      output_mark,
      { details = true }
    )[3].virt_lines
    if #updated >= #rows then
      return false
    end
    for _, line in ipairs(updated) do
      for _, chunk in ipairs(line) do
        if
          chunk[1]:find(vim.fn.nr2char(0x10EEEE), 1, true)
          and vim.fn.strdisplaywidth(chunk[1]) > 12
        then
          return false
        end
      end
    end
    return true
  end),
  "resizing should update both images in the composed block"
)
local resized =
  vim.api.nvim_buf_get_extmark_by_id(buf, output_ns, output_mark, { details = true })[3].virt_lines
assert(
  resized[1][1][1] == "header"
    and resized[2][1][1] == "before"
    and resized[#resized][1][1] == "after",
  "resizing must retain text order"
)

api.clear_output(output)
assert(
  #vim.api.nvim_buf_get_extmark_by_id(buf, output_ns, output_mark, {}) == 0,
  "clearing output must remove its composed rows"
)
assert(
  api.image_at(buf, vim.api.nvim_get_current_win(), 1, 1) == nil,
  "cleared output must not be clickable"
)

vim.api.nvim_buf_delete(buf, { force = true })
vim.fn.delete(svg)
vim.fn.delete(second_svg)

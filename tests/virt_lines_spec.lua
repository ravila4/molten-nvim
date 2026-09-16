vim.opt.rtp:append(vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h"))
local virt_lines = require("molten.virt_lines")

local buf = vim.api.nvim_get_current_buf()
local win = vim.api.nvim_get_current_win()
vim.api.nvim_buf_set_lines(buf, 0, -1, false, { "line1", "line2", "line3", "line4" })
local ns = vim.api.nvim_create_namespace("molten-extmarks")
local id = vim.api.nvim_buf_set_extmark(buf, ns, 1, 0, {
  virt_lines = {
    { { "Out[1]:", "Comment" } },
    { { "| a |", "Comment" } },
    { { "󰁅 57 More Lines ", "Comment" } },
  },
  virt_lines_overflow = "scroll",
})
vim.cmd("redraw")

-- Screen rows: 1 line1, 2 line2, 3-5 virtual lines, 6 line3.
assert(virt_lines.at(buf, win, 2) == nil, "buffer line is not a virtual line")
local hit = virt_lines.at(buf, win, 3)
assert(hit and hit.id == id and hit.row == 1 and hit.text == "Out[1]:", vim.inspect(hit))
hit = virt_lines.at(buf, win, 5)
assert(hit and hit.row == 3 and virt_lines.is_footer(hit.text), vim.inspect(hit))
assert(virt_lines.at(buf, win, 6) == nil, "line3 is not a virtual line")
assert(not virt_lines.is_footer("| a |"))

-- A second output further down, after scrolling the window.
local id2 = vim.api.nvim_buf_set_extmark(buf, ns, 3, 0, {
  virt_lines = { { { "󰁝 Show Less ", "Comment" } } },
})
vim.api.nvim_win_set_cursor(win, { 3, 0 })
vim.fn.winrestview({ topline = 2 })
vim.cmd("redraw")
-- Screen rows now: 1 line2, 2-4 virtual, 5 line3, 6 line4, 7 collapse footer.
hit = virt_lines.at(buf, win, 7)
assert(hit and hit.id == id2 and hit.row == 1 and virt_lines.is_footer(hit.text), vim.inspect(hit))
assert(virt_lines.at(buf, win, 1) == nil, "scrolled: line2 is not virtual")
hit = virt_lines.at(buf, win, 2)
assert(hit and hit.id == id and hit.row == 1, "scrolled: first virt row " .. vim.inspect(hit))

print("virt_lines_spec: ok")

local M = {}

-- Screen row of the first virtual line below buffer row `row` (0-based) in `win`.
-- A text-height range ending at `row` covers its screen lines but not the virtual
-- lines below it, so the next screen row is where those virtual lines start.
local function first_virt_row(win, row)
  local info = vim.fn.getwininfo(win)[1]
  local view = vim.api.nvim_win_call(win, vim.fn.winsaveview)
  local top = vim.api.nvim_win_text_height(win, { end_row = view.topline - 1, end_vcol = 0 }).all
    - view.topfill
  if view.skipcol > 0 then
    top = top
      + vim.api.nvim_win_text_height(win, {
        start_row = view.topline - 1,
        end_row = view.topline - 1,
        start_vcol = 0,
        end_vcol = view.skipcol,
      }).all
  end
  return info.winrow + vim.api.nvim_win_text_height(win, { end_row = row }).all - top
end

-- The Molten virtual line under a screen row, as { id = extmark id, row = 1-based
-- index within that output, text = the line's text }, or nil.
-- Footer lines come from truncate_virt_lines in rplugin/python3/molten/outputbuffer.py.
function M.at(buffer, win, screenrow)
  if not vim.api.nvim_win_is_valid(win) or vim.api.nvim_win_get_buf(win) ~= buffer then
    return nil
  end
  local ns = vim.api.nvim_get_namespaces()["molten-extmarks"]
  if not ns then
    return nil
  end
  for _, mark in ipairs(vim.api.nvim_buf_get_extmarks(buffer, ns, 0, -1, { details = true })) do
    local virt_lines = mark[4].virt_lines
    if virt_lines and #virt_lines > 0 then
      local first = first_virt_row(win, mark[2])
      local row = screenrow - first + 1
      if row >= 1 and row <= #virt_lines then
        local text = {}
        for _, chunk in ipairs(virt_lines[row]) do
          text[#text + 1] = chunk[1]
        end
        return { id = mark[1], row = row, text = table.concat(text) }
      end
    end
  end
  return nil
end

-- True when the virtual line is one of Molten's expand/collapse footers.
function M.is_footer(text)
  return text:find("More Lines", 1, true) ~= nil or text:find("Show Less", 1, true) ~= nil
end

return M

local ok, snacks = pcall(require, "snacks")

if not ok then
  vim.api.nvim_echo({ { "[Molten] `snacks.nvim` not found" } }, true, { err = true })
  return
end

local snacks_api = {}
local images = {}
local outputs = {}
local next_output = 0
local compose

local function enable_scrolling(placement)
  for _, id in ipairs(placement.eids) do
    local mark =
      vim.api.nvim_buf_get_extmark_by_id(placement.buf, placement.ns, id, { details = true })
    local details = mark[3]
    if details and details.virt_lines then
      details.ns_id = nil
      details.id = id
      details.virt_lines_overflow = "scroll"
      vim.api.nvim_buf_set_extmark(placement.buf, placement.ns, mark[1], mark[2], details)
    end
  end
end

compose = function(identifier)
  local output = outputs[identifier]
  if not output or not vim.api.nvim_buf_is_valid(output.buffer) then
    return
  end
  local mark = vim.api.nvim_buf_get_extmark_by_id(output.buffer, output.ns, output.id, {})
  if #mark == 0 then
    return
  end
  local rows = vim.deepcopy(output.header)
  for _, entry in ipairs(output.entries) do
    if entry.kind == "text" then
      for _, line in ipairs(entry.lines) do
        rows[#rows + 1] = { { line, entry.highlight } }
      end
    else
      entry.first = #rows + 1
      vim.list_extend(rows, images[entry.identifier].rows or {})
      entry.last = #rows
    end
  end
  vim.api.nvim_buf_set_extmark(output.buffer, output.ns, mark[1], mark[2], {
    id = output.id,
    virt_lines = rows,
    virt_lines_overflow = "scroll",
  })
end

snacks_api.from_file = function(path, opts)
  local doc = snacks.config.image.doc or {}
  local previous = images[opts.id]
  if previous and previous.placement then
    previous.placement:close()
  end
  images[opts.id] = {
    path = path,
    img = snacks.image.image.new(path),
    buffer = opts.buffer,
    opts = {
      inline = true,
      auto_resize = true,
      pos = { opts.y, opts.x },
      max_width = doc.max_width or 80,
      max_height = doc.max_height or 40,
      on_update = function(placement)
        local image = images[opts.id]
        if image.output then
          image.rows = {}
          for _, id in ipairs(placement.eids) do
            local mark = vim.api.nvim_buf_get_extmark_by_id(
              placement.buf,
              placement.ns,
              id,
              { details = true }
            )
            if mark[3] then
              if mark[3].virt_lines then
                vim.list_extend(image.rows, mark[3].virt_lines)
              elseif mark[3].virt_text then
                image.rows[#image.rows + 1] = mark[3].virt_text
              end
              -- Keep Snacks' position marker; Molten owns the visible rows.
              vim.api.nvim_buf_del_extmark(placement.buf, placement.ns, id)
              vim.api.nvim_buf_set_extmark(
                placement.buf,
                placement.ns,
                mark[1],
                mark[2],
                { id = id }
              )
            end
          end
          compose(image.output)
        else
          enable_scrolling(placement)
        end
      end,
    },
  }
  return opts.id
end

snacks_api.begin_output = function(buffer, row, namespace, mark_id)
  next_output = next_output + 1
  local identifier = tostring(next_output)
  local mark = vim.api.nvim_buf_get_extmark_by_id(buffer, namespace, mark_id, { details = true })
  outputs[identifier] = {
    buffer = buffer,
    row = row,
    ns = namespace,
    id = mark_id,
    header = mark[3].virt_lines,
    entries = {},
  }
  return identifier
end

snacks_api.render = function(identifier, output)
  local image = images[identifier]
  if image and image.placement == nil then
    if output then
      image.output = output
      outputs[output].entries[#outputs[output].entries + 1] = {
        kind = "image",
        identifier = identifier,
      }
    end
    image.placement = Snacks.image.placement.new(image.buffer, image.path, image.opts)
  end
end

snacks_api.clear = function(identifier)
  local image = images[identifier]
  if image and image.placement then
    image.placement:close()
    image.placement = nil
    image.output = nil
    image.rows = nil
  end
end

snacks_api.clear_all = function()
  for identifier in pairs(outputs) do
    snacks_api.clear_output(identifier)
  end
  for identifier in pairs(images) do
    snacks_api.clear(identifier)
  end
end

snacks_api.image_size = function(identifier)
  local image = images[identifier]
  local bounds = {
    width = image.opts.max_width,
    height = image.opts.max_height,
  }
  if not image.img:ready() then
    return bounds
  end
  return snacks.image.util.fit(image.img.file, bounds, { info = image.img.info })
end

snacks_api.image_at = function(buffer, win, screenrow, screencol)
  if not vim.api.nvim_win_is_valid(win) or vim.api.nvim_win_get_buf(win) ~= buffer then
    return
  end

  local info = vim.fn.getwininfo(win)[1]
  if
    screenrow < info.winrow
    or screenrow >= info.winrow + info.height
    or screencol < info.wincol + info.textoff
    or screencol >= info.wincol + info.width
  then
    return
  end
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
  for _, output in pairs(outputs) do
    if output.buffer == buffer then
      local mark = vim.api.nvim_buf_get_extmark_by_id(buffer, output.ns, output.id, {})
      if #mark > 0 then
        local first = info.winrow
          + vim.api.nvim_win_text_height(win, { end_row = mark[1] }).all
          - top
        local row = screenrow - first + 1
        for _, entry in ipairs(output.entries) do
          if entry.kind == "image" and entry.first and row >= entry.first and row <= entry.last then
            local image = images[entry.identifier]
            local placement = image.placement
            if placement and not placement.hidden then
              local offset = 0
              for _, chunk in ipairs(image.rows[row - entry.first + 1]) do
                local width = vim.fn.strdisplaywidth(chunk[1])
                local left = info.wincol + info.textoff + offset - view.leftcol
                if
                  chunk[1]:find(vim.fn.nr2char(0x10EEEE), 1, true)
                  and screencol >= left
                  and screencol < left + width
                then
                  return image.path
                end
                offset = offset + width
              end
            end
          end
        end
      end
    end
  end
end

snacks_api.render_text = function(output, lines, highlight)
  outputs[output].entries[#outputs[output].entries + 1] = {
    kind = "text",
    lines = lines,
    highlight = highlight,
  }
end

snacks_api.finish_output = function(output)
  compose(output)
end

snacks_api.clear_output = function(identifier)
  local output = outputs[identifier]
  if not output then
    return
  end
  if vim.api.nvim_buf_is_valid(output.buffer) then
    vim.api.nvim_buf_del_extmark(output.buffer, output.ns, output.id)
  end
  for _, entry in ipairs(output.entries) do
    if entry.kind == "image" then
      snacks_api.clear(entry.identifier)
    end
  end
  outputs[identifier] = nil
end

return { snacks_api = snacks_api }

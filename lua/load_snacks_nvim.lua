local ok, snacks = pcall(require, "snacks")

if not ok then
  vim.api.nvim_echo({ { "[Molten] `snacks.nvim` not found" } }, true, { err = true })
  return
end

local snacks_api = {}
local images = {}

snacks_api.from_file = function(path, opts)
  local doc = snacks.config.image.doc or {}
  local previous = images[opts.id]
  if previous and previous.placement then
    previous.placement:close()
  end
  images[opts.id] = {
    path = path,
    buffer = opts.buffer,
    opts = {
      inline = true,
      pos = { opts.y, opts.x },
      max_width = doc.max_width or 80,
      max_height = doc.max_height or 40,
    },
  }
  return opts.id
end

snacks_api.render = function(identifier)
  local image = images[identifier]
  if image and image.placement == nil then
    image.placement = Snacks.image.placement.new(image.buffer, image.path, image.opts)
  end
end

snacks_api.clear = function(identifier)
  local image = images[identifier]
  if image and image.placement then
    image.placement:close()
    image.placement = nil
  end
end

snacks_api.clear_all = function()
  for identifier in pairs(images) do
    snacks_api.clear(identifier)
  end
end

snacks_api.image_size = function(identifier)
  local image = images[identifier]
  return snacks.image.util.fit(image.path, {
    width = image.opts.max_width,
    height = image.opts.max_height,
  })
end

return { snacks_api = snacks_api }

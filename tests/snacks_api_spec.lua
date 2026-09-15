local placements = {}
local fitted

package.loaded.snacks = {
  config = { image = {} },
  image = {
    image = {
      new = function(path)
        return {
          file = path .. ".converted.png",
          info = { size = { width = 120, height = 60 }, dpi = { width = 96, height = 96 } },
          ready = function()
            return true
          end,
        }
      end,
    },
    placement = {
      new = function(buffer, path, opts)
        local placement = {
          buffer = buffer,
          buf = buffer,
          path = path,
          opts = opts,
          ns = vim.api.nvim_create_namespace("mock-snacks-placement"),
          eids = {},
          closed = false,
        }
        function placement:close()
          self.closed = true
        end
        placements[#placements + 1] = placement
        return placement
      end,
    },
    util = {
      fit = function(path, bounds, opts)
        fitted = { path = path, info = opts and opts.info }
        return { path = path, width = bounds.width, height = bounds.height }
      end,
    },
  },
}
_G.Snacks = package.loaded.snacks

local api = require("load_snacks_nvim").snacks_api
local first = api.from_file("shared.png", { id = "first", buffer = 4, x = 2, y = 7 })
local second = api.from_file("shared.png", { id = "second", buffer = 4, x = 5, y = 9 })

assert(first == "first", "the Molten identifier should identify the placement")
assert(second == "second", "placements of the same file must remain independent")
assert(
  vim.deep_equal(api.image_size(first), {
    path = "shared.png.converted.png",
    width = 80,
    height = 40,
  }),
  "missing document size settings should use Molten's defaults"
)
assert(fitted.info.size.width == 120, "sizing should use converted image metadata")

api.render(first)
api.render(second)
assert(#placements == 2, "both placements should render")
assert(placements[1].path == "shared.png", "rendering should use the source path")
assert(
  vim.deep_equal(placements[1].opts.pos, { 7, 2 }),
  "placement should preserve buffer coordinates"
)

api.from_file("replacement.png", { id = "first", buffer = 4, x = 3, y = 8 })
assert(placements[1].closed, "replacing an identifier should close its previous placement")
api.render(first)
assert(#placements == 3, "replacing an identifier should create one new placement")
assert(placements[3].path == "replacement.png", "the replacement should use its new source")

api.clear(second)
assert(placements[2].closed, "clear should close the active placement")
assert(
  api.image_size(second).path == "shared.png.converted.png",
  "clear should retain metadata for redisplay"
)
api.render(second)
assert(#placements == 4, "a cleared image should render again")

api.clear_all()
assert(
  placements[3].closed and placements[4].closed,
  "clear_all should close every active placement"
)

local buf = vim.api.nvim_create_buf(false, true)
vim.api.nvim_set_current_buf(buf)
local ns = vim.api.nvim_create_namespace("snacks-scroll-test")
local rows = { { { "wide image row", "Normal" } } }
local eid = vim.api.nvim_buf_set_extmark(buf, ns, 0, 0, {
  virt_lines = rows,
  virt_lines_above = true,
  right_gravity = false,
})
api.from_file("scroll.png", { id = "scroll", buffer = buf, x = 0, y = 1 })
api.render("scroll")
local placement = placements[#placements]
placement.buf, placement.ns, placement.eids = buf, ns, { eid }
placement.opts.on_update(placement)
local mark = vim.api.nvim_buf_get_extmark_by_id(buf, ns, eid, { details = true })
assert(mark[3].virt_lines_overflow == "scroll", "image rows should follow horizontal scrolling")
assert(vim.deep_equal(mark[3].virt_lines, rows), "scrolling must retain image placeholders")
assert(mark[3].virt_lines_above and not mark[3].right_gravity, "retain placement properties")
placement.opts.on_update(placement)
assert(#vim.api.nvim_buf_get_extmarks(buf, ns, 0, -1, {}) == 1, "updates must not duplicate rows")
vim.api.nvim_buf_del_extmark(buf, ns, eid)

vim.api.nvim_buf_delete(buf, { force = true })

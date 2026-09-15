local placements = {}

package.loaded.snacks = {
  config = { image = {} },
  image = {
    placement = {
      new = function(buffer, path, opts)
        local placement = { buffer = buffer, path = path, opts = opts, closed = false }
        function placement:close()
          self.closed = true
        end
        placements[#placements + 1] = placement
        return placement
      end,
    },
    util = {
      fit = function(path, bounds)
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
    path = "shared.png",
    width = 80,
    height = 40,
  }),
  "missing document size settings should use Molten's defaults"
)

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
assert(api.image_size(second).path == "shared.png", "clear should retain metadata for redisplay")
api.render(second)
assert(#placements == 4, "a cleared image should render again")

api.clear_all()
assert(
  placements[3].closed and placements[4].closed,
  "clear_all should close every active placement"
)

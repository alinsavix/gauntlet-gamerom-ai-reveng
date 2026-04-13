-- table-widths.lua
-- Recalculate column widths based on max content width per column.
-- Prevents narrow-data columns (e.g. Address, Size) from consuming
-- disproportionate space relative to wide Description columns.

local function cell_text(cell)
  return pandoc.utils.stringify(cell.content or cell.contents)
end

function Table(tbl)
  local ncols = #tbl.colspecs
  local widths = {}
  for i = 1, ncols do widths[i] = 3 end  -- minimum floor

  local function measure(row)
    for i, cell in ipairs(row.cells) do
      if i <= ncols then
        -- Cap at 60 so one very long cell doesn't dominate
        local w = math.min(#cell_text(cell), 60)
        if w > widths[i] then widths[i] = w end
      end
    end
  end

  for _, row in ipairs(tbl.head.rows) do measure(row) end
  for _, body in ipairs(tbl.bodies) do
    for _, row in ipairs(body.body) do measure(row) end
  end

  local total = 0
  for _, w in ipairs(widths) do total = total + w end

  for i = 1, ncols do
    tbl.colspecs[i] = {tbl.colspecs[i][1], widths[i] / total}
  end

  return tbl
end

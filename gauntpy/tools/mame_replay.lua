-- Replay a lockstep flight on MAME: start from the harness ROM's RAM, feed its input per loop
-- pass, and print what changed after each pass. Driven by tools/mame_replay.py, which passes:
--   REPLAY_IMAGE   the harness ROM's RAM after its boot, as "address length" headed chunks
--   REPLAY_INPUT   one line per loop pass: four raw stick words, then the coins, in hex
--   REPLAY_POKES   "pass address word" lines: the harness's warps and score pokes, made after that pass
--   REPLAY_PASSES  how many passes to run
--   REPLAY_DUMP    optionally, a pass after which to print game RAM (D lines), to find a difference
local machine = manager.machine
local cpu = machine.devices[":maincpu"]
local program = cpu.spaces["program"]
local function r16(a) return program:read_u16(a) end

local inputs = {}
for line in io.lines(os.getenv("REPLAY_INPUT")) do
    local fields = {}
    for field in line:gmatch("%S+") do fields[#fields + 1] = tonumber(field, 16) end
    inputs[#inputs + 1] = fields
end
local passes = tonumber(os.getenv("REPLAY_PASSES"))
local dump_at = tonumber(os.getenv("REPLAY_DUMP") or "-1")
local pokes = {}
for line in io.lines(os.getenv("REPLAY_POKES")) do
    local number, address, word = line:match("(%x+) (%x+) (%x+)")
    number = tonumber(number, 16)
    pokes[number] = pokes[number] or {}
    table.insert(pokes[number], {tonumber(address, 16), tonumber(word, 16)})
end

local base = nil          -- the frame counter the image carries
local synced = false
local pass = 0
local prev = {}
local vblanks = 0
local done = false

local function load_image()
    local file = io.open(os.getenv("REPLAY_IMAGE"), "rb")
    local data = file:read("a")
    file:close()
    local at = 1
    while at <= #data do
        local address, length = string.unpack(">I4I4", data, at)
        at = at + 8
        for i = 0, length - 1, 2 do
            program:write_u16(address + i, string.unpack(">I2", data, at + i))
        end
        at = at + length
    end
    base = r16(0x904006)
end

-- The loop waits on the semaphore at 0x42A7E; between frames is where the harness's ROM sits.
semaphore_tap = program:install_read_tap(0x904002, 0x904003, "replay sync", function(offset, data, mask)
    if synced or data ~= 0 then return end
    local pc = cpu.state["PC"].value
    if pc < 0x42A7E or pc > 0x42A86 or r16(0x904006) < 20 then return end
    load_image()
    synced = true
    print(string.format("SYNC,%04x", base))
end)

-- 0x40644 reads the four stick words once a pass, after the loop counted it at 0x42A86.
input_tap = program:install_read_tap(0x803000, 0x803007, "replay input", function(offset, data, mask)
    if not synced then return end
    local index = (r16(0x904006) - base) & 0xFFFF
    local row = inputs[index]
    if row == nil then return end
    local player = (offset - 0x803000) // 2
    return row[player + 1]
end)

-- The pass is counted at 0x42A86; its coins land then, before coincheck reads them.
counter_tap = program:install_write_tap(0x904006, 0x904007, "replay coins", function(offset, data, mask)
    if not synced then return end
    local index = (data - base) & 0xFFFF
    local row = inputs[index]
    if row == nil then return end
    for i = 5, #row do program:write_u8(0x904FEC + row[i], 1) end
end)

vblank_tap = program:install_write_tap(0x904002, 0x904003, "replay vblanks", function(offset, data, mask)
    if synced and data ~= 0 then vblanks = vblanks + 1 end
end)

local function sample(overflow)
    pass = (r16(0x904006) - base) & 0xFFFF
    print(string.format("P,%d,%04x,%04x,%04x,%04x,%d", pass, r16(0x904BFC), r16(0x904918),
        overflow, r16(0x904004), vblanks))
    for slot = 0, 1023 do
        local key = string.format("%04x,%04x,%04x,%04x,%04x", r16(0x902000 + slot * 2),
            r16(0x903800 + slot * 2), r16(0x902800 + slot * 2), r16(0x903000 + slot * 2),
            r16(0x904066 + slot * 2))
        if prev[slot] ~= key then
            prev[slot] = key
            print("M," .. slot .. "," .. key)
        end
    end
    if dump_at == pass then
        for _, range in ipairs({{0x904000, 0x904C02}, {0x905000, 0x906000}, {0x910000, 0x910800}}) do
            local words = {}
            for address = range[1], range[2] - 2, 2 do words[#words + 1] = string.format("%04x", r16(address)) end
            print(string.format("D,%x,%s", range[1], table.concat(words, "")))
        end
    end
    if pass >= passes then
        done = true
        machine:exit()
    end
end

-- Every pass ends by writing frame_overflow (0x42B4E or 0x42B5E): the exact end of a pass,
-- even one that overran and runs straight into the next.
overflow_tap = program:install_write_tap(0x904916, 0x904917, "replay passes", function(offset, data, mask)
    if done or not synced then return end
    local pc = cpu.state["PC"].value
    if pc < 0x42B4E or pc > 0x42B66 then return end
    sample(data)
    for _, poke in ipairs(pokes[pass] or {}) do program:write_u16(poke[1], poke[2]) end
end)

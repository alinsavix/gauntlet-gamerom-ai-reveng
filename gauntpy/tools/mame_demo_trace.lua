-- Full-state attract-demo trace: per-frame globals plus MOB slot deltas, with
-- optional RAM pokes. Run through tools/demo_compare.py, which also applies the
-- same pokes to gauntpy; keep POKES in that file in step with this one.
--
-- POKE_MODE (environment): none (default), families, lobbers, death.
local machine = manager.machine
local cpu = machine.devices[":maincpu"]
local program = cpu.spaces["program"]
local out = { write = function(_, s) print(s:sub(1, -2)) end, close = function() end }
local demo_frame = 0
local prev = {}
local prev_mode = nil
local done = false

local function r16(a) return program:read_u16(a) end


local POKE_MODE = os.getenv("POKE_MODE") or "none"
local poked_f, poked_d = false, false
local function apply_pokes()
    local fc = program:read_u16(0x904006)
    if POKE_MODE == "families" and fc == 1 and not poked_f then
        poked_f = true
        for slot = 32, 1023 do
            local link = program:read_u16(0x903800 + slot * 2)
            local t = link >> 10
            local nt = nil
            if t == 0x12 or t == 0x13 or t == 0x17 then
                nt = ({0x14, 0x15, 0x16})[(slot % 3) + 1]
            elseif t >= 0x1C and t <= 0x21 then
                nt = t + 6
            elseif t >= 0x2B and t <= 0x2D then
                nt = t - 3
            end
            if nt then
                program:write_u16(0x903800 + slot * 2, (link & 0x3FF) | (nt << 10))
                if nt <= 0x16 then
                    local h = program:read_u16(0x902800 + slot * 2)
                    local tier = (nt == 0x14) and 8 or 0xB
                    program:write_u16(0x902800 + slot * 2, (h & 0xFFF0) | tier)
                end
            end
        end
    end
    if POKE_MODE == "lobbers" and fc == 1 and not poked_f then
        poked_f = true
        for slot = 32, 1023 do
            local link = program:read_u16(0x903800 + slot * 2)
            local t = link >> 10
            local nt = nil
            if t >= 0x1C and t <= 0x1E then
                nt = t + 9
            elseif t >= 0x1F and t <= 0x21 then
                nt = t + 6
            elseif t >= 0x2B and t <= 0x2D then
                nt = t - 6
            end
            if nt then
                program:write_u16(0x903800 + slot * 2, (link & 0x3FF) | (nt << 10))
            end
        end
    end
    if POKE_MODE == "death" and fc == 1500 and not poked_d then
        poked_d = true
        program:write_u32(0x904984, 0)
    end
end
emu.register_frame_done(function()
    if done then return end
    local mode = r16(0x904918)
    if mode ~= prev_mode then
        out:write(string.format("MODE,%d,%04x,%04x\n", demo_frame, mode, r16(0x904BFC)))
        prev_mode = mode
    end
    if mode ~= 0xfffd then
        out:write(string.format("PRE,%04x,%04x,%04x\n", mode, r16(0x904BFC), r16(0x904006)))
        if demo_frame > 0 then done = true; out:close(); machine:exit() end
        return
    end
    demo_frame = demo_frame + 1
    local ps = r16(0x9048ca)
    out:write(string.format(
        "F,%d,%04x,%04x,%04x,%04x,%04x,%04x,%04x,%04x,%04x,%04x,%08x,%02x,%04x,%02x,%04x\n",
        demo_frame, r16(0x904006), r16(0x904916), r16(0x904BFC),
        r16(0x9048A0), r16(0x9048A2), r16(0x9048A4), r16(0x9048A6),
        ps, r16(0x902800 + ps * 2), r16(0x903000 + ps * 2),
        program:read_u32(0x904b6a), program:read_u8(0x904b77),
        r16(0x9049dc), program:read_u8(0x904056), r16(0x904002)))
    local slip = {}
    for i = 0, 33 do slip[#slip + 1] = string.format("%04x", r16(0x905F80 + i * 2)) end
    out:write(string.format("S,%d,%04x,%04x,%04x,%04x,%s\n", demo_frame,
        r16(0x904008), r16(0x90400A), r16(0x9049DE), r16(0x904A60),
        table.concat(slip, ",")))
    for slot = 0, 1023 do
        local p = r16(0x902000 + slot * 2)
        local l = r16(0x903800 + slot * 2)
        local h = r16(0x902800 + slot * 2)
        local v = r16(0x903000 + slot * 2)
        local st = r16(0x904066 + slot * 2)
        local key = string.format("%04x,%04x,%04x,%04x,%04x", p, l, h, v, st)
        if prev[slot] ~= key then
            prev[slot] = key
            out:write("M," .. slot .. "," .. key .. "\n")
        end
    end
    apply_pokes()
end)

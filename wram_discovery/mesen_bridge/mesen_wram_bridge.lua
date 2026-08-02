-- Lufia II WRAM discovery bridge for Mesen 2.x.
--
-- Load this file in Mesen's Script Window and enable:
--   Allow access to I/O and OS functions
--
-- The Python side writes one request at a time into BRIDGE_ROOT. Requests are
-- handled on an emulated frame boundary, so every dump is a coherent SNES WRAM
-- snapshot rather than an external process-memory scan.

local BRIDGE_ROOT = "D:/Projects/AI_Emu_Player/wram_discovery/mesen_bridge/shared"
local REQUEST_PATH = BRIDGE_ROOT .. "/request.txt"
local RESPONSE_PATH = BRIDGE_ROOT .. "/response.txt"
local WRAM = emu.memType.snesWorkRam
local BRIDGE_PROTOCOL_VERSION = 2
local POLL_EVERY_FRAMES = 3
local VALID_BUTTONS = {
    up = true, down = true, left = true, right = true,
    a = true, b = true, x = true, y = true,
    l = true, r = true, start = true, select = true,
}
local pendingPulse = nil

if io == nil or os == nil then
    emu.displayMessage(
        "WRAM Bridge",
        "Enable 'Allow access to I/O and OS functions' in the Script Window."
    )
    error("Mesen Lua I/O access is disabled")
end

local function sanitize(value)
    return tostring(value or ""):gsub("[\t\r\n]", " ")
end

local function splitTabs(value)
    local parts = {}
    for part in (value .. "\t"):gmatch("(.-)\t") do
        table.insert(parts, part)
    end
    return parts
end

local function readText(path)
    local handle = io.open(path, "rb")
    if handle == nil then
        return nil
    end
    local value = handle:read("*a")
    handle:close()
    return value
end

local function acknowledgeRequest()
    -- Windows can briefly deny os.remove even after readText closed its handle.
    -- Never process an unacknowledged request: otherwise an expensive DUMP is
    -- repeated every poll until Python happens to remove the file.
    local removed = os.remove(REQUEST_PATH)
    if removed then
        return true
    end

    local handle = io.open(REQUEST_PATH, "wb")
    if handle ~= nil then
        handle:close()
        return true
    end
    return false
end

local function writeTextAtomic(value)
    local temporary = RESPONSE_PATH .. ".tmp"
    os.remove(temporary)
    local handle = assert(io.open(temporary, "wb"))
    handle:write(value)
    handle:close()
    os.remove(RESPONSE_PATH)
    assert(os.rename(temporary, RESPONSE_PATH))
end

local function writeDump(path)
    local size = emu.getMemorySize(WRAM)
    local handle = assert(io.open(path, "wb"))
    local block = {}
    for offset = 0, size - 1 do
        block[#block + 1] = string.char(emu.read(offset, WRAM))
        if #block == 256 then
            handle:write(table.concat(block))
            block = {}
        end
    end
    if #block > 0 then
        handle:write(table.concat(block))
    end
    handle:close()
    return size
end

local function writeBinary(path, value)
    local handle = assert(io.open(path, "wb"))
    handle:write(value)
    handle:close()
    return #value
end

local function readHex(offset, length)
    local values = {}
    for index = 0, length - 1 do
        values[#values + 1] = string.format("%02X", emu.read(offset + index, WRAM))
    end
    return table.concat(values)
end

local function processRequest(raw)
    local parts = splitTabs(raw:gsub("[\r\n]+$", ""))
    local requestId = parts[1] or ""
    local command = (parts[2] or ""):upper()

    if requestId == "" or command == "" then
        return "unknown\tERROR\tMalformed request"
    end

    if command == "PING" then
        local rom = emu.getRomInfo() or {}
        local size = emu.getMemorySize(WRAM)
        return table.concat({
            requestId,
            "OK",
            "PONG",
            tostring(size),
            sanitize(rom.name),
            sanitize(rom.fileSha1Hash),
            sanitize(rom.path),
            tostring(BRIDGE_PROTOCOL_VERSION),
        }, "\t")
    end

    if command == "DUMP" then
        local dumpPath = BRIDGE_ROOT .. "/dump_" .. requestId .. ".bin"
        local size = writeDump(dumpPath)
        return table.concat({
            requestId,
            "OK",
            "DUMP",
            tostring(size),
            dumpPath,
        }, "\t")
    end

    if command == "READ" then
        local offset = tonumber(parts[3] or "")
        local length = tonumber(parts[4] or "")
        local size = emu.getMemorySize(WRAM)
        if offset == nil or length == nil or offset < 0 or length < 1
            or offset + length > size then
            return requestId .. "\tERROR\tInvalid READ range"
        end
        return table.concat({
            requestId,
            "OK",
            "READ",
            tostring(offset),
            tostring(length),
            readHex(offset, length),
        }, "\t")
    end

    if command == "SCREENSHOT" then
        local screenshotPath = BRIDGE_ROOT .. "/screenshot_" .. requestId .. ".png"
        local size = writeBinary(screenshotPath, emu.takeScreenshot())
        return table.concat({
            requestId,
            "OK",
            "SCREENSHOT",
            tostring(size),
            screenshotPath,
        }, "\t")
    end

    if command == "PROBE" then
        local offset = tonumber(parts[3] or "")
        local length = tonumber(parts[4] or "")
        local size = emu.getMemorySize(WRAM)
        if offset == nil or length == nil or offset < 0 or length < 1
            or offset + length > size then
            return requestId .. "\tERROR\tInvalid PROBE range"
        end
        local screenshotPath = BRIDGE_ROOT .. "/probe_" .. requestId .. ".png"
        local screenshotSize = writeBinary(screenshotPath, emu.takeScreenshot())
        return table.concat({
            requestId,
            "OK",
            "PROBE",
            tostring(offset),
            tostring(length),
            readHex(offset, length),
            tostring(screenshotSize),
            screenshotPath,
        }, "\t")
    end

    if command == "PULSE" then
        local button = (parts[3] or ""):lower()
        local frames = tonumber(parts[4] or "2")
        if not VALID_BUTTONS[button] or frames == nil or frames < 1 or frames > 30 then
            return requestId .. "\tERROR\tInvalid PULSE button/frames"
        end
        pendingPulse = {
            buttons = { button },
            leadButton = nil,
            leadFrames = 0,
            pressFrames = math.floor(frames),
            -- Keep an explicit neutral interval after every tap. Python also
            -- waits before issuing the next command, so separate actions can
            -- never collapse into one emulated-frame burst.
            releaseFrames = 4,
        }
        return table.concat({
            requestId,
            "OK",
            "PULSE",
            button,
            tostring(math.floor(frames)),
        }, "\t")
    end

    if command == "CHORD" then
        local heldButton = (parts[3] or ""):lower()
        local pressedButton = (parts[4] or ""):lower()
        local leadFrames = tonumber(parts[5] or "2")
        local pressFrames = tonumber(parts[6] or "2")
        if not VALID_BUTTONS[heldButton] or not VALID_BUTTONS[pressedButton]
            or heldButton == pressedButton or leadFrames == nil or pressFrames == nil
            or leadFrames < 1 or leadFrames > 30
            or pressFrames < 1 or pressFrames > 30 then
            return requestId .. "\tERROR\tInvalid CHORD buttons/frames"
        end
        pendingPulse = {
            buttons = { heldButton, pressedButton },
            leadButton = heldButton,
            leadFrames = math.floor(leadFrames),
            pressFrames = math.floor(pressFrames),
            releaseFrames = 4,
        }
        return table.concat({
            requestId,
            "OK",
            "CHORD",
            heldButton,
            pressedButton,
            tostring(math.floor(leadFrames)),
            tostring(math.floor(pressFrames)),
        }, "\t")
    end

    if command == "HOLD_UNTIL" then
        local button = (parts[3] or ""):lower()
        local stopOffset = tonumber(parts[4] or "")
        local stopValue = tonumber(parts[5] or "")
        local maxFrames = tonumber(parts[6] or "3600")
        local size = emu.getMemorySize(WRAM)
        if not VALID_BUTTONS[button] or stopOffset == nil or stopValue == nil
            or maxFrames == nil or stopOffset < 0 or stopOffset >= size
            or stopValue < 0 or stopValue > 255
            or maxFrames < 1 or maxFrames > 3600 then
            return requestId .. "\tERROR\tInvalid HOLD_UNTIL arguments"
        end
        pendingPulse = {
            buttons = { button },
            leadButton = nil,
            leadFrames = 0,
            pressFrames = math.floor(maxFrames),
            releaseFrames = 4,
            stopOffset = math.floor(stopOffset),
            stopValue = math.floor(stopValue),
        }
        return table.concat({
            requestId,
            "OK",
            "HOLD_UNTIL",
            button,
            tostring(math.floor(stopOffset)),
            tostring(math.floor(stopValue)),
            tostring(math.floor(maxFrames)),
        }, "\t")
    end

    if command == "GETINPUT" then
        local input = emu.getInput(0) or {}
        local values = {}
        for key, value in pairs(input) do
            values[#values + 1] = sanitize(key) .. "=" .. sanitize(value)
        end
        table.sort(values)
        return table.concat({
            requestId,
            "OK",
            "GETINPUT",
            table.concat(values, ","),
        }, "\t")
    end

    return requestId .. "\tERROR\tUnknown command: " .. sanitize(command)
end

local frameCounter = 0
local function onEndFrame()
    frameCounter = frameCounter + 1

    -- Count pulse duration in emulated frames, not in inputPolled callbacks.
    -- Mesen may poll the controller multiple times per frame; decrementing in
    -- onInputPolled made a nominal one-frame pulse produce several game inputs.
    if pendingPulse ~= nil then
        if pendingPulse.stopOffset ~= nil
            and emu.read(pendingPulse.stopOffset, WRAM) == pendingPulse.stopValue then
            pendingPulse.leadFrames = 0
            pendingPulse.pressFrames = 0
        end
        if pendingPulse.leadFrames > 0 then
            pendingPulse.leadFrames = pendingPulse.leadFrames - 1
        elseif pendingPulse.pressFrames > 0 then
            pendingPulse.pressFrames = pendingPulse.pressFrames - 1
        else
            pendingPulse.releaseFrames = pendingPulse.releaseFrames - 1
            if pendingPulse.releaseFrames <= 0 then
                pendingPulse = nil
            end
        end
    end

    if frameCounter % POLL_EVERY_FRAMES ~= 0 then
        return
    end

    local request = readText(REQUEST_PATH)
    if request == nil or request == "" then
        return
    end

    if not acknowledgeRequest() then
        emu.log("WRAM bridge could not acknowledge request; retrying without processing")
        return
    end
    local ok, response = pcall(processRequest, request)
    if not ok then
        local requestId = splitTabs(request)[1] or "unknown"
        response = requestId .. "\tERROR\t" .. sanitize(response)
    end
    writeTextAtomic(response)
end

local function onInputPolled()
    if pendingPulse == nil then
        return
    end

    local input = {}
    if pendingPulse.leadFrames > 0 then
        input[pendingPulse.leadButton] = true
    elseif pendingPulse.pressFrames > 0 then
        for _, button in ipairs(pendingPulse.buttons) do
            input[button] = true
        end
    else
        for _, button in ipairs(pendingPulse.buttons) do
            input[button] = false
        end
    end
    emu.setInput(input, 0)
end

emu.addEventCallback(onEndFrame, emu.eventType.endFrame)
emu.addEventCallback(onInputPolled, emu.eventType.inputPolled)
emu.displayMessage("WRAM Bridge", "Ready - Python can now read SNES WRAM.")
emu.log("Lufia II WRAM bridge ready at: " .. BRIDGE_ROOT)

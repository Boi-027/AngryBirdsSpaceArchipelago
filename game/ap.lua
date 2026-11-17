-- Archipelago for Angry Birds Space.
-- Loaded by the gamelogic.lua wrapper right after the original game logic.
--
-- Client -> game: "ap_in.lua" (plain Lua, next to the exe), defines global apIn:
--   seed, slot, episodes{folder=true}, open{levelName=true}, eagles, powerups{id=n},
--   messages{{id,text}}, deathlink{id,source}, deathlinkEnabled
-- Game -> client: "ap_state.lua" via saveLuaFile (encrypted save), global apState:
--   seed, cleared{levelName=true}, perfect{levelName=true}, applied{...}, msgSeen, deaths, deathSeen
-- Progress is kept per seed in the game's own settings save (settings.root.archipelago).

local IN_FILE = "ap_in.lua"
local POLL_FRAMES = 30
-- Episodes whose levels are gated by Archipelago (the client sends the real list in apIn.managed);
-- everything else keeps vanilla rules.
local MANAGED = { theme1 = true, theme2 = true, theme3 = true, theme4 = true, theme5 = true, theme6 = true,
  theme7 = true, theme81 = true, theme82 = true, theme9 = true, dangerZone = true }
local POWERUPS = { "flock", "antenna", "inflate" } -- keys of powerups.powerUps (wingman is uncounted)

AP = { active = false, open = {}, episodes = {}, needs = {} }

local function managed(folder)
  if AP.managed then return AP.managed[folder] == true end
  return MANAGED[folder] == true
end

local vanillaIsLevelUnlocked
local listenerAdded = false
local announced = false
local dirty = true
local frames = 0

local function data()
  if not (settings and settings.root) then return nil end
  local d = settings.root.archipelago
  if not d then
    d = { seed = "", cleared = {}, perfect = {}, applied = {}, msgSeen = 0, deaths = 0, deathSeen = 0 }
    settings.root.archipelago = d
  end
  d.stars = d.stars or {}  -- best stars per level this seed (Star Hunt goal)
  return d
end

local function toast(text)
  pcall(function()
    requireFile("menu/Toast.lua")
    menu.Toast.queueNotification(text)
  end)
end

local function apIsLevelUnlocked(folder, n)
  if not AP.active or not managed(folder) then
    return vanillaIsLevelUnlocked(folder, n)
  end
  local list = actions.myLevels[folder]
  local name = list and list[n]
  if not name then return false end
  if AP.open[name] then return true end
  local meta = getLevelMetadata(name)
  if meta and meta.type == "comic" then return AP.episodes[folder] == true end
  return false
end

local function installHooks()
  if menu and menu.MainMenu and not menu.MainMenu.__ap then pcall(addMainMenuButton) end
  if menu and menu.EpisodeButton and not menu.EpisodeButton.__ap then pcall(addEpisodeLocks) end
  if menu and menu.LevelButton and not menu.LevelButton.__ap then pcall(addLevelHints) end
  if SettingsWrapper and not SettingsWrapper.__apEgg then
    -- Eggsteroids levels normally unlock by finding eggsteroids; when AP manages them, items decide
    SettingsWrapper.__apEgg = true
    local vanillaEgg = SettingsWrapper.isEggsteroidLevelUnlocked
    function SettingsWrapper:isEggsteroidLevelUnlocked(name, ...)
      if AP.active and managed("bonus") then return AP.open[name] == true end
      return vanillaEgg(self, name, ...)
    end
  end
  if isLevelUnlocked and isLevelUnlocked ~= apIsLevelUnlocked then
    vanillaIsLevelUnlocked = isLevelUnlocked
    isLevelUnlocked = apIsLevelUnlocked
  end
  if not listenerAdded and GameSystem and GameSystem.eventManager and events then
    listenerAdded = true
    local l = { name = "Archipelago" }
    function l:eventTriggered(ev)
      local d = data()
      if not d or not AP.active then return end
      if mirrorWorldHandler and mirrorWorldHandler.mirror then return end
      local list = actions.myLevels[currentFolder]
      local name = list and list[currentLevel]
      if not name or not managed(currentFolder) then return end
      if ev.id == events.EID_LEVEL_COMPLETED then
        d.cleared[name] = true
        if (ev.stars or 0) >= 3 then d.perfect[name] = true end
        if (ev.stars or 0) > (d.stars[name] or 0) then d.stars[name] = ev.stars end
      elseif ev.id == events.EID_LEVEL_FAILED then
        d.deaths = (d.deaths or 0) + 1
      end
      dirty = true
    end
    GameSystem.eventManager:addEventListener(events.EID_LEVEL_COMPLETED, l)
    GameSystem.eventManager:addEventListener(events.EID_LEVEL_FAILED, l)
  end
end

-- Bird Swap Trap: swap the bird on the slingshot for another kind already in this level (its art is
-- loaded). Traps wait until you are in a level, and fire at most one every 20 seconds.
local lastTrapFrame = -100000
local function applyTraps(d, inp)
  local total = inp.traps and inp.traps.birdswap or 0
  local done = d.applied.birdswap or 0
  if total <= done or frames - lastTrapFrame < 1200 then return end
  if not (isInGameMode and isInGameMode()) or levelCompleted or not birdReady or type(birds) ~= "table" then return end
  local cur = currentBirdName and objects.world[currentBirdName]
  local current = cur and cur.definition
  local choices, seen = {}, {}
  for _, b in pairs(birds) do
    local def = b.definition
    if b.controllable and not b.shot and def and def ~= current and not seen[def]
        and def ~= "ME_BAIT" and def ~= "BirdAntennaEgg" and string.find(def, "Bird") then
      seen[def] = true
      table.insert(choices, def)
    end
  end
  d.applied.birdswap = done + 1
  lastTrapFrame = frames
  dirty = true
  if #choices == 0 then
    toast("Bird Swap Trap fizzled: there is no other kind of bird here!")
  elseif pcall(powerups.replaceNextBirdWithBird, choices[math.random(#choices)]) then
    toast("Bird Swap Trap! The pigs switched your bird!")
  end
end

local function applyConsumables(d, inp)
  local changed = false
  local function delta(key, total)
    local have = d.applied[key] or 0
    if (total or 0) > have then
      d.applied[key] = total
      changed = true
      return total - have
    end
    return 0
  end
  local e = delta("eagles", inp.eagles)
  if e > 0 then SettingsWrapper:addMightyEagles(e) end
  for _, id in ipairs(POWERUPS) do
    local n = delta(id, inp.powerups and inp.powerups[id])
    if n > 0 then SettingsWrapper:setPowerUpAmount(id, SettingsWrapper:getPowerUpAmount(id) + n) end
  end
  if changed then
    pcall(savePurchases)
    dirty = true
  end
end

-- ---------------------------------------------------------------- connection (in-game connect screen)
-- The game cannot open sockets, so a hidden helper (the AP client started through ap_helper.lnk) does the
-- networking. The game hands it the connection details in "ap_connect.lua" (saveLuaFile) and the helper
-- reports progress in "ap_status.lua" (plain Lua next to the exe, global apStatus = { text = "..." }).
AP.status = "Not connected"

function readStatus()
  local chunk = loadfile("ap_status.lua")
  if not chunk then return end
  apStatus = nil
  -- only status about the current request counts (the file may be left over from a previous session)
  if pcall(chunk) and type(apStatus) == "table" and apStatus.text and apStatus.req == AP.req
      and apStatus.text ~= AP.status then
    AP.status = apStatus.text
    if not (menu.APConnect and menu.APConnect.open) and apStatus.toast then toast(AP.status) end
  end
end

function requestConnect(c)
  local saved = settings.root.archipelagoConnection or {}
  local req = ((saved.req or 0) % 100000) + 1  -- small ints: game numbers are float32
  AP.req = req
  settings.root.archipelagoConnection = { host = c.host, port = c.port, slot = c.slot, password = c.password, req = req }
  apConnect = { host = c.host, port = c.port, slot = c.slot, password = c.password, req = req }
  pcall(saveLuaFile, "ap_connect.lua", "apConnect")
  pcall(saveLuaFile, "settings.lua", "settings")
  AP.status = "Connecting..."
  pcall(res.openURL, "ap_helper.lnk")  -- the helper is single-instance; a running one just reconnects
end

function addMainMenuButton()
  local M = menu.MainMenu
  if M.__ap then return end
  M.__ap = true
  local vanillaInit, vanillaLayout = M.init, M.layout
  function M:init(...)
    vanillaInit(self, ...)
    local b = ui.ScalableButton:new("apButton", true)
    b:setImage("BTN_BG_GREEN")
    b.returnValue = "AP_OPEN"
    b.clickSound = "ButtonProceed"
    local icon = ui.Image:new("apIcon")
    icon:setImage("ICON_ARCHIPELAGO")
    b:addChild(icon)
    function b:onPointerEvent(...)
      local r = ui.ScalableButton.onPointerEvent(self, ...)
      if r == "AP_OPEN" then openConnectScreen() end
      return r
    end
    self:addChild(b)
  end
  function M:layout(...)
    vanillaLayout(self, ...)
    local b, exit = self:getChild("apButton"), self:getChild("exitButton")
    if b and exit then
      -- third slot of the bottom-left row (exit at 0.55, second button at 1.7 button widths)
      b.x = exit.x / 0.55 * 2.85
      b.y = exit.y
      b:setScale(ReferenceScaler.getWorldScale(true))
    end
  end
end

-- Clicking a locked level says what it still needs ("Needs: Ice Bird, Lazer Bird").
function addLevelHints()
  local B = menu.LevelButton
  if B.__ap then return end
  B.__ap = true
  local vanillaPointer = B.onPointerEvent
  function B:onPointerEvent(t, x, y, ...)
    if t == "LPRESS" and self.disabled and AP.active and managed(self.currentFolder) then
      local po, list = self.physicsObject, actions.myLevels[self.currentFolder]
      local name = po and list and list[po.startNumber]
      local need = name and AP.needs[name]
      if need and self.hitTest and self:hitTest(x, y) then toast("Needs: " .. need) end
    end
    return vanillaPointer(self, t, x, y, ...)
  end
end

-- Episode planets: AP episodes you have not received get the game's own planet padlock and
-- refuse clicks (the game's isEpisodeDisabledByDevice flag does both). Updated every frame,
-- so a planet opens as soon as its episode arrives.
function addEpisodeLocks()
  local B = menu.EpisodeButton
  if B.__ap then return end
  B.__ap = true
  local vanillaDraw = B.draw
  function B:draw(...)
    local po = self.physicsObject
    local folder = po and po.startNumber and actions.myLevelFolders[po.startNumber]
    if AP.active and folder and managed(folder) then
      self.isEpisodeDisabledByDevice = not AP.episodes[folder]
    end
    return vanillaDraw(self, ...)
  end
end

-- ---------------------------------------------------------------- locked episodes and levels
-- The episode carousel and the comics bypass the level buttons, so the entry points themselves are guarded.
local function lockedSound()
  pcall(playAudio, "LevelLocked")
end

local vanillaGotoLevelSelection = gotoLevelSelectionMenu
function gotoLevelSelectionMenu(p, ...)
  local folder = type(p) == "table" and p.startNumber and actions.myLevelFolders[p.startNumber]
  if AP.active and folder and managed(folder) and not AP.episodes[folder] then
    lockedSound()
    toast("Needs: " .. tostring(AP.episodeItems and AP.episodeItems[folder] or "this episode"))
    return
  end
  return vanillaGotoLevelSelection(p, ...)
end

-- "Next level" (level end screen, after a comic) must not walk into a level you do not have yet;
-- fall back to the level selection screen the same way the game does for its own locked levels.
local vanillaSetNextLevel = setNextLevel
function setNextLevel(a, b, ...)
  if not a and not b and AP.active and managed(currentFolder) and not (objects and objects.previousLevel) then
    local meta = getLevelMetadata(levelName)
    if not (meta and meta.nextLevelName) and not apIsLevelUnlocked(currentFolder, currentLevel + 1) then
      local list = actions.myLevels[currentFolder]
      local nxt = list and list[currentLevel + 1]
      if nxt and AP.needs[nxt] then toast("Next level needs: " .. AP.needs[nxt]) end
      setLevelName("LevelSelection")
      GameSystem.eventManager:notify({ id = events.EID_CHANGE_SCENE, target = "GameScene" })
      return
    end
  end
  return vanillaSetNextLevel(a, b, ...)
end

-- Padlocks on the planets of the episode carousel: the scene is rebuilt from this data file every
-- time the screen opens, so locked planets get the game's EPISODE_PLANET_LOCK sprite added on top.
local function lockPlanetDef(def)
  if type(def) ~= "table" then return end
  if def.condition then  -- some planets (Danger Zone, Eggsteroids) sit inside a conditional definition
    lockPlanetDef(def.condition.trueDef)
    lockPlanetDef(def.condition.falseDef)
  end
  if def.metaType == "episode_button" and def.metaData and type(def.composite) == "table" then
    for i = #def.composite, 1, -1 do
      if def.composite[i].apLock then table.remove(def.composite, i) end
    end
    local folder = actions.myLevelFolders[def.metaData.episode]
    if folder and managed(folder) and not AP.episodes[folder] then
      table.insert(def.composite, { sprite = "EPISODE_PLANET_LOCK", pos = { x = 0, y = 0 }, apLock = true })
    end
  end
end

local function lockScenePlanets(t)
  for _, ent in pairs(t.entities or {}) do lockPlanetDef(ent.def) end
end

if native and native.loadLuaTable then
  local vanillaLoadLuaTable = native.loadLuaTable
  native.loadLuaTable = function(path, ...)
    local t, err = vanillaLoadLuaTable(path, ...)
    if path == "scenes/EpisodeSelection.lua" and type(t) == "table" and AP.active then pcall(lockScenePlanets, t) end
    return t, err
  end
end

local vanillaRequireFile = requireFile
function requireFile(path, ...)
  local r = vanillaRequireFile(path, ...)
  if path == "menu/MainMenu.lua" and menu and menu.MainMenu then pcall(addMainMenuButton) end
  if path == "menu/EpisodeButton.lua" and menu and menu.EpisodeButton then pcall(addEpisodeLocks) end
  if path == "menu/LevelButton.lua" and menu and menu.LevelButton then pcall(addLevelHints) end
  return r
end

-- The connect screen, built from the game's own dialog panel, fonts and buttons.
local FIELDS = {
  { key = "host", label = "Server", default = "archipelago.gg" },
  { key = "port", label = "Port", default = "38281", digits = true },
  { key = "slot", label = "Slot name", default = "" },
  { key = "password", label = "Password", default = "", secret = true },
}
local MAX_LEN = 40

local function ensureConnectClass()
  if menu.APConnect then return end
  for _, f in ipairs({ "lua/Class.lua", "ui/Frame.lua", "ui/BGBox.lua", "ui/Text.lua", "ui/TextLine.lua",
    "ui/Image.lua", "ui/ScalableButton.lua", "referenceScaler.lua" }) do requireFile(f) end
  local C = lua.Class.create(ui.Frame)
  menu.APConnect = C

  function C:init()
    ui.Frame.init(self, "apConnect")
    local saved = settings.root.archipelagoConnection or {}
    self.values, self.focus, self.blink, self.shift, self.ctrl = {}, 3, 0, false, false
    for i, f in ipairs(FIELDS) do
      self.values[f.key] = tostring(saved[f.key] or f.default)
      if f.key == "slot" and self.values.slot == "" then self.focus = 3 end
    end
    local bg = ui.BGBox:new("panel")
    bg.hanchor, bg.vanchor = "LEFT", "TOP"
    self:addChild(bg)
    self:addChild(ui.Text:new("title", "Connect to Archipelago", nil, getFontHeadline))
    for i, f in ipairs(FIELDS) do
      self:addChild(ui.TextLine:new("label" .. i, f.label, nil, getFontBasic, "LEFT", "VCENTER"))
      self:addChild(ui.BGBox:new("box" .. i))
      self:addChild(ui.TextLine:new("value" .. i, " ", nil, getFontBasic, "LEFT", "VCENTER"))
    end
    self:addChild(ui.Text:new("status", " ", nil, getFontBasic))
    local close = ui.ScalableButton:new("close", true)
    close:setImage("BTN_X")
    close.returnValue, close.clickSound = "AP_CLOSE", "ButtonBack"
    self:addChild(close)
    local ok = ui.ScalableButton:new("confirm", true)
    ok:setImage("BTN_CHECK")
    ok.returnValue = "AP_CONNECT"
    self:addChild(ok)
    C.open = true
    self:refresh()
    self:layout()
  end

  function C:layout()
    ui.Frame.layout(self)
    local s = ReferenceScaler.getWorldScale(true)
    local W, H = screenWidth * 0.62 / s, screenHeight * 0.88 / s
    local px, py = (screenWidth - W * s) * 0.5, (screenHeight - H * s) * 0.5
    local bg = self:getChild("panel")
    bg:setScale(s)
    bg:setSize(W, H)
    bg.x, bg.y = px, py
    local title = self:getChild("title")
    title:setScale(s)
    title.x, title.y = screenWidth * 0.5, py + H * s * 0.10
    self.boxes = {}
    local rowH = H * s * 0.17  -- box borders have a minimum height, so space rows instead of shrinking boxes
    for i in ipairs(FIELDS) do
      local y = py + H * s * 0.25 + (i - 1) * rowH
      local label, box, value = self:getChild("label" .. i), self:getChild("box" .. i), self:getChild("value" .. i)
      label:setScale(s)
      label.x, label.y = px + W * s * 0.07, y
      local bw, bh = W * 0.6, rowH / s * 0.55
      box:setScale(s)
      box:setSize(bw, bh)
      box.x, box.y = px + W * s * 0.66, y
      value:setScale(s)
      value.x, value.y = box.x - bw * s * 0.5 + 12 * s, y
      self.boxes[i] = { x = box.x, y = y, w = bw * s, h = bh * s }
    end
    local status = self:getChild("status")
    status:setScale(s * 0.8)
    status.x, status.y = screenWidth * 0.5, py + H * s * 0.87
    local close, ok = self:getChild("close"), self:getChild("confirm")
    close:setScale(s)
    ok:setScale(s)
    close.x, close.y = px + close.w * s * 0.4, py + H * s
    ok.x, ok.y = px + W * s - ok.w * s * 0.4, py + H * s
  end

  function C:refresh()
    for i, f in ipairs(FIELDS) do
      local v = self.values[f.key]
      if f.secret then v = string.rep("*", string.len(v)) end
      if string.len(v) > 22 then v = ".." .. string.sub(v, -20) end
      if i == self.focus and self.blink < 0.5 then v = v .. "_" end
      self:getChild("value" .. i):setText(v ~= "" and v or " ")
    end
    self:getChild("status"):setText(AP.status or " ")
  end

  function C:update(dt, ...)
    ui.Frame.update(self, dt, ...)
    self.blink = ((self.blink or 0) + (tonumber(dt) or 0.016)) % 1
    self:refresh()
  end

  function C:draw(x, y)
    drawRect(0, 0, 0, 0.7, 0, 0, screenWidth, screenHeight, false)
    ui.Frame.draw(self, x, y)
  end

  function C:close()
    C.open = false
    self:removeSelf()
  end

  function C:submit()
    local v = self.values
    if v.slot == "" then
      AP.status = "Enter your slot name"
      self.focus = 3
      return
    end
    requestConnect({ host = v.host, port = v.port, slot = v.slot, password = v.password })
  end

  function C:paste()
    local ok, text = pcall(getClipboardText)
    if not ok or type(text) ~= "string" then return end
    text = string.gsub(string.gsub(text, "^%s+", ""), "%s+$", "")
    local key = FIELDS[self.focus].key
    if key == "host" then
      text = string.gsub(string.gsub(text, "^/connect%s+", ""), "^wss?://", "")
      local h, p = string.match(text, "^([^:]+):(%d+)$")
      if h then
        self.values.host, self.values.port = h, p
        return
      end
    end
    self:type(text)
  end

  function C:type(text)
    local f = FIELDS[self.focus]
    if f.digits then text = string.gsub(text, "%D", "") end
    text = string.gsub(text, "[^%w%s%.%-_:@!%?#%$%%&%*%+=/]", "")
    self.values[f.key] = string.sub(self.values[f.key] .. text, 1, MAX_LEN)
  end

  function C:onKeyEvent(t, k)
    if k == "SHIFT" then self.shift = (t ~= "RELEASE") return -1 end
    if k == "CONTROL" then self.ctrl = (t ~= "RELEASE") return -1 end
    if t ~= "PRESS" then return -1 end
    local key = FIELDS[self.focus].key
    if k == "ESCAPE" or k == "KEY_BACK" then
      playAudio("ButtonBack")
      self:close()
    elseif k == "RETURN" then
      self:submit()
    elseif k == "TAB" or k == "DOWN" then
      self.focus = self.focus % #FIELDS + 1
    elseif k == "UP" then
      self.focus = (self.focus + #FIELDS - 2) % #FIELDS + 1
    elseif k == "BACKSPACE" or k == "DELETE" then
      self.values[key] = string.sub(self.values[key], 1, -2)
    elseif (k == "V" and self.ctrl) or (k == "INSERT" and self.shift) then
      self:paste()
    elseif k == "SPACE" then
      self:type(key == "host" and "." or " ")  -- the engine has no '.' key; hostnames never contain spaces
    elseif k == "DASH" or k == "SUBTRACT" then
      self:type(self.shift and "_" or "-")
    elseif string.len(k) == 1 and not self.ctrl then
      self:type(self.shift and k or string.lower(k))
    end
    self.blink = 0
    return -1
  end

  function C:onPointerEvent(t, x, y)
    local r = ui.Frame.onPointerEvent(self, t, x, y)
    if r == "AP_CLOSE" then
      self:close()
    elseif r == "AP_CONNECT" then
      self:submit()
    elseif t == "LPRESS" and self.boxes then  -- the engine reports mouse presses as LPRESS
      for i, b in ipairs(self.boxes) do
        if math.abs(x - b.x) <= b.w * 0.5 and math.abs(y - b.y) <= b.h * 0.5 then
          self.focus, self.blink = i, 0
        end
      end
    end
    return -1
  end
end

function openConnectScreen()
  local ok, err = pcall(function()
    ensureConnectClass()
    local nf = GameSystem.menuManager:notificationsFrame()
    if nf:getChild("apConnect") then return end  -- already open
    nf:addChild(menu.APConnect:new())
  end)
  if not ok then
    apError = { msg = "connect screen: " .. tostring(err) }
    pcall(saveLuaFile, "ap_error.lua", "apError")
  end
end

local function poll()
  installHooks()
  -- wait until the splash screens are done and the menus exist
  if not (menu and menu.SplashPage and menu.SplashPage.splashShown and GameSystem and GameSystem.menuManager) then
    return
  end
  local d = data()
  if not d then return end
  readStatus()
  if not AP.autoConnected then
    AP.autoConnected = true
    local c = settings.root.archipelagoConnection
    if c and c.slot and c.slot ~= "" then requestConnect(c) end
  end
  local chunk = loadfile(IN_FILE)
  if not chunk then return end
  apIn = nil
  if not pcall(chunk) or type(apIn) ~= "table" or not apIn.seed then return end
  local inp = apIn

  if d.seed ~= inp.seed then
    -- new multiworld: forget the previous seed's AP progress (vanilla highscores are untouched)
    d.seed, d.cleared, d.perfect, d.applied, d.msgSeen, d.deaths = inp.seed, {}, {}, {}, 0, 0
    d.stars = {}
    d.deathSeen = inp.deathlink and inp.deathlink.id or 0
    dirty = true
  end
  AP.active = true
  AP.managed = inp.managed
  AP.needs = inp.needs or {}
  AP.episodeItems = inp.episodeItems
  AP.open = inp.open or {}
  AP.episodes = inp.episodes or {}
  for folder in pairs(AP.episodes) do
    if g_episodePurchasesTable and g_episodePurchasesTable.root then g_episodePurchasesTable.root[folder] = true end
  end
  if not announced then
    announced = true
    toast("Archipelago: playing as " .. tostring(inp.slot))
  end

  applyConsumables(d, inp)
  applyTraps(d, inp)

  for _, m in ipairs(inp.messages or {}) do
    if m.id > (d.msgSeen or 0) then
      d.msgSeen = m.id
      toast(m.text)
      dirty = true
    end
  end

  local dl = inp.deathlink
  if dl and dl.id > (d.deathSeen or 0) then
    d.deathSeen = dl.id
    dirty = true
    if inp.deathlinkEnabled and isInGameMode and isInGameMode() and not levelCompleted then
      toast(tostring(dl.source) .. " died. The pigs win this one!")
      pcall(returnToLevelSelection)
    end
  end

  if dirty then
    dirty = false
    apState = d
    pcall(saveLuaFile, "ap_state.lua", "apState")
    pcall(saveLuaFile, "settings.lua", "settings")
  end
end

local vanillaUpdate = update
function update(...)
  frames = frames + 1
  if frames % POLL_FRAMES == 0 then
    local ok, err = pcall(poll)
    if not ok then
      apError = { msg = tostring(err) }
      pcall(saveLuaFile, "ap_error.lua", "apError")
    end
  end
  return vanillaUpdate(...)
end

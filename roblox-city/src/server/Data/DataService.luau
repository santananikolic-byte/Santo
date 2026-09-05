--!strict
--[[
	DataService
	Laden, Halten und Speichern von Spielerprofilen.

	Der wichtigste Teil ist die Sitzungssperre. Ohne sie funktioniert der
	klassischste Dupe der Roblox-Welt: Spieler joint Server A, wartet bis
	geladen, joint parallel Server B mit demselben Speicherstand, gibt auf
	A das Geld aus, laesst B mit dem alten Stand speichern. Die Sperre
	macht daraus einen Ladefehler statt einer Geldquelle.

	Ein Schreibvorgang erledigt beides gleichzeitig: er speichert die Daten
	und erneuert die Sperre.
]]

local DataStoreService = game:GetService("DataStoreService")
local HttpService = game:GetService("HttpService")
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")

local Config = require(ReplicatedStorage.Shared.Config)
local Signal = require(ReplicatedStorage.Shared.Signal)
local Profile = require(script.Parent.Profile)

type Data = Profile.Data

type Session = {
	player: Player,
	userId: number,
	key: string,
	data: Data,
	-- Solange false, darf nichts mehr geschrieben werden: der Spieler ist
	-- bereits raus und die Sperre freigegeben.
	active: boolean,
	loadedAt: number,
}

local DataService = {}

-- Feuert, sobald ein Profil geladen und benutzbar ist: (player, data)
DataService.ProfileLoaded = Signal.new()
-- Feuert kurz vor dem letzten Speichern: (player, data)
DataService.ProfileReleasing = Signal.new()

local store: DataStore
local sessions: { [number]: Session } = {}
local jobId: string
local usingMemoryFallback = false
local shuttingDown = false

-- ============================================================
-- Interne Helfer
-- ============================================================

local function keyFor(userId: number): string
	return `Player_{userId}`
end

--[[
	Wiederholt eine DataStore-Operation mit exponentiell wachsender Pause.

	DataStore-Fehler sind fast immer transient (Drosselung, kurzer Ausfall).
	Ein einzelner fehlgeschlagener Versuch darf deshalb nie zu einem
	zurueckgesetzten Profil fuehren.
]]
local function withRetry<T>(label: string, operation: () -> T): (boolean, T?)
	local delay = Config.Data.RetryBaseDelay

	for attempt = 1, Config.Data.MaxRetries do
		local ok, result = pcall(operation)
		if ok then
			return true, result
		end

		if attempt == Config.Data.MaxRetries then
			warn(`[DataService] {label} nach {attempt} Versuchen aufgegeben: {result}`)
			return false, nil
		end

		task.wait(delay)
		delay *= 2
	end

	return false, nil
end

--[[
	Holt die Sperre und liefert die Daten zurueck.

	Rueckgabe:
	  "ok",      data   - Sperre gehoert uns
	  "locked",  nil    - anderer Server haelt eine frische Sperre
	  "error",   nil    - DataStore nicht erreichbar
]]
local function acquire(userId: number): (string, Data?)
	local key = keyFor(userId)
	local outcome = "error"
	local loaded: Data? = nil

	local ok = withRetry(`acquire {key}`, function()
		store:UpdateAsync(key, function(entry)
			entry = entry or {}
			local lock = entry.lock
			local now = os.time()

			-- Fremde, noch gueltige Sperre: Schreibvorgang abbrechen.
			-- nil aus dem Transformer heisst "nichts aendern".
			if lock and lock.jobId ~= jobId and (now - (lock.heartbeat or 0)) < Config.Data.SessionLockSeconds then
				outcome = "locked"
				return nil
			end

			local data, repaired = Profile.reconcile(entry.data)
			if repaired and entry.data ~= nil then
				warn(`[DataService] Profil {key} musste repariert werden`)
			end

			entry.data = data
			entry.lock = { jobId = jobId, heartbeat = now }

			outcome = "ok"
			loaded = data
			return entry
		end)
		return true
	end)

	if not ok then
		return "error", nil
	end
	return outcome, loaded
end

--[[
	Schreibt die Daten und erneuert oder loest die Sperre.

	releaseLock = true wird beim Verlassen benutzt. Der naechste Server
	kann dann sofort laden statt SessionLockSeconds zu warten.
]]
local function commit(session: Session, releaseLock: boolean): boolean
	if usingMemoryFallback then
		return true
	end

	session.data.lastSeen = os.time()
	local snapshot = session.data

	local ok = withRetry(`commit {session.key}`, function()
		store:UpdateAsync(session.key, function(entry)
			entry = entry or {}
			local lock = entry.lock

			-- Fremde Sperre bedeutet: unsere Sitzung wurde uebernommen,
			-- weil wir zu lange nicht geschrieben haben. Dann sind unsere
			-- Daten die veralteten und duerfen nichts ueberschreiben.
			if lock and lock.jobId ~= jobId then
				warn(`[DataService] Sperre fuer {session.key} gehoert inzwischen {lock.jobId} - Schreibvorgang verworfen`)
				return nil
			end

			entry.data = snapshot
			entry.lock = if releaseLock then nil else { jobId = jobId, heartbeat = os.time() }
			return entry
		end)
		return true
	end)

	return ok
end

-- ============================================================
-- Lebenszyklus eines Spielers
-- ============================================================

local function onPlayerAdded(player: Player)
	local userId = player.UserId
	local outcome, data = acquire(userId)

	if outcome == "locked" then
		-- Kein stiller Neustart mit leerem Profil: lieber ein ehrlicher
		-- Kick als ein Spieler, der auf einem Nullstand weiterspielt und
		-- den Fortschritt beim Speichern verliert.
		player:Kick("Dein Speicherstand ist noch auf einem anderen Server aktiv. Bitte in etwa einer Minute erneut beitreten.")
		return
	end

	if outcome ~= "ok" or not data then
		player:Kick("Speicherstand konnte nicht geladen werden. Bitte erneut versuchen.")
		return
	end

	-- Waehrend des Ladens kann der Spieler laengst weg sein.
	if not player.Parent then
		local throwaway: Session = {
			player = player,
			userId = userId,
			key = keyFor(userId),
			data = data,
			active = true,
			loadedAt = os.clock(),
		}
		commit(throwaway, true)
		return
	end

	local session: Session = {
		player = player,
		userId = userId,
		key = keyFor(userId),
		data = data,
		active = true,
		loadedAt = os.clock(),
	}
	sessions[userId] = session

	DataService.ProfileLoaded:Fire(player, data)

	-- Speicher- und Sperrenschleife. Laeuft, bis die Sitzung endet.
	task.spawn(function()
		while session.active do
			task.wait(Config.Data.SaveIntervalSeconds)
			if not session.active or shuttingDown then
				break
			end
			commit(session, false)
		end
	end)
end

local function onPlayerRemoving(player: Player)
	local session = sessions[player.UserId]
	if not session then
		return
	end

	session.active = false
	sessions[player.UserId] = nil

	DataService.ProfileReleasing:Fire(player, session.data)
	commit(session, true)
end

-- ============================================================
-- Oeffentliche API
-- ============================================================

--[[ Liefert die lebende Profiltabelle oder nil, wenn nicht geladen. ]]
function DataService.get(player: Player): Data?
	local session = sessions[player.UserId]
	return if session and session.active then session.data else nil
end

function DataService.isReady(player: Player): boolean
	return DataService.get(player) ~= nil
end

--[[
	Wartet, bis das Profil geladen ist. Gibt nil zurueck, wenn der Spieler
	vorher geht oder die Zeit ablaeuft.
]]
function DataService.await(player: Player, timeout: number?): Data?
	local deadline = os.clock() + (timeout or 20)

	while os.clock() < deadline do
		local data = DataService.get(player)
		if data then
			return data
		end
		if not player.Parent then
			return nil
		end
		task.wait(0.1)
	end

	return nil
end

--[[ Erzwingt ein sofortiges Speichern. Fuer Kaeufe mit echtem Wert. ]]
function DataService.flush(player: Player): boolean
	local session = sessions[player.UserId]
	if not session or not session.active then
		return false
	end
	return commit(session, false)
end

function DataService.init()
	jobId = if game.JobId ~= "" then game.JobId else `studio-{HttpService:GenerateGUID(false)}`

	local ok, result = pcall(function()
		return DataStoreService:GetDataStore(Config.Data.StoreName)
	end)

	if ok and result then
		store = result
	else
		usingMemoryFallback = true
		warn("[DataService] Kein DataStore-Zugriff. Profile bleiben nur im Speicher dieser Sitzung.")
	end

	-- Studio ohne aktivierten API-Zugriff: einmal testen statt bei jedem
	-- Join in fuenf Wiederholungen zu laufen.
	if not usingMemoryFallback and RunService:IsStudio() then
		local reachable = pcall(function()
			store:GetAsync("__connectivity_probe")
		end)
		if not reachable then
			usingMemoryFallback = true
			warn("[DataService] Studio ohne API-Zugriff. Profile bleiben nur im Speicher dieser Sitzung.")
		end
	end
end

function DataService.start()
	if usingMemoryFallback then
		-- Ersatzpfad: Template statt DataStore, damit das Spiel in Studio
		-- ohne API-Zugriff trotzdem vollstaendig spielbar ist.
		local function grantTemplate(player: Player)
			local session: Session = {
				player = player,
				userId = player.UserId,
				key = keyFor(player.UserId),
				data = Profile.template(),
				active = true,
				loadedAt = os.clock(),
			}
			sessions[player.UserId] = session
			DataService.ProfileLoaded:Fire(player, session.data)
		end

		Players.PlayerAdded:Connect(grantTemplate)
		for _, player in Players:GetPlayers() do
			task.spawn(grantTemplate, player)
		end
		Players.PlayerRemoving:Connect(onPlayerRemoving)
		return
	end

	Players.PlayerAdded:Connect(function(player)
		task.spawn(onPlayerAdded, player)
	end)
	Players.PlayerRemoving:Connect(onPlayerRemoving)

	-- Spieler, die vor dem Start des Skripts drin waren (Studio, Reload).
	for _, player in Players:GetPlayers() do
		task.spawn(onPlayerAdded, player)
	end

	game:BindToClose(function()
		shuttingDown = true

		local pending = 0
		local finished = 0

		for _, session in sessions do
			pending += 1
			task.spawn(function()
				session.active = false
				DataService.ProfileReleasing:Fire(session.player, session.data)
				commit(session, true)
				finished += 1
			end)
		end

		if pending == 0 then
			return
		end

		local deadline = os.clock() + Config.Data.ShutdownTimeout
		while finished < pending and os.clock() < deadline do
			task.wait(0.1)
		end

		if finished < pending then
			warn(`[DataService] Serverabbau: {pending - finished} Profile konnten nicht mehr gespeichert werden`)
		end
	end)
end

return DataService

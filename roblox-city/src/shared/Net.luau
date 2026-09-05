--!strict
--[[
	Net
	Ein einziger Ort, an dem jedes Remote des Spiels deklariert ist.

	Warum das wichtig ist: ein Remote, das irgendwo im Code per
	Instance.new() entsteht, hat garantiert kein Rate-Limit und garantiert
	keine Argumentpruefung. Hier bekommt jedes Remote beides, oder es
	existiert nicht.

	Der Server erzeugt die Instanzen beim Start, der Client wartet auf sie.
]]

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")

local RateLimiter = require(script.Parent.RateLimiter)

local IS_SERVER = RunService:IsServer()
local REMOTE_TIMEOUT = 30

type Definition = {
	kind: "Event" | "Function",
	-- Nur relevant fuer Aufrufe vom Client. Server -> Client braucht kein Limit.
	limit: { calls: number, window: number }?,
}

local Net = {}

--[[
	Alle Remotes des Spiels. Die Limits sind bewusst knapp: ein ehrlicher
	Client kommt nie in ihre Naehe, ein Auto-Clicker sofort.
]]
local definitions: { [string]: Definition } = {
	-- Wirtschaft ------------------------------------------------------
	WalletChanged = { kind = "Event" },
	Notify = { kind = "Event" },

	RequestDeposit = { kind = "Function", limit = { calls = 4, window = 5 } },
	RequestWithdraw = { kind = "Function", limit = { calls = 4, window = 5 } },
	RequestPurchase = { kind = "Function", limit = { calls = 6, window = 10 } },

	-- Fuhrpark des Spielers. Reine Anzeige: der Server prueft beim
	-- Einsetzen erneut, was wirklich jemandem gehoert.
	GarageSync = { kind = "Event" },

	-- Fahrzeuge -------------------------------------------------------
	RequestSpawnVehicle = { kind = "Function", limit = { calls = 3, window = 10 } },
	RequestEnterVehicle = { kind = "Function", limit = { calls = 8, window = 5 } },
	RequestExitVehicle = { kind = "Event", limit = { calls = 8, window = 5 } },
	VehicleSpawned = { kind = "Event" },

	-- Bewusst NICHT vorhanden: ein Remote, ueber das der Client seine
	-- Fahrzeugposition oder -geschwindigkeit meldet. Der Server hat die
	-- Physik selbst; ein solches Remote waere reine Angriffsflaeche und
	-- genau der Hebel fuer Teleport- und Speed-Exploits.

	-- Fahndung --------------------------------------------------------
	WantedChanged = { kind = "Event" },

	-- Jobs ------------------------------------------------------------
	RequestStartJob = { kind = "Function", limit = { calls = 4, window = 10 } },
	RequestAbortJob = { kind = "Event", limit = { calls = 4, window = 10 } },
	JobStateChanged = { kind = "Event" },
	JobProgress = { kind = "Event" },
}

Net.Definitions = definitions

local remoteFolder: Folder
local cache: { [string]: Instance } = {}
local limiters: { [string]: RateLimiter.RateLimiter } = {}

local function ensureFolder(): Folder
	if remoteFolder then
		return remoteFolder
	end

	if IS_SERVER then
		local existing = ReplicatedStorage:FindFirstChild("Remotes")
		if existing then
			remoteFolder = existing :: Folder
		else
			remoteFolder = Instance.new("Folder")
			remoteFolder.Name = "Remotes"
			remoteFolder.Parent = ReplicatedStorage
		end
	else
		remoteFolder = ReplicatedStorage:WaitForChild("Remotes", REMOTE_TIMEOUT) :: Folder
		assert(remoteFolder, "Net: Remotes-Ordner ist nicht erschienen")
	end

	return remoteFolder
end

local function resolve(name: string): Instance
	local cached = cache[name]
	if cached then
		return cached
	end

	local definition = Net.Definitions[name]
	assert(definition, `Net: unbekanntes Remote "{name}"`)

	local folder = ensureFolder()
	local className = definition.kind == "Event" and "RemoteEvent" or "RemoteFunction"

	local instance: Instance
	if IS_SERVER then
		instance = folder:FindFirstChild(name) or (function()
			local created = Instance.new(className)
			created.Name = name
			created.Parent = folder
			return created
		end)()
	else
		instance = folder:WaitForChild(name, REMOTE_TIMEOUT)
		assert(instance, `Net: Remote "{name}" ist nicht erschienen`)
	end

	cache[name] = instance
	return instance
end

--[[ Erzeugt alle Remotes im Voraus. Nur Server, beim Start aufrufen. ]]
function Net.publish()
	assert(IS_SERVER, "Net.publish ist serverseitig")
	for name in Net.Definitions do
		resolve(name)
	end
end

function Net.event(name: string): RemoteEvent
	local definition = Net.Definitions[name]
	assert(definition and definition.kind == "Event", `Net: "{name}" ist kein RemoteEvent`)
	return resolve(name) :: RemoteEvent
end

function Net.remoteFunction(name: string): RemoteFunction
	local definition = Net.Definitions[name]
	assert(definition and definition.kind == "Function", `Net: "{name}" ist keine RemoteFunction`)
	return resolve(name) :: RemoteFunction
end

local function limiterFor(name: string): RateLimiter.RateLimiter?
	local definition = Net.Definitions[name]
	if not definition or not definition.limit then
		return nil
	end

	local limiter = limiters[name]
	if not limiter then
		limiter = RateLimiter.new(definition.limit.calls, definition.limit.window)
		limiters[name] = limiter
	end
	return limiter
end

--[[
	Bindet einen Server-Handler an ein RemoteEvent.

	Der Wrapper uebernimmt drei Dinge, die man sonst in jedem Handler
	einzeln vergisst:
	  1. Rate-Limit pro Spieler
	  2. pcall, damit ein Fehler in einem Handler nicht den Aufrufer toetet
	  3. eine verstaendliche Fehlermeldung mit Remote-Name im Log
]]
function Net.bindEvent(name: string, handler: (player: Player, ...any) -> ())
	assert(IS_SERVER, "Net.bindEvent ist serverseitig")

	local limiter = limiterFor(name)

	Net.event(name).OnServerEvent:Connect(function(player, ...)
		if limiter and not limiter:Consume(player.UserId) then
			return
		end

		local ok, err = pcall(handler, player, ...)
		if not ok then
			warn(`[Net] Handler "{name}" ist gescheitert fuer {player.Name}: {err}`)
		end
	end)
end

--[[
	Bindet einen Server-Handler an eine RemoteFunction.

	Wichtig: Ein Fehler wird hier NICHT weitergeworfen. Ein Error in einer
	RemoteFunction laesst den wartenden Client haengen. Stattdessen kommt
	immer eine Antwort im Format (ok: boolean, payloadOrReason: any).
]]
function Net.bindFunction(name: string, handler: (player: Player, ...any) -> ...any)
	assert(IS_SERVER, "Net.bindFunction ist serverseitig")

	local limiter = limiterFor(name)

	Net.remoteFunction(name).OnServerInvoke = function(player, ...)
		if limiter and not limiter:Consume(player.UserId) then
			return false, "Zu viele Anfragen. Kurz durchatmen."
		end

		local results = table.pack(pcall(handler, player, ...))
		if not results[1] then
			warn(`[Net] Handler "{name}" ist gescheitert fuer {player.Name}: {results[2]}`)
			return false, "Interner Fehler."
		end

		return table.unpack(results, 2, results.n)
	end
end

--[[ Gibt die Rate-Limit-Buckets eines Spielers frei. ]]
function Net.releasePlayer(userId: number)
	for _, limiter in limiters do
		limiter:Release(userId)
	end
end

return Net

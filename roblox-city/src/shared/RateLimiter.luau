--!strict
--[[
	RateLimiter
	Token-Bucket pro Spieler und Schluessel.

	Ein Remote ohne Limit ist die einfachste Denial-of-Service-Luecke, die es
	in Roblox gibt: ein Exploiter feuert es in einer while-true-Schleife und
	der Server steht. Jedes Remote in diesem Projekt laeuft durch hier.
]]

local RateLimiter = {}
RateLimiter.__index = RateLimiter

type Bucket = {
	tokens: number,
	lastRefill: number,
}

export type RateLimiter = typeof(setmetatable({} :: {
	_capacity: number,
	_window: number,
	_buckets: { [number]: Bucket },
}, RateLimiter))

--[[
	capacity = erlaubte Aufrufe pro window (Sekunden).
]]
function RateLimiter.new(capacity: number, window: number): RateLimiter
	assert(capacity > 0, "capacity muss positiv sein")
	assert(window > 0, "window muss positiv sein")

	return setmetatable({
		_capacity = capacity,
		_window = window,
		_buckets = {},
	}, RateLimiter) :: any
end

--[[
	Zieht ein Token. true = erlaubt, false = Budget aufgebraucht.
]]
function RateLimiter:Consume(userId: number, cost: number?): boolean
	local now = os.clock()
	local bucket = self._buckets[userId]

	if not bucket then
		bucket = { tokens = self._capacity, lastRefill = now }
		self._buckets[userId] = bucket
	end

	-- Kontinuierliches Nachfuellen statt fester Fenster. Verhindert den
	-- Burst genau an der Fenstergrenze, der bei naiven Zaehlern das
	-- Doppelte des Limits durchlaesst.
	local elapsed = now - bucket.lastRefill
	if elapsed > 0 then
		bucket.tokens = math.min(self._capacity, bucket.tokens + elapsed * (self._capacity / self._window))
		bucket.lastRefill = now
	end

	local amount = cost or 1
	if bucket.tokens >= amount then
		bucket.tokens -= amount
		return true
	end

	return false
end

--[[ Aufraeumen, wenn ein Spieler geht. Sonst waechst die Tabelle ueber die
     Serverlaufzeit unbegrenzt. ]]
function RateLimiter:Release(userId: number)
	self._buckets[userId] = nil
end

return RateLimiter

--!strict
--[[
	Signal
	Minimaler Ersatz fuer BindableEvents. Schneller, weil nichts durch die
	Roblox-Serialisierung laeuft, und Tabellen bleiben Referenzen statt Kopien.
]]

export type Connection = {
	Disconnect: (self: Connection) -> (),
	Connected: boolean,
}

--[[
	Handler laufen ueber task.spawn: ein Fehler in einem Handler soll die
	uebrigen nicht mitreissen, und ein langsamer Handler soll den Aufrufer
	von Fire nicht aufhalten.

	Ausserhalb von Roblox gibt es task nicht. Der direkte Aufruf als
	Rueckfallebene kostet zwei Zeilen und macht das Modul im Testlauf
	ohne Roblox-Nachbau pruefbar - genau die Tests, die die Buchfuehrung
	ueber die Handler absichern.
]]
local spawn: (fn: (...any) -> (), ...any) -> () = if task then task.spawn else function(fn, ...)
	fn(...)
end

local Connection = {}
Connection.__index = Connection

function Connection.new(signal, fn)
	return setmetatable({
		_signal = signal,
		_fn = fn,
		Connected = true,
	}, Connection)
end

function Connection:Disconnect()
	if not self.Connected then
		return
	end
	self.Connected = false

	local handlers = self._signal._handlers
	local index = table.find(handlers, self)
	if index then
		table.remove(handlers, index)
	end
end

local Signal = {}
Signal.__index = Signal

export type Signal = typeof(setmetatable({} :: {
	_handlers: { any },
}, Signal))

function Signal.new(): Signal
	return setmetatable({ _handlers = {} }, Signal) :: any
end

function Signal:Connect(fn: (...any) -> ()): Connection
	local connection = Connection.new(self, fn)
	table.insert(self._handlers, connection)
	return connection :: any
end

function Signal:Once(fn: (...any) -> ()): Connection
	local connection
	connection = self:Connect(function(...)
		connection:Disconnect()
		fn(...)
	end)
	return connection
end

function Signal:Fire(...: any)
	-- Ueber eine Kopie iterieren: ein Handler darf sich waehrend des
	-- Feuerns abmelden, ohne die Schleife zu zerstoeren.
	local snapshot = table.clone(self._handlers)
	for _, connection in snapshot do
		if connection.Connected then
			spawn(connection._fn, ...)
		end
	end
end

function Signal:DisconnectAll()
	for _, connection in table.clone(self._handlers) do
		connection:Disconnect()
	end
end

return Signal

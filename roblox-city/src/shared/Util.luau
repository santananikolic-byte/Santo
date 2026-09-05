--!strict
--[[ Util - kleine Helfer, die beide Seiten brauchen. ]]

local Util = {}

--[[
	Formatiert einen Betrag als Waehrung: 1234567 -> "$1.234.567"
]]
function Util.formatMoney(amount: number): string
	local negative = amount < 0
	local digits = tostring(math.floor(math.abs(amount)))

	local grouped = ""
	local count = 0
	for i = #digits, 1, -1 do
		grouped = digits:sub(i, i) .. grouped
		count += 1
		if count % 3 == 0 and i > 1 then
			grouped = "." .. grouped
		end
	end

	return (negative and "-$" or "$") .. grouped
end

--[[ Sekunden -> "3:07" ]]
function Util.formatClock(seconds: number): string
	seconds = math.max(0, math.floor(seconds))
	return string.format("%d:%02d", seconds // 60, seconds % 60)
end

--[[
	Rundet auf ganze Zahlen und klemmt in einen Bereich. Wird ueberall dort
	benutzt, wo Geld oder Punkte aus einer Formel kommen: Nachkommastellen
	in einer Waehrung sind der Anfang von Rundungs-Dupes.
]]
function Util.clampInt(value: number, min: number, max: number): number
	if value ~= value then -- NaN
		return min
	end
	return math.clamp(math.floor(value + 0.5), min, max)
end

--[[ Prueft, ob ein Wert eine endliche Zahl ist. Wichtig fuer alles, was
     ueber ein Remote hereinkommt: NaN und inf ueberleben die Serialisierung. ]]
function Util.isFiniteNumber(value: any): boolean
	return type(value) == "number" and value == value and value ~= math.huge and value ~= -math.huge
end

--[[ Sicherer Vector3 aus Remote-Daten. Gibt nil zurueck, wenn irgendeine
     Komponente Muell ist. ]]
function Util.sanitizeVector(value: any): Vector3?
	if typeof(value) ~= "Vector3" then
		return nil
	end
	if not (Util.isFiniteNumber(value.X) and Util.isFiniteNumber(value.Y) and Util.isFiniteNumber(value.Z)) then
		return nil
	end
	return value
end

--[[ Tiefe Kopie fuer Konfigurations- und Profiltabellen. ]]
function Util.deepCopy<T>(source: T): T
	if type(source) ~= "table" then
		return source
	end

	local copy = {}
	for key, value in source :: any do
		copy[key] = Util.deepCopy(value)
	end
	return copy :: any
end

--[[
	Fuellt fehlende Schluessel aus einem Template nach. Genau das braucht ein
	Profil, wenn eine neue Spielversion Felder ergaenzt, die alte Speicher-
	staende nicht kennen. Vorhandene Werte werden nie ueberschrieben.
]]
function Util.reconcile(data: { [string]: any }, template: { [string]: any }): { [string]: any }
	for key, templateValue in template do
		if data[key] == nil then
			data[key] = Util.deepCopy(templateValue)
		elseif type(templateValue) == "table" and type(data[key]) == "table" then
			Util.reconcile(data[key], templateValue)
		end
	end
	return data
end

return Util

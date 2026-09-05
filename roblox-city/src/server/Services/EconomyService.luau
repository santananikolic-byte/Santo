--!strict
--[[
	EconomyService
	Der einzige Ort im Projekt, an dem sich ein Geldbetrag aendert.

	Regeln, die hier nicht verhandelbar sind:

	1. Kein anderer Service fasst data.cash oder data.bank direkt an. Wer
	   das doch tut, umgeht Pruefung, Deckelung und Protokoll.
	2. Zwischen dem Lesen eines Kontostands und dem Schreiben des neuen
	   Werts wird nie geyieldet. Ein task.wait an dieser Stelle ist die
	   Standard-Dupe-Luecke: zwei Anfragen lesen denselben Stand und
	   schreiben beide ihre Erhoehung.
	3. Jede Auszahlung aus einem wiederholbaren Ablauf (Job, Belohnung)
	   traegt einen Idempotenzschluessel. Ein doppeltes Abschlusssignal
	   zahlt dann einmal aus statt zweimal.
]]

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Config = require(ReplicatedStorage.Shared.Config)
local Net = require(ReplicatedStorage.Shared.Net)
local Signal = require(ReplicatedStorage.Shared.Signal)
local Util = require(ReplicatedStorage.Shared.Util)

local DataService = require(script.Parent.Parent.Data.DataService)

export type Wallet = { cash: number, bank: number }

export type TransactionResult = {
	ok: boolean,
	reason: string?,
	cash: number,
	bank: number,
}

local MAX_LOG_ENTRIES = 40

local EconomyService = {}

-- (player, wallet, delta, reason)
EconomyService.WalletChanged = Signal.new()

-- Protokoll der letzten Transaktionen pro Spieler. Rein fuer Diagnose:
-- wenn ein Spieler mit unmoeglichem Kontostand auffaellt, steht hier, ueber
-- welchen Pfad das Geld kam.
local ledger: { [number]: { { delta: number, reason: string, at: number } } } = {}

-- Bereits eingeloeste Idempotenzschluessel der laufenden Sitzung.
local consumedKeys: { [number]: { [string]: true } } = {}

-- ============================================================
-- Intern
-- ============================================================

local function record(userId: number, delta: number, reason: string)
	local entries = ledger[userId]
	if not entries then
		entries = {}
		ledger[userId] = entries
	end

	table.insert(entries, { delta = delta, reason = reason, at = os.time() })
	if #entries > MAX_LOG_ENTRIES then
		table.remove(entries, 1)
	end
end

local function push(player: Player, wallet: Wallet, delta: number, reason: string)
	Net.event("WalletChanged"):FireClient(player, wallet.cash, wallet.bank, delta, reason)
	EconomyService.WalletChanged:Fire(player, wallet, delta, reason)
end

--[[
	Prueft einen Betrag, bevor er irgendetwas beruehrt.

	Betraege kommen aus Formeln (Job-Bonus mal Restzeit), und eine Formel
	mit einem nil-Faktor liefert nicht 0, sondern einen Fehler oder NaN.
	Beides darf nie in einem Kontostand landen.
]]
local function validateAmount(amount: any): (boolean, string?)
	if not Util.isFiniteNumber(amount) then
		return false, "Betrag ist keine endliche Zahl"
	end
	if amount <= 0 then
		return false, "Betrag muss positiv sein"
	end
	if amount > Config.Economy.MaxSingleTransaction then
		return false, "Betrag ueberschreitet das Transaktionslimit"
	end
	return true
end

-- ============================================================
-- Oeffentliche API
-- ============================================================

function EconomyService.getWallet(player: Player): Wallet?
	local data = DataService.get(player)
	if not data then
		return nil
	end
	return { cash = data.cash, bank = data.bank }
end

--[[
	Zahlt Geld aus.

	idempotencyKey ist optional, aber Pflicht fuer alles, was durch ein
	Netzwerk-Ereignis ausgeloest wird. Derselbe Schluessel zahlt innerhalb
	einer Sitzung nur einmal.
]]
function EconomyService.credit(player: Player, amount: number, reason: string, idempotencyKey: string?): TransactionResult
	local data = DataService.get(player)
	if not data then
		return { ok = false, reason = "Profil nicht geladen", cash = 0, bank = 0 }
	end

	local valid, why = validateAmount(amount)
	if not valid then
		warn(`[Economy] Gutschrift abgelehnt fuer {player.Name} ({reason}): {why}`)
		return { ok = false, reason = why, cash = data.cash, bank = data.bank }
	end

	if idempotencyKey then
		local keys = consumedKeys[player.UserId]
		if not keys then
			keys = {}
			consumedKeys[player.UserId] = keys
		end
		if keys[idempotencyKey] then
			-- Kein Fehler: der Aufrufer hat schlicht doppelt gemeldet.
			return { ok = true, reason = "bereits gutgeschrieben", cash = data.cash, bank = data.bank }
		end
		keys[idempotencyKey] = true
	end

	local granted = Util.clampInt(amount, 1, Config.Economy.MaxSingleTransaction)

	-- Ab hier kein Yield bis zum Schreiben.
	local before = data.cash
	data.cash = Util.clampInt(before + granted, 0, Config.Economy.MaxCash)
	local actualDelta = data.cash - before
	data.stats.totalEarned += actualDelta

	record(player.UserId, actualDelta, reason)

	local wallet: Wallet = { cash = data.cash, bank = data.bank }
	push(player, wallet, actualDelta, reason)

	return { ok = true, cash = wallet.cash, bank = wallet.bank }
end

--[[
	Bucht Geld ab. Schlaegt fehl, wenn die Deckung nicht reicht - es gibt
	keinen negativen Kontostand.
]]
function EconomyService.debit(player: Player, amount: number, reason: string): TransactionResult
	local data = DataService.get(player)
	if not data then
		return { ok = false, reason = "Profil nicht geladen", cash = 0, bank = 0 }
	end

	local valid, why = validateAmount(amount)
	if not valid then
		return { ok = false, reason = why, cash = data.cash, bank = data.bank }
	end

	local cost = Util.clampInt(amount, 1, Config.Economy.MaxSingleTransaction)
	if data.cash < cost then
		return { ok = false, reason = "Nicht genug Bargeld", cash = data.cash, bank = data.bank }
	end

	data.cash -= cost
	record(player.UserId, -cost, reason)

	local wallet: Wallet = { cash = data.cash, bank = data.bank }
	push(player, wallet, -cost, reason)

	return { ok = true, cash = wallet.cash, bank = wallet.bank }
end

--[[
	Zieht einen Anteil des Bargelds ab. Fuer Tod und Verhaftung.
	Bankguthaben bleibt unangetastet - das ist der Sinn der Bank.
]]
function EconomyService.forfeit(player: Player, fraction: number, reason: string): number
	local data = DataService.get(player)
	if not data or data.cash <= 0 then
		return 0
	end

	local lost = Util.clampInt(data.cash * math.clamp(fraction, 0, 1), 0, data.cash)
	if lost <= 0 then
		return 0
	end

	data.cash -= lost
	record(player.UserId, -lost, reason)

	push(player, { cash = data.cash, bank = data.bank }, -lost, reason)
	return lost
end

--[[ Schickt dem Client den aktuellen Stand, ohne etwas zu aendern. ]]
function EconomyService.sync(player: Player)
	local wallet = EconomyService.getWallet(player)
	if wallet then
		Net.event("WalletChanged"):FireClient(player, wallet.cash, wallet.bank, 0, "sync")
	end
end

function EconomyService.getLedger(player: Player)
	return ledger[player.UserId] or {}
end

-- ============================================================
-- Bank
-- ============================================================

local function deposit(player: Player, amount: any): (boolean, any)
	local data = DataService.get(player)
	if not data then
		return false, "Profil nicht geladen"
	end

	if not Util.isFiniteNumber(amount) then
		return false, "Ungueltiger Betrag"
	end

	local value = Util.clampInt(amount, 0, Config.Economy.MaxCash)
	if value <= 0 then
		return false, "Betrag muss positiv sein"
	end
	if data.cash < value then
		return false, "Nicht genug Bargeld"
	end

	data.cash -= value
	data.bank = Util.clampInt(data.bank + value, 0, Config.Economy.MaxCash)
	record(player.UserId, 0, "bank:deposit")

	push(player, { cash = data.cash, bank = data.bank }, 0, "bank:deposit")
	return true, { cash = data.cash, bank = data.bank }
end

local function withdraw(player: Player, amount: any): (boolean, any)
	local data = DataService.get(player)
	if not data then
		return false, "Profil nicht geladen"
	end

	if not Util.isFiniteNumber(amount) then
		return false, "Ungueltiger Betrag"
	end

	local value = Util.clampInt(amount, 0, Config.Economy.MaxCash)
	if value <= 0 then
		return false, "Betrag muss positiv sein"
	end
	if data.bank < value then
		return false, "Nicht genug Guthaben"
	end

	data.bank -= value
	data.cash = Util.clampInt(data.cash + value, 0, Config.Economy.MaxCash)
	record(player.UserId, 0, "bank:withdraw")

	push(player, { cash = data.cash, bank = data.bank }, 0, "bank:withdraw")
	return true, { cash = data.cash, bank = data.bank }
end

-- ============================================================
-- Start
-- ============================================================

function EconomyService.init()
	Net.bindFunction("RequestDeposit", deposit)
	Net.bindFunction("RequestWithdraw", withdraw)
end

function EconomyService.start()
	DataService.ProfileLoaded:Connect(function(player: Player)
		EconomyService.sync(player)
	end)

	Players.PlayerRemoving:Connect(function(player)
		ledger[player.UserId] = nil
		consumedKeys[player.UserId] = nil
	end)
end

return EconomyService

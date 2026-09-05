--!strict
--[[
	MenuController
	Garage, Autohaus und Auftragsliste.

	Eine Regel fuer alle Panels hier: der Client schickt nur Schluessel.
	Kein Preis, keine Auszahlung, keine Menge. Alles, was in diesem Menue
	steht, ist Anzeige - die Entscheidung faellt auf dem Server.
]]

local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Config = require(ReplicatedStorage.Shared.Config)
local Net = require(ReplicatedStorage.Shared.Net)
local Util = require(ReplicatedStorage.Shared.Util)
local UI = require(script.Parent.Parent.UI)
local HudController = require(script.Parent.HudController)

local MenuController = {}

local panel: Frame
local listFrame: ScrollingFrame
local titleLabel: TextLabel
local openTab: string? = nil

local ownedVehicles: { any } = {}
local catalogue: { any } = {}

-- ============================================================
-- Zeilen
-- ============================================================

local function clearList()
	for _, child in listFrame:GetChildren() do
		if child:IsA("GuiObject") then
			child:Destroy()
		end
	end
end

local function addRow(order: number, title: string, subtitle: string, actionText: string, onAction: () -> ()): Frame
	local row = UI.panel({
		Parent = listFrame,
		Size = UDim2.new(1, -8, 0, 58),
		LayoutOrder = order,
		BackgroundTransparency = 0.25,
	})

	UI.label({
		Parent = row,
		Position = UDim2.fromOffset(12, 8),
		Size = UDim2.new(1, -130, 0, 20),
		Font = UI.FontBold,
		TextSize = 16,
		Text = title,
	})

	UI.label({
		Parent = row,
		Position = UDim2.fromOffset(12, 30),
		Size = UDim2.new(1, -130, 0, 18),
		TextSize = 13,
		TextColor3 = UI.Theme.TextMuted,
		Text = subtitle,
	})

	local button = UI.button({
		Parent = row,
		AnchorPoint = Vector2.new(1, 0.5),
		Position = UDim2.new(1, -12, 0.5, 0),
		Size = UDim2.fromOffset(96, 34),
		Text = actionText,
		TextSize = 14,
		BackgroundColor3 = UI.Theme.Accent,
		BackgroundTransparency = 0.7,
	})

	button.Activated:Connect(onAction)
	return row
end

-- ============================================================
-- Inhalte
-- ============================================================

local function showGarage()
	openTab = "garage"
	titleLabel.Text = "Garage"
	clearList()

	if #ownedVehicles == 0 then
		UI.label({
			Parent = listFrame,
			Size = UDim2.new(1, -8, 0, 40),
			LayoutOrder = 1,
			TextColor3 = UI.Theme.TextMuted,
			Text = "  Noch kein Fahrzeug. Schau im Autohaus vorbei.",
		})
		return
	end

	for index, entry in ownedVehicles do
		local spec = Config.Vehicles.Catalog[entry.model]
		local name = if spec then spec.DisplayName else entry.model

		addRow(index, name, `Kennzeichen {entry.plate}`, "Rufen", function()
			local ok, success, reason = pcall(function()
				return Net.remoteFunction("RequestSpawnVehicle"):InvokeServer(entry.model)
			end)

			if not ok then
				HudController.toast("Verbindung zum Server gestoert.", "error")
			elseif not success then
				HudController.toast(if type(reason) == "string" then reason else "Fehlgeschlagen", "warning")
			else
				HudController.toast(`{name} steht bereit.`, "success")
				MenuController.close()
			end
		end)
	end
end

local function showDealership()
	openTab = "shop"
	titleLabel.Text = "Autohaus"
	clearList()

	local ownedKeys: { [string]: boolean } = {}
	for _, entry in ownedVehicles do
		ownedKeys[entry.model] = true
	end

	for index, entry in catalogue do
		local owned = ownedKeys[entry.model]

		addRow(
			index,
			entry.displayName,
			`{Util.formatMoney(entry.price)}  -  {entry.topSpeed} Studs/s  -  {entry.seats} Sitze`,
			if owned then "Im Besitz" else "Kaufen",
			function()
				if owned then
					return
				end

				local ok, success, payload = pcall(function()
					return Net.remoteFunction("RequestPurchase"):InvokeServer("vehicle", entry.model)
				end)

				if not ok then
					HudController.toast("Verbindung zum Server gestoert.", "error")
				elseif not success then
					HudController.toast(if type(payload) == "string" then payload else "Kauf fehlgeschlagen", "warning")
				end
				-- Bei Erfolg meldet sich der Server von selbst: Notify fuer
				-- die Bestaetigung, GarageSync fuer die neue Liste.
			end
		)
	end
end

local function showJobs()
	openTab = "jobs"
	titleLabel.Text = "Auftraege"
	clearList()

	local order = 0
	for key, spec in Config.Jobs.Definitions do
		order += 1
		local risk = if spec.WantedOnStart > 0 then `{spec.WantedOnStart} Sterne zum Start` else "kein Fahndungslevel"

		addRow(
			order,
			spec.DisplayName,
			`{Util.formatMoney(spec.BasePayout)} Grundlohn  -  {risk}`,
			"Annehmen",
			function()
				local ok, success, reason = pcall(function()
					return Net.remoteFunction("RequestStartJob"):InvokeServer(key)
				end)

				if not ok then
					HudController.toast("Verbindung zum Server gestoert.", "error")
				elseif not success then
					HudController.toast(if type(reason) == "string" then reason else "Fehlgeschlagen", "warning")
				else
					HudController.toast(`{spec.DisplayName} angenommen. Ziel ist markiert.`, "success")
					MenuController.close()
				end
			end
		)
	end
end

-- ============================================================
-- Rahmen
-- ============================================================

function MenuController.close()
	openTab = nil
	panel.Visible = false
end

local function toggle(tab: string, show: () -> ())
	if openTab == tab then
		MenuController.close()
		return
	end

	panel.Visible = true
	show()
end

function MenuController.start(screenGui: ScreenGui)
	panel = UI.panel({
		Name = "Menu",
		Parent = screenGui,
		AnchorPoint = Vector2.new(0.5, 0.5),
		Position = UDim2.fromScale(0.5, 0.45),
		Size = UDim2.fromOffset(440, 380),
		BackgroundTransparency = 0.05,
		Visible = false,
	})

	titleLabel = UI.label({
		Parent = panel,
		Position = UDim2.fromOffset(18, 14),
		Size = UDim2.new(1, -60, 0, 26),
		Font = UI.FontBold,
		TextSize = 21,
		Text = "Garage",
	})

	local closeButton = UI.button({
		Parent = panel,
		AnchorPoint = Vector2.new(1, 0),
		Position = UDim2.new(1, -14, 0, 14),
		Size = UDim2.fromOffset(30, 30),
		Text = "X",
		TextSize = 15,
	})
	closeButton.Activated:Connect(MenuController.close)

	listFrame = UI.create("ScrollingFrame", {
		Parent = panel,
		Position = UDim2.fromOffset(14, 54),
		Size = UDim2.new(1, -28, 1, -70),
		BackgroundTransparency = 1,
		BorderSizePixel = 0,
		ScrollBarThickness = 4,
		ScrollBarImageColor3 = UI.Theme.PanelBorder,
		CanvasSize = UDim2.new(),
		AutomaticCanvasSize = Enum.AutomaticSize.Y,
	}, {
		UI.create("UIListLayout", {
			Padding = UDim.new(0, 6),
			SortOrder = Enum.SortOrder.LayoutOrder,
		}),
	}) :: ScrollingFrame

	-- Leiste unten links. Auf dem Handy bewusst gross genug zum Treffen.
	local bar = UI.create("Frame", {
		Name = "MenuBar",
		Parent = screenGui,
		Position = UDim2.new(0, 16, 1, -60),
		Size = UDim2.fromOffset(340, 44),
		BackgroundTransparency = 1,
	}, {
		UI.create("UIListLayout", {
			FillDirection = Enum.FillDirection.Horizontal,
			Padding = UDim.new(0, 8),
			SortOrder = Enum.SortOrder.LayoutOrder,
		}),
	}) :: Frame

	local tabs = {
		{ text = "Garage", order = 1, show = showGarage, tab = "garage" },
		{ text = "Autohaus", order = 2, show = showDealership, tab = "shop" },
		{ text = "Auftraege", order = 3, show = showJobs, tab = "jobs" },
	}

	for _, definition in tabs do
		local button = UI.button({
			Parent = bar,
			Size = UDim2.fromOffset(104, 44),
			LayoutOrder = definition.order,
			Text = definition.text,
			TextSize = 15,
			BackgroundTransparency = 0.1,
		})
		button.Activated:Connect(function()
			toggle(definition.tab, definition.show)
		end)
	end

	Net.event("GarageSync").OnClientEvent:Connect(function(vehicles, availableCatalogue)
		ownedVehicles = vehicles or {}
		catalogue = availableCatalogue or {}

		-- Offene Liste sofort auffrischen, damit ein Kauf sichtbar wird,
		-- ohne dass der Spieler das Panel schliessen muss.
		if openTab == "garage" then
			showGarage()
		elseif openTab == "shop" then
			showDealership()
		end
	end)
end

return MenuController

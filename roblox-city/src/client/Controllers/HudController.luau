--!strict
--[[
	HudController
	Geld, Fahndungssterne, Auftragsanzeige und Meldungen.

	Alle Werte kommen ueber Remotes vom Server. Der Client rechnet nichts
	aus und speichert nichts, was er beim naechsten Ereignis nicht ersetzt
	bekommt - so kann eine veraenderte Anzeige nie zu einem veraenderten
	Kontostand fuehren.
]]

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local TweenService = game:GetService("TweenService")

local Net = require(ReplicatedStorage.Shared.Net)
local Util = require(ReplicatedStorage.Shared.Util)
local UI = require(script.Parent.Parent.UI)

local HudController = {}

local cashLabel: TextLabel
local bankLabel: TextLabel
local deltaLabel: TextLabel
local starContainer: Frame
local stars: { TextLabel } = {}
local jobPanel: Frame
local jobTitle: TextLabel
local jobDetail: TextLabel
local jobBar: Frame
local toastContainer: Frame

local displayedCash = 0

-- ============================================================
-- Aufbau
-- ============================================================

local function buildWallet(parent: ScreenGui)
	local panel = UI.panel({
		Name = "Wallet",
		Parent = parent,
		AnchorPoint = Vector2.new(1, 0),
		Position = UDim2.new(1, -16, 0, 16),
		Size = UDim2.fromOffset(210, 74),
		BackgroundTransparency = 0.08,
	})

	cashLabel = UI.label({
		Parent = panel,
		Position = UDim2.fromOffset(14, 8),
		Size = UDim2.new(1, -28, 0, 30),
		Font = UI.FontBold,
		TextSize = 26,
		TextColor3 = UI.Theme.Money,
		TextXAlignment = Enum.TextXAlignment.Right,
		Text = "$0",
	})

	bankLabel = UI.label({
		Parent = panel,
		Position = UDim2.fromOffset(14, 40),
		Size = UDim2.new(1, -28, 0, 20),
		TextSize = 14,
		TextColor3 = UI.Theme.TextMuted,
		TextXAlignment = Enum.TextXAlignment.Right,
		Text = "Bank $0",
	})

	deltaLabel = UI.label({
		Parent = parent,
		AnchorPoint = Vector2.new(1, 0),
		Position = UDim2.new(1, -16, 0, 92),
		Size = UDim2.fromOffset(210, 24),
		Font = UI.FontBold,
		TextSize = 18,
		TextXAlignment = Enum.TextXAlignment.Right,
		TextTransparency = 1,
		Text = "",
	})
end

local function buildStars(parent: ScreenGui)
	starContainer = UI.create("Frame", {
		Name = "Wanted",
		Parent = parent,
		AnchorPoint = Vector2.new(1, 0),
		Position = UDim2.new(1, -16, 0, 118),
		Size = UDim2.fromOffset(210, 30),
		BackgroundTransparency = 1,
	}, {
		UI.create("UIListLayout", {
			FillDirection = Enum.FillDirection.Horizontal,
			HorizontalAlignment = Enum.HorizontalAlignment.Right,
			Padding = UDim.new(0, 4),
			SortOrder = Enum.SortOrder.LayoutOrder,
		}),
	}) :: Frame

	for index = 1, 5 do
		local star = UI.label({
			Parent = starContainer,
			Size = UDim2.fromOffset(26, 30),
			LayoutOrder = index,
			Font = UI.FontBold,
			TextSize = 26,
			TextXAlignment = Enum.TextXAlignment.Center,
			TextColor3 = UI.Theme.Star,
			TextTransparency = 0.82,
			Text = "*",
		})
		stars[index] = star
	end
end

local function buildJobPanel(parent: ScreenGui)
	jobPanel = UI.panel({
		Name = "Job",
		Parent = parent,
		AnchorPoint = Vector2.new(0, 0),
		Position = UDim2.fromOffset(16, 16),
		Size = UDim2.fromOffset(260, 78),
		BackgroundTransparency = 0.08,
		Visible = false,
	})

	jobTitle = UI.label({
		Parent = jobPanel,
		Position = UDim2.fromOffset(14, 10),
		Size = UDim2.new(1, -28, 0, 20),
		Font = UI.FontBold,
		TextSize = 17,
		Text = "",
	})

	jobDetail = UI.label({
		Parent = jobPanel,
		Position = UDim2.fromOffset(14, 32),
		Size = UDim2.new(1, -28, 0, 18),
		TextSize = 14,
		TextColor3 = UI.Theme.TextMuted,
		Text = "",
	})

	local track = UI.create("Frame", {
		Parent = jobPanel,
		Position = UDim2.fromOffset(14, 56),
		Size = UDim2.new(1, -28, 0, 8),
		BackgroundColor3 = UI.Theme.PanelBorder,
		BorderSizePixel = 0,
	}, { UI.corner(4) }) :: Frame

	jobBar = UI.create("Frame", {
		Parent = track,
		Size = UDim2.fromScale(0, 1),
		BackgroundColor3 = UI.Theme.Accent,
		BorderSizePixel = 0,
	}, { UI.corner(4) }) :: Frame
end

local function buildToasts(parent: ScreenGui)
	toastContainer = UI.create("Frame", {
		Name = "Toasts",
		Parent = parent,
		AnchorPoint = Vector2.new(0.5, 1),
		Position = UDim2.new(0.5, 0, 1, -140),
		Size = UDim2.fromOffset(380, 200),
		BackgroundTransparency = 1,
	}, {
		UI.create("UIListLayout", {
			FillDirection = Enum.FillDirection.Vertical,
			VerticalAlignment = Enum.VerticalAlignment.Bottom,
			HorizontalAlignment = Enum.HorizontalAlignment.Center,
			Padding = UDim.new(0, 6),
			SortOrder = Enum.SortOrder.LayoutOrder,
		}),
	}) :: Frame
end

-- ============================================================
-- Anzeige
-- ============================================================

local toastOrder = 0

function HudController.toast(message: string, kind: string?)
	toastOrder += 1

	local colour = UI.Theme.Text
	if kind == "success" then
		colour = UI.Theme.Money
	elseif kind == "error" or kind == "arrest" then
		colour = UI.Theme.Danger
	elseif kind == "warning" then
		colour = UI.Theme.Warning
	end

	local toast = UI.panel({
		Parent = toastContainer,
		Size = UDim2.new(1, 0, 0, 34),
		LayoutOrder = toastOrder,
		BackgroundTransparency = 0.1,
	}, {
		UI.label({
			Size = UDim2.fromScale(1, 1),
			Position = UDim2.fromOffset(12, 0),
			TextSize = 15,
			TextColor3 = colour,
			Text = message,
		}),
	})

	task.delay(4, function()
		if not toast.Parent then
			return
		end
		local fade = TweenService:Create(toast, TweenInfo.new(0.4), { BackgroundTransparency = 1 })
		fade:Play()
		fade.Completed:Wait()
		toast:Destroy()
	end)
end

local function showDelta(delta: number)
	if delta == 0 then
		return
	end

	local sign = if delta > 0 then "+" else "-"
	deltaLabel.Text = sign .. Util.formatMoney(math.abs(delta))
	deltaLabel.TextColor3 = if delta > 0 then UI.Theme.Money else UI.Theme.Danger
	deltaLabel.TextTransparency = 0

	TweenService:Create(deltaLabel, TweenInfo.new(1.6, Enum.EasingStyle.Quad), {
		TextTransparency = 1,
	}):Play()
end

local function setWallet(cash: number, bank: number, delta: number)
	bankLabel.Text = `Bank {Util.formatMoney(bank)}`
	showDelta(delta)

	-- Betrag hochzaehlen statt springen lassen. Kostet nichts und macht
	-- aus einer Auszahlung ein Ereignis statt einer Zahlenaenderung.
	local from = displayedCash
	displayedCash = cash

	if math.abs(cash - from) < 2 then
		cashLabel.Text = Util.formatMoney(cash)
		return
	end

	task.spawn(function()
		local startedAt = os.clock()
		local duration = 0.45

		while os.clock() - startedAt < duration do
			-- Abbrechen, wenn inzwischen ein neuerer Wert da ist.
			if displayedCash ~= cash then
				return
			end
			local alpha = (os.clock() - startedAt) / duration
			cashLabel.Text = Util.formatMoney(from + (cash - from) * alpha)
			task.wait()
		end

		if displayedCash == cash then
			cashLabel.Text = Util.formatMoney(cash)
		end
	end)
end

local function setStars(count: number)
	for index, star in stars do
		local lit = index <= count
		TweenService:Create(star, TweenInfo.new(0.2), {
			TextTransparency = if lit then 0 else 0.82,
		}):Play()
	end
end

function HudController.setJob(job: any)
	if not job then
		jobPanel.Visible = false
		return
	end

	jobPanel.Visible = true
	jobTitle.Text = job.displayName or "Auftrag"
	jobDetail.Text = job.description or ""
	jobBar.Size = UDim2.fromScale(0, 1)
end

function HudController.setJobProgress(progress: number, remaining: number)
	if not jobPanel.Visible then
		return
	end

	jobBar.Size = UDim2.fromScale(math.clamp(progress, 0, 1), 1)
	jobDetail.Text = `Noch {Util.formatClock(remaining)}`
end

-- ============================================================
-- Start
-- ============================================================

function HudController.start(screenGui: ScreenGui)
	buildWallet(screenGui)
	buildStars(screenGui)
	buildJobPanel(screenGui)
	buildToasts(screenGui)

	Net.event("WalletChanged").OnClientEvent:Connect(function(cash, bank, delta)
		setWallet(cash, bank, delta or 0)
	end)

	Net.event("WantedChanged").OnClientEvent:Connect(function(count)
		setStars(count)
	end)

	Net.event("Notify").OnClientEvent:Connect(function(message, kind)
		HudController.toast(message, kind)
	end)

	Net.event("JobStateChanged").OnClientEvent:Connect(function(job)
		HudController.setJob(job)
	end)

	Net.event("JobProgress").OnClientEvent:Connect(function(progress, remaining)
		HudController.setJobProgress(progress, remaining)
	end)
end

return HudController

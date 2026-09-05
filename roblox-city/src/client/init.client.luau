--!strict
--[[
	Clientstart.

	Eine ScreenGui fuer alles. Mehrere ScreenGuis wuerden die Zeichen-
	reihenfolge vom Zufall der Erstellungsreihenfolge abhaengig machen;
	mit einer einzigen entscheidet ZIndex, und das steht im Code.

	ResetOnSpawn = false ist Pflicht: sonst ist die gesamte Oberflaeche
	nach jedem Tod weg, und in diesem Spiel stirbt man oft.
]]

local Players = game:GetService("Players")

local DriveController = require(script.Controllers.DriveController)
local HudController = require(script.Controllers.HudController)
local InteractionController = require(script.Controllers.InteractionController)
local MenuController = require(script.Controllers.MenuController)

local player = Players.LocalPlayer
local playerGui = player:WaitForChild("PlayerGui")

local screenGui = Instance.new("ScreenGui")
screenGui.Name = "LibertyCity"
screenGui.ResetOnSpawn = false
screenGui.IgnoreGuiInset = true
screenGui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
screenGui.Parent = playerGui

local CONTROLLERS = {
	{ name = "Hud", module = HudController },
	{ name = "Drive", module = DriveController },
	{ name = "Interaction", module = InteractionController },
	{ name = "Menu", module = MenuController },
}

for _, entry in CONTROLLERS do
	-- Einzeln absichern: ein kaputtes Panel soll nicht die Geldanzeige
	-- und die Fahrsteuerung mitreissen.
	local ok, err = pcall(entry.module.start, screenGui)
	if not ok then
		warn(`[Client] {entry.name} konnte nicht starten: {err}`)
	end
end

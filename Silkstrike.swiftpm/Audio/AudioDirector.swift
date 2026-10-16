import Foundation
import AVFoundation
import UIKit
import QuartzCore

// =====================================================================
//  SILKSTRIKE – AudioDirector
//  100 % prozedurales Audio, keine Dateien:
//   • Soundeffekte werden zur Laufzeit synthetisiert (Rauschen, Filter,
//     Pitch-Sweeps, FM, Hüllkurven), als AVAudioPCMBuffer gecacht und über
//     einen Pool von AVAudioPlayerNodes abgespielt.
//   • Musik: pro MusicMood ein nahtloser Loop (Drones, Pads, Bass, Taiko,
//     Chor, Arpeggien …), einmalig im Hintergrund gerendert und mit
//     Lautstärke-Rampen überblendet.
//   • Sprache: AVSpeechSynthesizer (de-DE) – Ansager + Dialogstimmen.
//  Alle öffentlichen Methoden nur vom Main-Thread aufrufen.
// =====================================================================

final class AudioDirector {

    static let shared = AudioDirector()

    // MARK: - Konstanten & Hilfstypen

    private static let sfxVoiceCount = 14
    private static let musicVoiceCount = 3
    private static let maxPitchedFrames = 2_500_000      // ≈ 10 MB für tonhöhenverschobene Varianten
    private static let deferredPlayWindow: Double = 0.35

    private struct SfxKey: Hashable {
        let name: String
        let variant: Int
    }

    private struct PitchedKey: Hashable {
        let key: SfxKey
        let step: Int
    }

    private struct DeferredPlay {
        let key: SfxKey
        let volume: Float
        let pitch: Float
        let time: Double
    }

    // MARK: - Engine-Graph

    private let engine = AVAudioEngine()
    private let sfxMixer = AVAudioMixerNode()
    private let sfxEQ = AVAudioUnitEQ(numberOfBands: 2)
    private let musicMixer = AVAudioMixerNode()
    private let musicVarispeed = AVAudioUnitVarispeed()
    private let musicEQ = AVAudioUnitEQ(numberOfBands: 2)
    private var sfxPlayers: [AVAudioPlayerNode] = []
    private var sfxBusyUntil: [Double] = []
    private var sfxStartedAt: [Double] = []
    private var musicPlayers: [AVAudioPlayerNode] = []
    private var musicLevel: [Float] = []
    private var musicTarget: [Float] = []
    private var activeMusic = 0
    private var musicFadeRate: Float = 0.5
    private let monoFormat: AVAudioFormat?
    private let stereoFormat: AVAudioFormat?
    private var graphBuilt = false
    private var observersInstalled = false
    private var observerTokens: [NSObjectProtocol] = []
    private var tickTimer: Timer?
    private var lastTick: Double = 0
    private var lastStartAttempt: Double = -10
    private var needsMusicRefresh = false
    private var musicRetryClock: Float = 0

    // MARK: - Zustand

    private var settings = GameSettings()
    private var requestedMood: MusicMood = MusicMood.none
    private var playingMood: MusicMood = MusicMood.none

    // SFX-Caches
    private var sfxCache: [SfxKey: AVAudioPCMBuffer] = [:]
    private var pitchedCache: [PitchedKey: AVAudioPCMBuffer] = [:]
    private var pitchedFrames = 0
    private var sfxPending: Set<SfxKey> = []
    private var sfxQueueList: [SfxKey] = []
    private var sfxJobInFlight = false
    private var deferredPlays: [DeferredPlay] = []
    private var lastPlayTime: [SoundEffect: Double] = [:]
    private var lastVariant: [SoundEffect: Int] = [:]
    private var prewarmStarted = false

    // Musik-Cache
    private var musicCache: [MusicMood: AVAudioPCMBuffer] = [:]
    private var musicWanted: [MusicMood] = []
    private var musicJobInFlight = false
    private var musicJobMood: MusicMood = MusicMood.none
    private var musicPrewarmPending = false

    private let synthQueue = DispatchQueue(label: "silkstrike.audio.sfx", qos: .utility)
    private let musicQueue = DispatchQueue(label: "silkstrike.audio.music", qos: .userInitiated)

    // Zeitlupe / Ducking
    private var slowTarget: Float = 1
    private var slowCurrent: Float = 1
    private var appliedSlow: Float = -1
    private var sfxSlowPitch: Float = 1
    private var duck: Float = 1
    private var appliedSfxVolume: Float = -1
    private var appliedMusicVolume: Float = -1

    // Sprache
    private let announcer = AVSpeechSynthesizer()
    private let dialog = AVSpeechSynthesizer()
    private var voicesLoaded = false
    private var maleVoice: AVSpeechSynthesisVoice?
    private var femaleVoice: AVSpeechSynthesisVoice?
    private var anyGermanVoice: AVSpeechSynthesisVoice?

    private init() {
        monoFormat = AVAudioFormat(standardFormatWithSampleRate: 44100, channels: 1)
        stereoFormat = AVAudioFormat(standardFormatWithSampleRate: 44100, channels: 2)
    }

    // MARK: - Öffentliche API

    /// Audio-Session + Engine starten. Mehrfach aufrufbar (z. B. bei jeder Rückkehr in den Vordergrund).
    func start() {
        configureSession()
        buildGraphIfNeeded()
        installObserversIfNeeded()
        _ = startEngine(force: true)
        startTimerIfNeeded()
        Haptics.prepare()
        if !prewarmStarted {
            prewarmStarted = true
            beginPrewarm()
        }
        needsMusicRefresh = false
        refreshMusic()
    }

    func apply(_ newSettings: GameSettings) {
        settings = newSettings
        applyVolumes(force: true)
        if !newSettings.voicesEnabled { stopSpeech() }
        refreshMusic()
    }

    /// Spielt einen synthetisierten Soundeffekt. volume 0…1, pitch 0.25…4 (1 = Original).
    func play(_ sfx: SoundEffect, volume: Float = 1, pitch: Float = 1) {
        guard graphBuilt, settings.sfxVolume > 0.001, volume > 0.001 else { return }
        let now = CACurrentMediaTime()
        if let last = lastPlayTime[sfx], now - last < 0.025 { return }   // identische Doppel-Trigger im selben Frame
        lastPlayTime[sfx] = now

        let count = AudioSFXSynth.variantCount(sfx)
        var variant = 0
        if count > 1 {
            variant = Int.random(in: 0..<count)
            if let lastV = lastVariant[sfx], lastV == variant { variant = (variant + 1) % count }
            lastVariant[sfx] = variant
        }
        var p = pitch.isFinite ? pitch : 1
        if AudioSFXSynth.jitters(sfx) { p *= Float.random(in: 0.965...1.035) }
        let v = (volume.isFinite ? volume : 1) * AudioSFXSynth.mixLevel(sfx)
        playKey(SfxKey(name: sfx.rawValue, variant: variant), volume: v, pitch: p, now: now)
    }

    /// Prozedurale Musik je Stimmung (nahtloser Loop, Überblendung).
    func setMusic(_ mood: MusicMood) {
        requestedMood = mood
        refreshMusic()
    }

    /// Tiefer, dramatischer Ansager (deutsch) + dumpfer Kino-Schlag.
    func announce(_ text: String) {
        playKey(SfxKey(name: AudioSFXSynth.announceBoomName, variant: 0), volume: 0.7, pitch: 1, now: CACurrentMediaTime())
        guard settings.voicesEnabled else { return }
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        let utterance = AVSpeechUtterance(string: AudioDirector.speechText(trimmed))
        utterance.voice = germanVoice(male: true)
        utterance.pitchMultiplier = 0.6
        utterance.rate = AudioDirector.clampRate(AVSpeechUtteranceDefaultSpeechRate * 0.82)
        utterance.volume = 1
        utterance.preUtteranceDelay = 0.04
        _ = announcer.stopSpeaking(at: .immediate)
        announcer.speak(utterance)
    }

    /// Dialogzeile mit Stimmlage der Figur (nil = Erzähler).
    func speak(_ text: String, as cast: CastMember?) {
        guard settings.voicesEnabled else { return }
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        var pitch: Float = 0.82
        var rate: Float = 0.46
        var male = true
        if let c = cast {
            let (vp, vr) = Roster.voice(for: c)
            pitch = vp
            rate = vr
            male = AudioDirector.isMaleCast(c)
        }
        let utterance = AVSpeechUtterance(string: AudioDirector.speechText(trimmed))
        utterance.voice = germanVoice(male: male)
        utterance.pitchMultiplier = max(0.5, min(2.0, pitch.isFinite ? pitch : 1))
        utterance.rate = AudioDirector.clampRate(rate.isFinite ? rate : 0.48)
        utterance.volume = 1
        _ = dialog.stopSpeaking(at: .immediate)
        dialog.speak(utterance)
    }

    func stopSpeech() {
        _ = announcer.stopSpeaking(at: .immediate)
        _ = dialog.stopSpeaking(at: .immediate)
    }

    var isSpeaking: Bool {
        return announcer.isSpeaking || dialog.isSpeaking
    }

    /// 1 = normal, < 1 = Zeitlupe: Musik wird langsamer/tiefer und dumpfer, Effekte tiefer und wuchtiger.
    func setSlowMotion(_ factor: Float) {
        let f = factor.isFinite ? factor : 1
        slowTarget = max(0.05, min(1, f))
    }

    // Zusätzliche Helfer (optional nutzbar)

    var currentMood: MusicMood { return requestedMood }

    /// Stoppt sofort alle laufenden Soundeffekte (z. B. beim Szenenwechsel).
    func stopAllEffects() {
        for p in sfxPlayers { p.stop() }
        for i in 0..<sfxBusyUntil.count { sfxBusyUntil[i] = 0 }
        deferredPlays.removeAll()
    }

    // MARK: - Session & Graph

    private func configureSession() {
        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(.playback, mode: .default, options: [.mixWithOthers])
        try? session.setPreferredIOBufferDuration(0.006)
        try? session.setActive(true)
    }

    private func buildGraphIfNeeded() {
        guard !graphBuilt, let mono = monoFormat, let stereo = stereoFormat else { return }
        graphBuilt = true

        engine.attach(sfxMixer)
        engine.attach(sfxEQ)
        engine.attach(musicMixer)
        engine.attach(musicVarispeed)
        engine.attach(musicEQ)

        for _ in 0..<AudioDirector.sfxVoiceCount {
            let p = AVAudioPlayerNode()
            engine.attach(p)
            engine.connect(p, to: sfxMixer, format: mono)
            sfxPlayers.append(p)
            sfxBusyUntil.append(0)
            sfxStartedAt.append(0)
        }
        for _ in 0..<AudioDirector.musicVoiceCount {
            let p = AVAudioPlayerNode()
            engine.attach(p)
            engine.connect(p, to: musicMixer, format: stereo)
            p.volume = 0
            musicPlayers.append(p)
            musicLevel.append(0)
            musicTarget.append(0)
        }

        let main = engine.mainMixerNode
        engine.connect(sfxMixer, to: sfxEQ, format: stereo)
        engine.connect(sfxEQ, to: main, format: stereo)
        engine.connect(musicMixer, to: musicVarispeed, format: stereo)
        engine.connect(musicVarispeed, to: musicEQ, format: stereo)
        engine.connect(musicEQ, to: main, format: stereo)
        main.outputVolume = 1

        let sb = sfxEQ.bands
        if sb.count >= 2 {
            sb[0].filterType = .lowShelf
            sb[0].frequency = 140
            sb[0].gain = 0
            sb[0].bypass = false
            sb[1].filterType = .lowPass
            sb[1].frequency = 18000
            sb[1].bypass = true
        }
        let mb = musicEQ.bands
        if mb.count >= 2 {
            mb[0].filterType = .lowPass
            mb[0].frequency = 18000
            mb[0].bypass = true
            mb[1].filterType = .lowShelf
            mb[1].frequency = 120
            mb[1].gain = 0
            mb[1].bypass = false
        }
        musicVarispeed.rate = 1
        applyVolumes(force: true)
        engine.prepare()
    }

    /// Startet die Engine falls nötig. Bei einem echten (Neu-)Start werden alle Player zurückgesetzt.
    private func startEngine(force: Bool) -> Bool {
        guard graphBuilt else { return false }
        if engine.isRunning { return true }
        let now = CACurrentMediaTime()
        if !force && now - lastStartAttempt < 1.0 { return false }
        lastStartAttempt = now
        do {
            try engine.start()
        } catch {
            return false
        }
        guard engine.isRunning else { return false }
        for p in sfxPlayers { p.stop() }
        for i in 0..<sfxBusyUntil.count { sfxBusyUntil[i] = 0 }
        for p in musicPlayers {
            p.stop()
            p.volume = 0
        }
        for i in 0..<musicLevel.count {
            musicLevel[i] = 0
            musicTarget[i] = 0
        }
        playingMood = MusicMood.none
        needsMusicRefresh = true
        return true
    }

    private func installObserversIfNeeded() {
        guard !observersInstalled else { return }
        observersInstalled = true
        let nc = NotificationCenter.default
        let t1 = nc.addObserver(forName: .AVAudioEngineConfigurationChange, object: engine, queue: .main) { [weak self] _ in
            self?.handleEngineReset()
        }
        let t2 = nc.addObserver(forName: AVAudioSession.interruptionNotification,
                                object: AVAudioSession.sharedInstance(), queue: .main) { [weak self] note in
            self?.handleInterruption(note)
        }
        observerTokens = [t1, t2]
    }

    private func handleEngineReset() {
        lastStartAttempt = -10
        if startEngine(force: true) {
            needsMusicRefresh = false
            refreshMusic()
        }
    }

    private func handleInterruption(_ note: Notification) {
        guard let raw = note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
              let type = AVAudioSession.InterruptionType(rawValue: raw) else { return }
        if type == .ended {
            try? AVAudioSession.sharedInstance().setActive(true)
            handleEngineReset()
        }
    }

    private func startTimerIfNeeded() {
        guard tickTimer == nil else { return }
        lastTick = CACurrentMediaTime()
        let t = Timer(timeInterval: 1.0 / 30.0, repeats: true) { [weak self] _ in
            self?.tick()
        }
        RunLoop.main.add(t, forMode: .common)
        tickTimer = t
    }

    // MARK: - Lautstärken

    private func applyVolumes(force: Bool) {
        let sv = max(0, min(1, settings.sfxVolume)) * 0.9
        let mv = (settings.musicEnabled ? max(0, min(1, settings.musicVolume)) : 0) * duck
        if force || abs(sv - appliedSfxVolume) > 0.001 {
            sfxMixer.outputVolume = sv
            appliedSfxVolume = sv
        }
        if force || abs(mv - appliedMusicVolume) > 0.001 {
            musicMixer.outputVolume = mv
            appliedMusicVolume = mv
        }
    }

    // MARK: - Tick (Fades, Zeitlupe, Ducking) – 30 Hz auf dem Main-RunLoop

    private func tick() {
        let now = CACurrentMediaTime()
        var dt = Float(now - lastTick)
        lastTick = now
        if !(dt > 0) || dt > 0.25 { dt = 1.0 / 30.0 }

        if needsMusicRefresh {
            needsMusicRefresh = false
            refreshMusic()
        }

        // Musik-Überblendungen
        for i in 0..<musicPlayers.count {
            let target = musicTarget[i]
            var lvl = musicLevel[i]
            if lvl != target {
                let step = musicFadeRate * dt
                if lvl < target {
                    lvl = min(target, lvl + step)
                } else {
                    lvl = max(target, lvl - step * 1.25)
                }
                musicLevel[i] = lvl
                musicPlayers[i].volume = lvl * lvl * (3 - 2 * lvl)
                if lvl <= 0.0001 && target <= 0 {
                    musicPlayers[i].stop()
                }
            }
        }

        // Musik leiser, während gesprochen wird
        let duckTarget: Float = isSpeaking ? 0.55 : 1
        duck += (duckTarget - duck) * min(1, dt * 5)
        applyVolumes(force: false)

        // Zeitlupe weich nachführen (kein Zippern bei Hit-Stops)
        slowCurrent += (slowTarget - slowCurrent) * min(1, dt * 7)
        if abs(slowCurrent - appliedSlow) > 0.002 {
            applySlowMotionParams(slowCurrent)
        }

        // Verfallene Wartende entfernen
        if !deferredPlays.isEmpty {
            deferredPlays.removeAll { now - $0.time > AudioDirector.deferredPlayWindow }
        }

        // Gelegentlich prüfen, ob die gewünschte Musik läuft (z. B. nach fehlgeschlagenem Engine-Start)
        musicRetryClock += dt
        if musicRetryClock > 1.2 {
            musicRetryClock = 0
            let desired = desiredMood
            if desired != playingMood, musicCache[desired] != nil {
                refreshMusic()
            }
        }
    }

    private func applySlowMotionParams(_ s: Float) {
        appliedSlow = s
        let amount = max(0, min(1, (1 - s) / 0.9))     // 0 = normal, 1 = extreme Zeitlupe
        musicVarispeed.rate = 1 - 0.36 * amount
        sfxSlowPitch = 1 - 0.3 * amount
        let mb = musicEQ.bands
        if mb.count >= 2 {
            if amount < 0.01 {
                mb[0].bypass = true
                mb[1].gain = 0
            } else {
                mb[0].bypass = false
                mb[0].frequency = 450 + 17500 * pow(1 - amount, 2.2)
                mb[1].gain = 4 * amount
            }
        }
        let sb = sfxEQ.bands
        if sb.count >= 2 {
            sb[0].gain = 5 * amount
            if amount < 0.01 {
                sb[1].bypass = true
            } else {
                sb[1].bypass = false
                sb[1].frequency = 2800 + 16000 * pow(1 - amount, 1.5)
            }
        }
    }

    // MARK: - SFX-Wiedergabe

    private func playKey(_ key: SfxKey, volume: Float, pitch: Float, now: Double) {
        guard graphBuilt else { return }
        guard let base = baseBuffer(for: key) else {
            deferredPlays.append(DeferredPlay(key: key, volume: volume, pitch: pitch, time: now))
            if deferredPlays.count > 16 { deferredPlays.removeFirst() }
            return
        }
        guard startEngine(force: false) else { return }
        let effPitch = max(0.25, min(4, pitch * sfxSlowPitch))
        let buffer = pitchedBuffer(base: base, key: key, pitch: effPitch)
        guard let idx = pickVoice(now: now) else { return }
        let player = sfxPlayers[idx]
        let duration = Double(buffer.frameLength) / 44100.0
        sfxBusyUntil[idx] = now + duration + 0.02
        sfxStartedAt[idx] = now
        player.volume = max(0, min(1, volume))
        player.pan = Float.random(in: -0.12...0.12)
        player.scheduleBuffer(buffer, at: nil, options: [.interrupts], completionHandler: nil)
        if !player.isPlaying { player.play() }
    }

    private func pickVoice(now: Double) -> Int? {
        let count = sfxPlayers.count
        guard count > 0, sfxBusyUntil.count == count, sfxStartedAt.count == count else { return nil }
        for i in 0..<count where sfxBusyUntil[i] <= now {
            return i
        }
        // Alle belegt: ältesten Sound stehlen
        var oldest = 0
        for i in 1..<count where sfxStartedAt[i] < sfxStartedAt[oldest] {
            oldest = i
        }
        return oldest
    }

    private func baseBuffer(for key: SfxKey) -> AVAudioPCMBuffer? {
        if let b = sfxCache[key] { return b }
        if AudioSFXSynth.isLong(key.name) {
            enqueueSynth(key, front: true)
            return nil
        }
        // Kurze Sounds: sofort synchron erzeugen (dauert nur Millisekunden)
        let samples = AudioSFXSynth.render(name: key.name, variant: key.variant)
        guard let b = AudioDirector.makeBuffer(mono: samples, format: monoFormat) else { return nil }
        sfxCache[key] = b
        if sfxPending.contains(key), let i = sfxQueueList.firstIndex(of: key) {
            sfxQueueList.remove(at: i)
            sfxPending.remove(key)
        }
        return b
    }

    private func pitchedBuffer(base: AVAudioPCMBuffer, key: SfxKey, pitch: Float) -> AVAudioPCMBuffer {
        let step = Int((pitch * 50).rounded())
        if step == 50 || step <= 0 { return base }
        let pk = PitchedKey(key: key, step: step)
        if let b = pitchedCache[pk] { return b }
        guard let b = resample(base, ratio: Float(step) / 50) else { return base }
        if pitchedFrames + Int(b.frameLength) > AudioDirector.maxPitchedFrames {
            pitchedCache.removeAll()
            pitchedFrames = 0
        }
        pitchedCache[pk] = b
        pitchedFrames += Int(b.frameLength)
        return b
    }

    /// Lineare Neuabtastung: ratio > 1 = höher/kürzer, < 1 = tiefer/länger.
    private func resample(_ src: AVAudioPCMBuffer, ratio: Float) -> AVAudioPCMBuffer? {
        guard ratio > 0.05, let fmt = monoFormat, let sp = src.floatChannelData else { return nil }
        let n = Int(src.frameLength)
        guard n > 1 else { return nil }
        let outN = max(1, Int(Double(n - 1) / Double(ratio)))
        guard let out = AVAudioPCMBuffer(pcmFormat: fmt, frameCapacity: AVAudioFrameCount(outN)),
              let dp = out.floatChannelData else { return nil }
        out.frameLength = AVAudioFrameCount(outN)
        let s = sp[0]
        let d = dp[0]
        let r = Double(ratio)
        for i in 0..<outN {
            let p = Double(i) * r
            let i0 = min(Int(p), n - 1)
            let i1 = min(i0 + 1, n - 1)
            let f = Float(p - Double(i0))
            let a = s[i0]
            d[i] = a + (s[i1] - a) * f
        }
        return out
    }

    // MARK: - Hintergrund-Synthese (SFX)

    private func beginPrewarm() {
        // Häufige Kampf- und UI-Sounds zuerst
        let order: [SoundEffect] = [
            .punchLight, .punchHeavy, .kick, .block, .whoosh, .uiSelect, .uiConfirm, .uiBack,
            .webShoot, .webZip, .swingRelease, .land, .boneCrack, .gore, .slice, .bodyFall,
            .metalHit, .heartbeat, .thunder, .fire, .ice, .electric, .explosion, .teleport,
            .chain, .roar, .riftHum, .crowd
        ]
        var all = order
        for s in SoundEffect.allCases where !all.contains(s) { all.append(s) }
        for s in all {
            for v in 0..<AudioSFXSynth.variantCount(s) {
                enqueueSynth(SfxKey(name: s.rawValue, variant: v), front: false)
            }
        }
        enqueueSynth(SfxKey(name: AudioSFXSynth.announceBoomName, variant: 0), front: false)

        // Musik-Vorrat: nach dem ersten angeforderten Stück (oder spätestens nach 4 s)
        musicPrewarmPending = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 4.0) { [weak self] in
            self?.flushMusicPrewarm()
        }
    }

    private func enqueueSynth(_ key: SfxKey, front: Bool) {
        if sfxCache[key] != nil { return }
        if sfxPending.contains(key) {
            if front, let i = sfxQueueList.firstIndex(of: key) {
                sfxQueueList.remove(at: i)
                sfxQueueList.insert(key, at: 0)
            }
            return
        }
        sfxPending.insert(key)
        if front {
            sfxQueueList.insert(key, at: 0)
        } else {
            sfxQueueList.append(key)
        }
        pumpSynthQueue()
    }

    private func pumpSynthQueue() {
        guard !sfxJobInFlight else { return }
        while !sfxQueueList.isEmpty {
            let next = sfxQueueList.removeFirst()
            if sfxCache[next] != nil {
                sfxPending.remove(next)
                continue
            }
            sfxJobInFlight = true
            let fmt = monoFormat
            synthQueue.async { [weak self] in
                let samples = AudioSFXSynth.render(name: next.name, variant: next.variant)
                let buffer = AudioDirector.makeBuffer(mono: samples, format: fmt)
                DispatchQueue.main.async {
                    self?.finishSynthJob(next, buffer)
                }
            }
            return
        }
    }

    private func finishSynthJob(_ key: SfxKey, _ buffer: AVAudioPCMBuffer?) {
        sfxJobInFlight = false
        sfxPending.remove(key)
        if let b = buffer, sfxCache[key] == nil {
            sfxCache[key] = b
        }
        if !deferredPlays.isEmpty, sfxCache[key] != nil {
            let now = CACurrentMediaTime()
            let ready = deferredPlays.filter { $0.key == key }
            if !ready.isEmpty {
                deferredPlays.removeAll { $0.key == key }
                for d in ready where now - d.time < AudioDirector.deferredPlayWindow {
                    playKey(d.key, volume: d.volume, pitch: d.pitch, now: now)
                }
            }
        }
        pumpSynthQueue()
    }

    static func makeBuffer(mono samples: [Float], format: AVAudioFormat?) -> AVAudioPCMBuffer? {
        guard let fmt = format, !samples.isEmpty,
              let buf = AVAudioPCMBuffer(pcmFormat: fmt, frameCapacity: AVAudioFrameCount(samples.count)),
              let ch = buf.floatChannelData else { return nil }
        buf.frameLength = AVAudioFrameCount(samples.count)
        let dst = ch[0]
        for i in 0..<samples.count { dst[i] = samples[i] }
        return buf
    }

    static func makeBuffer(left: [Float], right: [Float], format: AVAudioFormat?) -> AVAudioPCMBuffer? {
        guard let fmt = format, fmt.channelCount >= 2 else { return nil }
        let n = min(left.count, right.count)
        guard n > 0,
              let buf = AVAudioPCMBuffer(pcmFormat: fmt, frameCapacity: AVAudioFrameCount(n)),
              let ch = buf.floatChannelData else { return nil }
        buf.frameLength = AVAudioFrameCount(n)
        let dl = ch[0]
        let dr = ch[1]
        for i in 0..<n {
            dl[i] = left[i]
            dr[i] = right[i]
        }
        return buf
    }

    // MARK: - Musik

    private var desiredMood: MusicMood {
        return settings.musicEnabled ? requestedMood : MusicMood.none
    }

    private func refreshMusic() {
        let desired = desiredMood
        if desired == playingMood {
            if desired != MusicMood.none, engine.isRunning,
               activeMusic < musicPlayers.count, !musicPlayers[activeMusic].isPlaying {
                // Player wurde extern gestoppt → neu ansetzen
                playingMood = MusicMood.none
                transitionMusic(to: desired)
            }
            return
        }
        transitionMusic(to: desired)
    }

    private func transitionMusic(to mood: MusicMood) {
        if mood == MusicMood.none {
            fadeOutAllMusic(seconds: 1.6)
            playingMood = MusicMood.none
            return
        }
        if let buffer = musicCache[mood] {
            crossfade(to: buffer, mood: mood)
        } else {
            // Noch nicht gerendert: altes Stück ausblenden, neues mit Priorität rendern
            if playingMood != MusicMood.none {
                fadeOutAllMusic(seconds: 1.4)
                playingMood = MusicMood.none
            }
            requestMusicRender(mood, urgent: true)
        }
    }

    private func fadeOutAllMusic(seconds: Float) {
        for i in 0..<musicTarget.count { musicTarget[i] = 0 }
        musicFadeRate = 1 / max(0.1, seconds)
    }

    private func crossfade(to buffer: AVAudioPCMBuffer, mood: MusicMood) {
        guard musicPlayers.count >= 2, musicLevel.count == musicPlayers.count else { return }
        guard startEngine(force: false) else { return }
        // Den leisesten freien Player nehmen (kein hartes Abschneiden laufender Ausblendungen)
        var next = -1
        var lowest: Float = 2
        for i in 0..<musicPlayers.count where i != activeMusic {
            if musicLevel[i] < lowest {
                lowest = musicLevel[i]
                next = i
            }
        }
        if next < 0 { next = (activeMusic + 1) % musicPlayers.count }
        let p = musicPlayers[next]
        p.stop()
        p.volume = 0
        musicLevel[next] = 0
        p.scheduleBuffer(buffer, at: nil, options: [.loops], completionHandler: nil)
        p.play()
        for i in 0..<musicTarget.count { musicTarget[i] = 0 }
        musicTarget[next] = 1
        activeMusic = next
        playingMood = mood
        musicFadeRate = 1 / AudioDirector.fadeSeconds(for: mood)
    }

    private static func fadeSeconds(for mood: MusicMood) -> Float {
        switch mood {
        case .none: return 1.5
        case .menu: return 2.4
        case .roam: return 2.0
        case .tension: return 2.0
        case .combat: return 1.0
        case .boss: return 1.0
        case .sad: return 2.6
        case .victory: return 0.6
        }
    }

    private func requestMusicRender(_ mood: MusicMood, urgent: Bool) {
        guard mood != MusicMood.none, musicCache[mood] == nil else { return }
        if musicJobInFlight && musicJobMood == mood { return }
        if let i = musicWanted.firstIndex(of: mood) { musicWanted.remove(at: i) }
        if urgent {
            musicWanted.insert(mood, at: 0)
        } else {
            musicWanted.append(mood)
        }
        if urgent { flushMusicPrewarm() }
        pumpMusicQueue()
    }

    private func flushMusicPrewarm() {
        guard musicPrewarmPending else { return }
        musicPrewarmPending = false
        let list: [MusicMood] = [.combat, .roam, .menu, .tension, .boss, .victory, .sad]
        for m in list where musicCache[m] == nil && !musicWanted.contains(m) {
            if musicJobInFlight && musicJobMood == m { continue }
            musicWanted.append(m)
        }
        pumpMusicQueue()
    }

    private func pumpMusicQueue() {
        guard !musicJobInFlight else { return }
        while !musicWanted.isEmpty {
            let mood = musicWanted.removeFirst()
            if musicCache[mood] != nil || mood == MusicMood.none { continue }
            musicJobInFlight = true
            musicJobMood = mood
            let fmt = stereoFormat
            musicQueue.async { [weak self] in
                let buffer = AudioMusicSynth.render(mood, format: fmt)
                DispatchQueue.main.async {
                    self?.finishMusicJob(mood, buffer)
                }
            }
            return
        }
    }

    private func finishMusicJob(_ mood: MusicMood, _ buffer: AVAudioPCMBuffer?) {
        musicJobInFlight = false
        musicJobMood = MusicMood.none
        if let b = buffer { musicCache[mood] = b }
        if desiredMood == mood && playingMood != mood {
            refreshMusic()
        }
        pumpMusicQueue()
    }

    // MARK: - Sprache

    private func germanVoice(male: Bool) -> AVSpeechSynthesisVoice? {
        if !voicesLoaded { loadVoices() }
        if male { return maleVoice ?? anyGermanVoice }
        return femaleVoice ?? anyGermanVoice
    }

    private func loadVoices() {
        voicesLoaded = true
        let all = AVSpeechSynthesisVoice.speechVoices().filter { $0.language.hasPrefix("de") }
        let deDE = all.filter { $0.language == "de-DE" }
        let pool = deDE.isEmpty ? all : deDE
        maleVoice = pool.filter { $0.gender == .male }.max(by: { $0.quality.rawValue < $1.quality.rawValue })
        femaleVoice = pool.filter { $0.gender == .female }.max(by: { $0.quality.rawValue < $1.quality.rawValue })
        anyGermanVoice = AVSpeechSynthesisVoice(language: "de-DE") ?? pool.first
    }

    private static func clampRate(_ r: Float) -> Float {
        return max(AVSpeechUtteranceMinimumSpeechRate, min(AVSpeechUtteranceMaximumSpeechRate, r))
    }

    /// Reine Großbuchstaben ("VOLLENDE ES!") würden teils buchstabiert → "Vollende Es!".
    private static func speechText(_ text: String) -> String {
        let hasLower = text.rangeOfCharacter(from: CharacterSet.lowercaseLetters) != nil
        return hasLower ? text : text.capitalized
    }

    private static func isMaleCast(_ cast: CastMember) -> Bool {
        switch cast {
        case .fighter(let id):
            switch id {
            case .saya, .inferna: return false
            case .silkstrike, .nachtseide, .vex, .brutus, .malrek: return true
            }
        case .heroDarkSuit, .morgrim: return true
        case .lena, .civilian: return false
        }
    }
}

// =====================================================================
//  AudioDSP – kleine DSP-Bausteine (thread-sicher, rein funktional)
// =====================================================================

enum AudioDSP {
    static let sr: Float = 44100
    static let twoPi: Float = 2 * Float.pi
    static let tableSize = 4096

    /// xorshift64* – deterministisches Rauschen pro Sound.
    struct Rand {
        private var state: UInt64
        init(seed: UInt64) {
            state = (seed &* 0x9E3779B97F4A7C15) | 1
        }
        mutating func next() -> UInt64 {
            state ^= state >> 12
            state ^= state << 25
            state ^= state >> 27
            return state &* 2685821657736338717
        }
        /// 0 ..< 1
        mutating func unit() -> Float {
            return Float(next() >> 40) / 16777216.0
        }
        /// -1 ... 1
        mutating func bi() -> Float {
            return unit() * 2 - 1
        }
        mutating func range(_ lo: Float, _ hi: Float) -> Float {
            return lo + (hi - lo) * unit()
        }
    }

    /// Zustandsvariablen-Filter (TPT / Simper) – stabil bei allen Frequenzen.
    struct SVF {
        var ic1: Float = 0
        var ic2: Float = 0
        var k: Float = 1.414
        var a1: Float = 0
        var a2: Float = 0
        var a3: Float = 0

        mutating func set(cutoff: Float, q: Float) {
            let fc = min(max(cutoff, 10), AudioDSP.sr * 0.45)
            let g = tan(Float.pi * fc / AudioDSP.sr)
            k = 1 / max(q, 0.05)
            a1 = 1 / (1 + g * (g + k))
            a2 = g * a1
            a3 = g * a2
        }

        /// (Tiefpass, Bandpass, Hochpass). Normierter Bandpass = band * k.
        mutating func tick(_ v0: Float) -> (Float, Float, Float) {
            let v3 = v0 - ic2
            let v1 = a1 * ic1 + a2 * v3
            let v2 = ic2 + a2 * ic1 + a3 * v3
            ic1 = 2 * v1 - ic1
            ic2 = 2 * v2 - ic2
            return (v2, v1, v0 - k * v1 - v2)
        }
    }

    /// Einpoliger Tief-/Hochpass.
    struct OnePole {
        var y: Float = 0
        var a: Float = 1
        init(cutoff: Float) {
            a = AudioDSP.lpCoef(cutoff)
        }
        mutating func lp(_ x: Float) -> Float {
            y += a * (x - y)
            return y
        }
        mutating func hp(_ x: Float) -> Float {
            y += a * (x - y)
            return x - y
        }
    }

    static func lpCoef(_ cutoff: Float) -> Float {
        let fc = min(max(cutoff, 1), sr * 0.49)
        return 1 - exp(-twoPi * fc / sr)
    }

    static func hz(_ midi: Float) -> Float {
        return 440 * pow(2, (midi - 69) / 12)
    }

    static let sineTable: [Float] = AudioDSP.makeTable(harmonics: 1, oddOnly: false)
    static let sawTable: [Float] = AudioDSP.makeTable(harmonics: 16, oddOnly: false)

    /// Bandbegrenzte Wellenform (Sägezahn bzw. Sinus), Größe tableSize + 1 (Schutzpunkt für Interpolation).
    static func makeTable(harmonics: Int, oddOnly: Bool) -> [Float] {
        let n = tableSize
        var t = [Float](repeating: 0, count: n + 1)
        for i in 0..<n {
            let x = Double(i) / Double(n) * 2 * Double.pi
            var v: Double = 0
            for h in 1...max(1, harmonics) {
                if oddOnly && h % 2 == 0 { continue }
                v += sin(x * Double(h)) / Double(h)
            }
            t[i] = Float(v)
        }
        var m: Float = 0
        for i in 0..<n { m = max(m, abs(t[i])) }
        if m > 0 {
            for i in 0..<n { t[i] /= m }
        }
        t[n] = t[0]
        return t
    }

    /// Tabellen-Oszillator, phase in Perioden (beliebiger Wert, wird gewickelt).
    static func lookup(_ table: [Float], _ phase: Float) -> Float {
        let p = phase - floor(phase)
        let x = p * Float(tableSize)
        var i = Int(x)
        if i >= tableSize { i = tableSize - 1 }
        if i < 0 { i = 0 }
        let f = x - Float(i)
        let a = table[i]
        return a + (table[i + 1] - a) * f
    }

    /// FNV-1a – stabiler Seed aus einem Namen.
    static func hashName(_ s: String) -> UInt64 {
        var h: UInt64 = 14695981039346656037
        for b in s.utf8 {
            h ^= UInt64(b)
            h = h &* 1099511628211
        }
        return h
    }
}

// =====================================================================
//  AudioSFXSynth – synthetisiert jeden SoundEffect (mono, 44,1 kHz)
// =====================================================================

enum AudioSFXSynth {

    static let announceBoomName = "_announceBoom"

    static func variantCount(_ s: SoundEffect) -> Int {
        switch s {
        case .punchLight, .punchHeavy, .kick, .whoosh, .boneCrack, .gore: return 3
        case .block, .slice, .metalHit, .land, .thunder, .chain, .bodyFall, .webShoot: return 2
        case .webZip, .fire, .ice, .electric, .explosion, .teleport, .roar,
             .uiSelect, .uiConfirm, .uiBack, .heartbeat, .riftHum, .crowd, .swingRelease: return 1
        }
    }

    /// Leichte Zufallsverstimmung gegen den "Maschinengewehr-Effekt".
    static func jitters(_ s: SoundEffect) -> Bool {
        switch s {
        case .punchLight, .punchHeavy, .kick, .block, .whoosh, .webShoot, .land, .bodyFall,
             .boneCrack, .gore, .slice, .chain, .metalHit, .swingRelease, .webZip:
            return true
        case .fire, .ice, .electric, .explosion, .teleport, .roar, .uiSelect, .uiConfirm,
             .uiBack, .heartbeat, .thunder, .riftHum, .crowd:
            return false
        }
    }

    /// Relative Mischpegel (Peaks sind normiert).
    static func mixLevel(_ s: SoundEffect) -> Float {
        switch s {
        case .punchLight: return 0.78
        case .punchHeavy: return 1.0
        case .kick: return 0.88
        case .block: return 0.72
        case .whoosh: return 0.5
        case .webShoot: return 0.56
        case .webZip: return 0.5
        case .land: return 0.78
        case .bodyFall: return 0.85
        case .boneCrack: return 0.88
        case .gore: return 0.82
        case .slice: return 0.72
        case .fire: return 0.72
        case .ice: return 0.66
        case .electric: return 0.56
        case .explosion: return 1.0
        case .teleport: return 0.66
        case .chain: return 0.62
        case .roar: return 0.88
        case .uiSelect: return 0.45
        case .uiConfirm: return 0.62
        case .uiBack: return 0.5
        case .heartbeat: return 0.85
        case .thunder: return 0.95
        case .riftHum: return 0.62
        case .crowd: return 0.58
        case .metalHit: return 0.68
        case .swingRelease: return 0.46
        }
    }

    /// Lange Sounds werden nie synchron auf dem Main-Thread erzeugt.
    static func isLong(_ name: String) -> Bool {
        if name == announceBoomName { return true }
        guard let s = SoundEffect(rawValue: name) else { return false }
        switch s {
        case .thunder, .crowd, .riftHum, .explosion, .roar, .fire: return true
        default: return false
        }
    }

    static func render(name: String, variant: Int) -> [Float] {
        var rng = AudioDSP.Rand(seed: AudioDSP.hashName(name) &+ UInt64(max(0, variant)) &* 7919)
        if let s = SoundEffect(rawValue: name) {
            return renderEffect(s, variant: max(0, variant), rng: &rng)
        }
        if name == announceBoomName {
            return announceBoom(&rng)
        }
        return [Float](repeating: 0, count: 64)
    }

    private static func renderEffect(_ e: SoundEffect, variant v: Int, rng r: inout AudioDSP.Rand) -> [Float] {
        switch e {
        case .punchLight: return punchLight(v, &r)
        case .punchHeavy: return punchHeavy(v, &r)
        case .kick: return kick(v, &r)
        case .block: return block(v, &r)
        case .whoosh: return whoosh(v, &r)
        case .webShoot: return webShoot(v, &r)
        case .webZip: return webZip(&r)
        case .land: return land(v, &r)
        case .bodyFall: return bodyFall(v, &r)
        case .boneCrack: return boneCrack(v, &r)
        case .gore: return gore(v, &r)
        case .slice: return slice(v, &r)
        case .fire: return fire(&r)
        case .ice: return ice(&r)
        case .electric: return electric(&r)
        case .explosion: return explosion(&r)
        case .teleport: return teleport(&r)
        case .chain: return chain(&r)
        case .roar: return roar(&r)
        case .uiSelect: return uiSelect(&r)
        case .uiConfirm: return uiConfirm(&r)
        case .uiBack: return uiBack(&r)
        case .heartbeat: return heartbeat(&r)
        case .thunder: return thunder(v, &r)
        case .riftHum: return riftHum(&r)
        case .crowd: return crowd(&r)
        case .metalHit: return metalHit(v, &r)
        case .swingRelease: return swingRelease(&r)
        }
    }

    // MARK: Baukasten

    enum NoiseMode {
        case white
        case low(Float)
        case high(Float)
        case band(Float, Float)                     // Mitte, Güte
        case bandSweep(Float, Float, Float, Float)  // von, nach, Zeitkonstante, Güte
        case lowSweep(Float, Float, Float, Float)   // von, nach, Zeitkonstante, Güte
    }

    struct Buf {
        var s: [Float]
        let sr: Float = 44100

        init(seconds: Float) {
            s = [Float](repeating: 0, count: max(64, Int(seconds * 44100)))
        }

        private func span(_ t0: Float, _ length: Float) -> (Int, Int)? {
            let start = Int(max(0, t0) * sr)
            guard start < s.count else { return nil }
            let n = min(s.count - start, Int(max(0, length) * sr))
            guard n > 0 else { return nil }
            return (start, n)
        }

        /// Sinus mit exponentiellem Pitch-Sweep (Wumms / Bauch-Treffer).
        mutating func thump(at t0: Float, f0: Float, f1: Float, sweep: Float, decay: Float, amp: Float, attack: Float = 0.001) {
            guard let (start, n) = span(t0, attack + decay * 8) else { return }
            var ph: Float = 0
            let sw = max(sweep, 0.0001)
            let at = max(attack, 0.00001)
            for i in 0..<n {
                let t = Float(i) / sr
                let f = f1 + (f0 - f1) * exp(-t / sw)
                ph += f / sr
                if ph >= 1 { ph -= 1 }
                let e = t < at ? t / at : exp(-(t - at) / decay)
                s[start + i] += sin(ph * AudioDSP.twoPi) * e * amp
            }
        }

        /// Gefiltertes Rauschen mit Hüllkurve. Pegel ist grob auf gleiche Lautheit normiert.
        mutating func noise(_ r: inout AudioDSP.Rand, at t0: Float, attack: Float, decay: Float, amp: Float, mode: NoiseMode, length: Float = 0) {
            let len = length > 0 ? length : attack + decay * 8
            guard let (start, n) = span(t0, len) else { return }
            var svf = AudioDSP.SVF()
            var norm: Float = 1
            switch mode {
            case .white:
                norm = 1
            case .low(let fc):
                svf.set(cutoff: fc, q: 0.707)
                norm = min(10, sqrt(22050 / (1.6 * max(fc, 20))))
            case .high(let fc):
                svf.set(cutoff: fc, q: 0.707)
                norm = 1.1
            case .band(let fc, let q):
                svf.set(cutoff: fc, q: q)
                norm = min(12, sqrt(22050 * q / (1.6 * max(fc, 20))))
            case .bandSweep(let a, _, _, let q):
                svf.set(cutoff: a, q: q)
            case .lowSweep(let a, _, _, let q):
                svf.set(cutoff: a, q: q)
            }
            let at = max(attack, 0.00001)
            for i in 0..<n {
                let t = Float(i) / sr
                let x = r.bi()
                var y: Float = 0
                switch mode {
                case .white:
                    y = x
                case .low:
                    y = svf.tick(x).0
                case .high:
                    y = svf.tick(x).2
                case .band:
                    y = svf.tick(x).1 * svf.k
                case .bandSweep(let a, let b, let tau, let q):
                    if i % 8 == 0 {
                        let fc = b + (a - b) * exp(-t / max(tau, 0.0001))
                        svf.set(cutoff: fc, q: q)
                        norm = min(12, sqrt(22050 * q / (1.6 * max(fc, 20))))
                    }
                    y = svf.tick(x).1 * svf.k
                case .lowSweep(let a, let b, let tau, let q):
                    if i % 8 == 0 {
                        let fc = b + (a - b) * exp(-t / max(tau, 0.0001))
                        svf.set(cutoff: fc, q: q)
                        norm = min(10, sqrt(22050 / (1.6 * max(fc, 20))))
                    }
                    y = svf.tick(x).0
                }
                let e = t < at ? t / at : exp(-(t - at) / decay)
                s[start + i] += y * e * amp * norm * 0.6
            }
        }

        /// Summe gedämpfter (oft unharmonischer) Sinus-Teiltöne – Metall, Glocke, Eis.
        mutating func partials(at t0: Float, freqs: [Float], decays: [Float], amps: [Float], amp: Float, attack: Float = 0.0005, drop: Float = 0) {
            let m = min(freqs.count, min(decays.count, amps.count))
            guard m > 0 else { return }
            var maxDecay: Float = 0.01
            for k in 0..<m { maxDecay = max(maxDecay, decays[k]) }
            guard let (start, n) = span(t0, maxDecay * 7 + attack) else { return }
            let at = max(attack, 0.00001)
            for k in 0..<m {
                var ph = Float(k) * 0.37
                let dec = exp(-1 / (max(decays[k], 0.0005) * sr))
                var e: Float = 1
                let fk = min(freqs[k], sr * 0.45)
                for i in 0..<n {
                    let t = Float(i) / sr
                    let f = drop > 0 ? fk * (1 + drop * exp(-t / 0.03)) : fk
                    ph += f / sr
                    if ph >= 1 { ph -= 1 }
                    let a = t < at ? t / at : 1
                    s[start + i] += sin(ph * AudioDSP.twoPi) * e * a * amps[k] * amp
                    e *= dec
                }
            }
        }

        /// FM-Ton, optional mit exponentiellem Frequenz-Sweep (sweepTo > 0).
        mutating func fm(at t0: Float, carrier: Float, ratio: Float, index: Float, indexDecay: Float, decay: Float, amp: Float,
                         attack: Float = 0.001, sweepTo: Float = 0, sweepTau: Float = 0.05) {
            guard let (start, n) = span(t0, attack + decay * 8) else { return }
            var pc: Float = 0
            var pm: Float = 0
            let at = max(attack, 0.00001)
            for i in 0..<n {
                let t = Float(i) / sr
                let fc = sweepTo > 0 ? sweepTo + (carrier - sweepTo) * exp(-t / max(sweepTau, 0.0001)) : carrier
                pm += fc * ratio / sr
                pm -= floor(pm)
                pc += fc / sr
                pc -= floor(pc)
                let idx = index * exp(-t / max(indexDecay, 0.0001))
                let v = sin(pc * AudioDSP.twoPi + idx * sin(pm * AudioDSP.twoPi))
                let e = t < at ? t / at : exp(-(t - at) / decay)
                s[start + i] += v * e * amp
            }
        }

        /// Sehr kurzer, heller Knack.
        mutating func click(_ r: inout AudioDSP.Rand, at t0: Float, amp: Float, width: Float = 0.0012, bright: Float = 4000) {
            noise(&r, at: t0, attack: 0.00005, decay: width, amp: amp * 1.4, mode: .high(bright))
        }

        /// Zufällig verteilte Knackser (Feuer, Trümmer, Blitzeinschlag).
        mutating func crackle(_ r: inout AudioDSP.Rand, from t0: Float, to t1: Float, count: Int, amp: Float, decayTau: Float, bright: Float = 3000) {
            guard count > 0 else { return }
            for _ in 0..<count {
                let t = r.range(t0, t1)
                let fall = exp(-(t - t0) / max(decayTau, 0.001))
                let rnd = r.range(0.3, 1)
                let dec = r.range(0.0006, 0.003)
                let fc = r.range(bright * 0.6, bright * 1.6)
                noise(&r, at: t, attack: 0.00005, decay: dec, amp: amp * fall * rnd, mode: .band(fc, 1.2))
            }
        }

        /// DC entfernen, normieren, Sättigung, Ränder blenden, Stille am Ende kappen.
        mutating func finish(drive: Float, peak: Float) -> [Float] {
            var y: Float = 0
            var xPrev: Float = 0
            for i in 0..<s.count {
                let x = s[i]
                y = x - xPrev + 0.9985 * y
                xPrev = x
                s[i] = y
            }
            var m: Float = 0
            for v in s { m = max(m, abs(v)) }
            guard m > 1e-6 else { return s }
            let g = 1 / m
            if drive > 0.05 {
                let nrm = 1 / tanh(drive)
                for i in 0..<s.count { s[i] = tanh(s[i] * g * drive) * nrm }
            } else {
                for i in 0..<s.count { s[i] *= g }
            }
            var m2: Float = 0
            for v in s { m2 = max(m2, abs(v)) }
            let g2: Float = m2 > 1e-6 ? peak / m2 : 0
            var last = s.count - 1
            while last > 256 && abs(s[last]) * g2 < 0.0004 { last -= 1 }
            var out = Array(s[0...last])
            let count = out.count
            let fadeIn = min(count, 24)
            let fadeOut = min(count, 240)
            for i in 0..<count {
                var v = out[i] * g2
                if i < fadeIn { v *= Float(i) / Float(fadeIn) }
                let rem = count - 1 - i
                if rem < fadeOut { v *= Float(rem) / Float(fadeOut) }
                out[i] = v
            }
            return out
        }
    }

    // MARK: Kampf

    private static func punchLight(_ v: Int, _ r: inout AudioDSP.Rand) -> [Float] {
        let vf = Float(v)
        var b = Buf(seconds: 0.28)
        b.thump(at: 0, f0: 240 + 25 * vf, f1: 95, sweep: 0.022, decay: 0.05, amp: 0.85)
        b.thump(at: 0, f0: 420, f1: 190, sweep: 0.012, decay: 0.03, amp: 0.35)
        b.noise(&r, at: 0, attack: 0.0004, decay: 0.013, amp: 0.8, mode: .band(2300 + 400 * vf, 1.1))
        b.noise(&r, at: 0.001, attack: 0.001, decay: 0.03, amp: 0.55, mode: .low(1100))
        b.click(&r, at: 0, amp: 0.4)
        return b.finish(drive: 1.8, peak: 0.95)
    }

    private static func punchHeavy(_ v: Int, _ r: inout AudioDSP.Rand) -> [Float] {
        let vf = Float(v)
        var b = Buf(seconds: 0.55)
        // tiefer Wumms + Sub
        b.thump(at: 0, f0: 160 - 10 * vf, f1: 56, sweep: 0.04, decay: 0.12, amp: 1)
        b.thump(at: 0, f0: 75, f1: 38, sweep: 0.08, decay: 0.2, amp: 0.4, attack: 0.003)
        // Körper (trägt auch auf kleinen iPhone-/iPad-Lautsprechern)
        b.thump(at: 0, f0: 330, f1: 125, sweep: 0.018, decay: 0.05, amp: 0.6)
        // Knall
        b.click(&r, at: 0, amp: 0.9, width: 0.0015, bright: 3500)
        b.noise(&r, at: 0, attack: 0.0003, decay: 0.014, amp: 0.9, mode: .high(2800))
        b.noise(&r, at: 0.007, attack: 0.0005, decay: 0.025, amp: 0.75, mode: .band(1700 + 300 * vf, 1.3))
        // Fleisch
        b.noise(&r, at: 0, attack: 0.002, decay: 0.07, amp: 0.8, mode: .band(650, 0.9))
        b.noise(&r, at: 0.01, attack: 0.004, decay: 0.12, amp: 0.3, mode: .lowSweep(4200, 300, 0.035, 0.8))
        return b.finish(drive: 2.6, peak: 0.98)
    }

    private static func kick(_ v: Int, _ r: inout AudioDSP.Rand) -> [Float] {
        let vf = Float(v)
        var b = Buf(seconds: 0.42)
        b.thump(at: 0, f0: 175 + 10 * vf, f1: 62, sweep: 0.03, decay: 0.085, amp: 1)
        b.thump(at: 0, f0: 300, f1: 130, sweep: 0.015, decay: 0.04, amp: 0.5)
        b.noise(&r, at: 0, attack: 0.0005, decay: 0.03, amp: 0.75, mode: .band(1250, 1))
        b.noise(&r, at: 0.002, attack: 0.0003, decay: 0.008, amp: 0.5, mode: .band(3800, 1.8))
        b.click(&r, at: 0, amp: 0.5)
        return b.finish(drive: 2.0, peak: 0.95)
    }

    private static func block(_ v: Int, _ r: inout AudioDSP.Rand) -> [Float] {
        let vf = Float(v)
        var b = Buf(seconds: 0.32)
        b.thump(at: 0, f0: 280, f1: 120, sweep: 0.015, decay: 0.035, amp: 0.7)
        b.fm(at: 0, carrier: 540 + 60 * vf, ratio: 1.48, index: 3, indexDecay: 0.015, decay: 0.045, amp: 0.45)
        b.noise(&r, at: 0, attack: 0.0005, decay: 0.02, amp: 0.5, mode: .low(1900))
        b.noise(&r, at: 0, attack: 0.0002, decay: 0.004, amp: 0.4, mode: .high(5000))
        b.partials(at: 0.002, freqs: [1260, 2330], decays: [0.05, 0.035], amps: [0.15, 0.1], amp: 1)
        return b.finish(drive: 1.5, peak: 0.88)
    }

    private static func whoosh(_ v: Int, _ r: inout AudioDSP.Rand) -> [Float] {
        let vf = Float(v)
        let dur: Float = 0.28 + 0.05 * vf
        var b = Buf(seconds: dur + 0.02)
        var svf = AudioDSP.SVF()
        let n = min(b.s.count, Int(dur * b.sr))
        let peakPos: Float = 0.36 + 0.05 * vf
        let fLow: Float = 320 + 60 * vf
        let fHigh: Float = 1900 + 300 * vf
        var air = AudioDSP.OnePole(cutoff: 500)
        for i in 0..<n {
            let u = Float(i) / Float(n)
            let e: Float = u < peakPos ? pow(u / peakPos, 1.6) : pow(max(0, 1 - u) / (1 - peakPos), 2.2)
            if i % 8 == 0 { svf.set(cutoff: fLow + (fHigh - fLow) * e, q: 1.4) }
            let x = r.bi()
            let o = svf.tick(x)
            let low = air.lp(x)
            b.s[i] += (o.1 * svf.k * 2.2 + low * 1.5) * e
        }
        return b.finish(drive: 0.8, peak: 0.85)
    }

    private static func land(_ v: Int, _ r: inout AudioDSP.Rand) -> [Float] {
        var b = Buf(seconds: 0.5)
        b.thump(at: 0, f0: 115, f1: 46, sweep: 0.045, decay: 0.14, amp: 1)
        b.thump(at: 0, f0: 240, f1: 95, sweep: 0.02, decay: 0.05, amp: 0.8)
        b.noise(&r, at: 0, attack: 0.001, decay: 0.06, amp: 0.8, mode: .low(750))
        b.noise(&r, at: 0.002, attack: 0.002, decay: 0.1, amp: 0.3, mode: .bandSweep(3200, 800, 0.08, 0.8))
        b.crackle(&r, from: 0.005, to: 0.2, count: 14 + 4 * v, amp: 0.5, decayTau: 0.08, bright: 2600)
        return b.finish(drive: 2.2, peak: 0.95)
    }

    private static func bodyFall(_ v: Int, _ r: inout AudioDSP.Rand) -> [Float] {
        let vf = Float(v)
        var b = Buf(seconds: 0.9)
        let hits: [(Float, Float)] = [(0, 1), (0.085 + 0.02 * vf, 0.6), (0.2 + 0.03 * vf, 0.35)]
        for h in hits {
            b.thump(at: h.0, f0: 100, f1: 44, sweep: 0.04, decay: 0.1, amp: h.1)
            b.thump(at: h.0, f0: 220, f1: 95, sweep: 0.02, decay: 0.045, amp: 0.75 * h.1)
            b.noise(&r, at: h.0, attack: 0.001, decay: 0.05, amp: 0.7 * h.1, mode: .low(520))
            b.noise(&r, at: h.0, attack: 0.0005, decay: 0.02, amp: 0.4 * h.1, mode: .band(1400, 0.8))
        }
        b.noise(&r, at: 0.04, attack: 0.03, decay: 0.15, amp: 0.1, mode: .bandSweep(2600, 900, 0.2, 0.9))
        return b.finish(drive: 2.0, peak: 0.95)
    }

    private static func boneCrack(_ v: Int, _ r: inout AudioDSP.Rand) -> [Float] {
        let vf = Float(v)
        var b = Buf(seconds: 0.45)
        // trockener Bruch
        b.fm(at: 0, carrier: 1100 + 120 * vf, ratio: 2.7, index: 4, indexDecay: 0.004, decay: 0.012, amp: 0.6)
        b.thump(at: 0, f0: 190, f1: 80, sweep: 0.012, decay: 0.03, amp: 0.45)
        // Serie scharfer Klicks
        let extra = Int(r.unit() * 3)
        let clickCount = 6 + v + extra
        var t: Float = 0.001
        var a: Float = 1
        for _ in 0..<clickCount {
            b.click(&r, at: t, amp: a * 0.9, width: 0.0007, bright: 3500)
            let pf = r.range(1800, 4200)
            b.partials(at: t, freqs: [pf], decays: [0.004], amps: [0.4 * a], amp: 1)
            t += r.range(0.004, 0.024)
            a *= 0.8
        }
        // Knirschen (granulares, bandgefiltertes Rauschen)
        var svf = AudioDSP.SVF()
        svf.set(cutoff: 1700, q: 1.4)
        let n = min(b.s.count, Int(0.22 * b.sr))
        var gate: Float = 1
        for i in 0..<n {
            if i % 120 == 0 {
                let chance = r.unit()
                gate = chance < 0.55 ? r.range(0.4, 1) : 0
            }
            let tt = Float(i) / b.sr
            let x = r.bi()
            let o = svf.tick(x)
            b.s[i] += o.1 * svf.k * gate * exp(-tt / 0.07) * 2.2
        }
        return b.finish(drive: 2.4, peak: 0.95)
    }

    private static func gore(_ v: Int, _ r: inout AudioDSP.Rand) -> [Float] {
        var b = Buf(seconds: 0.75)
        // Aufprall-Klatscher
        b.noise(&r, at: 0, attack: 0.001, decay: 0.08, amp: 0.8, mode: .lowSweep(3600, 500, 0.03, 1.2))
        // nasses Schmatzen: resonanter Tiefpass mit wackelnder Grenzfrequenz
        var svf = AudioDSP.SVF()
        let n = min(b.s.count, Int(0.55 * b.sr))
        var lfoPh = r.unit()
        let lfoRate: Float = 11 + 6 * r.unit()
        for i in 0..<n {
            let t = Float(i) / b.sr
            let e = min(1, t / 0.012) * exp(-t / 0.2)
            lfoPh += lfoRate / b.sr
            if lfoPh >= 1 { lfoPh -= 1 }
            if i % 8 == 0 {
                let wob = 0.5 + 0.5 * sin(lfoPh * AudioDSP.twoPi)
                svf.set(cutoff: 380 + 1100 * wob * (0.4 + 0.6 * e), q: 5)
            }
            let x = r.bi()
            let o = svf.tick(x)
            b.s[i] += o.0 * e * 1.6
        }
        // Tropfen / Blasen
        let extra = Int(r.unit() * 3)
        let drops = 5 + v + extra
        for _ in 0..<drops {
            let t0 = r.range(0.06, 0.6)
            let f0 = r.range(280, 700)
            let amp = r.range(0.12, 0.3)
            b.fm(at: t0, carrier: f0, ratio: 1, index: 0, indexDecay: 1, decay: 0.012, amp: amp, attack: 0.001, sweepTo: f0 * 2.4, sweepTau: 0.012)
        }
        b.thump(at: 0, f0: 130, f1: 50, sweep: 0.02, decay: 0.06, amp: 0.5)
        return b.finish(drive: 1.8, peak: 0.95)
    }

    private static func slice(_ v: Int, _ r: inout AudioDSP.Rand) -> [Float] {
        let vf = Float(v)
        var b = Buf(seconds: 0.55)
        // Klingen-"Schiing": nach oben gleitendes Bandrauschen
        b.noise(&r, at: 0, attack: 0.004, decay: 0.07, amp: 0.7, mode: .bandSweep(2400, 8800, 0.05, 2.2))
        let k: Float = 1 + 0.035 * vf
        b.partials(at: 0.004, freqs: [2210 * k, 3380 * k, 4960 * k, 6720 * k], decays: [0.25, 0.18, 0.12, 0.08],
                   amps: [0.22, 0.18, 0.14, 0.09], amp: 1, attack: 0.003)
        // Schnitt ins Fleisch
        b.noise(&r, at: 0.022, attack: 0.002, decay: 0.04, amp: 0.4, mode: .band(900, 1))
        return b.finish(drive: 1.2, peak: 0.85)
    }

    // MARK: Elemente & Spezialangriffe

    private static func fire(_ r: inout AudioDSP.Rand) -> [Float] {
        var b = Buf(seconds: 1.15)
        var svf = AudioDSP.SVF()
        let n = min(b.s.count, Int(1.1 * b.sr))
        for i in 0..<n {
            let t = Float(i) / b.sr
            let e = (1 - exp(-t / 0.04)) * exp(-t / 0.38)
            if i % 8 == 0 { svf.set(cutoff: 300 + 3200 * e, q: 0.9) }
            let x = r.bi()
            b.s[i] += svf.tick(x).0 * e * 2.4
        }
        b.noise(&r, at: 0, attack: 0.03, decay: 0.4, amp: 0.5, mode: .low(170))
        b.crackle(&r, from: 0.02, to: 0.95, count: 34, amp: 0.45, decayTau: 0.5, bright: 3000)
        b.thump(at: 0, f0: 90, f1: 45, sweep: 0.05, decay: 0.15, amp: 0.4, attack: 0.01)
        return b.finish(drive: 1.6, peak: 0.9)
    }

    private static func ice(_ r: inout AudioDSP.Rand) -> [Float] {
        var b = Buf(seconds: 0.95)
        b.noise(&r, at: 0, attack: 0.0002, decay: 0.012, amp: 0.8, mode: .high(2600))
        b.noise(&r, at: 0.002, attack: 0.001, decay: 0.05, amp: 0.4, mode: .band(3300, 1.5))
        b.thump(at: 0, f0: 320, f1: 120, sweep: 0.01, decay: 0.035, amp: 0.3)
        // Splitter-Klingeln
        for _ in 0..<16 {
            let u1 = r.unit()
            let u2 = r.unit()
            let t0 = 0.5 * u1 * u2          // Häufung am Anfang
            let f = r.range(2400, 8200)
            let d1 = r.range(0.03, 0.14)
            let a1 = r.range(0.08, 0.22)
            b.partials(at: t0, freqs: [f, f * 1.53], decays: [d1, 0.03], amps: [a1, 0.06], amp: 1)
        }
        return b.finish(drive: 1.0, peak: 0.85)
    }

    private static func electric(_ r: inout AudioDSP.Rand) -> [Float] {
        var b = Buf(seconds: 0.75)
        let n = min(b.s.count, Int(0.7 * b.sr))
        var ph: Float = 0
        var f: Float = 95
        var gate: Float = 1
        var hp = AudioDSP.SVF()
        hp.set(cutoff: 1500, q: 0.7)
        for i in 0..<n {
            let t = Float(i) / b.sr
            if i % 220 == 0 {
                f = 80 + r.unit() * 60
                let g = r.unit()
                gate = g < 0.7 ? 1 : 0.15
            }
            ph += f / b.sr
            if ph >= 1 { ph -= 1 }
            let sq: Float = ph < 0.5 ? 1 : -1
            let ph2 = (ph * 2) - floor(ph * 2)
            let sq2: Float = ph2 < 0.5 ? 1 : -1
            let nz = r.bi()
            let zap = hp.tick(nz * sq2).2
            let e = min(1, t / 0.004) * exp(-t / 0.3)
            b.s[i] += (sq * 0.35 + zap * 0.8 + nz * 0.08) * gate * e
        }
        b.crackle(&r, from: 0, to: 0.5, count: 10, amp: 0.6, decayTau: 0.3, bright: 5000)
        return b.finish(drive: 2.6, peak: 0.8)
    }

    private static func explosion(_ r: inout AudioDSP.Rand) -> [Float] {
        var b = Buf(seconds: 2.5)
        b.noise(&r, at: 0, attack: 0.0002, decay: 0.015, amp: 0.9, mode: .white)
        b.thump(at: 0, f0: 90, f1: 26, sweep: 0.12, decay: 0.5, amp: 1, attack: 0.002)
        b.thump(at: 0, f0: 210, f1: 70, sweep: 0.05, decay: 0.15, amp: 0.5)
        b.noise(&r, at: 0, attack: 0.004, decay: 0.75, amp: 0.85, mode: .lowSweep(1600, 110, 0.45, 0.8), length: 2.45)
        b.noise(&r, at: 0.01, attack: 0.02, decay: 0.3, amp: 0.6, mode: .band(700, 0.7))
        b.crackle(&r, from: 0.05, to: 1.7, count: 46, amp: 0.55, decayTau: 0.6, bright: 2800)
        return b.finish(drive: 3.0, peak: 1.0)
    }

    private static func teleport(_ r: inout AudioDSP.Rand) -> [Float] {
        var b = Buf(seconds: 0.8)
        let suckEnd: Float = 0.48
        var svf = AudioDSP.SVF()
        let n = min(b.s.count, Int(suckEnd * b.sr))
        var ph: Float = 0
        // Einsaugen: absteigender Bandpass, anschwellend
        for i in 0..<n {
            let t = Float(i) / b.sr
            let u = t / suckEnd
            let e = pow(u, 2.2)
            if i % 8 == 0 { svf.set(cutoff: 4200 * pow(0.06, u) + 200, q: 3) }
            let x = r.bi()
            let o = svf.tick(x)
            let f = 1500 * pow(0.06, u) + 60
            ph += f / b.sr
            if ph >= 1 { ph -= 1 }
            let tail = min(1, (suckEnd - t) / 0.01)
            b.s[i] += (o.1 * svf.k * 1.4 + sin(ph * AudioDSP.twoPi) * 0.25) * e * max(0, tail)
        }
        // Plopp beim Auftauchen
        b.thump(at: suckEnd, f0: 250, f1: 55, sweep: 0.02, decay: 0.08, amp: 0.9)
        b.noise(&r, at: suckEnd, attack: 0.0005, decay: 0.03, amp: 0.5, mode: .band(900, 0.9))
        b.partials(at: suckEnd, freqs: [1870, 2810, 3940], decays: [0.15, 0.1, 0.07], amps: [0.1, 0.07, 0.05], amp: 1)
        return b.finish(drive: 1.6, peak: 0.9)
    }

    private static func chain(_ r: inout AudioDSP.Rand) -> [Float] {
        var b = Buf(seconds: 0.65)
        b.noise(&r, at: 0, attack: 0.01, decay: 0.06, amp: 0.3, mode: .bandSweep(1400, 5200, 0.05, 1.2))
        var t: Float = 0.015
        let extra = Int(r.unit() * 4)
        let count = 7 + extra
        var a: Float = 1
        for _ in 0..<count {
            let f = r.range(1800, 3300)
            b.partials(at: t, freqs: [f, f * 1.47, f * 2.09, f * 2.83], decays: [0.05, 0.035, 0.025, 0.018],
                       amps: [0.3, 0.22, 0.15, 0.1], amp: a)
            b.click(&r, at: t, amp: 0.35 * a, width: 0.0006, bright: 5000)
            t += r.range(0.022, 0.06)
            a *= r.range(0.78, 0.95)
        }
        return b.finish(drive: 1.3, peak: 0.85)
    }

    private static func roar(_ r: inout AudioDSP.Rand) -> [Float] {
        var b = Buf(seconds: 1.85)
        let dur: Float = 1.75
        let n = min(b.s.count, Int(dur * b.sr))
        var f1 = AudioDSP.SVF()
        f1.set(cutoff: 560, q: 4)
        var f2 = AudioDSP.SVF()
        f2.set(cutoff: 1150, q: 5)
        var f3 = AudioDSP.SVF()
        f3.set(cutoff: 2450, q: 6)
        var br = AudioDSP.SVF()
        br.set(cutoff: 900, q: 0.8)
        var ph: Float = 0
        var phs: Float = 0
        let saw = AudioDSP.sawTable
        var jitter: Float = 0
        for i in 0..<n {
            let t = Float(i) / b.sr
            let u = t / dur
            if i % 441 == 0 { jitter = r.bi() * 0.04 }
            let f0 = (88 - 22 * u) * (1 + 0.03 * sin(t * 5.5 * AudioDSP.twoPi) + jitter)
            ph += f0 / b.sr
            if ph >= 1 { ph -= 1 }
            phs += f0 * 0.5 / b.sr
            if phs >= 1 { phs -= 1 }
            let src = AudioDSP.lookup(saw, ph)
            let nz = r.bi()
            let a1 = f1.tick(src + nz * 0.3).1 * f1.k
            let a2 = f2.tick(src + nz * 0.3).1 * f2.k
            let a3 = f3.tick(src + nz * 0.2).1 * f3.k
            let breath = br.tick(nz).1 * br.k
            let sub = sin(phs * AudioDSP.twoPi)
            let release: Float = u > 0.65 ? max(0, 1 - (u - 0.65) / 0.35) : 1
            let env = min(1, t / 0.22) * release
            let v = (1.4 * a1 + 0.8 * a2 + 0.35 * a3 + 0.35 * breath + 0.15 * sub) * env
            b.s[i] += tanh(v * 2.2)
        }
        return b.finish(drive: 1.5, peak: 0.92)
    }

    // MARK: UI

    private static func uiSelect(_ r: inout AudioDSP.Rand) -> [Float] {
        var b = Buf(seconds: 0.12)
        b.partials(at: 0, freqs: [1650, 3300], decays: [0.025, 0.012], amps: [0.6, 0.18], amp: 1, attack: 0.0008)
        b.thump(at: 0, f0: 500, f1: 380, sweep: 0.01, decay: 0.012, amp: 0.3)
        b.click(&r, at: 0, amp: 0.15)
        return b.finish(drive: 0.5, peak: 0.7)
    }

    private static func uiConfirm(_ r: inout AudioDSP.Rand) -> [Float] {
        var b = Buf(seconds: 0.85)
        b.thump(at: 0, f0: 170, f1: 62, sweep: 0.04, decay: 0.18, amp: 0.75)
        b.fm(at: 0, carrier: 660, ratio: 1.4, index: 2.4, indexDecay: 0.12, decay: 0.32, amp: 0.38, attack: 0.002)
        b.fm(at: 0.06, carrier: 990, ratio: 1.4, index: 2, indexDecay: 0.1, decay: 0.28, amp: 0.28, attack: 0.002)
        b.noise(&r, at: 0, attack: 0.001, decay: 0.12, amp: 0.06, mode: .high(7000))
        return b.finish(drive: 1.2, peak: 0.8)
    }

    private static func uiBack(_ r: inout AudioDSP.Rand) -> [Float] {
        var b = Buf(seconds: 0.4)
        b.fm(at: 0, carrier: 740, ratio: 1.4, index: 1.6, indexDecay: 0.06, decay: 0.09, amp: 0.4)
        b.fm(at: 0.07, carrier: 494, ratio: 1.4, index: 1.6, indexDecay: 0.06, decay: 0.12, amp: 0.4)
        b.thump(at: 0.07, f0: 140, f1: 70, sweep: 0.02, decay: 0.06, amp: 0.3)
        b.click(&r, at: 0, amp: 0.08)
        return b.finish(drive: 0.8, peak: 0.7)
    }

    // MARK: Atmosphäre

    private static func heartbeat(_ r: inout AudioDSP.Rand) -> [Float] {
        var b = Buf(seconds: 0.95)
        b.thump(at: 0, f0: 72, f1: 42, sweep: 0.03, decay: 0.075, amp: 1, attack: 0.004)
        b.thump(at: 0, f0: 150, f1: 85, sweep: 0.02, decay: 0.05, amp: 0.35, attack: 0.004)
        b.noise(&r, at: 0, attack: 0.004, decay: 0.05, amp: 0.35, mode: .low(170))
        b.thump(at: 0.27, f0: 66, f1: 40, sweep: 0.03, decay: 0.065, amp: 0.72, attack: 0.004)
        b.thump(at: 0.27, f0: 140, f1: 80, sweep: 0.02, decay: 0.045, amp: 0.25, attack: 0.004)
        b.noise(&r, at: 0.27, attack: 0.004, decay: 0.045, amp: 0.25, mode: .low(160))
        return b.finish(drive: 1.6, peak: 0.95)
    }

    private static func thunder(_ v: Int, _ r: inout AudioDSP.Rand) -> [Float] {
        let vf = Float(v)
        let total: Float = 5.2
        var b = Buf(seconds: total)
        // Einschlag-Knacken
        b.noise(&r, at: 0, attack: 0.0005, decay: 0.035, amp: 0.8, mode: .high(900))
        b.crackle(&r, from: 0, to: 0.4 + 0.2 * vf, count: 36, amp: 0.9, decayTau: 0.18, bright: 2200)
        // rollendes Grollen: braunes Rauschen, tiefpassgefiltert, langsam moduliert
        let n = b.s.count
        var brown: Float = 0
        var lp = AudioDSP.SVF()
        lp.set(cutoff: 240 + 60 * vf, q: 0.7)
        var mid = AudioDSP.SVF()
        mid.set(cutoff: 900, q: 0.7)
        var roll: Float = 0.6
        var rollTarget: Float = 0.6
        for i in 0..<n {
            let t = Float(i) / b.sr
            if i % 2205 == 0 { rollTarget = r.range(0.25, 1) }
            roll += (rollTarget - roll) * 0.0009
            let w = r.bi()
            brown = brown * 0.996 + w * 0.06
            let lo = lp.tick(brown).0
            let w2 = r.bi()
            let mi = mid.tick(w2).0
            let e = min(1, t / 0.07) * exp(-t / 1.5)
            let e2 = min(1, t / 0.02) * exp(-t / 0.5)
            b.s[i] += lo * 2.4 * roll * e + mi * 0.5 * e2
        }
        return b.finish(drive: 1.5, peak: 0.95)
    }

    private static func riftHum(_ r: inout AudioDSP.Rand) -> [Float] {
        let total: Float = 3.4
        var b = Buf(seconds: total)
        let n = b.s.count
        // verstimmte tiefe Drones + hörbare Obertöne (kleine Lautsprecher)
        let freqs: [Float] = [55, 55.7, 82.4, 110.9, 164.3, 220.5, 331.2, 441.7]
        let amps: [Float] = [0.45, 0.4, 0.25, 0.22, 0.12, 0.16, 0.1, 0.06]
        var phases = [Float](repeating: 0, count: freqs.count)
        var bp = AudioDSP.SVF()
        bp.set(cutoff: 420, q: 2)
        let saw = AudioDSP.sawTable
        var sawPh: Float = 0
        var lp = AudioDSP.OnePole(cutoff: 900)
        for i in 0..<n {
            let t = Float(i) / b.sr
            var v: Float = 0
            for k in 0..<freqs.count {
                phases[k] += freqs[k] / b.sr
                if phases[k] >= 1 { phases[k] -= 1 }
                v += sin(phases[k] * AudioDSP.twoPi) * amps[k]
            }
            sawPh += 110.3 / b.sr
            if sawPh >= 1 { sawPh -= 1 }
            v += lp.lp(AudioDSP.lookup(saw, sawPh)) * 0.3
            let x = r.bi()
            let breath = bp.tick(x).1 * bp.k * (0.5 + 0.5 * sin(t * 0.7 * AudioDSP.twoPi))
            v += breath * 0.8
            let wob = 1 - 0.18 * (0.5 + 0.5 * sin(t * 6 * AudioDSP.twoPi))
            let env = min(1, t / 0.45) * min(1, (total - t) / 0.7)
            b.s[i] += v * wob * max(0, env)
        }
        return b.finish(drive: 1.2, peak: 0.85)
    }

    private static func crowd(_ r: inout AudioDSP.Rand) -> [Float] {
        let total: Float = 3.6
        var b = Buf(seconds: total)
        let n = b.s.count
        // viele gefilterte Rausch-"Stimmen" mit Silben-Rhythmus
        for _ in 0..<12 {
            var f1 = AudioDSP.SVF()
            f1.set(cutoff: r.range(380, 1200), q: r.range(3, 6))
            var f2 = AudioDSP.SVF()
            f2.set(cutoff: r.range(1500, 2700), q: r.range(4, 8))
            var level: Float = 0
            var target: Float = 0
            let syll = max(100, Int(b.sr / r.range(3, 7)))
            let offset = Int(r.unit() * Float(syll))
            let gain = r.range(0.5, 1)
            for i in 0..<n {
                if (i + offset) % syll == 0 {
                    let c = r.unit()
                    target = c < 0.8 ? r.range(0.3, 1) : 0.05
                }
                level += (target - level) * 0.0025
                let x = r.bi()
                let o1 = f1.tick(x).1 * f1.k
                let o2 = f2.tick(x).1 * f2.k
                b.s[i] += (o1 + 0.5 * o2) * level * gain
            }
        }
        b.noise(&r, at: 0, attack: 0.5, decay: 2.0, amp: 0.3, mode: .low(300), length: total)
        for i in 0..<n {
            let t = Float(i) / b.sr
            let env = min(1, t / 0.6) * min(1, (total - t) / 1.0)
            b.s[i] *= max(0, env)
        }
        return b.finish(drive: 1.3, peak: 0.85)
    }

    private static func metalHit(_ v: Int, _ r: inout AudioDSP.Rand) -> [Float] {
        let vf = Float(v)
        var b = Buf(seconds: 1.1)
        let k: Float = 1 + 0.045 * vf
        b.partials(at: 0, freqs: [380 * k, 1020 * k, 1690 * k, 2410 * k, 3530 * k, 4870 * k],
                   decays: [0.6, 0.45, 0.3, 0.22, 0.15, 0.1],
                   amps: [0.55, 0.45, 0.35, 0.28, 0.2, 0.14], amp: 1, attack: 0.0005, drop: 0.012)
        b.noise(&r, at: 0, attack: 0.0002, decay: 0.006, amp: 0.7, mode: .high(3000))
        b.thump(at: 0, f0: 160, f1: 85, sweep: 0.015, decay: 0.04, amp: 0.4)
        return b.finish(drive: 1.2, peak: 0.85)
    }

    private static func swingRelease(_ r: inout AudioDSP.Rand) -> [Float] {
        var b = Buf(seconds: 0.45)
        let dur: Float = 0.38
        var svf = AudioDSP.SVF()
        let n = min(b.s.count, Int(dur * b.sr))
        for i in 0..<n {
            let u = Float(i) / Float(n)
            let e = sin(Float.pi * u) * (1 - u * 0.4)
            if i % 8 == 0 { svf.set(cutoff: 420 + 2000 * u, q: 1.5) }
            let x = r.bi()
            b.s[i] += svf.tick(x).1 * svf.k * e * 1.6
        }
        b.click(&r, at: 0, amp: 0.45, width: 0.001, bright: 5000)
        b.fm(at: 0, carrier: 1450, ratio: 1, index: 0, indexDecay: 1, decay: 0.035, amp: 0.2, attack: 0.001, sweepTo: 880, sweepTau: 0.02)
        return b.finish(drive: 1.0, peak: 0.8)
    }

    // MARK: Netz

    private static func webShoot(_ v: Int, _ r: inout AudioDSP.Rand) -> [Float] {
        let vf = Float(v)
        var b = Buf(seconds: 0.34)
        // hohes "Thwip": resonantes Bandrauschen fällt schnell ab
        b.noise(&r, at: 0, attack: 0.002, decay: 0.06, amp: 0.8, mode: .bandSweep(7500 - 600 * vf, 1700, 0.04, 4.5))
        b.fm(at: 0, carrier: 3300, ratio: 0.5, index: 0.8, indexDecay: 0.03, decay: 0.05, amp: 0.35, attack: 0.002, sweepTo: 620, sweepTau: 0.022)
        b.thump(at: 0, f0: 420, f1: 150, sweep: 0.01, decay: 0.014, amp: 0.4)
        b.noise(&r, at: 0.01, attack: 0.005, decay: 0.035, amp: 0.15, mode: .high(6500))
        return b.finish(drive: 1.3, peak: 0.9)
    }

    private static func webZip(_ r: inout AudioDSP.Rand) -> [Float] {
        let dur: Float = 0.55
        var b = Buf(seconds: 0.6)
        var svf = AudioDSP.SVF()
        var amPh: Float = 0
        var ph: Float = 0
        let n = min(b.s.count, Int(dur * b.sr))
        for i in 0..<n {
            let t = Float(i) / b.sr
            let u = t / dur
            let e = min(1, t / 0.015) * pow(max(0, 1 - u), 1.4)
            if i % 8 == 0 { svf.set(cutoff: 700 * pow(7, u), q: 3) }
            let amRate = 45 + 90 * u
            amPh += amRate / b.sr
            if amPh >= 1 { amPh -= 1 }
            let teeth: Float = amPh < 0.35 ? 1 : 0.45
            let x = r.bi()
            let o = svf.tick(x)
            let f = 260 * pow(4.5, u)
            ph += f / b.sr
            if ph >= 1 { ph -= 1 }
            b.s[i] += (o.1 * svf.k * 1.6 * teeth + sin(ph * AudioDSP.twoPi) * 0.22) * e
        }
        b.noise(&r, at: 0, attack: 0.001, decay: 0.02, amp: 0.4, mode: .bandSweep(6000, 2000, 0.02, 3))
        return b.finish(drive: 1.4, peak: 0.88)
    }

    // MARK: Ansager-Schlag

    private static func announceBoom(_ r: inout AudioDSP.Rand) -> [Float] {
        var b = Buf(seconds: 2.4)
        b.thump(at: 0, f0: 68, f1: 30, sweep: 0.15, decay: 0.7, amp: 1, attack: 0.004)
        b.thump(at: 0, f0: 190, f1: 75, sweep: 0.04, decay: 0.12, amp: 0.55, attack: 0.003)
        b.noise(&r, at: 0, attack: 0.004, decay: 0.25, amp: 0.35, mode: .band(500, 0.8))
        b.noise(&r, at: 0, attack: 0.004, decay: 0.8, amp: 0.45, mode: .low(260), length: 2.35)
        b.noise(&r, at: 0, attack: 0.0004, decay: 0.02, amp: 0.4, mode: .high(1800))
        b.partials(at: 0.01, freqs: [440, 659, 987, 1318], decays: [1.0, 0.8, 0.6, 0.5],
                   amps: [0.05, 0.04, 0.03, 0.02], amp: 1, attack: 0.02)
        return b.finish(drive: 1.8, peak: 0.95)
    }
}

// =====================================================================
//  AudioMusicSynth – prozedurale, nahtlos loopende Musik pro Stimmung
//  (Noten, die über das Loop-Ende hinausklingen, werden an den Anfang
//   gewickelt; Filter/Hall/Delay laufen zirkulär → kein Knacksen.)
// =====================================================================

enum AudioMusicSynth {

    static func render(_ mood: MusicMood, format: AVAudioFormat?) -> AVAudioPCMBuffer? {
        guard let fmt = format, fmt.channelCount >= 2 else { return nil }
        var c: Canvas
        var peak: Float = 0.75
        var drive: Float = 1.4
        switch mood {
        case .none:
            return nil
        case .menu:
            c = composeMenu()
            peak = 0.7
            drive = 1.2
        case .roam:
            c = composeRoam()
            peak = 0.72
            drive = 1.5
        case .tension:
            c = composeTension()
            peak = 0.7
            drive = 1.4
        case .combat:
            c = composeCombat()
            peak = 0.8
            drive = 1.8
        case .boss:
            c = composeBoss()
            peak = 0.82
            drive = 1.9
        case .sad:
            c = composeSad()
            peak = 0.66
            drive = 1.0
        case .victory:
            c = composeVictory()
            peak = 0.78
            drive = 1.5
        }
        c.master(peak: peak, drive: drive)
        return AudioDirector.makeBuffer(left: c.l, right: c.r, format: fmt)
    }

    /// Einpoliger Filter, zirkulär (zweiter Durchlauf schreibt, Zustand vom Loop-Ende).
    static func circularOnePole(_ x: inout [Float], cutoff: Float, highpass: Bool) {
        let n = x.count
        guard n > 0 else { return }
        let a = AudioDSP.lpCoef(cutoff)
        var y: Float = 0
        for i in 0..<n { y += a * (x[i] - y) }
        for i in 0..<n {
            let xi = x[i]
            y += a * (xi - y)
            x[i] = highpass ? xi - y : y
        }
    }

    // MARK: Hall-Bausteine (zirkulär: 1. Durchlauf wärmt den Zustand an, 2. Durchlauf schreibt)

    /// Gedämpfter Kammfilter über das ganze Signal; Ausgang wird auf `acc` addiert.
    static func combPass(_ input: [Float], _ acc: inout [Float], length: Int, fb: Float, damp: Float) {
        let n = input.count
        guard n > 0, acc.count >= n, length > 0 else { return }
        var buf = [Float](repeating: 0, count: length)
        var idx = 0
        var store: Float = 0
        input.withUnsafeBufferPointer { inp in
            acc.withUnsafeMutableBufferPointer { out in
                buf.withUnsafeMutableBufferPointer { b in
                    guard let ip = inp.baseAddress, let op = out.baseAddress, let bp = b.baseAddress else { return }
                    for pass in 0..<2 {
                        for i in 0..<n {
                            let y = bp[idx]
                            store = y * (1 - damp) + store * damp
                            bp[idx] = ip[i] + store * fb
                            if pass == 1 { op[i] += y }
                            idx += 1
                            if idx >= length { idx = 0 }
                        }
                    }
                }
            }
        }
    }

    /// Schroeder-Allpass (g = 0.5), in-place über das ganze Signal.
    static func allpassPass(_ x: inout [Float], length: Int) {
        let n = x.count
        guard n > 0, length > 0 else { return }
        var buf = [Float](repeating: 0, count: length)
        var idx = 0
        x.withUnsafeMutableBufferPointer { xb in
            buf.withUnsafeMutableBufferPointer { b in
                guard let xp = xb.baseAddress, let bp = b.baseAddress else { return }
                for pass in 0..<2 {
                    for i in 0..<n {
                        let input = xp[i]
                        let bv = bp[idx]
                        bp[idx] = input + bv * 0.5
                        if pass == 1 { xp[i] = bv - input }
                        idx += 1
                        if idx >= length { idx = 0 }
                    }
                }
            }
        }
    }

    // MARK: Leinwand + Instrumente

    struct Canvas {
        let sr: Float
        let frames: Int
        let beat: Float
        let seconds: Float
        var l: [Float]
        var r: [Float]
        var sendL: [Float]
        var sendR: [Float]
        var rng: AudioDSP.Rand

        init(bpm: Float, bars: Int, seed: UInt64) {
            sr = AudioDSP.sr
            beat = 60 / bpm
            let secs = beat * 4 * Float(max(1, bars))
            frames = max(44100, Int((secs * AudioDSP.sr).rounded()))
            seconds = Float(frames) / AudioDSP.sr
            l = [Float](repeating: 0, count: frames)
            r = [Float](repeating: 0, count: frames)
            sendL = [Float](repeating: 0, count: frames)
            sendR = [Float](repeating: 0, count: frames)
            rng = AudioDSP.Rand(seed: seed)
        }

        static func panGains(_ pan: Float) -> (Float, Float) {
            let a = (max(-1, min(1, pan)) + 1) * 0.25 * Float.pi
            return (cos(a), sin(a))
        }

        func startIndex(_ t: Float) -> Int {
            var i = Int((t * sr).rounded()) % frames
            if i < 0 { i += frames }
            return i
        }

        func noteLength(_ secs: Float) -> Int {
            return min(frames - 1, max(1, Int(secs * sr)))
        }

        /// Durchgehender, exakt periodischer Drone (ganzzahlige Zyklen pro Loop).
        mutating func drone(_ midi: Float, amp: Float, pan: Float = 0, beatHz: Float = 0.2, saw: Bool = false,
                            cutoff: Float = 400, lfoCycles: Int = 2, lfoDepth: Float = 0.3) {
            let secs = Double(frames) / Double(sr)
            let base = Double(AudioDSP.hz(midi))
            let c1 = max(1, (base * secs).rounded())
            let c2 = max(1, ((base + Double(beatHz)) * secs).rounded())
            let step1 = c1 / Double(frames)
            let step2 = c2 / Double(frames)
            let table = saw ? AudioDSP.sawTable : AudioDSP.sineTable
            let sine = AudioDSP.sineTable
            var lpL = AudioDSP.OnePole(cutoff: cutoff)
            var lpR = AudioDSP.OnePole(cutoff: cutoff)
            let (gl, gr) = Canvas.panGains(pan)
            let cyc = Float(max(1, lfoCycles))
            let off = rng.unit()
            let passes = saw ? 2 : 1
            for pass in 0..<passes {
                let write = pass == passes - 1
                for i in 0..<frames {
                    let a = Double(i) * step1
                    let b = Double(i) * step2
                    let s1 = AudioDSP.lookup(table, Float(a - a.rounded(.down)))
                    let s2 = AudioDSP.lookup(table, Float(b - b.rounded(.down)))
                    var vl = s1 * 0.6 + s2 * 0.4
                    var vr = s1 * 0.4 + s2 * 0.6
                    if saw {
                        vl = lpL.lp(vl)
                        vr = lpR.lp(vr)
                    }
                    if write {
                        let u = Float(i) / Float(frames)
                        let lfo = 1 - lfoDepth * (0.5 + 0.5 * AudioDSP.lookup(sine, u * cyc + off))
                        l[i] += vl * amp * lfo * gl * 1.41
                        r[i] += vr * amp * lfo * gr * 1.41
                    }
                }
            }
        }

        /// Wind-/Atmosphären-Rauschen über den ganzen Loop.
        mutating func wind(amp: Float, cutoff: Float, lfoCycles: Int = 3) {
            var nl = [Float](repeating: 0, count: frames)
            var nr = [Float](repeating: 0, count: frames)
            for i in 0..<frames {
                let a = rng.bi()
                let b = rng.bi()
                nl[i] = a
                nr[i] = b
            }
            AudioMusicSynth.circularOnePole(&nl, cutoff: cutoff, highpass: false)
            AudioMusicSynth.circularOnePole(&nl, cutoff: cutoff, highpass: false)
            AudioMusicSynth.circularOnePole(&nr, cutoff: cutoff, highpass: false)
            AudioMusicSynth.circularOnePole(&nr, cutoff: cutoff, highpass: false)
            let gain = amp * min(20, sqrt(22050 / (max(cutoff, 20) * 1.2)))
            let cyc = Float(max(1, lfoCycles))
            let off = rng.unit()
            let sine = AudioDSP.sineTable
            for i in 0..<frames {
                let u = Float(i) / Float(frames)
                let lfoL = 0.55 + 0.45 * AudioDSP.lookup(sine, u * cyc + off)
                let lfoR = 0.55 + 0.45 * AudioDSP.lookup(sine, u * cyc + off + 0.25)
                l[i] += nl[i] * gain * lfoL
                r[i] += nr[i] * gain * lfoR
            }
        }

        /// Breiter Synth-Pad / Streicher (3 verstimmte Sägezähne, Tiefpass), optional Tremolo.
        mutating func pad(_ midi: Float, at t0: Float, dur: Float, amp: Float, pan: Float = 0, bright: Float = 0.5,
                          attack: Float = 0.8, release: Float = 1.4, detune: Float = 0.1, tremolo: Float = 0) {
            let f = AudioDSP.hz(midi)
            let n = noteLength(dur + release)
            let saw = AudioDSP.sawTable
            let sine = AudioDSP.sineTable
            let dDown: Float = pow(2, -detune / 12)
            let dUp: Float = pow(2, detune / 12)
            let inc0 = f * dDown / sr
            let inc1 = f / sr
            let inc2 = f * dUp / sr
            var p0 = rng.unit()
            var p1 = rng.unit()
            var p2 = rng.unit()
            let cut = min(9000, f * (1.5 + 6 * bright))
            var lpL = AudioDSP.OnePole(cutoff: cut)
            var lpR = AudioDSP.OnePole(cutoff: cut)
            let (gl, gr) = Canvas.panGains(pan)
            let atkN = max(1, attack * sr)
            let durN = dur * sr
            let relN = max(1, release * sr)
            var trem: Float = 0
            let tremInc = tremolo / sr
            var idx = startIndex(t0)
            for i in 0..<n {
                let fi = Float(i)
                var env: Float = fi < atkN ? fi / atkN : 1
                if fi > durN { env *= max(0, 1 - (fi - durN) / relN) }
                env = env * env * (3 - 2 * env)
                if tremolo > 0 {
                    trem += tremInc
                    if trem >= 1 { trem -= 1 }
                    env *= 0.6 + 0.4 * AudioDSP.lookup(sine, trem)
                }
                p0 += inc0
                if p0 >= 1 { p0 -= 1 }
                p1 += inc1
                if p1 >= 1 { p1 -= 1 }
                p2 += inc2
                if p2 >= 1 { p2 -= 1 }
                let s0 = AudioDSP.lookup(saw, p0)
                let s1 = AudioDSP.lookup(saw, p1)
                let s2 = AudioDSP.lookup(saw, p2)
                let a = lpL.lp(s0 + 0.6 * s1)
                let b = lpR.lp(s2 + 0.6 * s1)
                let g = env * amp * 0.8
                l[idx] += a * g * gl
                r[idx] += b * g * gr
                idx += 1
                if idx >= frames { idx = 0 }
            }
        }

        /// Gezupfter, gesättigter Synth-Bass mit Filter-Hüllkurve (+ Sub-Oktave).
        mutating func bass(_ midi: Float, at t0: Float, dur: Float, amp: Float, cutoff: Float = 400,
                           envAmt: Float = 2000, envDecay: Float = 0.07, drive: Float = 1.6) {
            let f = AudioDSP.hz(midi)
            let rel: Float = 0.03
            let n = noteLength(dur + rel)
            let durN = dur * sr
            let relN = rel * sr
            let atkN: Float = 0.002 * sr
            var svf = AudioDSP.SVF()
            var fe: Float = 1
            let fdec = exp(-1 / (max(envDecay, 0.001) * sr))
            var p0: Float = 0
            var p1: Float = 0
            let saw = AudioDSP.sawTable
            let sine = AudioDSP.sineTable
            let dr = max(0.2, drive)
            let norm = 1 / tanh(dr)
            var idx = startIndex(t0)
            for i in 0..<n {
                let fi = Float(i)
                if i % 16 == 0 { svf.set(cutoff: cutoff + envAmt * fe, q: 1.1) }
                p0 += f / sr
                if p0 >= 1 { p0 -= 1 }
                p1 += f * 0.5 / sr
                if p1 >= 1 { p1 -= 1 }
                let y = svf.tick(AudioDSP.lookup(saw, p0)).0 + 0.55 * AudioDSP.lookup(sine, p1)
                var env: Float = fi < atkN ? fi / atkN : 1
                if fi > durN { env *= max(0, 1 - (fi - durN) / relN) }
                let v = tanh(y * dr) * norm * env * amp
                l[idx] += v * 0.707
                r[idx] += v * 0.707
                fe *= fdec
                idx += 1
                if idx >= frames { idx = 0 }
            }
        }

        /// FM-Pluck / Glocke (ratio 1.4 = glockig, 2–3 = gläsern).
        mutating func pluck(_ midi: Float, at t0: Float, amp: Float, pan: Float = 0, decay: Float = 0.5,
                            ratio: Float = 2, index: Float = 1.5, send: Float = 0) {
            let f = AudioDSP.hz(midi)
            let n = noteLength(decay * 4.6)
            let sine = AudioDSP.sineTable
            var pc: Float = 0
            var pm: Float = 0
            var e: Float = 1
            let dec = exp(-1 / (max(decay, 0.01) * sr))
            var ie: Float = 1
            let idec = exp(-1 / (max(0.01, decay * 0.3) * sr))
            let atkN: Float = 0.0025 * sr
            let incC = f / sr
            let incM = f * ratio / sr
            let idxScale = index / AudioDSP.twoPi
            let fadeN = max(1, Float(n) * 0.2)
            let (gl, gr) = Canvas.panGains(pan)
            var idx = startIndex(t0)
            for i in 0..<n {
                pm += incM
                pm -= floor(pm)
                pc += incC
                pc -= floor(pc)
                let mod = AudioDSP.lookup(sine, pm) * idxScale * ie
                let s = AudioDSP.lookup(sine, pc + mod)
                let fi = Float(i)
                let a: Float = fi < atkN ? fi / atkN : 1
                let tailFade = min(1, Float(n - i) / fadeN)
                let v = s * e * a * amp * tailFade
                l[idx] += v * gl
                r[idx] += v * gr
                if send > 0 {
                    sendL[idx] += v * gl * send
                    sendR[idx] += v * gr * send
                }
                e *= dec
                ie *= idec
                idx += 1
                if idx >= frames { idx = 0 }
            }
        }

        /// Klavierähnlicher Ton (leicht unharmonische Teiltöne + Hammergeräusch).
        mutating func piano(_ midi: Float, at t0: Float, amp: Float, pan: Float = 0, decay: Float = 1.6, send: Float = 0) {
            let f = AudioDSP.hz(midi)
            // 4 leicht gespreizte Teiltöne (Saiten-Inharmonizität), höhere klingen schneller ab
            let nyq = sr * 0.45
            let f1 = f
            let f2 = f * 2 * sqrt(1 + 0.0016)
            let f3 = f * 3 * sqrt(1 + 0.0036)
            let f4 = f * 4 * sqrt(1 + 0.0064)
            let inc1 = f1 < nyq ? f1 / sr : 0
            let inc2 = f2 < nyq ? f2 / sr : 0
            let inc3 = f3 < nyq ? f3 / sr : 0
            let inc4 = f4 < nyq ? f4 / sr : 0
            let d = max(0.05, decay)
            let dec1 = exp(-1 / (d * sr))
            let dec2 = exp(-1 / (d / 1.74 * sr))
            let dec3 = exp(-1 / (d / 2.41 * sr))
            let dec4 = exp(-1 / (d / 3.03 * sr))
            var p1: Float = 0
            var p2: Float = 0
            var p3: Float = 0
            var p4: Float = 0
            var e1: Float = 1
            var e2: Float = 0.5
            var e3: Float = 0.26
            var e4: Float = 0.15
            let n = noteLength(min(d * 2.8, 5))
            let fadeN = max(1, Float(n) * 0.3)
            var ne: Float = 1
            let ndec = exp(-1 / (0.006 * sr))
            var lp = AudioDSP.OnePole(cutoff: 2500)
            var atk: Float = 0
            let atkInc = 1 / (0.002 * sr)
            let sine = AudioDSP.sineTable
            let (gl, gr) = Canvas.panGains(pan)
            var idx = startIndex(t0)
            for i in 0..<n {
                p1 += inc1
                if p1 >= 1 { p1 -= 1 }
                p2 += inc2
                if p2 >= 1 { p2 -= 1 }
                p3 += inc3
                if p3 >= 1 { p3 -= 1 }
                p4 += inc4
                if p4 >= 1 { p4 -= 1 }
                var v = AudioDSP.lookup(sine, p1) * e1 + AudioDSP.lookup(sine, p2) * e2
                v += AudioDSP.lookup(sine, p3) * e3 + AudioDSP.lookup(sine, p4) * e4
                e1 *= dec1
                e2 *= dec2
                e3 *= dec3
                e4 *= dec4
                if ne > 1e-5 {          // Hammergeräusch (danach abschalten: keine Subnormal-Zahlen)
                    let x = rng.bi()
                    v += lp.lp(x) * ne * 0.6
                    ne *= ndec
                }
                atk = min(1, atk + atkInc)
                let tailFade = min(1, Float(n - i) / fadeN)
                let out = v * amp * atk * tailFade
                l[idx] += out * gl
                r[idx] += out * gr
                if send > 0 {
                    sendL[idx] += out * gl * send
                    sendR[idx] += out * gr * send
                }
                idx += 1
                if idx >= frames { idx = 0 }
            }
        }

        /// Taiko-Trommel: tiefer Pitch-Drop + Fell-Schlag.
        mutating func taiko(at t0: Float, amp: Float, pitch: Float = 1, pan: Float = 0) {
            let n = noteLength(1.1)
            let sine = AudioDSP.sineTable
            var ph: Float = 0
            var ph2: Float = 0
            var env: Float = 1
            let dec = exp(-1 / (0.38 * sr))
            var env2: Float = 1
            let dec2 = exp(-1 / (0.12 * sr))
            var nenv: Float = 1
            let ndec = exp(-1 / (0.03 * sr))
            var pe: Float = 1
            let pdec = exp(-1 / (0.035 * sr))
            var lp = AudioDSP.OnePole(cutoff: 900)
            let (gl, gr) = Canvas.panGains(pan)
            var idx = startIndex(t0)
            for _ in 0..<n {
                let f = (52 + 80 * pe) * pitch
                ph += f / sr
                if ph >= 1 { ph -= 1 }
                ph2 += f * 1.58 / sr
                if ph2 >= 1 { ph2 -= 1 }
                let body = AudioDSP.lookup(sine, ph) * env + AudioDSP.lookup(sine, ph2) * env2 * 0.35
                let x = rng.bi()
                let skin = lp.lp(x) * nenv * 2.2
                let v = tanh((body + skin) * amp * 1.4)
                l[idx] += v * gl
                r[idx] += v * gr
                env *= dec
                env2 *= dec2
                nenv *= ndec
                pe *= pdec
                idx += 1
                if idx >= frames { idx = 0 }
            }
        }

        mutating func kick(at t0: Float, amp: Float) {
            let n = noteLength(0.55)
            let sine = AudioDSP.sineTable
            var ph: Float = 0
            var pe: Float = 1
            let pdec = exp(-1 / (0.03 * sr))
            var e: Float = 1
            let edec = exp(-1 / (0.2 * sr))
            var ce: Float = 1
            let cdec = exp(-1 / (0.0025 * sr))
            var idx = startIndex(t0)
            for _ in 0..<n {
                let f = 44 + 115 * pe
                ph += f / sr
                if ph >= 1 { ph -= 1 }
                var click: Float = 0
                if ce > 1e-5 {
                    let x = rng.bi()
                    click = x * ce * 0.35
                    ce *= cdec
                }
                let v = tanh((AudioDSP.lookup(sine, ph) * e + click) * amp * 1.8)
                l[idx] += v * 0.707
                r[idx] += v * 0.707
                pe *= pdec
                e *= edec
                idx += 1
                if idx >= frames { idx = 0 }
            }
        }

        mutating func snare(at t0: Float, amp: Float, pan: Float = 0) {
            let n = noteLength(0.5)
            let sine = AudioDSP.sineTable
            var bp = AudioDSP.SVF()
            bp.set(cutoff: 2300, q: 0.7)
            var hp = AudioDSP.SVF()
            hp.set(cutoff: 5000, q: 0.7)
            var p1: Float = 0
            var p2: Float = 0
            var te: Float = 1
            let tdec = exp(-1 / (0.05 * sr))
            var ne: Float = 1
            let ndec = exp(-1 / (0.13 * sr))
            var pe: Float = 1
            let pdec = exp(-1 / (0.008 * sr))
            let (gl, gr) = Canvas.panGains(pan)
            var idx = startIndex(t0)
            for _ in 0..<n {
                let pm = 1 + 0.5 * pe
                p1 += 185 * pm / sr
                if p1 >= 1 { p1 -= 1 }
                p2 += 330 * pm / sr
                if p2 >= 1 { p2 -= 1 }
                let tone = (AudioDSP.lookup(sine, p1) + 0.6 * AudioDSP.lookup(sine, p2)) * te
                let x = rng.bi()
                let nz = bp.tick(x).1 * bp.k * 1.6 + hp.tick(x).2 * 0.5
                let v = tanh((tone * 0.8 + nz * ne) * amp * 1.5)
                l[idx] += v * gl
                r[idx] += v * gr
                te *= tdec
                ne *= ndec
                pe *= pdec
                idx += 1
                if idx >= frames { idx = 0 }
            }
        }

        mutating func hat(at t0: Float, amp: Float, open: Bool = false, pan: Float = 0) {
            let decay: Float = open ? 0.14 : 0.025
            let n = noteLength(decay * 6)
            var hp = AudioDSP.SVF()
            hp.set(cutoff: 7200, q: 0.7)
            var bp = AudioDSP.SVF()
            bp.set(cutoff: 10000, q: 1.2)
            var env: Float = 1
            let dec = exp(-1 / (decay * sr))
            let (gl, gr) = Canvas.panGains(pan)
            var idx = startIndex(t0)
            for _ in 0..<n {
                let x = rng.bi()
                let h = hp.tick(x).2
                let b = bp.tick(h).1 * bp.k
                let v = (h * 0.6 + b * 0.6) * env * amp
                l[idx] += v * gl
                r[idx] += v * gr
                env *= dec
                idx += 1
                if idx >= frames { idx = 0 }
            }
        }

        /// Pauke: unharmonische Teiltöne, kurzer Pitch-Drop, Schlägelgeräusch.
        mutating func timpani(_ midi: Float, at t0: Float, amp: Float, pan: Float = 0) {
            let f = AudioDSP.hz(midi)
            // Kesselmoden (unharmonisch): 1, 1.504, 1.742, 2.0
            let inc1 = f / sr
            let inc2 = f * 1.504 / sr
            let inc3 = f * 1.742 / sr
            let inc4 = f * 2.0 / sr
            let dec1 = exp(-1 / (1.3 * sr))
            let dec2 = exp(-1 / (0.7 * sr))
            let dec3 = exp(-1 / (0.5 * sr))
            let dec4 = exp(-1 / (0.4 * sr))
            var p1: Float = 0
            var p2: Float = 0
            var p3: Float = 0
            var p4: Float = 0
            var e1: Float = 1
            var e2: Float = 0.5
            var e3: Float = 0.3
            var e4: Float = 0.25
            let n = noteLength(1.7)
            let fadeN = max(1, Float(n) * 0.25)
            var pe: Float = 1
            let pdec = exp(-1 / (0.02 * sr))
            var ne: Float = 1
            let ndec = exp(-1 / (0.015 * sr))
            var lp = AudioDSP.OnePole(cutoff: 700)
            let sine = AudioDSP.sineTable
            let (gl, gr) = Canvas.panGains(pan)
            var idx = startIndex(t0)
            for i in 0..<n {
                let bend = 1 + 0.035 * pe
                p1 += inc1 * bend
                if p1 >= 1 { p1 -= 1 }
                p2 += inc2 * bend
                if p2 >= 1 { p2 -= 1 }
                p3 += inc3 * bend
                if p3 >= 1 { p3 -= 1 }
                p4 += inc4 * bend
                if p4 >= 1 { p4 -= 1 }
                var v = AudioDSP.lookup(sine, p1) * e1 + AudioDSP.lookup(sine, p2) * e2
                v += AudioDSP.lookup(sine, p3) * e3 + AudioDSP.lookup(sine, p4) * e4
                e1 *= dec1
                e2 *= dec2
                e3 *= dec3
                e4 *= dec4
                if ne > 1e-5 {          // Schlägelgeräusch
                    let x = rng.bi()
                    v += lp.lp(x) * ne * 2.0
                    ne *= ndec
                }
                if pe > 1e-6 { pe *= pdec } else { pe = 0 }
                let tailFade = min(1, Float(n - i) / fadeN)
                let out = v * amp * tailFade
                l[idx] += out * gl
                r[idx] += out * gr
                idx += 1
                if idx >= frames { idx = 0 }
            }
        }

        /// Synthetischer Chor ("Ah"/"Oh"): verstimmte Sägezähne mit Vibrato durch Formantfilter.
        mutating func choir(_ midi: Float, at t0: Float, dur: Float, amp: Float, pan: Float = 0, vowel: Int = 0) {
            let f = AudioDSP.hz(midi)
            let rel: Float = 1.2
            let n = noteLength(dur + rel)
            let atkN: Float = 0.7 * sr
            let durN = dur * sr
            let relN = rel * sr
            let formants: [Float] = vowel == 0 ? [760, 1150, 2600] : [460, 820, 2500]
            var fA = AudioDSP.SVF()
            fA.set(cutoff: formants[0], q: 5)
            var fB = AudioDSP.SVF()
            fB.set(cutoff: formants[1], q: 7)
            var fC = AudioDSP.SVF()
            fC.set(cutoff: formants[2], q: 9)
            var body = AudioDSP.OnePole(cutoff: min(3000, f * 4))
            let saw = AudioDSP.sawTable
            let sine = AudioDSP.sineTable
            let d1: Float = pow(2, -0.08 / 12)
            let d2: Float = pow(2, 0.07 / 12)
            var p0 = rng.unit()
            var p1 = rng.unit()
            var p2 = rng.unit()
            var vph = rng.unit()
            let vrate: Float = (4.8 + 0.8 * rng.unit()) / sr
            let (gl, gr) = Canvas.panGains(pan)
            var idx = startIndex(t0)
            for i in 0..<n {
                let fi = Float(i)
                var env: Float = fi < atkN ? fi / atkN : 1
                if fi > durN { env *= max(0, 1 - (fi - durN) / relN) }
                env = env * env * (3 - 2 * env)
                vph += vrate
                if vph >= 1 { vph -= 1 }
                let vib = AudioDSP.lookup(sine, vph)
                let vib0 = 1 + 0.005 * vib
                let vib1 = 1 - 0.004 * vib
                let vib2 = 1 + 0.0025 * vib
                p0 += f * vib0 / sr
                if p0 >= 1 { p0 -= 1 }
                p1 += f * d1 * vib1 / sr
                if p1 >= 1 { p1 -= 1 }
                p2 += f * d2 * vib2 / sr
                if p2 >= 1 { p2 -= 1 }
                let src = AudioDSP.lookup(saw, p0) + AudioDSP.lookup(saw, p1) + AudioDSP.lookup(saw, p2)
                let a = fA.tick(src).1 * fA.k
                let b = fB.tick(src).1 * fB.k
                let c3 = fC.tick(src).1 * fC.k
                let lo = body.lp(src)
                let v = (a + 0.55 * b + 0.22 * c3 + 0.25 * lo) * env * amp * 0.5
                l[idx] += v * gl
                r[idx] += v * gr
                idx += 1
                if idx >= frames { idx = 0 }
            }
        }

        /// Blechbläser-artiger Synth (Filter öffnet beim Anblasen, verzögertes Vibrato).
        mutating func brass(_ midi: Float, at t0: Float, dur: Float, amp: Float, pan: Float = 0, bright: Float = 1) {
            let f = AudioDSP.hz(midi)
            let rel: Float = 0.28
            let n = noteLength(dur + rel)
            let durN = dur * sr
            let relN = rel * sr
            let atkN: Float = 0.035 * sr
            var svf = AudioDSP.SVF()
            let saw = AudioDSP.sawTable
            let sine = AudioDSP.sineTable
            var p0 = rng.unit()
            var p1 = rng.unit()
            var vib: Float = 0
            let d: Float = pow(2, 0.06 / 12)
            let (gl, gr) = Canvas.panGains(pan)
            var idx = startIndex(t0)
            for i in 0..<n {
                let fi = Float(i)
                let t = fi / sr
                var env: Float = fi < atkN ? fi / atkN : 1
                if fi > durN { env *= max(0, 1 - (fi - durN) / relN) }
                if i % 16 == 0 {
                    let fenv: Float = t < 0.06 ? t / 0.06 : 0.55 + 0.45 * exp(-(t - 0.06) / 0.25)
                    svf.set(cutoff: f * (1.2 + (2.5 + 5 * bright) * fenv), q: 0.9)
                }
                vib += 5.5 / sr
                if vib >= 1 { vib -= 1 }
                let vibAmt: Float = t > 0.3 ? 0.003 * min(1, (t - 0.3) / 0.4) : 0
                let fm = 1 + vibAmt * AudioDSP.lookup(sine, vib)
                p0 += f * fm / sr
                if p0 >= 1 { p0 -= 1 }
                p1 += f * d * fm / sr
                if p1 >= 1 { p1 -= 1 }
                let src = AudioDSP.lookup(saw, p0) + AudioDSP.lookup(saw, p1)
                let y = svf.tick(src).0
                let v = tanh(y * 0.9) * env * amp
                l[idx] += v * gl
                r[idx] += v * gr
                idx += 1
                if idx >= frames { idx = 0 }
            }
        }

        /// Rausch-Steigerung (Riser) – Bandpass gleitet von `from` nach `to`.
        mutating func swell(at t0: Float, dur: Float, amp: Float, from: Float, to: Float) {
            let n = noteLength(dur)
            var fl = AudioDSP.SVF()
            var fr = AudioDSP.SVF()
            let ratio = max(0.01, to / max(from, 1))
            var idx = startIndex(t0)
            let fadeN = Float(min(n, 220))
            for i in 0..<n {
                let u = Float(i) / Float(n)
                if i % 16 == 0 {
                    let fc = from * pow(ratio, u)
                    fl.set(cutoff: fc, q: 0.8)
                    fr.set(cutoff: fc * 1.05, q: 0.8)
                }
                let e = pow(u, 2.5) * min(1, Float(n - i) / fadeN)
                let a = rng.bi()
                let b = rng.bi()
                let vl = fl.tick(a).1 * fl.k * e * amp * 2
                let vr = fr.tick(b).1 * fr.k * e * amp * 2
                l[idx] += vl
                r[idx] += vr
                idx += 1
                if idx >= frames { idx = 0 }
            }
        }

        /// Becken-Crash (Stereo-Rauschen, Hochpass, langes Ausklingen).
        mutating func crash(at t0: Float, amp: Float) {
            let n = noteLength(1.8)
            var hl = AudioDSP.SVF()
            hl.set(cutoff: 5200, q: 0.6)
            var hr = AudioDSP.SVF()
            hr.set(cutoff: 5600, q: 0.6)
            var env: Float = 1
            let dec = exp(-1 / (0.55 * sr))
            var idx = startIndex(t0)
            for i in 0..<n {
                let a = rng.bi()
                let b = rng.bi()
                let atk = min(1, Float(i) / 40)
                let vl = hl.tick(a).2 * env * amp * atk
                let vr = hr.tick(b).2 * env * amp * atk
                l[idx] += vl
                r[idx] += vr
                env *= dec
                idx += 1
                if idx >= frames { idx = 0 }
            }
        }

        /// Ping-Pong-Delay auf dem Send-Bus (zirkulär).
        mutating func applyDelay(time: Float, feedback: Float, mix: Float) {
            let d = max(1, min(frames - 1, Int(time * sr)))
            var bufL = [Float](repeating: 0, count: d)
            var bufR = [Float](repeating: 0, count: d)
            var outL = [Float](repeating: 0, count: frames)
            var outR = [Float](repeating: 0, count: frames)
            var dampL = AudioDSP.OnePole(cutoff: 3200)
            var dampR = AudioDSP.OnePole(cutoff: 3200)
            var di = 0
            for pass in 0..<2 {
                for i in 0..<frames {
                    let yl = bufL[di]
                    let yr = bufR[di]
                    let inL = sendL[i]
                    let inR = sendR[i]
                    let fbR = dampR.lp(yr) * feedback
                    let fbL = dampL.lp(yl) * feedback
                    bufL[di] = inL + fbR
                    bufR[di] = inR * 0.3 + fbL
                    if pass == 1 {
                        outL[i] = yl
                        outR[i] = yr
                    }
                    di += 1
                    if di >= d { di = 0 }
                }
            }
            for i in 0..<frames {
                l[i] += outL[i] * mix
                r[i] += outR[i] * mix
            }
        }

        /// Schroeder/Freeverb-artiger Hall (4 Kämme + 2 Allpässe je Kanal), zirkulär.
        mutating func applyReverb(mix: Float, room: Float, damp: Float) {
            var input = [Float](repeating: 0, count: frames)
            for i in 0..<frames { input[i] = (l[i] + r[i]) * 0.14 }
            AudioMusicSynth.circularOnePole(&input, cutoff: 220, highpass: true)
            var wetL = [Float](repeating: 0, count: frames)
            var wetR = [Float](repeating: 0, count: frames)
            for len in [1116, 1277, 1422, 1557] {
                AudioMusicSynth.combPass(input, &wetL, length: len, fb: room, damp: damp)
                AudioMusicSynth.combPass(input, &wetR, length: len + 23, fb: room, damp: damp)
            }
            AudioMusicSynth.allpassPass(&wetL, length: 556)
            AudioMusicSynth.allpassPass(&wetL, length: 341)
            AudioMusicSynth.allpassPass(&wetR, length: 579)
            AudioMusicSynth.allpassPass(&wetR, length: 364)
            for i in 0..<frames {
                l[i] += wetL[i] * mix
                r[i] += wetR[i] * mix
            }
        }

        /// DC-Filter, Normierung, sanfte Sättigung.
        mutating func master(peak: Float, drive: Float) {
            AudioMusicSynth.circularOnePole(&l, cutoff: 24, highpass: true)
            AudioMusicSynth.circularOnePole(&r, cutoff: 24, highpass: true)
            var m: Float = 0
            for i in 0..<frames { m = max(m, abs(l[i]), abs(r[i])) }
            guard m > 1e-6 else { return }
            let g = 1 / m
            let k = max(0.3, drive)
            let norm = peak / tanh(k)
            for i in 0..<frames {
                l[i] = tanh(l[i] * g * k) * norm
                r[i] = tanh(r[i] * g * k) * norm
            }
        }
    }

    // MARK: - Kompositionen

    /// Menü: dunkel, mysteriös – d-Moll, Drone, Pads, gläsernes Arpeggio, ferne Pauken.
    static func composeMenu() -> Canvas {
        var c = Canvas(bpm: 72, bars: 4, seed: 11)
        let chords: [[Float]] = [[50, 53, 57], [50, 53, 58], [50, 55, 58], [49, 52, 57]]   // Dm – B – Gm – A
        let roots: [Float] = [38, 34, 31, 33]
        let bar = c.beat * 4
        let eighth = c.beat * 0.5
        c.drone(26, amp: 0.2, beatHz: 0.18, saw: false, lfoCycles: 1, lfoDepth: 0.35)
        c.drone(38, amp: 0.07, beatHz: 0.31, saw: true, cutoff: 260, lfoCycles: 2, lfoDepth: 0.5)
        c.wind(amp: 0.05, cutoff: 700, lfoCycles: 3)
        for b in 0..<4 {
            let t0 = Float(b) * bar
            let tones = chords[b]
            for k in 0..<tones.count {
                c.pad(tones[k], at: t0, dur: bar, amp: 0.07, pan: Float(k - 1) * 0.45, bright: 0.35, attack: 1.4, release: 1.8, detune: 0.11)
            }
            c.pad(roots[b], at: t0, dur: bar, amp: 0.11, pan: 0, bright: 0.12, attack: 0.6, release: 1.2, detune: 0.05)
            let pattern: [Float] = [tones[0] + 12, tones[1] + 12, tones[2] + 12, tones[0] + 24,
                                    tones[2] + 12, tones[1] + 12, tones[0] + 24, tones[2] + 12]
            for s in 0..<8 {
                let accent: Float = s == 0 ? 1.0 : 0.75
                let pan: Float = s % 2 == 0 ? -0.35 : 0.35
                c.pluck(pattern[s], at: t0 + Float(s) * eighth, amp: 0.055 * accent, pan: pan, decay: 0.9, ratio: 3, index: 1.1, send: 0.55)
            }
        }
        c.timpani(38, at: 0, amp: 0.32)
        c.timpani(31, at: 2 * bar, amp: 0.3)
        c.pluck(81, at: bar + 2 * c.beat, amp: 0.05, pan: 0.5, decay: 2.5, ratio: 1.4, index: 2.2, send: 0.6)
        c.pluck(85, at: 3 * bar + 2 * c.beat, amp: 0.045, pan: -0.5, decay: 2.5, ratio: 1.4, index: 2.2, send: 0.6)
        c.applyDelay(time: c.beat * 0.75, feedback: 0.42, mix: 0.6)
        c.applyReverb(mix: 0.5, room: 0.88, damp: 0.3)
        return c
    }

    /// Offene Welt: nächtlich-heroisch, c-Moll, pulsierender Achtelbass, Arpeggio, Leitmotiv.
    static func composeRoam() -> Canvas {
        var c = Canvas(bpm: 104, bars: 8, seed: 23)
        let chords: [[Float]] = [[60, 63, 67], [60, 63, 68], [58, 63, 67], [58, 62, 65],
                                 [60, 63, 67], [60, 63, 68], [60, 65, 68], [59, 62, 67]]   // Cm Ab Eb B♭ Cm Ab Fm G
        let roots: [Float] = [36, 32, 39, 34, 36, 32, 41, 43]
        let bar = c.beat * 4
        let eighth = c.beat * 0.5
        let s16 = c.beat * 0.25
        let bassOffsets: [Float] = [0, 0, 12, 0, 0, 0, 12, 7]
        c.wind(amp: 0.03, cutoff: 900, lfoCycles: 4)
        c.drone(24, amp: 0.08, beatHz: 0.2, saw: false, lfoCycles: 2, lfoDepth: 0.4)
        for b in 0..<8 {
            let t0 = Float(b) * bar
            let tones = chords[b]
            for k in 0..<tones.count {
                c.pad(tones[k], at: t0, dur: bar, amp: 0.05, pan: Float(k - 1) * 0.5, bright: 0.55, attack: 0.5, release: 1.0, detune: 0.09)
            }
            for s in 0..<8 {
                let acc: Float = (s == 0 || s == 4) ? 1.0 : 0.78
                c.bass(roots[b] + bassOffsets[s], at: t0 + Float(s) * eighth, dur: eighth * 0.8, amp: 0.2 * acc,
                       cutoff: 320, envAmt: 1600 * acc, envDecay: 0.06, drive: 1.6)
            }
            c.kick(at: t0, amp: 0.42)
            c.kick(at: t0 + 2 * c.beat, amp: 0.36)
            if b % 2 == 1 { c.kick(at: t0 + 2.75 * c.beat, amp: 0.22) }
            c.snare(at: t0 + c.beat, amp: 0.2, pan: 0.05)
            c.snare(at: t0 + 3 * c.beat, amp: 0.22, pan: 0.05)
            for s in 0..<16 {
                let a: Float = s % 2 == 0 ? 0.05 : 0.022
                c.hat(at: t0 + Float(s) * s16, amp: a, open: s == 14 && b % 2 == 1, pan: 0.25)
            }
            let arp: [Float] = [tones[0] + 12, tones[1] + 12, tones[2] + 12, tones[1] + 12]
            for s in 0..<16 {
                let pan = -0.5 + Float(s) / 15
                let a: Float = s % 4 == 0 ? 0.04 : 0.028
                c.pluck(arp[s % 4], at: t0 + Float(s) * s16, amp: a, pan: pan, decay: 0.28, ratio: 2, index: 1.3, send: 0.35)
            }
        }
        let motif: [(Float, Float, Float)] = [
            (67, 0, 1.5), (72, 1.5, 0.5), (74, 2, 1), (75, 3, 1), (74, 4, 2), (72, 6, 1), (70, 7, 1),
            (67, 16, 1.5), (72, 17.5, 0.5), (74, 18, 1), (75, 19, 1), (77, 20, 2), (75, 22, 1), (74, 23, 1), (72, 24, 4)
        ]
        for m in motif {
            c.brass(m.0, at: m.1 * c.beat, dur: m.2 * c.beat, amp: 0.075, pan: 0.1, bright: 0.5)
        }
        c.applyDelay(time: c.beat * 0.75, feedback: 0.35, mix: 0.45)
        c.applyReverb(mix: 0.32, room: 0.85, damp: 0.3)
        return c
    }

    /// Spannung: Tritonus-Drone, Herzschlag-Taikos, dissonantes Streicher-Tremolo, metallische Pings.
    static func composeTension() -> Canvas {
        var c = Canvas(bpm: 84, bars: 4, seed: 37)
        let bar = c.beat * 4
        c.drone(25, amp: 0.2, beatHz: 0.22, saw: false, lfoCycles: 2, lfoDepth: 0.3)
        c.drone(31, amp: 0.09, beatHz: 0.37, saw: false, lfoCycles: 3, lfoDepth: 0.5)
        c.drone(37, amp: 0.05, beatHz: 0.15, saw: true, cutoff: 300, lfoCycles: 1, lfoDepth: 0.6)
        c.wind(amp: 0.045, cutoff: 500, lfoCycles: 2)
        for b in 0..<4 {
            let t0 = Float(b) * bar
            for beatIdx in [0, 2] {
                let t = t0 + Float(beatIdx) * c.beat
                c.taiko(at: t, amp: 0.34, pitch: 0.62)
                c.taiko(at: t + 0.27, amp: 0.2, pitch: 0.58)
            }
            for q in 0..<4 {
                c.bass(37, at: t0 + Float(q) * c.beat, dur: c.beat * 0.5, amp: 0.1, cutoff: 200, envAmt: 500, envDecay: 0.09, drive: 1.3)
            }
            for s in 0..<8 {
                let a: Float = s % 2 == 0 ? 0.03 : 0.018
                let pan: Float = s % 2 == 0 ? -0.3 : 0.3
                c.hat(at: t0 + Float(s) * c.beat * 0.5, amp: a, open: false, pan: pan)
            }
        }
        c.pad(80, at: 0, dur: 2 * bar, amp: 0.022, pan: -0.4, bright: 0.3, attack: 3, release: 1.5, detune: 0.06, tremolo: 7)
        c.pad(81, at: 0, dur: 2 * bar, amp: 0.018, pan: 0.4, bright: 0.3, attack: 3, release: 1.5, detune: 0.06, tremolo: 7.5)
        c.pad(81, at: 2 * bar, dur: 2 * bar, amp: 0.022, pan: -0.4, bright: 0.3, attack: 3, release: 1.5, detune: 0.06, tremolo: 7)
        c.pad(82, at: 2 * bar, dur: 2 * bar, amp: 0.02, pan: 0.4, bright: 0.3, attack: 3, release: 1.5, detune: 0.06, tremolo: 8)
        c.pluck(86, at: bar + 3 * c.beat, amp: 0.05, pan: 0.6, decay: 2.2, ratio: 1.41, index: 3, send: 0.7)
        c.pluck(80, at: 3 * bar + 1.5 * c.beat, amp: 0.045, pan: -0.6, decay: 2.2, ratio: 1.41, index: 3, send: 0.7)
        c.applyDelay(time: c.beat * 1.5, feedback: 0.45, mix: 0.5)
        c.applyReverb(mix: 0.45, room: 0.88, damp: 0.35)
        return c
    }

    /// Kampf: 132 BPM, treibender 16tel-Bass, Taiko-Grooves mit Fills, Chor, Blech-Stabs.
    static func composeCombat() -> Canvas {
        var c = Canvas(bpm: 132, bars: 8, seed: 51)
        let chords: [[Float]] = [[62, 65, 69], [62, 65, 69], [62, 65, 70], [60, 64, 67],
                                 [62, 65, 69], [62, 65, 69], [63, 67, 70], [60, 64, 67]]   // Dm Dm B♭ C Dm Dm E♭ C
        let roots: [Float] = [38, 38, 34, 36, 38, 38, 39, 36]
        let bar = c.beat * 4
        let s16 = c.beat * 0.25
        let eighth = c.beat * 0.5
        let grooveHits: [(Float, Float, Float)] = [(0, 0.6, 1), (1.5, 0.3, 1.15), (2, 0.5, 0.95), (3, 0.32, 1.2), (3.5, 0.3, 1.1)]
        let fillHits: [(Float, Float, Float)] = [(0, 0.6, 1), (1.5, 0.32, 1.1), (2, 0.42, 1.2), (2.25, 0.3, 1.25), (2.5, 0.45, 1.15),
                                                 (2.75, 0.34, 1.3), (3, 0.5, 1.1), (3.25, 0.4, 1.2), (3.5, 0.55, 1.0), (3.75, 0.62, 0.9)]
        c.drone(26, amp: 0.1, beatHz: 0.25, saw: false, lfoCycles: 4, lfoDepth: 0.3)
        for b in 0..<8 {
            let t0 = Float(b) * bar
            let tones = chords[b]
            let root = roots[b]
            for s in 0..<16 {
                let pos = s % 4
                let note = root + (pos == 2 ? 12 : 0)
                let acc: Float = pos == 0 ? 1 : 0.72
                c.bass(note, at: t0 + Float(s) * s16, dur: s16 * 0.82, amp: 0.2 * acc, cutoff: 260, envAmt: 2300 * acc, envDecay: 0.05, drive: 2.2)
            }
            let hits = (b == 3 || b == 7) ? fillHits : grooveHits
            for h in hits {
                c.taiko(at: t0 + h.0 * c.beat, amp: h.1, pitch: h.2, pan: (h.2 - 1) * 1.5)
            }
            c.kick(at: t0, amp: 0.45)
            c.kick(at: t0 + 2 * c.beat, amp: 0.4)
            c.kick(at: t0 + 2.75 * c.beat, amp: 0.24)
            c.snare(at: t0 + c.beat, amp: 0.3, pan: 0)
            c.snare(at: t0 + 3 * c.beat, amp: 0.32, pan: 0)
            for s in 0..<16 {
                let a: Float = s % 2 == 0 ? 0.055 : 0.025
                c.hat(at: t0 + Float(s) * s16, amp: a, open: s == 6 && b % 2 == 0, pan: 0.3)
            }
            for n in tones {
                c.brass(n, at: t0, dur: c.beat * 0.4, amp: 0.06, pan: 0, bright: 1)
            }
            if b % 2 == 1 {
                for n in tones {
                    c.brass(n, at: t0 + 2.5 * c.beat, dur: c.beat * 0.3, amp: 0.045, pan: 0, bright: 0.9)
                }
            }
            let choirAmp: Float = b < 4 ? 0.028 : 0.045
            for k in 0..<tones.count {
                c.choir(tones[k] - 12, at: t0, dur: bar, amp: choirAmp, pan: Float(k - 1) * 0.5, vowel: 0)
            }
            let ost: [Float] = [tones[0] + 12, tones[1] + 12, tones[2] + 12, tones[1] + 12]
            for s in 0..<8 {
                let pan: Float = s % 2 == 0 ? -0.4 : 0.4
                c.pluck(ost[s % 4], at: t0 + Float(s) * eighth, amp: 0.035, pan: pan, decay: 0.22, ratio: 1, index: 2.2, send: 0.25)
            }
        }
        c.swell(at: 7 * bar, dur: bar, amp: 0.09, from: 600, to: 9000)
        c.crash(at: 0, amp: 0.1)
        c.applyDelay(time: c.beat * 0.75, feedback: 0.3, mix: 0.4)
        c.applyReverb(mix: 0.26, room: 0.84, damp: 0.3)
        return c
    }

    /// Endboss: Orgel-Drone, massive Halbtempo-Taikos, Chor, Totenglocke, Tritonus-Harmonik.
    static func composeBoss() -> Canvas {
        var c = Canvas(bpm: 116, bars: 8, seed: 67)
        let chords: [[Float]] = [[60, 63, 67], [60, 63, 67], [61, 65, 68], [61, 65, 68],
                                 [60, 63, 67], [60, 63, 67], [61, 66, 70], [59, 62, 67]]   // Cm Cm D♭ D♭ Cm Cm G♭ G
        let roots: [Float] = [36, 36, 37, 37, 36, 36, 42, 43]
        let bar = c.beat * 4
        let eighth = c.beat * 0.5
        let s16 = c.beat * 0.25
        let grooveHits: [(Float, Float, Float)] = [(0, 0.72, 0.85), (0.75, 0.32, 1.0), (1.5, 0.4, 0.95), (2, 0.66, 0.8), (3.5, 0.34, 1.05)]
        let fillHits: [(Float, Float, Float)] = [(0, 0.72, 0.85), (1, 0.4, 1.0), (2, 0.6, 0.85), (2.5, 0.45, 1.0),
                                                 (3, 0.55, 1.1), (3.25, 0.5, 1.15), (3.5, 0.6, 1.2), (3.75, 0.7, 1.25)]
        c.drone(24, amp: 0.14, beatHz: 0.2, saw: true, cutoff: 220, lfoCycles: 4, lfoDepth: 0.35)
        c.drone(36, amp: 0.06, beatHz: 0.33, saw: true, cutoff: 500, lfoCycles: 2, lfoDepth: 0.5)
        for b in 0..<8 {
            let t0 = Float(b) * bar
            let tones = chords[b]
            let root = roots[b]
            for s in 0..<8 {
                let acc: Float = s % 4 == 0 ? 1 : 0.75
                let note = root + (s % 2 == 1 ? 12 : 0)
                c.bass(note, at: t0 + Float(s) * eighth, dur: eighth * 0.75, amp: 0.22 * acc, cutoff: 220, envAmt: 1500 * acc, envDecay: 0.07, drive: 2.6)
            }
            let hits = b == 7 ? fillHits : grooveHits
            for h in hits {
                c.taiko(at: t0 + h.0 * c.beat, amp: h.1, pitch: h.2, pan: (h.2 - 1) * 1.2)
            }
            c.kick(at: t0, amp: 0.48)
            c.kick(at: t0 + 2 * c.beat, amp: 0.4)
            c.snare(at: t0 + 2 * c.beat, amp: 0.34, pan: 0)
            for s in 0..<8 {
                let a: Float = s % 2 == 0 ? 0.04 : 0.025
                c.hat(at: t0 + Float(s) * eighth, amp: a, open: false, pan: -0.25)
            }
            let vowel = b < 4 ? 1 : 0
            for k in 0..<tones.count {
                c.choir(tones[k] - 12, at: t0, dur: bar, amp: 0.05, pan: Float(k - 1) * 0.55, vowel: vowel)
            }
            c.choir(root + 12, at: t0, dur: bar, amp: 0.035, pan: 0, vowel: vowel)
            for s in 0..<16 {
                c.pluck(tones[s % 3] + 12, at: t0 + Float(s) * s16, amp: 0.022, pan: 0.45, decay: 0.15, ratio: 1, index: 1.8, send: 0.2)
            }
        }
        for bIdx in [2, 6] {
            for n in chords[bIdx] {
                c.brass(n - 12, at: Float(bIdx) * bar, dur: c.beat * 1.5, amp: 0.075, pan: 0, bright: 0.9)
            }
        }
        for bIdx in [0, 2, 4, 6] {
            c.pluck(48, at: Float(bIdx) * bar, amp: 0.13, pan: 0, decay: 2.8, ratio: 1.4, index: 2.6, send: 0.3)
        }
        c.crash(at: 0, amp: 0.1)
        c.applyDelay(time: c.beat * 0.75, feedback: 0.3, mix: 0.3)
        c.applyReverb(mix: 0.32, room: 0.87, damp: 0.28)
        return c
    }

    /// Trauer: a-Moll, Klavier-Arpeggien, zarte Streicher, Cello-Grundton.
    static func composeSad() -> Canvas {
        var c = Canvas(bpm: 66, bars: 4, seed: 79)
        let chords: [[Float]] = [[57, 60, 64], [57, 60, 65], [57, 62, 65], [56, 59, 64]]   // Am F Dm E
        let roots: [Float] = [45, 41, 38, 40]
        let bar = c.beat * 4
        let eighth = c.beat * 0.5
        c.wind(amp: 0.02, cutoff: 600, lfoCycles: 2)
        for b in 0..<4 {
            let t0 = Float(b) * bar
            let t = chords[b]
            let low = roots[b]
            let pattern: [Float] = [low, t[0], t[1], t[2], t[0] + 12, t[2], t[1], t[0]]
            for s in 0..<8 {
                let a: Float = s == 0 ? 0.15 : 0.1
                c.piano(pattern[s], at: t0 + Float(s) * eighth, amp: a, pan: -0.2 + Float(s) * 0.05, decay: 1.8, send: 0.2)
            }
            for k in 0..<t.count {
                c.pad(t[k], at: t0, dur: bar, amp: 0.03, pan: Float(k - 1) * 0.5, bright: 0.25, attack: 1.6, release: 2.0, detune: 0.08)
            }
            c.pad(low - 12, at: t0, dur: bar, amp: 0.09, pan: 0, bright: 0.15, attack: 0.9, release: 1.5, detune: 0.04)
        }
        let melody: [(Float, Float)] = [(76, 0), (74, 3), (72, 4), (69, 6), (74, 8), (77, 10), (76, 12), (68, 15)]
        for m in melody {
            c.piano(m.0, at: m.1 * c.beat, amp: 0.15, pan: 0.15, decay: 2.6, send: 0.35)
        }
        c.applyDelay(time: c.beat * 0.75, feedback: 0.3, mix: 0.35)
        c.applyReverb(mix: 0.55, room: 0.89, damp: 0.35)
        return c
    }

    /// Sieg: D-Dur mit B♭/C-Wechsel (heroisch), Blech, Pauken-Wirbel, helle Arpeggien.
    static func composeVictory() -> Canvas {
        var c = Canvas(bpm: 100, bars: 4, seed: 97)
        let chords: [[Float]] = [[62, 66, 69], [62, 65, 70], [60, 64, 67], [62, 66, 69]]   // D B♭ C D
        let roots: [Float] = [38, 34, 36, 38]
        let bar = c.beat * 4
        let eighth = c.beat * 0.5
        for b in 0..<4 {
            let t0 = Float(b) * bar
            let t = chords[b]
            for k in 0..<t.count {
                c.brass(t[k], at: t0, dur: bar * 0.92, amp: 0.05, pan: Float(k - 1) * 0.4, bright: 0.75)
            }
            c.brass(roots[b] + 12, at: t0, dur: bar * 0.92, amp: 0.06, pan: 0, bright: 0.5)
            c.pad(roots[b], at: t0, dur: bar, amp: 0.1, pan: 0, bright: 0.2, attack: 0.3, release: 0.8, detune: 0.05)
            c.timpani(roots[b], at: t0, amp: 0.34)
            c.kick(at: t0, amp: 0.36)
            c.kick(at: t0 + 2 * c.beat, amp: 0.3)
            c.snare(at: t0 + c.beat, amp: 0.18, pan: 0)
            c.snare(at: t0 + 3 * c.beat, amp: 0.2, pan: 0)
            for s in 0..<8 {
                let a: Float = s % 2 == 0 ? 0.04 : 0.025
                c.hat(at: t0 + Float(s) * eighth, amp: a, open: s == 7, pan: 0.2)
            }
            let arp: [Float] = [t[0] + 12, t[1] + 12, t[2] + 12, t[0] + 24, t[2] + 12, t[1] + 12, t[2] + 12, t[0] + 24]
            for s in 0..<8 {
                let pan: Float = s % 2 == 0 ? -0.35 : 0.35
                c.pluck(arp[s], at: t0 + Float(s) * eighth, amp: 0.04, pan: pan, decay: 0.45, ratio: 2, index: 1.4, send: 0.35)
            }
        }
        for s in 0..<16 {
            let p = Float(s) / 15
            c.timpani(36, at: 2 * bar + 2 * c.beat + Float(s) * c.beat * 0.125, amp: 0.07 + 0.2 * p)
        }
        let melody: [(Float, Float, Float)] = [
            (69, 0, 1), (74, 1, 1), (78, 2, 2), (77, 4, 1.5), (74, 5.5, 0.5), (70, 6, 2),
            (72, 8, 1), (76, 9, 1), (79, 10, 2), (81, 12, 3), (78, 15, 1)
        ]
        for m in melody {
            c.brass(m.0, at: m.1 * c.beat, dur: m.2 * c.beat, amp: 0.07, pan: 0.05, bright: 1)
        }
        c.crash(at: 0, amp: 0.12)
        c.swell(at: 3 * bar + 2 * c.beat, dur: 2 * c.beat, amp: 0.07, from: 1000, to: 10000)
        c.applyDelay(time: c.beat * 0.75, feedback: 0.3, mix: 0.35)
        c.applyReverb(mix: 0.38, room: 0.87, damp: 0.25)
        return c
    }
}

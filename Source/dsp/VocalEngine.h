#pragma once

#include "AutoTuner.h"
#include "Effects.h"
#include "VocalChain.h"

#include <juce_core/juce_core.h>
#include <atomic>

namespace av
{
struct EngineParams
{
    int style = 1;                 // 0 natural, 1 modern, 2 hard
    float tune = 1.0f;             // 0 … 1
    float retuneMs = 20.0f;
    int keyMode = -1;              // -1 auto, 0 … 11
    int scaleMode = 0;             // KeyDetector::ScaleMode
    bool learn = true;
    bool autoMix = true;
    float warmth = 0.3f, deess = 0.5f, dynamics = 0.72f, autoEq = 0.7f;
    float delay = 0.12f, reverb = 0.28f, outputDb = 0.0f;
    double bpm = 120.0;
};

struct LearnedState
{
    KeyDetector::State key;
    VocalChain::Learned chain;
};

/** The complete AutoVocal signal path: tuner → channel strip → effects → limiter. */
class VocalEngine
{
public:
    struct PitchPoint
    {
        float in = 0, out = 0, target = 0;
        bool voiced = false;
    };

    void prepare (double sampleRate, int maxBlock);
    void reset();
    int getLatency() const noexcept { return tuner.getLatency() + limiter.getLatency(); }
    void setParams (const EngineParams& p) noexcept { params = p; }

    void process (const float* in, float* outL, float* outR, int numSamples) noexcept;

    // learned state (thread safe: snapshot / pending)
    LearnedState getLearnedState();
    void setLearnedState (const LearnedState& s);
    void relearn() { relearnRequested.store (true); }

    // telemetry for the editor
    int readPitchPoints (PitchPoint* dest, int maxPoints);
    std::atomic<float> inPeak { 0 }, outPeak { 0 }, gateGr { 0 }, deessGr { 0 }, compGr { 0 }, limGr { 0 };
    std::atomic<float> keyConfidence { 0 }, learnProgress { 0 }, lowCut { 80 };
    std::atomic<int> keyTonic { -1 }, keyMinor { 0 }, keyMask { 0x0FFF }, keyIsLearning { 1 };
    std::array<std::atomic<float>, VocalChain::kBands> eqGains {};

private:
    EngineParams params;
    AutoTuner tuner;
    VocalChain chain;
    FdnReverb reverb;
    PingPongDelay delay;
    Limiter limiter;
    double sr = 44100.0;
    int gateLook = 132;
    float outGain = 1.0f, outCoef = 0.999f;
    int snapshotCounter = 0;

    juce::SpinLock stateLock;
    LearnedState snapshot, pending;
    bool hasPending = false;
    std::atomic<bool> relearnRequested { false };

    juce::AbstractFifo pitchFifo { 2048 };
    std::array<PitchPoint, 2048> pitchBuf {};
};
} // namespace av

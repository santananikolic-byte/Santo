#include "VocalEngine.h"

namespace av
{
namespace
{
constexpr float kRt60[3] = { 1.7f, 1.3f, 1.1f };
constexpr float kSize[3] = { 1.0f, 0.9f, 0.85f };
} // namespace

void VocalEngine::prepare (double sampleRate, int)
{
    sr = sampleRate;
    tuner.prepare (sr);
    chain.prepare (sr);
    reverb.prepare (sr);
    delay.prepare (sr);
    limiter.prepare (sr);
    limiter.setCeiling (-1.0f);
    gateLook = (int) std::lround (sr * 0.003);
    outCoef = timeCoef (30.0f, sr);
    reset();
}

void VocalEngine::reset()
{
    tuner.reset();
    chain.reset();
    reverb.reset();
    delay.reset();
    limiter.reset();
    outGain = dbToGain (params.outputDb);
    pitchFifo.reset();
}

LearnedState VocalEngine::getLearnedState()
{
    const juce::SpinLock::ScopedLockType lock (stateLock);
    return hasPending ? pending : snapshot;
}

void VocalEngine::setLearnedState (const LearnedState& s)
{
    const juce::SpinLock::ScopedLockType lock (stateLock);
    pending = s;
    snapshot = s;
    hasPending = true;
}

int VocalEngine::readPitchPoints (PitchPoint* dest, int maxPoints)
{
    int start1, size1, start2, size2;
    pitchFifo.prepareToRead (maxPoints, start1, size1, start2, size2);
    for (int i = 0; i < size1; ++i) dest[i] = pitchBuf[(size_t) (start1 + i)];
    for (int i = 0; i < size2; ++i) dest[size1 + i] = pitchBuf[(size_t) (start2 + i)];
    pitchFifo.finishedRead (size1 + size2);
    return size1 + size2;
}

void VocalEngine::process (const float* in, float* outL, float* outR, int numSamples) noexcept
{
    // apply restored / reset state from the message thread
    {
        const juce::SpinLock::ScopedTryLockType lock (stateLock);
        if (lock.isLocked())
        {
            if (relearnRequested.exchange (false))
            {
                pending = LearnedState {};
                hasPending = true;
            }
            if (hasPending)
            {
                tuner.keyDetector().setState (pending.key);
                if (pending.chain.valid)
                    chain.setLearned (pending.chain);
                else
                    chain.clearLearned();
                hasPending = false;
            }
        }
    }

    const int st = std::clamp (params.style, 0, 2);

    AutoTuner::Settings ts;
    ts.amount = params.tune;
    ts.retuneMs = params.retuneMs;
    ts.keyMode = params.keyMode;
    ts.scaleMode = params.scaleMode;
    ts.learn = params.learn;
    tuner.setSettings (ts);

    VocalChain::Settings cs;
    cs.style = st;
    cs.warmth = params.warmth;
    cs.deess = params.deess;
    cs.dynamics = params.dynamics;
    cs.autoEq = params.autoEq;
    cs.learn = params.learn;
    chain.setSettings (cs);

    reverb.setTime (kRt60[st], kSize[st]);
    delay.setDelaySeconds ((float) (60.0 / std::clamp (params.bpm, 40.0, 240.0)) * (st == 2 ? 0.5f : 1.0f));
    const float revGain = 0.5f * params.reverb;
    const float dlyGain = 0.5f * params.delay;
    const float outTarget = dbToGain (params.outputDb);
    const int tunerLatency = tuner.getLatency();

    float pkIn = 0.0f, pkOut = 0.0f;
    for (int i = 0; i < numSamples; ++i)
    {
        const float x = in[i];
        pkIn = std::max (pkIn, std::abs (x));

        const float tuned = tuner.processSample (x);
        chain.setLowestPitch (tuner.lowestPitchHz());
        const float ahead = tuner.rawAt (tuner.samplesWritten() - 1 - tunerLatency + gateLook);
        const float dry = params.autoMix ? chain.processSample (tuned, ahead) : tuned;

        const float act = params.autoMix ? chain.vocalActivity() : 0.0f;
        float rl = 0, rr = 0, dl = 0, dr = 0;
        reverb.process (dry * revGain * (1.0f - 0.37f * act), rl, rr);
        delay.process (dry * dlyGain * (1.0f - 0.5f * act), dl, dr);

        outGain = outTarget + outCoef * (outGain - outTarget);
        float l = (dry + rl + dl) * outGain;
        float r = (dry + rr + dr) * outGain;
        limiter.process (l, r);
        outL[i] = l;
        outR[i] = r;
        pkOut = std::max (pkOut, std::max (std::abs (l), std::abs (r)));
    }

    // telemetry
    AutoTuner::FrameInfo fi;
    while (tuner.popFrame (fi))
    {
        int s1, n1, s2, n2;
        pitchFifo.prepareToWrite (1, s1, n1, s2, n2);
        if (n1 > 0)
        {
            pitchBuf[(size_t) s1] = { fi.inMidi, fi.outMidi, fi.targetMidi, fi.voiced };
            pitchFifo.finishedWrite (1);
        }
    }
    inPeak.store (std::max (inPeak.load(), pkIn));
    outPeak.store (std::max (outPeak.load(), pkOut));
    const auto& m = chain.getMeters();
    gateGr.store (params.autoMix ? m.gateGr : 0.0f);
    deessGr.store (params.autoMix ? m.deessGr : 0.0f);
    compGr.store (params.autoMix ? m.compGr : 0.0f);
    limGr.store (limiter.getGainReductionDb());
    auto& kd = tuner.keyDetector();
    keyTonic.store (tuner.currentTonic());
    keyMinor.store (tuner.currentMinor() ? 1 : 0);
    keyMask.store (tuner.currentMask());
    keyConfidence.store (kd.getConfidence());
    keyIsLearning.store (params.keyMode < 0 && params.scaleMode != KeyDetector::scaleChromatic && tuner.currentTonic() < 0 ? 1 : 0);
    learnProgress.store (kd.learnProgress());
    lowCut.store (chain.getLearned().lowCutHz);
    const auto g = chain.appliedEqGains();
    for (int b = 0; b < VocalChain::kBands; ++b)
        eqGains[(size_t) b].store (g[(size_t) b]);

    snapshotCounter += numSamples;
    if (snapshotCounter > (int) (sr * 0.5))
    {
        snapshotCounter = 0;
        const juce::SpinLock::ScopedTryLockType lock (stateLock);
        if (lock.isLocked() && ! hasPending)
        {
            snapshot.key = kd.getState();
            snapshot.chain = chain.getLearned();
        }
    }
}
} // namespace av

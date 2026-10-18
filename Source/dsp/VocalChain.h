#pragma once

#include "DspUtils.h"

#include <juce_dsp/juce_dsp.h>
#include <atomic>
#include <memory>

namespace av
{
/** Self-adjusting vocal channel strip.

    Low cut → gate/expander → auto EQ → de-esser → leveling + peak compressor
    → saturation → auto gain. Every stage measures the signal and adapts its
    settings continuously ("learning"), so the vocal ends up balanced without
    manual tweaking. Learning can be frozen, and the learned state is saved.
*/
class VocalChain
{
public:
    static constexpr int kBands = 8;

    struct Settings
    {
        int style = 1;         // 0 natural, 1 modern, 2 hard
        float warmth = 0.15f;  // saturation amount 0 … 1
        float deess = 0.5f;    // 0 … 1
        float dynamics = 0.7f; // 0 = open, 1 = very controlled
        float autoEq = 0.7f;   // 0 … 1
        bool learn = true;
    };

    struct Learned
    {
        std::array<float, kBands> eqGains {};
        float compThreshold = -30.0f;
        float autoGainDb = 0.0f;
        float activeDb = -24.0f, floorDb = -70.0f;
        float lowCutHz = 80.0f;
        bool valid = false;
    };

    struct Meters
    {
        float gateGr = 0, deessGr = 0, compGr = 0;
    };

    void prepare (double sampleRate);
    void reset();
    void setSettings (const Settings& s) noexcept;

    /** x = tuned vocal, ahead = raw vocal a few ms in the future (for the gate). */
    float processSample (float x, float ahead) noexcept;

    void setLowestPitch (float hz) noexcept { lowestPitch = hz; }
    const Learned& getLearned() const noexcept { return learned; }
    void setLearned (const Learned& l) noexcept;
    void clearLearned() noexcept;
    const Meters& getMeters() const noexcept { return meters; }
    float vocalActivity() const noexcept { return activity; }

    static float bandFrequency (int b) noexcept;
    /** Builds the EQ filter bank for the given band gains (also used by the editor display). */
    static void designBank (double sampleRate, const std::array<float, kBands>& gains, std::array<Biquad, kBands>& bank) noexcept;
    /** Current EQ response in dB at frequency f (for the display). */
    float eqResponseDb (float f) const noexcept;
    std::array<float, kBands> appliedEqGains() const noexcept { return applied; }

private:
    void blockUpdate() noexcept;
    void analyseSpectrum() noexcept;
    void updateEqTargets() noexcept;
    void designEq (std::array<Biquad, kBands>& bank, const std::array<float, kBands>& g) const noexcept;
    float targetPsdDb (float f) const noexcept;
    void computeTargetBands() noexcept;

    double sr = 44100.0;
    Settings settings;
    Learned learned;
    Meters meters;

    // low cut
    Biquad hp1, hp2;
    float lowestPitch = 0.0f, appliedLowCut = 0.0f;

    // gate
    float gateEnv = 0, gateGr = 0, gateHeld = 0, gateAtt = 0, gateRel = 0, gateEnvCoef = 0;
    int gateHold = 0, gateHoldSamples = 0;

    // auto EQ
    std::array<Biquad, kBands> eq;
    std::array<float, kBands> applied {}, desired {}, targetBand {};
    std::array<double, kBands> bandPower {};
    double spectrumSeconds = 0.0;
    std::unique_ptr<juce::dsp::FFT> fft;
    std::vector<float> fftIn, fftWork, window;
    int fftSize = 2048, fftFill = 0;
    std::vector<int> binBand;

    // de-esser (Linkwitz-Riley 4 split)
    Biquad lp1, lp2, hpA, hpB;
    float sibEnv = 0, sibGr = 0, sibEnvCoef = 0, sibAtt = 0, sibRel = 0;

    // compressors
    float c1Env = 0, c1Gr = 0, c1EnvCoef = 0, c1Att = 0, c1Rel = 0;
    float c2Env = 0, c2Gr = 0, c2EnvCoef = 0, c2Att = 0, c2Rel = 0;

    // saturation / gain
    float peakEnv = 0.1f, peakRel = 0;
    float gainLin = 1.0f, gainCoef = 0;

    // level statistics (10 ms blocks)
    int blockLen = 441, blockPos = 0;
    double blockIn = 0, blockPre = 0, blockOut = 0, blockAhead = 0;
    float shortOut = -100.0f;
    LevelHistogram rawHist, preHist, outHist;
    float activity = 0.0f, actCoef = 0.0f;
    int blocksSinceUpdate = 0, eqCounter = 0;
};
} // namespace av

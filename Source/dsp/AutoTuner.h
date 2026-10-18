#pragma once

#include "DspUtils.h"
#include "KeyDetector.h"

#include <juce_dsp/juce_dsp.h>
#include <memory>

namespace av
{
/** Real-time pitch correction.

    - pitch detection: YIN (FFT based) every ~3 ms
    - note decision with hysteresis on the learned / chosen scale
    - correction with adjustable retune speed (0 ms = hard "robot" effect)
    - pitch shifting: pitch-synchronous overlap-add (TD-PSOLA), keeps the formants

    The output is delayed by getLatency() samples; this look-ahead is what makes
    the PSOLA grains and the median smoothing of the pitch track possible.
*/
class AutoTuner
{
public:
    struct Settings
    {
        float amount = 1.0f;     // 0 … 1
        float retuneMs = 20.0f;  // 0 = instant
        int keyMode = -1;        // -1 = auto, 0 … 11 = C … B
        int scaleMode = KeyDetector::scaleAuto;
        bool learn = true;
    };

    struct FrameInfo
    {
        float inMidi = 0, outMidi = 0, targetMidi = 0, levelDb = -120;
        bool voiced = false;
    };

    void prepare (double sampleRate);
    void reset();
    int getLatency() const noexcept { return latency; }
    void setSettings (const Settings& s) noexcept { settings = s; }

    /** Pushes one input sample and returns the tuned sample from getLatency() samples ago. */
    float processSample (float x) noexcept;

    /** Raw (untuned) input at an absolute position not newer than the last pushed sample. */
    float rawAt (int64_t pos) const noexcept { return pos < 0 ? 0.0f : in[(size_t) (pos & ringMask)]; }
    int64_t samplesWritten() const noexcept { return n; }

    bool popFrame (FrameInfo& f) noexcept;

    KeyDetector& keyDetector() noexcept { return keys; }
    uint16_t currentMask() const noexcept { return mask; }
    int currentTonic() const noexcept { return tonic; }
    bool currentMinor() const noexcept { return minor; }
    float lowestPitchHz() const noexcept { return lowPitch; }

private:
    struct Frame
    {
        float f0Raw = 0, midiRaw = 0, aper = 1, levelDb = -120;
        bool voicedRaw = false;
        float f0 = 0, midi = 0, corr = 0, note = 0;
        bool voiced = false;
    };

    struct Mark
    {
        int64_t pos = 0;
        float period = 0;
        bool voiced = false;
    };

    void analyseFrame() noexcept;
    void finaliseFrame (int64_t k) noexcept;
    void placeMarks() noexcept;
    void synthesise (int64_t outPos) noexcept;
    double frameCenter (int64_t k) const noexcept { return (double) ((k + 1) * hop) - frameLen * 0.5; }
    float pitchAt (int64_t t, bool& voiced, float* corr) const noexcept;
    float nearestNote (float midi) const noexcept;
    Frame& frame (int64_t k) noexcept { return frames[(size_t) (k & frameMask)]; }
    const Frame& frame (int64_t k) const noexcept { return frames[(size_t) (k & frameMask)]; }

    Settings settings;
    KeyDetector keys;
    double sr = 44100.0;

    // geometry
    int hop = 128, tmin = 40, tmax = 600, win = 600, frameLen = 1200, nfft = 2048, latency = 2700, unvoicedPeriod = 176;
    std::unique_ptr<juce::dsp::FFT> fft;
    std::vector<float> fftA, fftB, frameBuf;
    std::vector<double> cumEnergy, cmnd;

    // rings
    static constexpr int kRingBits = 16;
    static constexpr int64_t ringMask = (1 << kRingBits) - 1;
    std::vector<float> in, det, lp, acc, wsum;
    int64_t n = 0;
    float dcX = 0, dcY = 0, dcR = 0.997f;
    Biquad lpf;

    // frames
    static constexpr int64_t frameMask = 511;
    std::vector<Frame> frames;
    int64_t framesComputed = 0, framesFinal = 0;
    float floorDb = -100, topDb = -100;

    // correction state
    bool prevVoiced = false;
    float noteSmooth = 0, curNote = 0, corrState = 0;
    uint16_t mask = 0x0FFF;
    int tonic = -1;
    bool minor = false;
    float lowPitch = 0.0f;

    // PSOLA
    static constexpr int64_t markMask = 4095;
    std::vector<Mark> marks;
    int64_t markCount = 0, markSearch = 0;
    double nextMarkPos = 0, synthPos = 0;
    bool prevMarkVoiced = false;
    std::array<float, 4097> hann {};
    float mixState = 1.0f, mixCoef = 0.999f;

    // telemetry
    std::array<FrameInfo, 256> fifo {};
    int fifoWrite = 0, fifoRead = 0;
};
} // namespace av

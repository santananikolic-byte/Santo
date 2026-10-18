#pragma once

#include "DspUtils.h"

namespace av
{
/** Learns the key of the song from the sung pitch classes (Krumhansl-Kessler profiles). */
class KeyDetector
{
public:
    enum ScaleMode { scaleAuto = 0, scaleMajor, scaleMinor, scaleChromatic };

    struct State
    {
        std::array<double, 12> hist {};
        double voicedSeconds = 0.0;
        int tonic = -1;
        bool minor = false;
    };

    void reset() noexcept
    {
        state = {};
        confidence = 0.0f;
        candidateCount = 0;
        sinceEval = 0.0;
    }

    void setState (const State& s) noexcept
    {
        state = s;
        evaluate();
    }

    const State& getState() const noexcept { return state; }

    void addFrame (float midi, float weight, double dt) noexcept
    {
        const double decay = std::exp (-dt / kMemorySeconds);
        for (auto& h : state.hist)
            h *= decay;
        const int pc = ((int) std::lround (midi) % 12 + 12) % 12;
        state.hist[(size_t) pc] += weight;
        state.voicedSeconds += dt;
        sinceEval += dt;
        if (sinceEval >= 0.5)
        {
            sinceEval = 0.0;
            evaluate();
        }
    }

    bool isLearning() const noexcept { return state.voicedSeconds < kLearnSeconds; }
    float learnProgress() const noexcept { return (float) std::min (1.0, state.voicedSeconds / kLearnSeconds); }
    int detectedTonic() const noexcept { return state.tonic; }
    bool detectedMinor() const noexcept { return state.minor; }
    float getConfidence() const noexcept { return confidence; }

    /** Bit mask of allowed pitch classes (bit 0 = C) for the given user settings. */
    uint16_t allowedMask (int keyMode, int scaleMode, int& tonicOut, bool& minorOut) const noexcept
    {
        tonicOut = -1;
        minorOut = false;
        if (scaleMode == scaleChromatic)
            return 0x0FFF;

        int tonic = keyMode;
        bool minor = scaleMode == scaleMinor;

        if (keyMode < 0)
        {
            if (state.tonic < 0 || isLearning())
                return 0x0FFF; // until the key is known: correct chromatically
            if (scaleMode == scaleAuto)
            {
                tonic = state.tonic;
                minor = state.minor;
            }
            else
            {
                tonic = bestTonicForMode (minor);
            }
        }
        else if (scaleMode == scaleAuto)
        {
            minor = correlation (keyMode, true) > correlation (keyMode, false);
        }

        tonicOut = tonic;
        minorOut = minor;
        uint16_t mask = scaleMask (tonic, minor);

        // Notes the singer clearly uses a lot stay allowed (e.g. leading tone in minor)
        const double sum = total();
        if (sum > 1e-9 && ! isLearning())
            for (int pc = 0; pc < 12; ++pc)
                if (state.hist[(size_t) pc] / sum > 0.09)
                    mask |= (uint16_t) (1u << pc);
        return mask;
    }

    static uint16_t scaleMask (int tonic, bool minor) noexcept
    {
        static constexpr int major[] = { 0, 2, 4, 5, 7, 9, 11 };
        static constexpr int minorSteps[] = { 0, 2, 3, 5, 7, 8, 10 };
        uint16_t m = 0;
        for (int i = 0; i < 7; ++i)
            m |= (uint16_t) (1u << ((tonic + (minor ? minorSteps[i] : major[i])) % 12));
        return m;
    }

private:
    static constexpr double kMemorySeconds = 40.0;
    static constexpr double kLearnSeconds = 4.0;

    double total() const noexcept
    {
        double s = 0;
        for (auto h : state.hist)
            s += h;
        return s;
    }

    double correlation (int tonic, bool minor) const noexcept
    {
        static constexpr double majorProfile[] = { 6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88 };
        static constexpr double minorProfile[] = { 6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17 };
        const double* prof = minor ? minorProfile : majorProfile;
        double mx = 0, my = 0;
        for (int i = 0; i < 12; ++i)
        {
            mx += prof[i];
            my += state.hist[(size_t) i];
        }
        mx /= 12;
        my /= 12;
        double sxy = 0, sxx = 0, syy = 0;
        for (int i = 0; i < 12; ++i)
        {
            const double x = prof[((i - tonic) % 12 + 12) % 12] - mx;
            const double y = state.hist[(size_t) i] - my;
            sxy += x * y;
            sxx += x * x;
            syy += y * y;
        }
        return (sxx > 0 && syy > 1e-12) ? sxy / std::sqrt (sxx * syy) : 0.0;
    }

    int bestTonicForMode (bool minor) const noexcept
    {
        int best = 0;
        double r = -2;
        for (int t = 0; t < 12; ++t)
        {
            const double c = correlation (t, minor);
            if (c > r) { r = c; best = t; }
        }
        return best;
    }

    void evaluate() noexcept
    {
        int bestT = 0;
        bool bestM = false;
        double bestR = -2;
        for (int m = 0; m < 2; ++m)
            for (int t = 0; t < 12; ++t)
            {
                const double r = correlation (t, m == 1);
                if (r > bestR) { bestR = r; bestT = t; bestM = m == 1; }
            }

        if (state.tonic < 0)
        {
            if (! isLearning() && bestR > 0.5)
            {
                state.tonic = bestT;
                state.minor = bestM;
            }
        }
        else if (bestT != state.tonic || bestM != state.minor)
        {
            const double cur = correlation (state.tonic, state.minor);
            candidateCount = (bestR > cur + 0.06) ? candidateCount + 1 : 0;
            if (candidateCount >= 4)
            {
                state.tonic = bestT;
                state.minor = bestM;
                candidateCount = 0;
            }
        }
        else
        {
            candidateCount = 0;
        }
        confidence = state.tonic >= 0 ? (float) std::max (0.0, correlation (state.tonic, state.minor)) : 0.0f;
    }

    State state;
    float confidence = 0.0f;
    int candidateCount = 0;
    double sinceEval = 0.0;
};
} // namespace av

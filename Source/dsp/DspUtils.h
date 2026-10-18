#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <vector>

namespace av
{
constexpr double kPi = 3.14159265358979323846;

inline float dbToGain (float db) noexcept { return std::pow (10.0f, db * 0.05f); }
inline float gainToDb (float g) noexcept  { return 20.0f * std::log10 (std::max (g, 1.0e-9f)); }
inline float powToDb (float p) noexcept   { return 10.0f * std::log10 (std::max (p, 1.0e-12f)); }

/** One-pole smoothing coefficient for a time constant in milliseconds. */
inline float timeCoef (float ms, double sampleRate) noexcept
{
    if (ms <= 0.0f)
        return 0.0f;
    return (float) std::exp (-1.0 / (sampleRate * ms * 0.001));
}

//==============================================================================
/** Transposed direct form II biquad with RBJ cookbook designs. */
struct Biquad
{
    float b0 = 1, b1 = 0, b2 = 0, a1 = 0, a2 = 0;
    float z1 = 0, z2 = 0;

    void reset() noexcept { z1 = z2 = 0; }

    inline float process (float x) noexcept
    {
        const float y = b0 * x + z1;
        z1 = b1 * x - a1 * y + z2;
        z2 = b2 * x - a2 * y;
        return y;
    }

    void setNormalised (double B0, double B1, double B2, double A0, double A1, double A2) noexcept
    {
        b0 = (float) (B0 / A0); b1 = (float) (B1 / A0); b2 = (float) (B2 / A0);
        a1 = (float) (A1 / A0); a2 = (float) (A2 / A0);
    }

    void lowPass (double sr, double fc, double q) noexcept
    {
        const double w = 2 * kPi * fc / sr, c = std::cos (w), al = std::sin (w) / (2 * q);
        setNormalised ((1 - c) / 2, 1 - c, (1 - c) / 2, 1 + al, -2 * c, 1 - al);
    }

    void highPass (double sr, double fc, double q) noexcept
    {
        const double w = 2 * kPi * fc / sr, c = std::cos (w), al = std::sin (w) / (2 * q);
        setNormalised ((1 + c) / 2, -(1 + c), (1 + c) / 2, 1 + al, -2 * c, 1 - al);
    }

    void bandPass (double sr, double fc, double q) noexcept
    {
        const double w = 2 * kPi * fc / sr, c = std::cos (w), al = std::sin (w) / (2 * q);
        setNormalised (al, 0, -al, 1 + al, -2 * c, 1 - al);
    }

    void peak (double sr, double fc, double q, double gainDb) noexcept
    {
        const double A = std::pow (10.0, gainDb / 40.0);
        const double w = 2 * kPi * fc / sr, c = std::cos (w), al = std::sin (w) / (2 * q);
        setNormalised (1 + al * A, -2 * c, 1 - al * A, 1 + al / A, -2 * c, 1 - al / A);
    }

    void lowShelf (double sr, double fc, double q, double gainDb) noexcept
    {
        const double A = std::pow (10.0, gainDb / 40.0);
        const double w = 2 * kPi * fc / sr, c = std::cos (w), al = std::sin (w) / (2 * q);
        const double sa = 2 * std::sqrt (A) * al;
        setNormalised (A * ((A + 1) - (A - 1) * c + sa), 2 * A * ((A - 1) - (A + 1) * c),
                       A * ((A + 1) - (A - 1) * c - sa), (A + 1) + (A - 1) * c + sa,
                       -2 * ((A - 1) + (A + 1) * c), (A + 1) + (A - 1) * c - sa);
    }

    void highShelf (double sr, double fc, double q, double gainDb) noexcept
    {
        const double A = std::pow (10.0, gainDb / 40.0);
        const double w = 2 * kPi * fc / sr, c = std::cos (w), al = std::sin (w) / (2 * q);
        const double sa = 2 * std::sqrt (A) * al;
        setNormalised (A * ((A + 1) + (A - 1) * c + sa), -2 * A * ((A - 1) + (A + 1) * c),
                       A * ((A + 1) + (A - 1) * c - sa), (A + 1) - (A - 1) * c + sa,
                       2 * ((A - 1) - (A + 1) * c), (A + 1) - (A - 1) * c - sa);
    }

    /** Magnitude response in dB at frequency f. */
    double magnitudeDb (double sr, double f) const noexcept
    {
        const double w = 2 * kPi * f / sr;
        const double cw = std::cos (w), sw = std::sin (w), c2 = std::cos (2 * w), s2 = std::sin (2 * w);
        const double nr = b0 + b1 * cw + b2 * c2, ni = -(b1 * sw + b2 * s2);
        const double dr = 1 + a1 * cw + a2 * c2, di = -(a1 * sw + a2 * s2);
        return 10.0 * std::log10 ((nr * nr + ni * ni) / std::max (dr * dr + di * di, 1e-30));
    }
};

//==============================================================================
/** Histogram of levels in 1 dB bins (-120 … 0 dB) with exponential forgetting. */
class LevelHistogram
{
public:
    static constexpr int kBins = 120;

    void reset() noexcept { bins.fill (0.0); total = 0.0; }

    void setDecay (double perUpdate) noexcept { decay = perUpdate; }

    void add (float levelDb, double weight = 1.0) noexcept
    {
        for (auto& b : bins)
            b *= decay;
        total *= decay;
        const int i = std::clamp ((int) std::floor (levelDb + 120.0f), 0, kBins - 1);
        bins[(size_t) i] += weight;
        total += weight;
    }

    float percentile (double p, float fallback) const noexcept
    {
        if (total < 1e-6)
            return fallback;
        const double goal = total * p;
        double acc = 0.0;
        for (int i = 0; i < kBins; ++i)
        {
            const double prev = acc;
            acc += bins[(size_t) i];
            if (acc >= goal)
            {
                const double frac = bins[(size_t) i] > 0 ? (goal - prev) / bins[(size_t) i] : 0.5;
                return (float) (i - 120 + frac);
            }
        }
        return 0.0f;
    }

    double weight() const noexcept { return total; }

private:
    std::array<double, kBins> bins {};
    double total = 0.0, decay = 1.0;
};
} // namespace av

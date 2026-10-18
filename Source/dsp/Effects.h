#pragma once

#include "DspUtils.h"

namespace av
{
//==============================================================================
/** Fractional delay line (linear interpolation). */
class DelayLine
{
public:
    void prepare (int maxSamples)
    {
        size = 1;
        while (size < maxSamples + 4)
            size <<= 1;
        buf.assign ((size_t) size, 0.0f);
        pos = 0;
    }
    void reset() { std::fill (buf.begin(), buf.end(), 0.0f); pos = 0; }
    inline void push (float x) noexcept { buf[(size_t) pos] = x; pos = (pos + 1) & (size - 1); }
    inline float read (float delay) const noexcept
    {
        const float rp = (float) pos - 1.0f - delay;
        const int i0 = (int) std::floor (rp);
        const float f = rp - (float) i0;
        const float a = buf[(size_t) (i0 & (size - 1))], b = buf[(size_t) ((i0 + 1) & (size - 1))];
        return a + f * (b - a);
    }
    inline float readInt (int delay) const noexcept { return buf[(size_t) ((pos - 1 - delay) & (size - 1))]; }

private:
    std::vector<float> buf;
    int size = 1, pos = 0;
};

//==============================================================================
/** 8-line feedback delay network reverb (Householder matrix, damped, modulated). */
class FdnReverb
{
public:
    void prepare (double sampleRate)
    {
        sr = sampleRate;
        for (auto& d : lines)
            d.prepare ((int) (sr * 0.2));
        for (auto& d : diffusers)
            d.prepare ((int) (sr * 0.03));
        predelay.prepare ((int) (sr * 0.1));
        inHp.highPass (sr, 220.0, 0.7071);
        inLp.lowPass (sr, 8500.0, 0.7071);
        setTime (1.4f, 1.0f);
        reset();
        calibrate();
    }

    void reset()
    {
        for (auto& d : lines) d.reset();
        for (auto& d : diffusers) d.reset();
        predelay.reset();
        inHp.reset();
        inLp.reset();
        damp.fill (0.0f);
        lfo = 0.0;
    }

    /** rt60 in seconds, size scales the room dimensions. */
    void setTime (float rt60, float size)
    {
        if (std::abs (rt60 - curRt60) < 1e-3f && std::abs (size - curSize) < 1e-3f)
            return;
        curRt60 = rt60;
        curSize = size;
        static constexpr float baseMs[8] = { 29.7f, 37.1f, 41.1f, 43.7f, 53.3f, 59.9f, 67.3f, 73.1f };
        for (int i = 0; i < 8; ++i)
        {
            lengths[(size_t) i] = baseMs[i] * 0.001f * size * (float) sr;
            gains[(size_t) i] = std::pow (10.0f, -3.0f * lengths[(size_t) i] / (rt60 * (float) sr));
        }
        // high frequencies decay roughly twice as fast
        dampCoef = (float) std::exp (-2.0 * kPi * 5200.0 / sr);
    }

    inline void process (float x, float& outL, float& outR) noexcept
    {
        predelay.push (x);
        float v = predelay.readInt ((int) (sr * 0.025));
        v = inLp.process (inHp.process (v));

        static constexpr float diffMs[4] = { 4.7f, 3.6f, 12.7f, 9.3f };
        for (int i = 0; i < 4; ++i)
        {
            auto& d = diffusers[(size_t) i];
            const float delayed = d.readInt ((int) (diffMs[i] * 0.001f * (float) sr));
            const float w = v + 0.6f * delayed;
            d.push (w);
            v = delayed - 0.6f * w;
        }

        lfo += 0.6 / sr;
        if (lfo > 1.0) lfo -= 1.0;
        const float mod = (float) std::sin (2.0 * kPi * lfo) * (float) (sr * 0.0003);

        float y[8];
        float sum = 0.0f;
        for (int i = 0; i < 8; ++i)
        {
            const float len = lengths[(size_t) i] + (i == 1 ? mod : (i == 6 ? -mod : 0.0f));
            float s = lines[(size_t) i].read (len) * gains[(size_t) i];
            damp[(size_t) i] = s + dampCoef * (damp[(size_t) i] - s); // one-pole low pass
            s = 0.55f * s + 0.45f * damp[(size_t) i];
            y[i] = s;
            sum += s;
        }
        const float h = sum * 0.25f; // Householder: y - 2/N * sum
        static constexpr float signsIn[8] = { 1, -1, 1, -1, 1, 1, -1, -1 };
        for (int i = 0; i < 8; ++i)
            lines[(size_t) i].push (y[i] - h + signsIn[i] * v * 0.35f);

        outL = norm * (y[0] + y[2] + y[4] + y[6] - y[1] * 0.5f);
        outR = norm * (y[1] + y[3] + y[5] + y[7] - y[0] * 0.5f);
    }

private:
    /** Normalise the impulse response to unit energy so the wet level is predictable. */
    void calibrate()
    {
        norm = 1.0f;
        reset();
        double e = 0.0;
        const int len = (int) (sr * 3.0);
        for (int i = 0; i < len; ++i)
        {
            float l, r;
            process (i == 0 ? 1.0f : 0.0f, l, r);
            e += 0.5 * ((double) l * l + (double) r * r);
        }
        norm = e > 0 ? (float) (1.0 / std::sqrt (e)) : 1.0f;
        reset();
    }

    double sr = 44100.0, lfo = 0.0;
    std::array<DelayLine, 8> lines;
    std::array<DelayLine, 4> diffusers;
    DelayLine predelay;
    Biquad inHp, inLp;
    std::array<float, 8> lengths {}, gains {}, damp {};
    float dampCoef = 0.5f, norm = 1.0f, curRt60 = -1.0f, curSize = -1.0f;
};

//==============================================================================
/** Tempo-synced stereo ping-pong delay with filtered feedback. */
class PingPongDelay
{
public:
    void prepare (double sampleRate)
    {
        sr = sampleRate;
        left.prepare ((int) (sr * 2.1));
        right.prepare ((int) (sr * 2.1));
        hpCoef = (float) std::exp (-2.0 * kPi * 300.0 / sr);
        lpCoef = (float) std::exp (-2.0 * kPi * 4500.0 / sr);
        slew = timeCoef (200.0f, sr);
        reset();
    }

    void reset()
    {
        left.reset();
        right.reset();
        hpL = hpR = lpL = lpR = 0.0f;
        curDelay = -1.0f;
    }

    void setDelaySeconds (float s) noexcept { targetDelay = std::clamp (s, 0.05f, 2.0f) * (float) sr; }

    inline void process (float x, float& outL, float& outR) noexcept
    {
        if (curDelay < 0.0f)
            curDelay = targetDelay;
        curDelay = targetDelay + slew * (curDelay - targetDelay);

        const float dl = left.read (curDelay);
        const float dr = right.read (curDelay);
        auto filt = [this] (float s, float& hp, float& lp)
        {
            lp = s + lpCoef * (lp - s);
            hp = lp + hpCoef * (hp - lp);
            return lp - hp;
        };
        const float fl = filt (dl, hpL, lpL);
        const float fr = filt (dr, hpR, lpR);
        left.push (x + 0.32f * fr);
        right.push (0.32f * fl);
        outL = dl;
        outR = dr;
    }

private:
    double sr = 44100.0;
    DelayLine left, right;
    float hpCoef = 0, lpCoef = 0, hpL = 0, hpR = 0, lpL = 0, lpR = 0;
    float targetDelay = 22050.0f, curDelay = -1.0f, slew = 0.999f;
};

//==============================================================================
/** Look-ahead brickwall limiter (stereo linked). The gain never exceeds what is needed. */
class Limiter
{
public:
    void prepare (double sampleRate)
    {
        sr = sampleRate;
        look = std::max (8, (int) std::lround (sr * 0.0015));
        dl.prepare (look + 2);
        dr.prepare (look + 2);
        req.assign ((size_t) look + 1, 1.0f);
        minQ.assign ((size_t) look + 2, 0);
        ma.assign ((size_t) look, 1.0f);
        release = timeCoef (80.0f, sr);
        reset();
    }

    void reset()
    {
        dl.reset();
        dr.reset();
        std::fill (req.begin(), req.end(), 1.0f);
        std::fill (ma.begin(), ma.end(), 1.0f);
        qHead = qTail = 0;
        t = 0;
        maPos = 0;
        maSum = (double) look;
        slow = 1.0f;
        lastGr = 0.0f;
    }

    int getLatency() const noexcept { return look; }
    void setCeiling (float db) noexcept { ceiling = dbToGain (db); }
    float getGainReductionDb() const noexcept { return lastGr; }

    inline void process (float& l, float& r) noexcept
    {
        const float peak = std::max (std::abs (l), std::abs (r));
        const float g = peak > ceiling ? ceiling / peak : 1.0f;

        // sliding minimum over the last look+1 required gains (monotonic queue)
        const int cap = look + 1;
        req[(size_t) (t % cap)] = g;
        while (qTail > qHead && req[(size_t) (minQ[(size_t) ((qTail - 1) % (cap + 1))] % cap)] >= g)
            --qTail;
        minQ[(size_t) (qTail % (cap + 1))] = t;
        ++qTail;
        while (minQ[(size_t) (qHead % (cap + 1))] <= t - cap)
            ++qHead;
        const float wmin = req[(size_t) (minQ[(size_t) (qHead % (cap + 1))] % cap)];
        ++t;

        // moving average of the window minimum (smooth attack, still never above required)
        maSum += wmin - ma[(size_t) maPos];
        ma[(size_t) maPos] = wmin;
        maPos = (maPos + 1) % look;
        const float avg = (float) (maSum / look);

        slow = std::min (avg, slow + (1.0f - slow) * (1.0f - release));

        dl.push (l);
        dr.push (r);
        l = std::clamp (dl.readInt (look) * slow, -ceiling, ceiling);
        r = std::clamp (dr.readInt (look) * slow, -ceiling, ceiling);
        lastGr = -gainToDb (slow);
    }

private:
    double sr = 44100.0;
    int look = 64;
    DelayLine dl, dr;
    std::vector<float> req, ma;
    std::vector<int64_t> minQ;
    int64_t qHead = 0, qTail = 0, t = 0;
    int maPos = 0;
    double maSum = 0;
    float slow = 1.0f, release = 0.999f, ceiling = 0.891f, lastGr = 0.0f;
};
} // namespace av

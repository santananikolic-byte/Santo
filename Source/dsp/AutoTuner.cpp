#include "AutoTuner.h"

namespace av
{
static int nextPow2 (int v)
{
    int p = 1;
    while (p < v)
        p <<= 1;
    return p;
}

void AutoTuner::prepare (double sampleRate)
{
    sr = sampleRate;
    constexpr double fmin = 75.0, fmax = 1000.0;
    hop = std::max (32, (int) std::lround (sr / 344.0));
    tmax = (int) std::ceil (sr / fmin);
    tmin = std::max (2, (int) std::floor (sr / fmax));
    win = tmax;
    frameLen = win + tmax + 2;
    nfft = nextPow2 (frameLen + win);
    unvoicedPeriod = std::max (16, (int) std::lround (sr * 0.004));
    latency = (int) std::ceil (frameLen * 0.5 + 4.0 * hop + 2.7 * tmax + 8.0);

    int order = 0;
    while ((1 << order) < nfft)
        ++order;
    fft = std::make_unique<juce::dsp::FFT> (order);
    fftA.assign ((size_t) nfft * 2, 0.0f);
    fftB.assign ((size_t) nfft * 2, 0.0f);
    frameBuf.assign ((size_t) frameLen, 0.0f);
    cumEnergy.assign ((size_t) frameLen + 1, 0.0);
    cmnd.assign ((size_t) tmax + 2, 1.0);

    const size_t ringSize = (size_t) 1 << kRingBits;
    in.assign (ringSize, 0.0f);
    det.assign (ringSize, 0.0f);
    lp.assign (ringSize, 0.0f);
    acc.assign (ringSize, 0.0f);
    wsum.assign (ringSize, 0.0f);
    frames.assign ((size_t) frameMask + 1, Frame {});
    marks.assign ((size_t) markMask + 1, Mark {});

    for (size_t i = 0; i < hann.size(); ++i)
    {
        const double x = (double) i / (double) (hann.size() - 1) * 2.0 - 1.0; // -1 … 1
        hann[i] = (float) (0.5 + 0.5 * std::cos (kPi * x));
    }

    dcR = (float) (1.0 - 2.0 * kPi * 20.0 / sr);
    lpf.lowPass (sr, 900.0, 0.7071);
    mixCoef = timeCoef (20.0f, sr);
    reset();
}

void AutoTuner::reset()
{
    std::fill (in.begin(), in.end(), 0.0f);
    std::fill (det.begin(), det.end(), 0.0f);
    std::fill (lp.begin(), lp.end(), 0.0f);
    std::fill (acc.begin(), acc.end(), 0.0f);
    std::fill (wsum.begin(), wsum.end(), 0.0f);
    std::fill (frames.begin(), frames.end(), Frame {});
    n = 0;
    dcX = dcY = 0;
    lpf.reset();
    framesComputed = framesFinal = 0;
    floorDb = topDb = -100;
    prevVoiced = false;
    noteSmooth = curNote = corrState = 0;
    markCount = markSearch = 0;
    nextMarkPos = synthPos = 0;
    prevMarkVoiced = false;
    mixState = settings.amount > 0.001f ? 1.0f : 0.0f;
    fifoWrite = fifoRead = 0;
}

bool AutoTuner::popFrame (FrameInfo& f) noexcept
{
    if (fifoRead == fifoWrite)
        return false;
    f = fifo[(size_t) fifoRead];
    fifoRead = (fifoRead + 1) & 255;
    return true;
}

float AutoTuner::processSample (float x) noexcept
{
    const size_t i = (size_t) (n & ringMask);
    in[i] = x;
    const float d = x - dcX + dcR * dcY;
    dcX = x;
    dcY = d;
    det[i] = d;
    lp[i] = lpf.process (x);
    ++n;

    if (n % hop == 0)
        analyseFrame();

    placeMarks();

    const int64_t outPos = n - 1 - latency;
    synthesise (outPos);

    if (outPos < 0)
        return 0.0f;

    const size_t oi = (size_t) (outPos & ringMask);
    const float dry = in[oi];
    const float w = wsum[oi];
    const float wet = w > 0.05f ? acc[oi] / w : dry;
    acc[oi] = 0.0f;
    wsum[oi] = 0.0f;

    const float target = settings.amount > 0.001f ? 1.0f : 0.0f;
    mixState = target + mixCoef * (mixState - target);
    return dry + mixState * (wet - dry);
}

//==============================================================================
void AutoTuner::analyseFrame() noexcept
{
    const int64_t k = framesComputed;
    const int64_t start = n - frameLen;

    double mean = 0.0;
    for (int j = 0; j < frameLen; ++j)
    {
        const float v = start + j >= 0 ? det[(size_t) ((start + j) & ringMask)] : 0.0f;
        frameBuf[(size_t) j] = v;
        mean += v;
    }
    mean /= frameLen;
    double energy = 0.0;
    cumEnergy[0] = 0.0;
    for (int j = 0; j < frameLen; ++j)
    {
        frameBuf[(size_t) j] -= (float) mean;
        const double e = (double) frameBuf[(size_t) j] * frameBuf[(size_t) j];
        energy += e;
        cumEnergy[(size_t) j + 1] = energy;
    }
    const float levelDb = powToDb ((float) (energy / frameLen));

    std::fill (fftA.begin(), fftA.end(), 0.0f);
    std::fill (fftB.begin(), fftB.end(), 0.0f);
    std::copy (frameBuf.begin(), frameBuf.end(), fftA.begin());
    std::copy (frameBuf.begin(), frameBuf.begin() + win, fftB.begin());
    fft->performRealOnlyForwardTransform (fftA.data(), true);
    fft->performRealOnlyForwardTransform (fftB.data(), true);
    for (int b = 0; b <= nfft / 2; ++b)
    {
        const float ar = fftA[(size_t) (2 * b)], ai = fftA[(size_t) (2 * b + 1)];
        const float br = fftB[(size_t) (2 * b)], bi = -fftB[(size_t) (2 * b + 1)]; // conj(B)
        fftA[(size_t) (2 * b)] = ar * br - ai * bi;
        fftA[(size_t) (2 * b + 1)] = ar * bi + ai * br;
    }
    fft->performRealOnlyInverseTransform (fftA.data());
    // fftA[tau] now holds sum_j x[j] * x[j + tau] for j < win

    const double e0 = cumEnergy[(size_t) win];
    double running = 0.0;
    cmnd[0] = 1.0;
    for (int tau = 1; tau <= tmax; ++tau)
    {
        const double et = cumEnergy[(size_t) (tau + win)] - cumEnergy[(size_t) tau];
        const double dval = std::max (0.0, e0 + et - 2.0 * (double) fftA[(size_t) tau]);
        running += dval;
        cmnd[(size_t) tau] = running > 1e-20 ? dval * tau / running : 1.0;
    }

    constexpr double threshold = 0.15;
    int best = -1;
    for (int tau = tmin; tau < tmax; ++tau)
    {
        if (cmnd[(size_t) tau] < threshold)
        {
            while (tau + 1 < tmax && cmnd[(size_t) tau + 1] < cmnd[(size_t) tau])
                ++tau;
            best = tau;
            break;
        }
    }
    if (best < 0)
    {
        best = tmin;
        for (int tau = tmin; tau < tmax; ++tau)
            if (cmnd[(size_t) tau] < cmnd[(size_t) best])
                best = tau;
    }
    double off = 0.0;
    if (best > 1 && best < tmax)
    {
        const double a = cmnd[(size_t) best - 1], b = cmnd[(size_t) best], c = cmnd[(size_t) best + 1];
        const double den = a - 2 * b + c;
        if (std::abs (den) > 1e-12)
            off = std::clamp (0.5 * (a - c) / den, -1.0, 1.0);
    }
    const float aper = (float) cmnd[(size_t) best];
    const float f0 = (float) (sr / (best + off));

    // adaptive level gate for voicing
    const float dt = (float) hop / (float) sr;
    if (floorDb < -99.0f)
        floorDb = levelDb;
    floorDb = levelDb < floorDb ? floorDb + 0.05f * (levelDb - floorDb) : floorDb + 1.0f * dt;
    topDb = levelDb > topDb ? levelDb : topDb - 0.5f * dt;
    const float lvlThr = std::max ({ std::min (floorDb + 10.0f, topDb - 25.0f), topDb - 50.0f, -65.0f });

    Frame& fr = frame (k);
    fr = Frame {};
    fr.f0Raw = f0;
    fr.midiRaw = 69.0f + 12.0f * std::log2 (f0 / 440.0f);
    fr.aper = aper;
    fr.levelDb = levelDb;
    fr.voicedRaw = aper < 0.25f && levelDb > lvlThr;
    framesComputed = k + 1;

    if (k >= 2)
        finaliseFrame (k - 2);
}

void AutoTuner::finaliseFrame (int64_t k) noexcept
{
    // 5-frame majority vote (voicing) and median (pitch) – removes octave jumps and blips
    float vals[5];
    int count = 0;
    int votes = 0;
    for (int64_t j = k - 2; j <= k + 2; ++j)
    {
        if (j < 0)
            continue;
        const Frame& f = frame (j);
        if (f.voicedRaw)
        {
            ++votes;
            vals[count++] = f.midiRaw;
        }
    }
    Frame& fr = frame (k);
    fr.voiced = votes >= 3;
    if (fr.voiced)
    {
        for (int x = 1; x < count; ++x) // insertion sort (max. 5 values)
            for (int y = x; y > 0 && vals[y - 1] > vals[y]; --y)
                std::swap (vals[y - 1], vals[y]);
        fr.midi = count % 2 ? vals[count / 2] : 0.5f * (vals[count / 2 - 1] + vals[count / 2]);
        fr.f0 = 440.0f * std::pow (2.0f, (fr.midi - 69.0f) / 12.0f);
    }

    const double dt = (double) hop / sr;
    if (fr.voiced && settings.learn)
        keys.addFrame (fr.midi, dbToGain (fr.levelDb), dt);
    mask = keys.allowedMask (settings.keyMode, settings.scaleMode, tonic, minor);

    if (fr.voiced)
    {
        if (lowPitch <= 0.0f)
            lowPitch = fr.f0;
        lowPitch += (fr.f0 < lowPitch ? 0.02f : 0.0005f) * (fr.f0 - lowPitch);

        const float amount = std::clamp (settings.amount, 0.0f, 1.0f);
        if (! prevVoiced)
        {
            noteSmooth = fr.midi;
            curNote = nearestNote (fr.midi);
            corrState = std::clamp ((curNote - fr.midi) * amount, -1.5f, 1.5f);
        }
        noteSmooth += (float) (1.0 - std::exp (-dt / 0.03)) * (fr.midi - noteSmooth);
        const float cand = nearestNote (noteSmooth);
        if (std::abs (cand - curNote) > 0.5f && std::abs (noteSmooth - cand) + 0.2f < std::abs (noteSmooth - curNote))
            curNote = cand;
        if ((mask >> (((int) curNote % 12 + 12) % 12) & 1) == 0) // scale changed
            curNote = cand;
        const float raw = std::clamp ((curNote - fr.midi) * amount, -1.5f, 1.5f);
        const float a = settings.retuneMs <= 0.0f ? 1.0f : (float) (1.0 - std::exp (-dt / (settings.retuneMs * 0.001)));
        corrState += a * (raw - corrState);
        fr.corr = corrState;
        fr.note = curNote;
    }
    else
    {
        corrState = 0.0f;
        fr.corr = 0.0f;
    }
    prevVoiced = fr.voiced;
    framesFinal = k + 1;

    FrameInfo info;
    info.voiced = fr.voiced;
    info.inMidi = fr.midi;
    info.outMidi = fr.midi + fr.corr;
    info.targetMidi = fr.note;
    info.levelDb = fr.levelDb;
    const int next = (fifoWrite + 1) & 255;
    if (next != fifoRead)
    {
        fifo[(size_t) fifoWrite] = info;
        fifoWrite = next;
    }
}

float AutoTuner::nearestNote (float midi) const noexcept
{
    const int base = (int) std::lround (midi);
    float best = (float) base;
    float bestDist = 1e9f;
    for (int d = -6; d <= 6; ++d)
    {
        const int note = base + d;
        if ((mask >> ((note % 12 + 12) % 12)) & 1)
        {
            const float dist = std::abs (midi - (float) note);
            if (dist < bestDist)
            {
                bestDist = dist;
                best = (float) note;
            }
        }
    }
    return best;
}

float AutoTuner::pitchAt (int64_t t, bool& voiced, float* corr) const noexcept
{
    voiced = false;
    if (corr != nullptr)
        *corr = 0.0f;
    if (framesFinal < 2)
        return 0.0f;

    const double kf = ((double) t - frameCenter (0)) / hop;
    int64_t k0 = (int64_t) std::floor (kf);
    double frac = kf - (double) k0;
    const int64_t lo = std::max<int64_t> (0, framesFinal - frameMask + 2);
    if (k0 < lo)                { k0 = lo; frac = 0.0; }
    if (k0 > framesFinal - 2)   { k0 = framesFinal - 2; frac = 1.0; }

    const Frame& a = frame (k0);
    const Frame& b = frame (k0 + 1);
    voiced = frac < 0.5 ? a.voiced : b.voiced;
    if (corr != nullptr)
        *corr = (float) (a.corr + frac * (b.corr - a.corr));
    if (a.voiced && b.voiced)
        return (float) (a.f0 + frac * (b.f0 - a.f0));
    return a.voiced ? a.f0 : b.f0;
}

//==============================================================================
void AutoTuner::placeMarks() noexcept
{
    if (framesFinal < 2)
        return;
    const double known = frameCenter (framesFinal - 1);

    while (nextMarkPos + 0.15 * tmax + 1.0 <= known)
    {
        int64_t ti = (int64_t) nextMarkPos;
        bool voiced = false;
        const float f0 = pitchAt (ti, voiced, nullptr);
        const double T = voiced && f0 > 0 ? sr / f0 : (double) unvoicedPeriod;
        const int64_t prevPos = markCount > 0 ? marks[(size_t) ((markCount - 1) & markMask)].pos : -1;

        if (voiced)
        {
            int64_t lo, hi;
            if (! prevMarkVoiced)
            {
                lo = ti;
                hi = ti + (int64_t) T;
            }
            else
            {
                const int64_t r = std::max<int64_t> (1, (int64_t) (0.12 * T));
                lo = ti - r;
                hi = ti + r;
            }
            lo = std::max (lo, prevPos + 1);
            hi = std::min (hi, n - 1);
            float bestV = -1e30f;
            for (int64_t j = lo; j <= hi; ++j)
            {
                const float v = lp[(size_t) (j & ringMask)];
                if (v > bestV)
                {
                    bestV = v;
                    ti = j;
                }
            }
        }

        Mark& m = marks[(size_t) (markCount & markMask)];
        m.pos = ti;
        m.period = (float) T;
        m.voiced = voiced;
        ++markCount;
        prevMarkVoiced = voiced;
        nextMarkPos = (double) ti + T;
    }
}

void AutoTuner::synthesise (int64_t outPos) noexcept
{
    const double limit = (double) outPos + tmax + 2.0;
    const float hannScale = (float) (hann.size() - 1) * 0.5f;

    while (synthPos <= limit)
    {
        const int64_t si = (int64_t) std::llround (synthPos);
        bool voiced = false;
        float corr = 0.0f;
        const float f0 = pitchAt (si, voiced, &corr);

        int64_t ta = si;
        int T = unvoicedPeriod;
        double step = unvoicedPeriod;

        if (voiced && f0 > 0.0f)
        {
            const double tSyn = sr / f0;
            T = (int) std::lround (tSyn);
            step = tSyn / std::pow (2.0, corr / 12.0);

            // nearest analysis mark
            const int64_t oldest = std::max<int64_t> (0, markCount - markMask);
            markSearch = std::max (markSearch, oldest);
            while (markSearch + 1 < markCount && marks[(size_t) ((markSearch + 1) & markMask)].pos <= si)
                ++markSearch;
            if (markSearch < markCount)
            {
                int64_t best = markSearch;
                if (markSearch + 1 < markCount)
                {
                    const int64_t d0 = std::abs (marks[(size_t) (markSearch & markMask)].pos - si);
                    const int64_t d1 = std::abs (marks[(size_t) ((markSearch + 1) & markMask)].pos - si);
                    if (d1 < d0)
                        best = markSearch + 1;
                }
                const Mark& m = marks[(size_t) (best & markMask)];
                if (m.voiced && std::abs (m.pos - si) <= (int64_t) m.period)
                {
                    ta = m.pos;
                    T = std::max (2, (int) std::lround (m.period));
                }
            }
        }

        T = std::min (T, tmax + 1);
        const float inv = 1.0f / (float) T;
        for (int j = -T; j <= T; ++j)
        {
            const int64_t dpos = si + j;
            if (dpos < 0 || dpos < outPos) // already played out
                continue;
            const float w = hann[(size_t) ((j * inv + 1.0f) * hannScale + 0.5f)];
            const int64_t src = ta + j;
            const float s = src >= 0 ? in[(size_t) (src & ringMask)] : 0.0f;
            const size_t dst = (size_t) (dpos & ringMask);
            acc[dst] += s * w;
            wsum[dst] += w;
        }
        synthPos += std::max (step, 1.0);
    }
}
} // namespace av

#include "VocalChain.h"

namespace av
{
namespace
{
constexpr float kBandFreq[VocalChain::kBands] = { 150.0f, 300.0f, 600.0f, 1200.0f, 2400.0f, 4000.0f, 7000.0f, 11000.0f };
constexpr float kBandEval[VocalChain::kBands] = { 120.0f, 300.0f, 600.0f, 1200.0f, 2400.0f, 4000.0f, 7000.0f, 12000.0f };
constexpr float kBandMin[VocalChain::kBands] = { -8, -6, -6, -6, -6, -6, -6, -4 };
constexpr float kBandMax[VocalChain::kBands] = { 1, 5, 5, 5, 5, 5, 5, 4 };
constexpr float kPresence[3] = { 1.0f, 1.5f, 2.0f };
constexpr float kAir[3] = { 1.5f, 2.5f, 3.0f };
constexpr float kAutoGainTargetDb = -16.0f;
} // namespace

float VocalChain::bandFrequency (int b) noexcept { return kBandFreq[b]; }

void VocalChain::prepare (double sampleRate)
{
    sr = sampleRate;
    blockLen = std::max (1, (int) std::lround (sr * 0.01));

    fftSize = sr > 100000 ? 8192 : (sr > 50000 ? 4096 : 2048);
    int order = 0;
    while ((1 << order) < fftSize)
        ++order;
    fft = std::make_unique<juce::dsp::FFT> (order);
    fftIn.assign ((size_t) fftSize, 0.0f);
    fftWork.assign ((size_t) fftSize * 2, 0.0f);
    window.resize ((size_t) fftSize);
    for (int i = 0; i < fftSize; ++i)
        window[(size_t) i] = (float) (0.5 - 0.5 * std::cos (2.0 * kPi * i / (fftSize - 1)));

    // assign FFT bins to the EQ bands (nearest band centre on a log scale)
    binBand.assign ((size_t) fftSize / 2 + 1, -1);
    for (int i = 1; i <= fftSize / 2; ++i)
    {
        const double f = (double) i * sr / fftSize;
        if (f < 80.0 || f > std::min (16000.0, 0.45 * sr))
            continue;
        int best = 0;
        double bestD = 1e9;
        for (int b = 0; b < kBands; ++b)
        {
            const double d = std::abs (std::log2 (f / kBandFreq[b]));
            if (d < bestD) { bestD = d; best = b; }
        }
        binBand[(size_t) i] = best;
    }

    gateEnvCoef = timeCoef (10.0f, sr);
    gateAtt = timeCoef (1.0f, sr);
    gateRel = timeCoef (120.0f, sr);
    gateHoldSamples = (int) (sr * 0.06);
    sibEnvCoef = timeCoef (5.0f, sr);
    sibAtt = timeCoef (0.5f, sr);
    sibRel = timeCoef (40.0f, sr);
    c1EnvCoef = timeCoef (20.0f, sr);
    c1Att = timeCoef (10.0f, sr);
    c1Rel = timeCoef (150.0f, sr);
    c2EnvCoef = timeCoef (3.0f, sr);
    c2Att = timeCoef (1.0f, sr);
    c2Rel = timeCoef (60.0f, sr);
    peakRel = timeCoef (1000.0f, sr);
    gainCoef = timeCoef (300.0f, sr);
    actCoef = 0.0f;

    const double xo = std::min (5000.0, 0.4 * sr);
    lp1.lowPass (sr, xo, 0.7071);
    lp2.lowPass (sr, xo, 0.7071);
    hpA.highPass (sr, xo, 0.7071);
    hpB.highPass (sr, xo, 0.7071);

    rawHist.setDecay (std::exp (-0.01 / 20.0));
    preHist.setDecay (std::exp (-0.01 / 12.0));
    outHist.setDecay (std::exp (-0.01 / 12.0));

    computeTargetBands();
    reset();
}

void VocalChain::reset()
{
    hp1.reset(); hp2.reset();
    for (auto& b : eq) b.reset();
    lp1.reset(); lp2.reset(); hpA.reset(); hpB.reset();
    gateEnv = gateGr = gateHeld = 0;
    gateHold = 0;
    sibEnv = sibGr = 0;
    c1Env = c1Gr = c2Env = c2Gr = 0;
    peakEnv = 0.1f;
    gainLin = dbToGain (learned.autoGainDb);
    fftFill = 0;
    blockPos = 0;
    blockIn = blockPre = blockOut = blockAhead = 0;
    shortOut = -100.0f;
    activity = 0.0f;
    blocksSinceUpdate = 0;
    if (! learned.valid)
    {
        rawHist.reset(); preHist.reset(); outHist.reset();
        bandPower.fill (0.0);
        spectrumSeconds = 0.0;
    }
    appliedLowCut = learned.lowCutHz;
    hp1.highPass (sr, appliedLowCut, 0.5412);
    hp2.highPass (sr, appliedLowCut, 1.3066);
    for (int b = 0; b < kBands; ++b)
        applied[(size_t) b] = learned.eqGains[(size_t) b] * settings.autoEq;
    designEq (eq, applied);
}

void VocalChain::setSettings (const Settings& s) noexcept
{
    const bool styleChanged = s.style != settings.style;
    settings = s;
    if (styleChanged)
        computeTargetBands();
}

void VocalChain::setLearned (const Learned& l) noexcept
{
    learned = l;
    learned.valid = true;
    for (int b = 0; b < kBands; ++b)
        applied[(size_t) b] = learned.eqGains[(size_t) b] * settings.autoEq;
    designEq (eq, applied);
    gainLin = dbToGain (learned.autoGainDb);
}

void VocalChain::clearLearned() noexcept
{
    learned = Learned {};
    rawHist.reset(); preHist.reset(); outHist.reset();
    bandPower.fill (0.0);
    spectrumSeconds = 0.0;
    applied.fill (0.0f);
    designEq (eq, applied);
    gainLin = 1.0f;
}

//==============================================================================
float VocalChain::targetPsdDb (float f) const noexcept
{
    const int st = std::clamp (settings.style, 0, 2);
    const double lf = std::log2 (std::max (f, 1.0f));
    double t = 0.0;
    if (f > 450.0f) t -= 6.0 * (lf - std::log2 (450.0));
    if (f < 140.0f) t -= 6.0 * (std::log2 (140.0) - lf);
    t += kPresence[st] * std::exp (-0.5 * std::pow ((lf - std::log2 (3500.0)) / 0.6, 2.0));
    t += kAir[st] / (1.0 + std::exp (-(lf - std::log2 (10000.0)) * 4.0));
    return (float) t;
}

void VocalChain::computeTargetBands() noexcept
{
    std::array<double, kBands> sum {};
    std::array<int, kBands> cnt {};
    for (size_t i = 1; i < binBand.size(); ++i)
    {
        const int b = binBand[i];
        if (b < 0)
            continue;
        sum[(size_t) b] += std::pow (10.0, targetPsdDb ((float) (i * sr / fftSize)) / 10.0);
        ++cnt[(size_t) b];
    }
    for (int b = 0; b < kBands; ++b)
        targetBand[(size_t) b] = cnt[(size_t) b] > 0 ? (float) (10.0 * std::log10 (sum[(size_t) b] / cnt[(size_t) b])) : 0.0f;
}

void VocalChain::designBank (double rate, const std::array<float, kBands>& g, std::array<Biquad, kBands>& bank) noexcept
{
    for (int b = 0; b < kBands; ++b)
    {
        const double f = std::min ((double) kBandFreq[b], 0.45 * rate);
        if (b == 0)
            bank[(size_t) b].lowShelf (rate, f, 0.7, g[(size_t) b]);
        else if (b == kBands - 1)
            bank[(size_t) b].highShelf (rate, f, 0.7, g[(size_t) b]);
        else
            bank[(size_t) b].peak (rate, f, 1.0, g[(size_t) b]);
    }
}

void VocalChain::designEq (std::array<Biquad, kBands>& bank, const std::array<float, kBands>& g) const noexcept
{
    designBank (sr, g, bank);
}

float VocalChain::eqResponseDb (float f) const noexcept
{
    double s = 0.0;
    for (auto& b : eq)
        s += b.magnitudeDb (sr, f);
    return (float) s;
}

void VocalChain::analyseSpectrum() noexcept
{
    double e = 0.0;
    for (auto v : fftIn)
        e += (double) v * v;
    const float frameDb = powToDb ((float) (e / fftSize));
    if (! settings.learn || frameDb < learned.activeDb - 20.0f || frameDb < -70.0f)
        return;

    std::fill (fftWork.begin(), fftWork.end(), 0.0f);
    for (int i = 0; i < fftSize; ++i)
        fftWork[(size_t) i] = fftIn[(size_t) i] * window[(size_t) i];
    fft->performFrequencyOnlyForwardTransform (fftWork.data(), true);

    std::array<double, kBands> p {};
    std::array<int, kBands> cnt {};
    for (size_t i = 1; i < binBand.size(); ++i)
    {
        const int b = binBand[i];
        if (b < 0)
            continue;
        p[(size_t) b] += (double) fftWork[i] * fftWork[i];
        ++cnt[(size_t) b];
    }
    const double frameSec = fftSize / sr;
    const double a = std::max (frameSec / 8.0, frameSec / (spectrumSeconds + frameSec));
    for (int b = 0; b < kBands; ++b)
        if (cnt[(size_t) b] > 0)
            bandPower[(size_t) b] += a * (p[(size_t) b] / cnt[(size_t) b] - bandPower[(size_t) b]);
    spectrumSeconds += frameSec;
}

void VocalChain::updateEqTargets() noexcept
{
    if (spectrumSeconds < 2.0)
        return;
    std::array<float, kBands> err {};
    for (int b = 0; b < kBands; ++b)
        err[(size_t) b] = targetBand[(size_t) b] - powToDb ((float) bandPower[(size_t) b]);
    float offset = 0.0f;
    for (int b = 1; b <= 5; ++b)
        offset += err[(size_t) b];
    offset /= 5.0f;
    for (int b = 0; b < kBands; ++b)
        desired[(size_t) b] = std::clamp (err[(size_t) b] - offset, kBandMin[b], kBandMax[b]);

    // compensate the overlap of neighbouring filters so the summed response hits the target
    std::array<float, kBands> g = desired;
    std::array<Biquad, kBands> bank;
    for (int it = 0; it < 6; ++it)
    {
        designEq (bank, g);
        for (int b = 0; b < kBands; ++b)
        {
            double r = 0.0;
            const double f = std::min ((double) kBandEval[b], 0.45 * sr);
            for (auto& q : bank)
                r += q.magnitudeDb (sr, f);
            g[(size_t) b] = std::clamp (g[(size_t) b] + 0.7f * (desired[(size_t) b] - (float) r), -9.0f, 7.0f);
        }
    }
    learned.eqGains = g;
}

void VocalChain::blockUpdate() noexcept
{
    blockPos = 0;
    const float aheadDb = powToDb ((float) (blockAhead / blockLen));
    const float preDb = powToDb ((float) (blockPre / blockLen));
    const float outDb = powToDb ((float) (blockOut / blockLen));
    blockAhead = blockPre = blockOut = 0;
    shortOut = shortOut < -99.0f ? outDb : 10.0f * std::log10 (0.9f * std::pow (10.0f, shortOut / 10.0f) + 0.1f * std::pow (10.0f, outDb / 10.0f));

    // vocal activity (used to duck the effects while singing)
    const float actTarget = std::clamp ((aheadDb - (learned.activeDb - 25.0f)) / 15.0f, 0.0f, 1.0f);
    activity += (actTarget > activity ? 0.6f : 0.04f) * (actTarget - activity);

    if (settings.learn)
    {
        if (aheadDb > -100.0f)
            rawHist.add (aheadDb);
        if (rawHist.weight() > 20.0)
        {
            learned.activeDb = rawHist.percentile (0.95, learned.activeDb);
            learned.floorDb = rawHist.percentile (0.10, learned.floorDb);
            if (! learned.valid) // until enough has been heard: moderate starting point
                learned.compThreshold = learned.activeDb - 8.0f;
        }
        if (preDb > learned.activeDb - 30.0f)
            preHist.add (preDb);
        if (shortOut > learned.activeDb - 40.0f && aheadDb > learned.activeDb - 30.0f)
            outHist.add (shortOut);

        if (++blocksSinceUpdate >= 25) // every 250 ms
        {
            blocksSinceUpdate = 0;
            if (! learned.valid && preHist.weight() > 50.0)
            {
                learned.compThreshold = preHist.percentile (0.5, learned.compThreshold);
                learned.valid = true;
            }
            if (learned.valid && outHist.weight() > 100.0)
            {
                const float spread = outHist.percentile (0.95, 0.0f) - outHist.percentile (0.10, 0.0f);
                const float target = 14.0f - 9.0f * settings.dynamics;
                const float err = spread - target;
                if (std::abs (err) > 0.5f)
                    learned.compThreshold = std::clamp (learned.compThreshold - 0.25f * err,
                                                        learned.activeDb - 35.0f, learned.activeDb - 2.0f);
                learned.autoGainDb = std::clamp (kAutoGainTargetDb - outHist.percentile (0.95, kAutoGainTargetDb), -12.0f, 30.0f);
            }
            if (lowestPitch > 0.0f)
                learned.lowCutHz = std::clamp (0.7f * lowestPitch, 60.0f, 140.0f);
            if (++eqCounter >= 2)
            {
                eqCounter = 0;
                updateEqTargets();
            }
        }
    }

    // follow the learned values smoothly
    bool changed = false;
    for (int b = 0; b < kBands; ++b)
    {
        const float target = learned.eqGains[(size_t) b] * settings.autoEq;
        const float d = target - applied[(size_t) b];
        if (std::abs (d) > 0.005f)
        {
            applied[(size_t) b] += 0.05f * d;
            changed = true;
        }
    }
    if (changed)
        designEq (eq, applied);

    if (std::abs (learned.lowCutHz - appliedLowCut) > 1.5f)
    {
        appliedLowCut += 0.2f * (learned.lowCutHz - appliedLowCut);
        hp1.highPass (sr, appliedLowCut, 0.5412);
        hp2.highPass (sr, appliedLowCut, 1.3066);
    }
}

//==============================================================================
float VocalChain::processSample (float x, float ahead) noexcept
{
    float y = hp2.process (hp1.process (x));

    // gate / expander (detector looks a few ms ahead on the raw signal)
    const float a2 = ahead * ahead;
    gateEnv = a2 + gateEnvCoef * (gateEnv - a2);
    {
        const float lvl = powToDb (gateEnv);
        const float span = learned.activeDb - learned.floorDb;
        float thr = learned.floorDb + std::max (6.0f, std::min (15.0f, 0.3f * span));
        thr = std::min (thr, learned.activeDb - 20.0f);
        const float range = span > 25.0f ? 12.0f : 6.0f;
        const float grT = std::clamp ((thr - lvl) * 1.5f, 0.0f, range);
        if (grT <= gateHeld) { gateHeld = grT; gateHold = gateHoldSamples; }
        else if (gateHold > 0) --gateHold;
        else gateHeld = grT;
        gateGr = gateHeld + (gateHeld < gateGr ? gateAtt : gateRel) * (gateGr - gateHeld);
        y *= dbToGain (-gateGr);
    }

    fftIn[(size_t) fftFill] = y;
    if (++fftFill >= fftSize)
    {
        fftFill = 0;
        analyseSpectrum();
    }

    for (auto& b : eq)
        y = b.process (y);

    // de-esser: compress only the band above 5 kHz while it is louder than the threshold
    {
        const float low = lp2.process (lp1.process (y));
        const float high = hpB.process (hpA.process (y));
        const float h2 = high * high;
        sibEnv = h2 + sibEnvCoef * (sibEnv - h2);
        const float thr = learned.activeDb - 2.0f - 6.0f * settings.deess;
        const float grT = std::clamp ((powToDb (sibEnv) - thr) * 0.75f, 0.0f, 12.0f * settings.deess);
        sibGr = grT + (grT > sibGr ? sibAtt : sibRel) * (sibGr - grT);
        y = low + high * dbToGain (-sibGr);
    }
    blockPre += (double) y * y;

    // leveling compressor (3:1, soft knee) + fast peak compressor (6:1)
    auto gainReduction = [] (float over, float ratio, float knee)
    {
        const float slope = 1.0f - 1.0f / ratio;
        if (over <= -knee * 0.5f) return 0.0f;
        if (over >= knee * 0.5f) return over * slope;
        const float t = over + knee * 0.5f;
        return slope * t * t / (2.0f * knee);
    };
    {
        const float y2 = y * y;
        c1Env = y2 + c1EnvCoef * (c1Env - y2);
        const float grT = gainReduction (powToDb (c1Env) - learned.compThreshold, 3.0f, 6.0f);
        c1Gr = grT + (grT > c1Gr ? c1Att : c1Rel) * (c1Gr - grT);
        y *= dbToGain (-c1Gr);
    }
    {
        const float y2 = y * y;
        c2Env = y2 + c2EnvCoef * (c2Env - y2);
        const float grT = gainReduction (powToDb (c2Env) - (learned.compThreshold + 8.0f), 6.0f, 4.0f);
        c2Gr = grT + (grT > c2Gr ? c2Att : c2Rel) * (c2Gr - grT);
        y *= dbToGain (-c2Gr);
    }

    // gentle saturation, drive follows the signal peak so it behaves the same at any level
    const float ay = std::abs (y);
    peakEnv = ay > peakEnv ? ay : std::max (1.0e-4f, peakEnv * peakRel);
    const float mix = 0.5f * settings.warmth;
    if (mix > 0.0f)
    {
        const float d = 1.8f / peakEnv;
        y = (1.0f - mix) * y + mix * std::tanh (d * y) / d;
    }
    blockOut += (double) y * y;

    const float g = dbToGain (learned.autoGainDb);
    gainLin = g + gainCoef * (gainLin - g);
    y *= gainLin;

    blockAhead += (double) a2;
    if (++blockPos >= blockLen)
        blockUpdate();

    meters.gateGr = gateGr;
    meters.deessGr = sibGr;
    meters.compGr = c1Gr + c2Gr;
    return y;
}
} // namespace av

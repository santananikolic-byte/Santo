// Offline test: runs the real plugin engine over a WAV file, exactly as a DAW would
// (block by block), and writes the result.
//
//   AutoVocalRender in.wav out.wav [natural|modern|hard] [passes]
//
// With passes = 2 the file is played once to learn (key, EQ, compression) and then
// rendered a second time with the learned settings – like playing a song in the DAW
// and bouncing it afterwards.

#include <juce_audio_formats/juce_audio_formats.h>
#include "dsp/VocalEngine.h"

#include <iostream>

static const char* noteNames[] = { "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B" };

int main (int argc, char** argv)
{
    if (argc < 3)
    {
        std::cerr << "usage: AutoVocalRender in.wav out.wav [natural|modern|hard] [passes] [dry|null]\n";
        return 1;
    }
    const juce::File inFile (juce::File::getCurrentWorkingDirectory().getChildFile (argv[1]));
    const juce::File outFile (juce::File::getCurrentWorkingDirectory().getChildFile (argv[2]));
    const juce::String styleName = argc > 3 ? argv[3] : "modern";
    const int passes = argc > 4 ? juce::jmax (1, juce::String (argv[4]).getIntValue()) : 1;

    juce::AudioFormatManager fm;
    fm.registerBasicFormats();
    std::unique_ptr<juce::AudioFormatReader> reader (fm.createReaderFor (inFile));
    if (reader == nullptr)
    {
        std::cerr << "cannot read " << inFile.getFullPathName() << "\n";
        return 1;
    }
    const int len = (int) reader->lengthInSamples;
    const double sr = reader->sampleRate;
    juce::AudioBuffer<float> input ((int) reader->numChannels, len);
    reader->read (&input, 0, len, 0, true, true);

    std::vector<float> mono ((size_t) len, 0.0f);
    for (int c = 0; c < input.getNumChannels(); ++c)
        for (int i = 0; i < len; ++i)
            mono[(size_t) i] += input.getSample (c, i) / (float) input.getNumChannels();

    av::EngineParams p;
    if (styleName == "natural")   { p.style = 0; p.retuneMs = 70.0f;  p.warmth = 0.1f; p.dynamics = 0.45f; p.delay = 0.0f;  p.reverb = 0.36f; }
    else if (styleName == "hard") { p.style = 2; p.retuneMs = 0.0f;   p.warmth = 0.4f; p.dynamics = 0.83f; p.delay = 0.15f; p.reverb = 0.25f; }
    else                          { p.style = 1; p.retuneMs = 20.0f;  p.warmth = 0.3f; p.dynamics = 0.72f; p.delay = 0.12f; p.reverb = 0.28f; }

    const juce::String mode = argc > 5 ? argv[5] : "";
    if (mode == "dry" || mode == "null")
    {
        p.autoMix = false;
        p.reverb = p.delay = 0.0f;
        p.outputDb = -6.0f; // keep the limiter out of the measurement
    }
    if (mode == "null")
        p.tune = 0.0f;

    av::VocalEngine engine;
    constexpr int block = 512;
    engine.prepare (sr, block);
    engine.setParams (p);
    const int latency = engine.getLatency();
    const int tail = (int) (sr * 2.0);
    const int total = len + latency + tail;

    juce::AudioBuffer<float> out (2, total);
    std::vector<float> inBlock (block);
    const auto startTime = juce::Time::getMillisecondCounterHiRes();

    for (int pass = 0; pass < passes; ++pass)
    {
        if (pass > 0)
        {
            const auto learned = engine.getLearnedState();
            engine.reset();
            engine.setLearnedState (learned);
        }
        out.clear();
        for (int pos = 0; pos < total; pos += block)
        {
            const int n = std::min (block, total - pos);
            for (int i = 0; i < n; ++i)
                inBlock[(size_t) i] = pos + i < len ? mono[(size_t) (pos + i)] : 0.0f;
            engine.process (inBlock.data(), out.getWritePointer (0, pos), out.getWritePointer (1, pos), n);
        }
    }
    const double secs = (juce::Time::getMillisecondCounterHiRes() - startTime) / 1000.0;

    // remove the plugin latency so the output lines up with the input
    juce::AudioBuffer<float> aligned (2, len + tail);
    for (int c = 0; c < 2; ++c)
        aligned.copyFrom (c, 0, out, c, latency, len + tail);

    outFile.deleteFile();
    juce::WavAudioFormat wav;
    std::unique_ptr<juce::OutputStream> os (outFile.createOutputStream());
    std::unique_ptr<juce::AudioFormatWriter> writer (wav.createWriterFor (os.get(), sr, 2, 24, {}, 0));
    if (writer == nullptr)
        return 1;
    os.release();
    writer->writeFromAudioSampleBuffer (aligned, 0, aligned.getNumSamples());
    writer.reset();

    const auto st = engine.getLearnedState();
    std::cout << "latency " << latency << " samples (" << juce::String (latency * 1000.0 / sr, 1) << " ms)\n";
    std::cout << "realtime factor " << juce::String ((len / sr * passes) / secs, 1) << "x\n";
    std::cout << "key " << (engine.keyTonic.load() >= 0 ? noteNames[engine.keyTonic.load()] : "?")
              << (engine.keyMinor.load() ? " minor" : " major")
              << "  confidence " << juce::String (engine.keyConfidence.load(), 2) << "\n";
    std::cout << "comp threshold " << st.chain.compThreshold << " dB, auto gain " << st.chain.autoGainDb
              << " dB, active " << st.chain.activeDb << " dB, floor " << st.chain.floorDb
              << " dB, low cut " << st.chain.lowCutHz << " Hz\n";
    std::cout << "eq:";
    for (int b = 0; b < av::VocalChain::kBands; ++b)
        std::cout << " " << (int) av::VocalChain::bandFrequency (b) << "Hz " << juce::String (st.chain.eqGains[(size_t) b], 1);
    std::cout << "\nlimiter gr " << engine.limGr.load() << " dB\n";
    return 0;
}

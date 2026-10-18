#pragma once

#include <juce_audio_processors/juce_audio_processors.h>
#include "dsp/VocalEngine.h"

namespace ParamIDs
{
inline constexpr const char* style    = "style";
inline constexpr const char* tune     = "tune";
inline constexpr const char* speed    = "speed";
inline constexpr const char* key      = "key";
inline constexpr const char* scale    = "scale";
inline constexpr const char* autoMix  = "automix";
inline constexpr const char* learn    = "learn";
inline constexpr const char* warmth   = "warmth";
inline constexpr const char* deess    = "deess";
inline constexpr const char* dynamics = "dynamics";
inline constexpr const char* autoEq   = "autoeq";
inline constexpr const char* delay    = "delay";
inline constexpr const char* reverb   = "reverb";
inline constexpr const char* output   = "output";
} // namespace ParamIDs

struct StylePreset
{
    float speedMs, warmth, dynamics, delay, reverb;
};

class AutoVocalProcessor : public juce::AudioProcessor
{
public:
    AutoVocalProcessor();
    ~AutoVocalProcessor() override = default;

    void prepareToPlay (double sampleRate, int samplesPerBlock) override;
    void releaseResources() override {}
    bool isBusesLayoutSupported (const BusesLayout& layouts) const override;
    void processBlock (juce::AudioBuffer<float>&, juce::MidiBuffer&) override;
    using AudioProcessor::processBlock;

    juce::AudioProcessorEditor* createEditor() override;
    bool hasEditor() const override { return true; }

    const juce::String getName() const override { return JucePlugin_Name; }
    bool acceptsMidi() const override { return false; }
    bool producesMidi() const override { return false; }
    bool isMidiEffect() const override { return false; }
    double getTailLengthSeconds() const override { return 3.0; }

    int getNumPrograms() override { return 1; }
    int getCurrentProgram() override { return 0; }
    void setCurrentProgram (int) override {}
    const juce::String getProgramName (int) override { return "Default"; }
    void changeProgramName (int, const juce::String&) override {}

    void getStateInformation (juce::MemoryBlock& destData) override;
    void setStateInformation (const void* data, int sizeInBytes) override;

    /** Sets the style and loads its matching knob settings (called from the editor). */
    void applyStyle (int styleIndex);

    static const StylePreset& presetFor (int styleIndex);

    juce::AudioProcessorValueTreeState apvts;
    av::VocalEngine engine;
    std::atomic<double> currentBpm { 120.0 };

private:
    static juce::AudioProcessorValueTreeState::ParameterLayout createLayout();
    float getValue (const char* id) const { return apvts.getRawParameterValue (id)->load(); }

    juce::HeapBlock<float> monoBuffer;
    int monoSize = 0;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (AutoVocalProcessor)
};

#include "PluginProcessor.h"
#include "PluginEditor.h"

namespace
{
const StylePreset kPresets[3] = {
    { 70.0f, 10.0f, 45.0f, 0.0f, 36.0f },  // Natürlich
    { 20.0f, 30.0f, 72.0f, 12.0f, 28.0f }, // Modern
    { 0.0f, 40.0f, 83.0f, 15.0f, 25.0f },  // Hart
};

juce::String percentText (float v, int) { return juce::String (juce::roundToInt (v)) + " %"; }
} // namespace

const StylePreset& AutoVocalProcessor::presetFor (int styleIndex)
{
    return kPresets[juce::jlimit (0, 2, styleIndex)];
}

juce::AudioProcessorValueTreeState::ParameterLayout AutoVocalProcessor::createLayout()
{
    using namespace juce;
    AudioProcessorValueTreeState::ParameterLayout layout;

    auto pct = [] (const char* id, const char* name, float def)
    {
        return std::make_unique<AudioParameterFloat> (ParameterID { id, 1 }, String::fromUTF8 (name), NormalisableRange<float> (0.0f, 100.0f, 0.1f), def,
                                                      AudioParameterFloatAttributes().withLabel ("%").withStringFromValueFunction (percentText));
    };

    layout.add (std::make_unique<AudioParameterChoice> (ParameterID { ParamIDs::style, 1 }, "Stil",
                                                        StringArray { String::fromUTF8 ("Natürlich"), "Modern", "Hart" }, 1));
    layout.add (pct (ParamIDs::tune, "Tune", 100.0f));

    NormalisableRange<float> speedRange (0.0f, 200.0f, 0.1f);
    speedRange.setSkewForCentre (30.0f);
    layout.add (std::make_unique<AudioParameterFloat> (ParameterID { ParamIDs::speed, 1 }, "Speed", speedRange, 20.0f,
                                                       AudioParameterFloatAttributes().withLabel ("ms").withStringFromValueFunction (
                                                           [] (float v, int) { return v < 0.5f ? String ("Robot") : String (roundToInt (v)) + " ms"; })));

    layout.add (std::make_unique<AudioParameterChoice> (ParameterID { ParamIDs::key, 1 }, "Tonart",
                                                        StringArray { "Auto", "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "H" }, 0));
    layout.add (std::make_unique<AudioParameterChoice> (ParameterID { ParamIDs::scale, 1 }, "Skala",
                                                        StringArray { "Auto", "Dur", "Moll", "Chromatisch" }, 0));
    layout.add (std::make_unique<AudioParameterBool> (ParameterID { ParamIDs::autoMix, 1 }, "Auto-Mix", true));
    layout.add (std::make_unique<AudioParameterBool> (ParameterID { ParamIDs::learn, 1 }, "Lernen", true));
    layout.add (pct (ParamIDs::warmth, "Wärme", 30.0f));
    layout.add (pct (ParamIDs::deess, "De-Esser", 50.0f));
    layout.add (pct (ParamIDs::dynamics, "Dynamik", 72.0f));
    layout.add (pct (ParamIDs::autoEq, "Auto-EQ", 70.0f));
    layout.add (pct (ParamIDs::delay, "Delay", 12.0f));
    layout.add (pct (ParamIDs::reverb, "Hall", 28.0f));
    layout.add (std::make_unique<AudioParameterFloat> (ParameterID { ParamIDs::output, 1 }, "Output",
                                                       NormalisableRange<float> (-24.0f, 12.0f, 0.1f), 0.0f,
                                                       AudioParameterFloatAttributes().withLabel ("dB").withStringFromValueFunction (
                                                           [] (float v, int) { return (v > 0 ? "+" : "") + String (v, 1) + " dB"; })));
    return layout;
}

AutoVocalProcessor::AutoVocalProcessor()
    : AudioProcessor (BusesProperties()
                          .withInput ("Input", juce::AudioChannelSet::mono(), true)
                          .withOutput ("Output", juce::AudioChannelSet::stereo(), true)),
      apvts (*this, nullptr, "AutoVocal", createLayout())
{
}

bool AutoVocalProcessor::isBusesLayoutSupported (const BusesLayout& layouts) const
{
    const auto in = layouts.getMainInputChannelSet();
    const auto out = layouts.getMainOutputChannelSet();
    const bool inOk = in == juce::AudioChannelSet::mono() || in == juce::AudioChannelSet::stereo();
    const bool outOk = out == juce::AudioChannelSet::mono() || out == juce::AudioChannelSet::stereo();
    return inOk && outOk;
}

void AutoVocalProcessor::prepareToPlay (double sampleRate, int samplesPerBlock)
{
    engine.prepare (sampleRate, samplesPerBlock);
    setLatencySamples (engine.getLatency());
    monoSize = juce::jmax (samplesPerBlock, 32);
    monoBuffer.allocate ((size_t) monoSize * 3, true);
}

void AutoVocalProcessor::processBlock (juce::AudioBuffer<float>& buffer, juce::MidiBuffer&)
{
    juce::ScopedNoDenormals noDenormals;
    const int numSamples = buffer.getNumSamples();
    const int numIn = getTotalNumInputChannels();
    const int numOut = getTotalNumOutputChannels();

    if (numSamples > monoSize)
    {
        // hosts may exceed the announced block size – grow (rare, outside steady state)
        monoSize = numSamples;
        monoBuffer.allocate ((size_t) monoSize * 3, true);
    }

    if (auto* ph = getPlayHead())
        if (auto pos = ph->getPosition())
            if (auto bpm = pos->getBpm())
                currentBpm.store (*bpm);

    av::EngineParams p;
    p.style = (int) getValue (ParamIDs::style);
    p.tune = getValue (ParamIDs::tune) * 0.01f;
    p.retuneMs = getValue (ParamIDs::speed);
    p.keyMode = (int) getValue (ParamIDs::key) - 1;
    p.scaleMode = (int) getValue (ParamIDs::scale);
    p.autoMix = getValue (ParamIDs::autoMix) > 0.5f;
    p.learn = getValue (ParamIDs::learn) > 0.5f;
    p.warmth = getValue (ParamIDs::warmth) * 0.01f;
    p.deess = getValue (ParamIDs::deess) * 0.01f;
    p.dynamics = getValue (ParamIDs::dynamics) * 0.01f;
    p.autoEq = getValue (ParamIDs::autoEq) * 0.01f;
    p.delay = getValue (ParamIDs::delay) * 0.01f;
    p.reverb = getValue (ParamIDs::reverb) * 0.01f;
    p.outputDb = getValue (ParamIDs::output);
    p.bpm = currentBpm.load();
    engine.setParams (p);

    float* mono = monoBuffer.get();
    float* outL = mono + monoSize;
    float* outR = outL + monoSize;
    juce::FloatVectorOperations::clear (mono, numSamples);
    for (int c = 0; c < numIn; ++c)
        juce::FloatVectorOperations::addWithMultiply (mono, buffer.getReadPointer (c), 1.0f / (float) numIn, numSamples);

    engine.process (mono, outL, outR, numSamples);

    if (numOut >= 2)
    {
        buffer.copyFrom (0, 0, outL, numSamples);
        buffer.copyFrom (1, 0, outR, numSamples);
        for (int c = 2; c < numOut; ++c)
            buffer.clear (c, 0, numSamples);
    }
    else if (numOut == 1)
    {
        buffer.copyFrom (0, 0, outL, numSamples, 0.5f);
        buffer.addFrom (0, 0, outR, numSamples, 0.5f);
    }
}

void AutoVocalProcessor::applyStyle (int styleIndex)
{
    const auto& pr = presetFor (styleIndex);
    auto set = [this] (const char* id, float value)
    {
        if (auto* param = apvts.getParameter (id))
        {
            param->beginChangeGesture();
            param->setValueNotifyingHost (param->convertTo0to1 (value));
            param->endChangeGesture();
        }
    };
    set (ParamIDs::style, (float) styleIndex);
    set (ParamIDs::speed, pr.speedMs);
    set (ParamIDs::warmth, pr.warmth);
    set (ParamIDs::dynamics, pr.dynamics);
    set (ParamIDs::delay, pr.delay);
    set (ParamIDs::reverb, pr.reverb);
}

//==============================================================================
void AutoVocalProcessor::getStateInformation (juce::MemoryBlock& destData)
{
    auto state = apvts.copyState();
    std::unique_ptr<juce::XmlElement> xml (state.createXml());

    const auto learned = engine.getLearnedState();
    auto* l = xml->createNewChildElement ("Learned");
    juce::StringArray hist;
    for (auto h : learned.key.hist)
        hist.add (juce::String (h, 6));
    l->setAttribute ("hist", hist.joinIntoString (","));
    l->setAttribute ("voicedSeconds", learned.key.voicedSeconds);
    l->setAttribute ("tonic", learned.key.tonic);
    l->setAttribute ("minor", learned.key.minor);
    juce::StringArray eq;
    for (auto g : learned.chain.eqGains)
        eq.add (juce::String (g, 3));
    l->setAttribute ("eq", eq.joinIntoString (","));
    l->setAttribute ("compThreshold", learned.chain.compThreshold);
    l->setAttribute ("autoGain", learned.chain.autoGainDb);
    l->setAttribute ("active", learned.chain.activeDb);
    l->setAttribute ("floor", learned.chain.floorDb);
    l->setAttribute ("lowCut", learned.chain.lowCutHz);
    l->setAttribute ("valid", learned.chain.valid);

    copyXmlToBinary (*xml, destData);
}

void AutoVocalProcessor::setStateInformation (const void* data, int sizeInBytes)
{
    std::unique_ptr<juce::XmlElement> xml (getXmlFromBinary (data, sizeInBytes));
    if (xml == nullptr)
        return;

    if (auto* l = xml->getChildByName ("Learned"))
    {
        av::LearnedState s;
        auto hist = juce::StringArray::fromTokens (l->getStringAttribute ("hist"), ",", "");
        for (int i = 0; i < 12 && i < hist.size(); ++i)
            s.key.hist[(size_t) i] = hist[i].getDoubleValue();
        s.key.voicedSeconds = l->getDoubleAttribute ("voicedSeconds");
        s.key.tonic = l->getIntAttribute ("tonic", -1);
        s.key.minor = l->getBoolAttribute ("minor");
        auto eq = juce::StringArray::fromTokens (l->getStringAttribute ("eq"), ",", "");
        for (int i = 0; i < av::VocalChain::kBands && i < eq.size(); ++i)
            s.chain.eqGains[(size_t) i] = eq[i].getFloatValue();
        s.chain.compThreshold = (float) l->getDoubleAttribute ("compThreshold", -30.0);
        s.chain.autoGainDb = (float) l->getDoubleAttribute ("autoGain", 0.0);
        s.chain.activeDb = (float) l->getDoubleAttribute ("active", -24.0);
        s.chain.floorDb = (float) l->getDoubleAttribute ("floor", -70.0);
        s.chain.lowCutHz = (float) l->getDoubleAttribute ("lowCut", 80.0);
        s.chain.valid = l->getBoolAttribute ("valid");
        engine.setLearnedState (s);
        xml->removeChildElement (l, true);
    }

    if (xml->hasTagName (apvts.state.getType()))
        apvts.replaceState (juce::ValueTree::fromXml (*xml));
}

juce::AudioProcessorEditor* AutoVocalProcessor::createEditor()
{
    return new AutoVocalEditor (*this);
}

juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter()
{
    return new AutoVocalProcessor();
}

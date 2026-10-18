#pragma once

#include "PluginProcessor.h"
#include "gui/Components.h"

class AutoVocalEditor : public juce::AudioProcessorEditor, private juce::Timer
{
public:
    explicit AutoVocalEditor (AutoVocalProcessor&);
    ~AutoVocalEditor() override;

    void paint (juce::Graphics&) override;
    void resized() override;

private:
    void timerCallback() override;
    void updateStyleButtons (int style);
    juce::String keyText() const;

    AutoVocalProcessor& proc;
    avgui::LookAndFeel lnf;

    juce::TextButton styleButtons[3];
    std::unique_ptr<juce::ParameterAttachment> styleAttachment;

    juce::ComboBox keyBox, scaleBox;
    juce::TextButton relearnButton { "NEU LERNEN" };
    juce::ToggleButton autoMixToggle { "AUTO-MIX" }, learnToggle { "LERNEN" };

    avgui::Knob tune { "TUNE", avgui::Colours::accent }, speed { "SPEED", avgui::Colours::accent };
    avgui::Knob warmth { "WÄRME", avgui::Colours::warn }, deess { "DE-ESSER", avgui::Colours::accent2 };
    avgui::Knob dynamics { "DYNAMIK", avgui::Colours::warn }, autoEq { "AUTO-EQ", avgui::Colours::accent2 };
    avgui::Knob delay { "DELAY", avgui::Colours::accent }, reverb { "HALL", avgui::Colours::accent };
    avgui::Knob output { "OUTPUT", avgui::Colours::text };

    avgui::PitchDisplay pitchDisplay;
    avgui::EqDisplay eqDisplay;
    avgui::DynamicsPanel dynamicsPanel;

    using SliderAtt = juce::AudioProcessorValueTreeState::SliderAttachment;
    using ComboAtt = juce::AudioProcessorValueTreeState::ComboBoxAttachment;
    using ButtonAtt = juce::AudioProcessorValueTreeState::ButtonAttachment;
    std::vector<std::unique_ptr<SliderAtt>> sliderAtts;
    std::unique_ptr<ComboAtt> keyAtt, scaleAtt;
    std::unique_ptr<ButtonAtt> autoMixAtt, learnAtt;

    juce::Rectangle<int> knobArea, headerKeyArea;
    std::array<av::VocalEngine::PitchPoint, 2048> pitchScratch {};

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (AutoVocalEditor)
};

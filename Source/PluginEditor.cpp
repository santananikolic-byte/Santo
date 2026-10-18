#include "PluginEditor.h"

using namespace avgui;

namespace
{
constexpr int kWidth = 940, kHeight = 620;
const char* kStyleNames[3] = { "NATÜRLICH", "MODERN", "HART" };
} // namespace

AutoVocalEditor::AutoVocalEditor (AutoVocalProcessor& p)
    : AudioProcessorEditor (&p), proc (p)
{
    setLookAndFeel (&lnf);
    setSize (kWidth, kHeight);

    for (int i = 0; i < 3; ++i)
    {
        auto& b = styleButtons[i];
        b.setButtonText (juce::String::fromUTF8 (kStyleNames[i]));
        b.setClickingTogglesState (false);
        b.onClick = [this, i] { proc.applyStyle (i); };
        addAndMakeVisible (b);
    }
    styleAttachment = std::make_unique<juce::ParameterAttachment> (
        *proc.apvts.getParameter (ParamIDs::style), [this] (float v) { updateStyleButtons (juce::roundToInt (v)); });
    styleAttachment->sendInitialUpdate();

    keyBox.addItemList ({ "Auto-Tonart", "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "H" }, 1);
    scaleBox.addItemList ({ "Auto-Skala", "Dur", "Moll", "Chromatisch" }, 1);
    keyBox.setTooltip ("Tonart (Auto = wird automatisch erkannt)");
    addAndMakeVisible (keyBox);
    addAndMakeVisible (scaleBox);
    keyAtt = std::make_unique<ComboAtt> (proc.apvts, ParamIDs::key, keyBox);
    scaleAtt = std::make_unique<ComboAtt> (proc.apvts, ParamIDs::scale, scaleBox);

    relearnButton.onClick = [this] { proc.engine.relearn(); };
    addAndMakeVisible (relearnButton);
    addAndMakeVisible (autoMixToggle);
    addAndMakeVisible (learnToggle);
    autoMixAtt = std::make_unique<ButtonAtt> (proc.apvts, ParamIDs::autoMix, autoMixToggle);
    learnAtt = std::make_unique<ButtonAtt> (proc.apvts, ParamIDs::learn, learnToggle);

    const std::pair<Knob*, const char*> knobs[] = {
        { &tune, ParamIDs::tune }, { &speed, ParamIDs::speed }, { &warmth, ParamIDs::warmth },
        { &deess, ParamIDs::deess }, { &dynamics, ParamIDs::dynamics }, { &autoEq, ParamIDs::autoEq },
        { &delay, ParamIDs::delay }, { &reverb, ParamIDs::reverb }, { &output, ParamIDs::output },
    };
    for (auto& [knob, id] : knobs)
    {
        addAndMakeVisible (*knob);
        sliderAtts.push_back (std::make_unique<SliderAtt> (proc.apvts, id, knob->slider));
        knob->slider.setDoubleClickReturnValue (true, proc.apvts.getParameterRange (id).convertFrom0to1 (
                                                          proc.apvts.getParameter (id)->getDefaultValue()));
    }

    addAndMakeVisible (pitchDisplay);
    addAndMakeVisible (eqDisplay);
    addAndMakeVisible (dynamicsPanel);

    startTimerHz (30);
}

AutoVocalEditor::~AutoVocalEditor()
{
    stopTimer();
    setLookAndFeel (nullptr);
}

void AutoVocalEditor::updateStyleButtons (int style)
{
    for (int i = 0; i < 3; ++i)
        styleButtons[i].setToggleState (i == style, juce::dontSendNotification);
}

juce::String AutoVocalEditor::keyText() const
{
    static const char* names[] = { "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "H" };
    const int scaleMode = scaleBox.getSelectedItemIndex();
    if (scaleMode == av::KeyDetector::scaleChromatic)
        return "CHROMATISCH";
    const int tonic = proc.engine.keyTonic.load();
    if (tonic < 0)
        return juce::String::fromUTF8 ("…");
    return juce::String (names[tonic]) + (proc.engine.keyMinor.load() ? "-MOLL" : "-DUR");
}

void AutoVocalEditor::timerCallback()
{
    auto& e = proc.engine;
    const int n = e.readPitchPoints (pitchScratch.data(), (int) pitchScratch.size());
    pitchDisplay.setMask (e.keyMask.load());
    pitchDisplay.push (pitchScratch.data(), n);
    pitchDisplay.repaint();

    std::array<float, av::VocalChain::kBands> g {};
    for (int b = 0; b < av::VocalChain::kBands; ++b)
        g[(size_t) b] = e.eqGains[(size_t) b].load();
    eqDisplay.setGains (g);

    dynamicsPanel.setValues (e.gateGr.load(), e.deessGr.load(), e.compGr.load(), e.limGr.load(),
                             e.inPeak.exchange (0.0f), e.outPeak.exchange (0.0f));
    repaint (headerKeyArea);
    repaint (getLocalBounds().removeFromBottom (30));
}

void AutoVocalEditor::paint (juce::Graphics& g)
{
    auto bounds = getLocalBounds().toFloat();
    juce::ColourGradient bg (Colours::bg0.brighter (0.04f), 0, 0, Colours::bg0, 0, bounds.getHeight(), false);
    g.setGradientFill (bg);
    g.fillAll();

    // logo
    {
        auto logo = juce::Rectangle<float> (18.0f, 16.0f, 38.0f, 38.0f);
        g.setColour (Colours::accent.withAlpha (0.15f));
        g.fillRoundedRectangle (logo, 10.0f);
        g.setColour (Colours::accent);
        g.drawRoundedRectangle (logo.reduced (0.5f), 10.0f, 1.2f);
        juce::Path wave;
        for (int i = 0; i <= 40; ++i)
        {
            const float t = (float) i / 40.0f;
            const float env = std::sin (t * juce::MathConstants<float>::pi);
            const float x = logo.getX() + 7.0f + t * (logo.getWidth() - 14.0f);
            const float y = logo.getCentreY() - std::sin (t * 13.0f) * env * 9.0f;
            if (i == 0) wave.startNewSubPath (x, y); else wave.lineTo (x, y);
        }
        g.strokePath (wave, juce::PathStrokeType (2.0f, juce::PathStrokeType::curved, juce::PathStrokeType::rounded));

        g.setFont (font (22.0f, true));
        g.setColour (Colours::accent);
        g.drawText ("AUTO", 66, 14, 64, 26, juce::Justification::centredLeft);
        g.setColour (Colours::text);
        g.drawText ("VOCAL", 120, 14, 90, 26, juce::Justification::centredLeft);
        g.setFont (font (10.5f, true));
        g.setColour (Colours::dim);
        g.drawText (utf8 ("AUTO-TUNE  ·  AUTO-MIX"), 67, 38, 200, 14, juce::Justification::centredLeft);
    }

    // key read-out
    {
        auto r = headerKeyArea.toFloat();
        g.setColour (Colours::dim);
        g.setFont (font (10.5f, true));
        g.drawText ("TONART", r.removeFromTop (14.0f), juce::Justification::centredLeft);
        const bool learning = proc.engine.keyIsLearning.load() != 0;
        g.setColour (learning ? Colours::warn : Colours::accent);
        g.setFont (font (20.0f, true));
        g.drawText (learning ? juce::String ("LERNT") : keyText(), r.removeFromTop (24.0f), juce::Justification::centredLeft);
        g.setColour (Colours::dim);
        g.setFont (font (11.0f));
        juce::String sub;
        if (learning)
            sub = utf8 ("erkennt Tonart … ") + juce::String (juce::roundToInt (proc.engine.learnProgress.load() * 100.0f)) + " %";
        else if (keyBox.getSelectedItemIndex() == 0 && scaleBox.getSelectedItemIndex() != 3)
            sub = utf8 ("automatisch erkannt · ") + juce::String (juce::roundToInt (proc.engine.keyConfidence.load() * 100.0f)) + " %";
        else
            sub = "manuell eingestellt";
        g.drawText (sub, r.removeFromTop (14.0f), juce::Justification::centredLeft);
    }

    // knob section
    drawPanel (g, knobArea.toFloat());
    {
        struct Group { const char* name; int first, count; };
        const Group groups[] = { { "TUNING", 0, 2 }, { "MIX", 2, 4 }, { "EFFEKTE", 6, 2 }, { "AUSGANG", 8, 1 } };
        Knob* all[] = { &tune, &speed, &warmth, &deess, &dynamics, &autoEq, &delay, &reverb, &output };
        for (const auto& grp : groups)
        {
            const auto first = all[grp.first]->getBounds();
            const auto last = all[grp.first + grp.count - 1]->getBounds();
            const auto span = first.getUnion (last);
            g.setColour (Colours::dim);
            g.setFont (font (10.5f, true));
            g.drawText (grp.name, span.getX(), knobArea.getY() + 10, span.getWidth(), 14, juce::Justification::centred);
            g.setColour (Colours::line);
            g.drawHorizontalLine (knobArea.getY() + 30, (float) span.getX() + 10.0f, (float) span.getRight() - 10.0f);
            if (grp.first > 0)
                g.drawVerticalLine (span.getX() - 8, (float) knobArea.getY() + 16.0f, (float) knobArea.getBottom() - 16.0f);
        }
    }

    // status line
    {
        const double sr = proc.getSampleRate() > 0 ? proc.getSampleRate() : 44100.0;
        const juce::String dot = utf8 ("   ·   ");
        const juce::String status = "Latenz " + juce::String (juce::roundToInt (proc.getLatencySamples() * 1000.0 / sr)) + " ms" + dot
                                    + "Low-Cut " + juce::String (juce::roundToInt (proc.engine.lowCut.load())) + " Hz" + dot
                                    + "Tempo " + juce::String (juce::roundToInt (proc.currentBpm.load())) + " BPM" + dot
                                    + "v" + JucePlugin_VersionString;
        g.setColour (Colours::faint);
        g.setFont (font (11.0f));
        g.drawText (status, 18, getHeight() - 26, 520, 18, juce::Justification::centredLeft);
    }
}

void AutoVocalEditor::resized()
{
    // header
    const int segW = 104, segH = 34, segX = 262;
    for (int i = 0; i < 3; ++i)
        styleButtons[i].setBounds (segX + i * (segW + 6), 19, segW, segH);
    headerKeyArea = { 600, 12, 150, 54 };
    keyBox.setBounds (752, 14, 84, 26);
    scaleBox.setBounds (840, 14, 84, 26);
    relearnButton.setBounds (752, 44, 172, 22);

    // middle
    pitchDisplay.setBounds (16, 80, 606, 300);
    eqDisplay.setBounds (634, 80, 290, 140);
    dynamicsPanel.setBounds (634, 230, 290, 150);

    // knobs
    knobArea = { 16, 392, 908, 192 };
    Knob* all[] = { &tune, &speed, &warmth, &deess, &dynamics, &autoEq, &delay, &reverb, &output };
    const int knobW = 90, knobH = 140, gap = 17;
    int x = knobArea.getX() + 14;
    for (int i = 0; i < 9; ++i)
    {
        if (i == 2 || i == 6 || i == 8)
            x += gap;
        all[i]->setBounds (x, knobArea.getY() + 40, knobW, knobH);
        x += knobW + 2;
    }

    // footer
    autoMixToggle.setBounds (kWidth - 16 - 230, kHeight - 30, 110, 24);
    learnToggle.setBounds (kWidth - 16 - 110, kHeight - 30, 110, 24);
}

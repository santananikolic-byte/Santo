#pragma once

#include <juce_gui_basics/juce_gui_basics.h>
#include "../dsp/VocalEngine.h"

namespace avgui
{
namespace Colours
{
inline const juce::Colour bg0     { 0xFF0C0E12 };
inline const juce::Colour bg1     { 0xFF14171D };
inline const juce::Colour bg2     { 0xFF1C2029 };
inline const juce::Colour line    { 0xFF272C37 };
inline const juce::Colour text    { 0xFFE8EBF2 };
inline const juce::Colour dim     { 0xFF8790A3 };
inline const juce::Colour faint   { 0xFF4D5466 };
inline const juce::Colour accent  { 0xFF1FE0B0 };
inline const juce::Colour accent2 { 0xFF7B6CFF };
inline const juce::Colour warn    { 0xFFFFB547 };
inline const juce::Colour red     { 0xFFFF5D6C };
} // namespace Colours

inline juce::Font font (float size, bool bold = false)
{
    return juce::Font (juce::FontOptions (size, bold ? juce::Font::bold : juce::Font::plain));
}

/** String literal with umlauts / symbols (source files are UTF-8). */
inline juce::String utf8 (const char* s) { return juce::String::fromUTF8 (s); }

inline juce::String noteName (int midi)
{
    static const char* names[] = { "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "H" };
    return juce::String (names[((midi % 12) + 12) % 12]) + juce::String (midi / 12 - 1);
}

inline void drawPanel (juce::Graphics& g, juce::Rectangle<float> r, const juce::String& title = {})
{
    g.setColour (Colours::bg1);
    g.fillRoundedRectangle (r, 10.0f);
    g.setColour (Colours::line);
    g.drawRoundedRectangle (r.reduced (0.5f), 10.0f, 1.0f);
    if (title.isNotEmpty())
    {
        g.setColour (Colours::dim);
        g.setFont (font (11.0f, true));
        g.drawText (title, r.reduced (12.0f, 8.0f).removeFromTop (14.0f), juce::Justification::topLeft);
    }
}

//==============================================================================
class LookAndFeel : public juce::LookAndFeel_V4
{
public:
    LookAndFeel()
    {
        setColour (juce::ResizableWindow::backgroundColourId, Colours::bg0);
        setColour (juce::ComboBox::backgroundColourId, Colours::bg2);
        setColour (juce::ComboBox::textColourId, Colours::text);
        setColour (juce::ComboBox::outlineColourId, Colours::line);
        setColour (juce::ComboBox::arrowColourId, Colours::dim);
        setColour (juce::PopupMenu::backgroundColourId, Colours::bg2);
        setColour (juce::PopupMenu::textColourId, Colours::text);
        setColour (juce::PopupMenu::highlightedBackgroundColourId, Colours::accent.withAlpha (0.2f));
        setColour (juce::PopupMenu::highlightedTextColourId, Colours::text);
        setColour (juce::TextButton::textColourOffId, Colours::dim);
        setColour (juce::TextButton::textColourOnId, Colours::text);
        setColour (juce::Slider::textBoxTextColourId, Colours::text);
    }

    void drawRotarySlider (juce::Graphics& g, int x, int y, int w, int h, float pos, float start, float end, juce::Slider& s) override
    {
        const auto bounds = juce::Rectangle<float> ((float) x, (float) y, (float) w, (float) h).reduced (4.0f);
        const float r = juce::jmin (bounds.getWidth(), bounds.getHeight()) * 0.5f;
        const auto c = bounds.getCentre();
        const float angle = start + pos * (end - start);
        const auto col = s.findColour (juce::Slider::rotarySliderFillColourId);
        const float thick = juce::jmax (3.0f, r * 0.11f);

        juce::Path track;
        track.addCentredArc (c.x, c.y, r - thick, r - thick, 0.0f, start, end, true);
        g.setColour (Colours::line);
        g.strokePath (track, juce::PathStrokeType (thick, juce::PathStrokeType::curved, juce::PathStrokeType::rounded));

        juce::Path value;
        value.addCentredArc (c.x, c.y, r - thick, r - thick, 0.0f, start, angle, true);
        g.setColour (col.withAlpha (0.25f));
        g.strokePath (value, juce::PathStrokeType (thick * 2.2f, juce::PathStrokeType::curved, juce::PathStrokeType::rounded));
        g.setColour (col);
        g.strokePath (value, juce::PathStrokeType (thick, juce::PathStrokeType::curved, juce::PathStrokeType::rounded));

        const float kr = r * 0.64f;
        juce::ColourGradient grad (juce::Colour (0xFF2A303C), c.x, c.y - kr, juce::Colour (0xFF15181E), c.x, c.y + kr, false);
        g.setGradientFill (grad);
        g.fillEllipse (c.x - kr, c.y - kr, kr * 2, kr * 2);
        g.setColour (juce::Colours::black.withAlpha (0.5f));
        g.drawEllipse (c.x - kr, c.y - kr, kr * 2, kr * 2, 1.0f);
        g.setColour (juce::Colours::white.withAlpha (0.06f));
        g.drawEllipse (c.x - kr + 1, c.y - kr + 1, kr * 2 - 2, kr * 2 - 2, 1.0f);

        juce::Path pointer;
        pointer.addRoundedRectangle (-1.5f, -kr * 0.92f, 3.0f, kr * 0.5f, 1.5f);
        g.setColour (Colours::text);
        g.fillPath (pointer, juce::AffineTransform::rotation (angle).translated (c));
    }

    void drawButtonBackground (juce::Graphics& g, juce::Button& b, const juce::Colour&, bool over, bool down) override
    {
        auto r = b.getLocalBounds().toFloat().reduced (1.0f);
        const bool on = b.getToggleState();
        g.setColour (on ? Colours::accent.withAlpha (0.16f) : Colours::bg2.brighter (over ? 0.08f : 0.0f).darker (down ? 0.1f : 0.0f));
        g.fillRoundedRectangle (r, 7.0f);
        g.setColour (on ? Colours::accent : Colours::line);
        g.drawRoundedRectangle (r, 7.0f, 1.0f);
    }

    void drawButtonText (juce::Graphics& g, juce::TextButton& b, bool, bool) override
    {
        g.setColour (b.getToggleState() ? Colours::text : Colours::dim);
        g.setFont (font (12.0f, true));
        g.drawText (b.getButtonText(), b.getLocalBounds(), juce::Justification::centred);
    }

    void drawToggleButton (juce::Graphics& g, juce::ToggleButton& b, bool over, bool) override
    {
        auto r = b.getLocalBounds().toFloat().reduced (1.0f);
        const bool on = b.getToggleState();
        g.setColour (Colours::bg2.brighter (over ? 0.06f : 0.0f));
        g.fillRoundedRectangle (r, r.getHeight() * 0.5f);
        g.setColour (on ? Colours::accent.withAlpha (0.6f) : Colours::line);
        g.drawRoundedRectangle (r, r.getHeight() * 0.5f, 1.0f);
        const float d = 8.0f;
        const auto led = juce::Rectangle<float> (r.getX() + 10.0f, r.getCentreY() - d * 0.5f, d, d);
        if (on)
        {
            g.setColour (Colours::accent.withAlpha (0.3f));
            g.fillEllipse (led.expanded (3.0f));
        }
        g.setColour (on ? Colours::accent : Colours::faint);
        g.fillEllipse (led);
        g.setColour (on ? Colours::text : Colours::dim);
        g.setFont (font (11.5f, true));
        g.drawText (b.getButtonText(), r.withTrimmedLeft (24.0f).withTrimmedRight (8.0f), juce::Justification::centredLeft);
    }

    void drawComboBox (juce::Graphics& g, int w, int h, bool, int, int, int, int, juce::ComboBox& box) override
    {
        auto r = juce::Rectangle<float> (0, 0, (float) w, (float) h).reduced (0.5f);
        g.setColour (Colours::bg2);
        g.fillRoundedRectangle (r, 6.0f);
        g.setColour (box.hasKeyboardFocus (false) ? Colours::accent : Colours::line);
        g.drawRoundedRectangle (r, 6.0f, 1.0f);
        juce::Path arrow;
        const float ax = (float) w - 14.0f, ay = (float) h * 0.5f;
        arrow.addTriangle (ax - 4, ay - 2, ax + 4, ay - 2, ax, ay + 3);
        g.setColour (Colours::dim);
        g.fillPath (arrow);
    }

    juce::Font getComboBoxFont (juce::ComboBox&) override { return font (12.5f, true); }
    juce::Font getPopupMenuFont() override { return font (13.0f); }

    void positionComboBoxText (juce::ComboBox& box, juce::Label& label) override
    {
        label.setBounds (8, 0, box.getWidth() - 24, box.getHeight());
        label.setFont (getComboBoxFont (box));
    }
};

//==============================================================================
/** Rotary knob with name and value text. */
class Knob : public juce::Component
{
public:
    Knob (const char* nameText, juce::Colour colour) : name (utf8 (nameText))
    {
        slider.setSliderStyle (juce::Slider::RotaryHorizontalVerticalDrag);
        slider.setTextBoxStyle (juce::Slider::NoTextBox, false, 0, 0);
        slider.setRotaryParameters (juce::MathConstants<float>::pi * 1.25f, juce::MathConstants<float>::pi * 2.75f, true);
        slider.setColour (juce::Slider::rotarySliderFillColourId, colour);
        slider.setVelocityBasedMode (false);
        slider.setMouseDragSensitivity (220);
        slider.onValueChange = [this] { repaint(); };
        addAndMakeVisible (slider);
    }

    void paint (juce::Graphics& g) override
    {
        auto r = getLocalBounds();
        g.setColour (Colours::dim);
        g.setFont (font (11.0f, true));
        g.drawText (name, r.removeFromTop (16), juce::Justification::centred);
        g.setColour (Colours::text);
        g.setFont (font (13.0f, true));
        g.drawText (slider.getTextFromValue (slider.getValue()), r.removeFromBottom (18), juce::Justification::centred);
    }

    void resized() override
    {
        auto r = getLocalBounds();
        r.removeFromTop (16);
        r.removeFromBottom (18);
        slider.setBounds (r);
    }

    juce::Slider slider;

private:
    juce::String name;
};

//==============================================================================
/** Scrolling pitch graph on a piano-roll grid: grey = sung, colour = corrected. */
class PitchDisplay : public juce::Component
{
public:
    void push (const av::VocalEngine::PitchPoint* pts, int n)
    {
        for (int i = 0; i < n; ++i)
        {
            hist[(size_t) head] = pts[i];
            head = (head + 1) % kHistory;
            count = juce::jmin (count + 1, kHistory);
        }
        // keep the view centred on what is being sung
        float sum = 0.0f;
        int cnt = 0;
        for (int i = 0; i < juce::jmin (count, 700); ++i)
        {
            const auto& p = at (count - 1 - i);
            if (p.voiced) { sum += p.out; ++cnt; }
        }
        if (cnt > 20)
            centre += 0.08f * (sum / (float) cnt - centre);
        idleFrames = cnt > 0 ? 0 : idleFrames + 1;
    }

    void setMask (int m) { mask = m; }

    void paint (juce::Graphics& g) override
    {
        auto bounds = getLocalBounds().toFloat();
        drawPanel (g, bounds);
        auto area = bounds.reduced (1.0f);
        const float gutter = 40.0f;
        auto header = area.removeFromTop (46.0f);
        auto plot = area.withTrimmedLeft (gutter).reduced (0.0f, 6.0f);

        const float lo = centre - kSpan * 0.5f, hi = centre + kSpan * 0.5f;
        auto yFor = [&] (float midi) { return plot.getBottom() - (midi - lo) / (hi - lo) * plot.getHeight(); };
        const float rowH = plot.getHeight() / kSpan;

        g.saveState();
        g.reduceClipRegion (area.toNearestInt());
        for (int s = (int) std::floor (lo) - 1; s <= (int) std::ceil (hi) + 1; ++s)
        {
            const bool allowed = (mask >> (((s % 12) + 12) % 12)) & 1;
            const float y = yFor ((float) s);
            if (allowed)
            {
                g.setColour (juce::Colours::white.withAlpha (0.025f));
                g.fillRect (plot.getX(), y - rowH * 0.5f, plot.getWidth(), rowH);
                g.setColour (juce::Colours::white.withAlpha (s % 12 == 0 ? 0.14f : 0.07f));
                g.drawHorizontalLine ((int) y, plot.getX(), plot.getRight());
                g.setColour (s % 12 == 0 ? Colours::text : Colours::dim);
                g.setFont (font (10.5f, s % 12 == 0));
                g.drawText (noteName (s), juce::Rectangle<float> (area.getX() + 6, y - 7, gutter - 10, 14), juce::Justification::centredLeft);
            }
        }
        g.setColour (Colours::line);
        g.drawVerticalLine ((int) (area.getX() + gutter), area.getY() + 2, area.getBottom() - 6);
        g.drawHorizontalLine ((int) area.getY(), area.getX() + 10.0f, area.getRight() - 10.0f);

        auto buildPath = [&] (bool corrected)
        {
            juce::Path p;
            bool started = false;
            for (int i = 0; i < count; ++i)
            {
                const auto& pt = at (i);
                const float x = plot.getRight() - (float) (count - 1 - i) / (float) (kHistory - 1) * plot.getWidth();
                if (! pt.voiced) { started = false; continue; }
                const float y = yFor (corrected ? pt.out : pt.in);
                if (! started) { p.startNewSubPath (x, y); started = true; }
                else p.lineTo (x, y);
            }
            return p;
        };
        g.setColour (juce::Colours::white.withAlpha (0.35f));
        g.strokePath (buildPath (false), juce::PathStrokeType (1.4f));
        const auto out = buildPath (true);
        g.setColour (Colours::accent.withAlpha (0.18f));
        g.strokePath (out, juce::PathStrokeType (6.0f, juce::PathStrokeType::curved, juce::PathStrokeType::rounded));
        g.setColour (Colours::accent);
        g.strokePath (out, juce::PathStrokeType (2.2f, juce::PathStrokeType::curved, juce::PathStrokeType::rounded));
        g.restoreState();

        // header: current note + legend
        auto h = header.reduced (14.0f, 8.0f);
        g.setColour (Colours::dim);
        g.setFont (font (11.0f, true));
        g.drawText (utf8 ("TONHÖHE"), h.removeFromLeft (70.0f), juce::Justification::centredLeft);

        auto legend = h.removeFromRight (190.0f);
        auto drawLegend = [&] (juce::Rectangle<float> r, juce::Colour col, float thick, const juce::String& label)
        {
            g.setColour (col);
            g.fillRoundedRectangle (r.removeFromLeft (18.0f).withSizeKeepingCentre (18.0f, thick), thick * 0.5f);
            g.setColour (Colours::dim);
            g.setFont (font (11.0f));
            g.drawText (label, r.withTrimmedLeft (6.0f), juce::Justification::centredLeft);
        };
        drawLegend (legend.removeFromLeft (92.0f), juce::Colours::white.withAlpha (0.45f), 1.6f, "gesungen");
        drawLegend (legend, Colours::accent, 3.0f, "korrigiert");

        const bool active = count > 0 && idleFrames < 40 && at (count - 1).voiced;
        if (active)
        {
            const auto& p = at (count - 1);
            const int target = juce::roundToInt (p.target);
            const int cents = juce::roundToInt ((p.in - p.target) * 100.0f);
            g.setColour (Colours::accent);
            g.setFont (font (22.0f, true));
            g.drawText (noteName (target), h.removeFromLeft (56.0f), juce::Justification::centredLeft);
            g.setColour (std::abs (cents) > 15 ? Colours::warn : Colours::dim);
            g.setFont (font (12.0f, true));
            g.drawText ((cents >= 0 ? "+" : "") + juce::String (cents) + utf8 (" ct gesungen → 0 ct"), h, juce::Justification::centredLeft);
        }
        if (count == 0 || idleFrames >= 40)
        {
            g.setColour (Colours::faint);
            g.setFont (font (14.0f));
            g.drawText (utf8 ("Warte auf Gesang …"), plot, juce::Justification::centred);
        }
    }

private:
    static constexpr int kHistory = 1400; // ~4 s
    static constexpr float kSpan = 17.0f;
    const av::VocalEngine::PitchPoint& at (int i) const { return hist[(size_t) ((head - count + i + kHistory) % kHistory)]; }

    std::array<av::VocalEngine::PitchPoint, kHistory> hist {};
    int head = 0, count = 0, idleFrames = 1000;
    float centre = 60.0f;
    int mask = 0x0FFF;
};

//==============================================================================
/** Response curve of the automatic EQ. */
class EqDisplay : public juce::Component
{
public:
    void setGains (const std::array<float, av::VocalChain::kBands>& g)
    {
        if (g != gains)
        {
            gains = g;
            repaint();
        }
    }

    void paint (juce::Graphics& g) override
    {
        auto bounds = getLocalBounds().toFloat();
        drawPanel (g, bounds, "AUTO-EQ");
        auto plot = bounds.reduced (12.0f).withTrimmedTop (16.0f).withTrimmedBottom (12.0f);
        const float fLo = 50.0f, fHi = 16000.0f, range = 10.0f;
        auto xFor = [&] (float f) { return plot.getX() + std::log (f / fLo) / std::log (fHi / fLo) * plot.getWidth(); };
        auto yFor = [&] (float dbv) { return plot.getCentreY() - juce::jlimit (-range, range, dbv) / range * plot.getHeight() * 0.5f; };

        g.setFont (font (9.5f));
        for (float f : { 100.0f, 1000.0f, 10000.0f })
        {
            g.setColour (Colours::line);
            g.drawVerticalLine ((int) xFor (f), plot.getY(), plot.getBottom());
            g.setColour (Colours::faint);
            g.drawText (f >= 1000.0f ? juce::String ((int) (f / 1000)) + "k" : juce::String ((int) f),
                        juce::Rectangle<float> (xFor (f) - 15, plot.getBottom() + 1, 30, 11), juce::Justification::centred);
        }
        g.setColour (Colours::line.brighter (0.2f));
        g.drawHorizontalLine ((int) plot.getCentreY(), plot.getX(), plot.getRight());

        std::array<av::Biquad, av::VocalChain::kBands> bank;
        av::VocalChain::designBank (48000.0, gains, bank);
        auto response = [&] (float f)
        {
            double s = 0.0;
            for (auto& b : bank)
                s += b.magnitudeDb (48000.0, f);
            return (float) s;
        };

        juce::Path curve, fill;
        for (int i = 0; i <= 160; ++i)
        {
            const float f = fLo * std::pow (fHi / fLo, (float) i / 160.0f);
            const float x = xFor (f), y = yFor (response (f));
            if (i == 0) { curve.startNewSubPath (x, y); fill.startNewSubPath (x, plot.getCentreY()); }
            else curve.lineTo (x, y);
            fill.lineTo (x, y);
        }
        fill.lineTo (plot.getRight(), plot.getCentreY());
        fill.closeSubPath();
        g.setColour (Colours::accent2.withAlpha (0.18f));
        g.fillPath (fill);
        g.setColour (Colours::accent2);
        g.strokePath (curve, juce::PathStrokeType (2.0f));

        for (int b = 0; b < av::VocalChain::kBands; ++b)
        {
            const float f = av::VocalChain::bandFrequency (b);
            const float x = xFor (f), y = yFor (response (f));
            g.setColour (Colours::bg1);
            g.fillEllipse (x - 3.5f, y - 3.5f, 7.0f, 7.0f);
            g.setColour (Colours::accent2.brighter (0.3f));
            g.drawEllipse (x - 3.5f, y - 3.5f, 7.0f, 7.0f, 1.5f);
        }
    }

private:
    std::array<float, av::VocalChain::kBands> gains {};
};

//==============================================================================
/** Gain reduction bars + input/output level meters. */
class DynamicsPanel : public juce::Component
{
public:
    void setValues (float gate, float deess, float comp, float lim, float inPk, float outPk)
    {
        auto smooth = [] (float& v, float target) { v = target > v ? target : v + 0.25f * (target - v); };
        smooth (gr[0], gate);
        smooth (gr[1], deess);
        smooth (gr[2], comp);
        smooth (gr[3], lim);
        auto level = [] (float& v, float& hold, int& holdTime, float pk)
        {
            const float d = juce::Decibels::gainToDecibels (pk, -60.0f);
            v = d > v ? d : juce::jmax (-60.0f, v - 1.2f);
            if (d >= hold) { hold = d; holdTime = 45; }
            else if (--holdTime < 0) hold = juce::jmax (-60.0f, hold - 0.8f);
        };
        level (inDb, inHold, inHoldT, inPk);
        level (outDb, outHold, outHoldT, outPk);
        repaint();
    }

    void paint (juce::Graphics& g) override
    {
        auto bounds = getLocalBounds().toFloat();
        drawPanel (g, bounds, "AUTO-MIX");
        auto r = bounds.reduced (12.0f).withTrimmedTop (18.0f);
        auto meters = r.removeFromRight (54.0f);
        r.removeFromRight (10.0f);

        static const char* labels[] = { "GATE", "DE-ESSER", "KOMPRESSOR", "LIMITER" };
        const juce::Colour cols[] = { Colours::dim, Colours::accent2, Colours::warn, Colours::red };
        const float rowH = r.getHeight() / 4.0f;
        for (int i = 0; i < 4; ++i)
        {
            auto row = r.removeFromTop (rowH).reduced (0.0f, 3.0f);
            auto top = row.removeFromTop (14.0f);
            g.setFont (font (10.0f, true));
            g.setColour (Colours::dim);
            g.drawText (labels[i], top, juce::Justification::centredLeft);
            g.setColour (gr[i] > 0.1f ? Colours::text : Colours::faint);
            g.drawText (gr[i] < 0.05f ? juce::String ("0.0 dB") : "-" + juce::String (gr[i], 1) + " dB", top, juce::Justification::centredRight);
            auto bar = row.removeFromTop (6.0f).withY (row.getY() + 2.0f);
            g.setColour (Colours::bg2);
            g.fillRoundedRectangle (bar, 3.0f);
            g.setColour (cols[i]);
            g.fillRoundedRectangle (bar.withWidth (bar.getWidth() * juce::jlimit (0.0f, 1.0f, gr[i] / 12.0f)), 3.0f);
        }

        auto drawMeter = [&] (juce::Rectangle<float> m, float dbv, float hold, const char* label)
        {
            auto lab = m.removeFromBottom (14.0f);
            g.setColour (Colours::dim);
            g.setFont (font (9.5f, true));
            g.drawText (label, lab, juce::Justification::centred);
            m = m.withSizeKeepingCentre (8.0f, m.getHeight());
            g.setColour (Colours::bg2);
            g.fillRoundedRectangle (m, 4.0f);
            const float frac = juce::jlimit (0.0f, 1.0f, (dbv + 60.0f) / 60.0f);
            auto lit = m.withTop (m.getBottom() - m.getHeight() * frac);
            juce::ColourGradient grad (Colours::red, m.getX(), m.getY(), Colours::accent, m.getX(), m.getBottom(), false);
            grad.addColour (0.15, Colours::warn);
            g.setGradientFill (grad);
            g.fillRoundedRectangle (lit, 4.0f);
            const float hy = m.getBottom() - m.getHeight() * juce::jlimit (0.0f, 1.0f, (hold + 60.0f) / 60.0f);
            g.setColour (Colours::text);
            g.fillRect (m.getX(), hy - 1.0f, m.getWidth(), 2.0f);
        };
        drawMeter (meters.removeFromLeft (27.0f), inDb, inHold, "IN");
        drawMeter (meters, outDb, outHold, "OUT");
    }

private:
    float gr[4] {};
    float inDb = -60, outDb = -60, inHold = -60, outHold = -60;
    int inHoldT = 0, outHoldT = 0;
};
} // namespace avgui

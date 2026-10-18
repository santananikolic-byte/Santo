// Renders the plugin editor to a PNG while audio is running through the plugin.
//   AutoVocalScreenshot vocal.wav out.png

#include <juce_audio_formats/juce_audio_formats.h>
#include <juce_gui_basics/juce_gui_basics.h>
#include "PluginProcessor.h"

int main (int argc, char** argv)
{
    if (argc < 3)
        return 1;
    juce::ScopedJuceInitialiser_GUI init;

    juce::AudioFormatManager fm;
    fm.registerBasicFormats();
    std::unique_ptr<juce::AudioFormatReader> reader (fm.createReaderFor (juce::File::getCurrentWorkingDirectory().getChildFile (argv[1])));
    if (reader == nullptr)
        return 1;
    juce::AudioBuffer<float> audio (1, (int) reader->lengthInSamples);
    reader->read (&audio, 0, audio.getNumSamples(), 0, true, false);
    const double sr = reader->sampleRate;

    AutoVocalProcessor proc;
    constexpr int block = 512;
    proc.setPlayConfigDetails (1, 2, sr, block);
    proc.prepareToPlay (sr, block);
    std::unique_ptr<juce::AudioProcessorEditor> editor (proc.createEditor());

    juce::AudioBuffer<float> buf (2, block);
    juce::MidiBuffer midi;
    int pos = 0;
    const int total = std::min (audio.getNumSamples(), (int) (sr * 20.0));
    while (pos + block <= total)
    {
        buf.clear();
        buf.copyFrom (0, 0, audio, 0, pos, block);
        proc.processBlock (buf, midi);
        pos += block;
        // let the editor's timer run during the last seconds (real-time pacing)
        if (pos > total - (int) (sr * 4.5))
            juce::MessageManager::getInstance()->runDispatchLoopUntil ((int) (block * 1000.0 / sr));
    }

    const auto img = editor->createComponentSnapshot (editor->getLocalBounds(), true, 2.0f);
    juce::File out (juce::File::getCurrentWorkingDirectory().getChildFile (argv[2]));
    out.deleteFile();
    juce::FileOutputStream os (out);
    juce::PNGImageFormat png;
    return png.writeImageToStream (img, os) ? 0 : 1;
}

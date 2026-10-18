cmake_minimum_required(VERSION 3.22)

project(AutoVocal VERSION 1.0.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

option(AUTOVOCAL_BUILD_PLUGIN "Build the AU/VST3/Standalone plugin" ON)
option(AUTOVOCAL_BUILD_TESTS "Build the offline render test tool" OFF)

# JUCE: use a local checkout (-DJUCE_SOURCE_DIR=...) or download it
if(DEFINED JUCE_SOURCE_DIR)
    add_subdirectory(${JUCE_SOURCE_DIR} juce EXCLUDE_FROM_ALL)
else()
    include(FetchContent)
    FetchContent_Declare(juce
        GIT_REPOSITORY https://github.com/juce-framework/JUCE.git
        GIT_TAG 8.0.9
        GIT_SHALLOW TRUE)
    FetchContent_MakeAvailable(juce)
endif()

set(AUTOVOCAL_DSP_SOURCES
    Source/dsp/AutoTuner.cpp
    Source/dsp/VocalChain.cpp
    Source/dsp/VocalEngine.cpp)

if(AUTOVOCAL_BUILD_PLUGIN)
    juce_add_plugin(AutoVocal
        COMPANY_NAME "AutoVocal"
        COMPANY_WEBSITE "https://github.com/santananikolic-byte/Santo"
        BUNDLE_ID com.autovocal.autovocal
        PLUGIN_MANUFACTURER_CODE Avoc
        PLUGIN_CODE Avt1
        FORMATS AU VST3 Standalone
        PRODUCT_NAME "AutoVocal"
        DESCRIPTION "Autonomous auto-tune and vocal mixing"
        IS_SYNTH FALSE
        NEEDS_MIDI_INPUT FALSE
        NEEDS_MIDI_OUTPUT FALSE
        IS_MIDI_EFFECT FALSE
        EDITOR_WANTS_KEYBOARD_FOCUS FALSE
        COPY_PLUGIN_AFTER_BUILD FALSE
        AU_MAIN_TYPE kAudioUnitType_Effect
        VST3_CATEGORIES Fx "Pitch Shift"
        MICROPHONE_PERMISSION_ENABLED TRUE
        MICROPHONE_PERMISSION_TEXT "AutoVocal braucht das Mikrofon, um deine Stimme live zu bearbeiten.")

    target_sources(AutoVocal PRIVATE
        Source/PluginProcessor.cpp
        Source/PluginEditor.cpp
        ${AUTOVOCAL_DSP_SOURCES})

    target_include_directories(AutoVocal PRIVATE Source)

    target_compile_definitions(AutoVocal PUBLIC
        JUCE_WEB_BROWSER=0
        JUCE_USE_CURL=0
        JUCE_VST3_CAN_REPLACE_VST2=0
        JUCE_DISPLAY_SPLASH_SCREEN=0)

    target_link_libraries(AutoVocal
        PRIVATE
            juce::juce_audio_utils
            juce::juce_dsp
        PUBLIC
            juce::juce_recommended_config_flags
            juce::juce_recommended_lto_flags
            juce::juce_recommended_warning_flags)
endif()

if(AUTOVOCAL_BUILD_TESTS)
    juce_add_console_app(AutoVocalRender PRODUCT_NAME "AutoVocalRender")
    target_sources(AutoVocalRender PRIVATE tests/OfflineRender.cpp ${AUTOVOCAL_DSP_SOURCES})
    target_include_directories(AutoVocalRender PRIVATE Source)
    target_compile_definitions(AutoVocalRender PRIVATE JUCE_WEB_BROWSER=0 JUCE_USE_CURL=0)
    target_link_libraries(AutoVocalRender
        PRIVATE juce::juce_audio_formats juce::juce_dsp
        PUBLIC juce::juce_recommended_config_flags juce::juce_recommended_warning_flags)

    juce_add_console_app(AutoVocalScreenshot PRODUCT_NAME "AutoVocalScreenshot")
    target_sources(AutoVocalScreenshot PRIVATE
        tests/Screenshot.cpp Source/PluginProcessor.cpp Source/PluginEditor.cpp ${AUTOVOCAL_DSP_SOURCES})
    target_include_directories(AutoVocalScreenshot PRIVATE Source)
    target_compile_definitions(AutoVocalScreenshot PRIVATE
        JUCE_WEB_BROWSER=0 JUCE_USE_CURL=0 JUCE_MODAL_LOOPS_PERMITTED=1
        JucePlugin_Name="AutoVocal" JucePlugin_VersionString="${PROJECT_VERSION}")
    target_link_libraries(AutoVocalScreenshot
        PRIVATE juce::juce_audio_utils juce::juce_dsp
        PUBLIC juce::juce_recommended_config_flags)
endif()

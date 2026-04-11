# 📦 Resource Pack System

Resource packs are the heart of ResonaDesktopPet, defining the character's appearance, voice, personality, and behavior.

## 1. Directory Structure
A standard resource pack (e.g., `packs/Example_Pack/`) follows this structure:
```text
Example_Pack/
├── pack.json               # Core configuration file
├── README.md               # Pack documentation
├── assets/
│   ├── sprites/            # Sprite assets
│   │   └── example_outfit/ # Specific outfit folder
│   │       ├── sum.json    # Emotion index file
│   │       └── *.png       # Image files
│   └── audio/              # Audio assets
├── logic/
│   ├── emotions.json       # TTS emotion references
│   ├── triggers.json       # Interaction trigger logic
│   ├── thinking.json       # Random texts shown while thinking
│   └── listening.json      # Random texts shown while recording
├── models/
│   └── sovits/             # GPT-SoVITS weights (.pth / .ckpt)
└── prompts/
    └── character_prompt.txt # LLM personality prompt
```

## 2. Core Config (`pack.json`)
The entry point of the pack, defining:
- **pack_info**: ID, name, version, and author.
- **character**: Character name, default outfit, TTS language, and SoVITS model paths.
- **logic**: Mappings for logic JSON files and prompts.
- **audio**: Root directories for event and emotion audio references.

## 3. Emotion Index (`sum.json`)
Located in each outfit folder:
```json
{
    "<E:smile>": ["outfit_smile_01", "outfit_smile_02"],
    "<E:angry>": ["outfit_angry_01"]
}
```
It maps emotion tags to specific filenames (without extensions). The program randomly selects one image from the list.

## 4. How to Customize a Resource Pack
1. **Use the Example**: The fastest way is to copy `packs/Example_Pack` and rename the folder.
2. **Modify pack.json**: Set a unique `id` and update the character name.
3. **Prepare Sprites**:
   - Process images using `tools/image_processor.py`.
   - Organize and generate `sum.json` using `tools/sprite_organizer.py`.
4. **Configure Voice**:
   - Place trained SoVITS models in `models/sovits/`.
   - Map emotions to reference audio in `logic/emotions.json`.
5. **Define Logic**:
   - Write the character's tone and background in `prompts/character_prompt.txt`.
   - Create interactive triggers using `tools/trigger_editor.py`.

---
Parts of this document were generated with the assistance of large language models, and translations were also completed by large language models. Any deviations do not represent the author's true intent.

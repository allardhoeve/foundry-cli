---
name: foundry-icon
description: Generate a Foundry item icon with the local Draw Things app, versioned under output/icons/. Use when the user wants an icon, image or picture for an item, or wants a new version of one.
---

# Foundry item icons

Icons are painted in the style of Foundry's built-in item icons (Rexard): one object, angled, filling the frame, visible brush strokes, muted colours, a soft glow on a dark background. Generation runs in Draw Things on the user's Mac through its HTTP API.

## Steps

1. **Read the item.** The user pastes the item text. Pick out what is *visible*: shape, material, colour, condition, what's in or on it. Rules text (luck tokens, slots, downtime) is not visible; leave it out.
2. **Write the version file.** Each item has a folder `output/icons/<slug>/` (kebab-case item name) with one `vN.json` per version. For a new item, start at `v1.json` from the template below. For a new version, copy the highest `vN.json` to `vN+1.json` and change only what fixes the flaws in its `notes`. Keep the seed when tweaking, so the change you made is the change you see. Done when the file has a prompt built from the template and a `notes` line saying what this version tries to fix.
3. **Generate.** Run in the background (about 3 minutes at 512×512):
   ```
   uv run --with pillow python .claude/skills/foundry-icon/generate.py output/icons/<slug>/vN.json
   ```
   The app's current Moodboard and project apply to API requests; the API cannot set them. Before generating, tell the user which Moodboard suits this item (or to empty it), then generate once they have set it. Record what was in it under `moodboard`. If the API is unreachable, ask the user to enable the API server in Draw Things settings.
4. **Review.** Look at `vN.png` against the item text: every visible trait from step 1 present, nothing extra. Write the flaws into `notes` in `vN.json` and report them with the path to `vN.webp`. Done when `notes` lists each trait that is missing or wrong, or says none.

5. **Finalise.** When the user picks a version, make the final icon `<item_name>.webp` in snake_case from its PNG, and add "Chosen as final" to that version's `notes`:
   ```
   uv run --with pillow python .claude/skills/foundry-icon/finalise.py output/icons/<slug>/vN.png tome_of_the_iron_golem.webp
   ```
   It brightens the muted generation to match Foundry's icons in the inventory list (saturation, contrast, sharpen; the frame is kept as generated).

The user uploads the final webp into Foundry; the live world is read-only for agents (see CLAUDE.md).

## Template

```json
{
  "item": "<item name>",
  "prompt": "hand-painted fantasy game item icon of <a single object: shape, material, colour, details>, viewed from slightly above at a three-quarter angle, the <object> fills most of the frame, muted desaturated colors, <two or three main colour tones>, thick visible brush strokes, simple shapes, strong highlights and deep shadows, faint <colour> glow behind it, dark background, 2D digital painting",
  "negative_prompt": "3D render, photorealistic, vibrant, saturated, text, watermark",
  "model": "flux_2_klein_base_4b_i8x.ckpt",
  "loras": [],
  "width": 512, "height": 512, "steps": 30, "guidance_scale": 4, "seed": 1234,
  "sampler": "DDIM Trailing", "seed_mode": "Scale Alike",
  "moodboard": "<what the user had in the Moodboard>",
  "notes": "<what this version changes; after review, its flaws>"
}
```

## What works

- **Base model with guidance 4.** The negative prompt only takes effect with the Base model and guidance above 1; the fast klein model ignores it. 512×512 is about 3 minutes; the icon ends up 256×256 anyway.
- **Style lives in the words.** "2D digital painting", "thick visible brush strokes" and the negative prompt keep it painted. The style LoRA trained on Foundry icons (`foundry_icons_*` in Draw Things) made it slicker and more 3D; keep `loras` empty.
- **Make counts visual.** "a tripod of exactly three short legs, one leg in front and two at the back" beats "three legs"; the model cannot count.
- **Contrast unusual materials.** "pages are thin dull metal sheets instead of paper"; without "instead of", the default material wins. Even then it may not read; say so in `notes`.
- **Say "a single … only one".** "Tome", "book" and similar nouns can come out as two objects; add `two books, multiple <objects>` to the negative prompt when it happens.
- **Spell out how parts connect.** A padlock ends up floating on the cover beside the chains; write "the padlock's shackle passing through the last chain links". When the rest of the image is good, inpainting just that area in the app beats a new version.
- **Name the object, not a lookalike.** "washbasin" or "bathroom sink" pulls in taps and pedestals; describe the shape ("wide and shallow oval ceramic bowl") instead.
- **Muted is the default.** Keep colour words few and dull; the Foundry icons are colourful, but the user prefers muted.
- **Images made in the app carry their settings.** A Draw Things PNG holds prompt, negative prompt, seed, size, model and LoRAs as JSON in its XMP `exif:UserComment` (`c` is the prompt, `uc` the negative, `v2.loras`). Read it to file an app-made image as a version; the Moodboard is not in it.
- **Early previews lie.** The first steps in the app draw over the previous canvas image, so step 3 can look like the last item.

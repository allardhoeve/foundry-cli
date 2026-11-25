---
name: visualize
description: Paint an item, character, location or creature with the local `visualize` CLI (FLUX.2 klein). Use when the user wants an image, icon, portrait or picture of something, or a new version of one.
---

# Visualize

`uv run python visualize.py` paints locally and headless; `--help` on each command has the options and a worked example. Each kind has a template and a moodbook of style references, so your job is the **subject** (what is visible) and the **judgement** (which variant, what to change).

## Steps

1. **Read the text.** The user pastes an item, NPC, place or monster. Pick out what is *visible*: shape, material, colour, condition, what's in or on it. Rules text (bonuses, slots, rust immunity) is not visible; leave it out. Pick the kind (`visualize kinds`). If `visualize moodbook list <kind>` is empty, run `moodbook init <kind>` for items, or tell the user the kind has no moodbook yet.
2. **Paint.** `visualize new <kind> "<Name>" --subject "<visible traits>"` makes four variants and prints the contact sheet path. Run it in the background: about 2–3 minutes for four.
3. **Review.** Read the sheet. Check every variant against the visible traits from step 1. Write the verdict into `notes` in `vN.json`: per variant, the traits that are missing or wrong. Done when each variant has a verdict.
4. **Fix or show.** If one variant has every trait, show it. Otherwise make one fix (see **Tacking**) and go back to step 2. After two rounds of your own, always show the user the best variants so far, whatever their state.
5. **Show.** Give the sheet path, which variants you would pick, and the round log: one line per round with what you tried and what it changed ("v1: colour grey. v2: edited v1-c to recolour; colour fixed, arm hole lost"). The user decides what is good enough.
6. **Finalise.** When the user picks a variant: `visualize final <kind> "<Name>" vN-x`. The user uploads the result into Foundry; the live world is read-only for agents (see CLAUDE.md).

## Tacking

A flaw that survives one wording fix is beyond what words can do for this model. Tack: change the approach, not the wording. In order of cost:

1. **Edit the best variant** with an instruction for just that flaw: `visualize edit ... --from vN-x --instruction "Open an arm hole on the side. Keep everything else the same."`
2. **Start from an existing picture.** A Foundry or Shadowdark icon of a similar object, edited, keeps its shape and style for free (`--from <path>`). This is how Verdigris Armor finally worked.
3. **Change the references.** Add an image that shows the wanted thing (`--ref`), or leave out the moodbook when it drags the shape toward its own objects (`--no-moodbook`).
4. **Simplify the subject.** Drop the detail the model fights, and say so in the round log.
5. **Ask the user.** They often know a picture or idea that isn't in the text.

## Writing the subject

The model has no negative prompt: say what you want, never what to avoid ("polished, undamaged" rather than "no rust"). Naming the unwanted thing puts it in the picture.

- **Make counts visual.** "a tripod of exactly three short legs, one in front and two at the back" beats "three legs"; the model cannot count.
- **Contrast unusual materials.** "pages are thin dull metal sheets instead of paper"; without "instead of", the default material wins.
- **Spell out how parts connect.** "the padlock's shackle passing through the last chain links", or the padlock floats beside the chains.
- **Name the shape, not a lookalike.** "washbasin" pulls in taps and pedestals; "wide and shallow oval ceramic bowl" does not.
- **Colour words few and dull.** Name one colour per part. A word like "verdigris" brings its associations (corroded copper); describe the colour instead ("sage green").
- **Keep the seed to compare wording.** `--seed` with the seed from `vN.json` shows exactly what your change did.

## Edit instructions

Write the change as an instruction, then what must stay: "Recolour every plate to muted sage green. Keep the shape, plates, dark outline and painting style the same." Name one change per edit; two changes in one instruction tend to lose one.

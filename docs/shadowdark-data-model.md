# Shadowdark RPG — Foundry VTT System Data Model Reference

System ID: `shadowdark`
Version: `4.0.6`
Foundry compatibility: minimum v13, verified v14

---

## Table of Contents

1. [System Metadata](#system-metadata)
2. [Actors](#actors)
   - [ActorBaseSD (shared base)](#actorbasesd-shared-base)
   - [Player](#player)
   - [NPC](#npc)
   - [Light (actor)](#light-actor)
3. [Shared Field Groups](#shared-field-groups)
   - [alignment()](#alignment)
   - [level()](#level)
   - [bonuses (NPC item bonus block)](#bonuses-npc-item-bonus-block)
   - [lightSource()](#lightsource)
   - [languageChoices()](#languagechoices)
   - [magic()](#magic)
   - [ranges()](#ranges)
4. [Items](#items)
   - [BaseItemSD (shared base)](#baseitemsd-shared-base)
   - [PhysicalItemSD (physical base)](#physicalitemsd-physical-base)
   - [Ancestry](#ancestry)
   - [Armor](#armor)
   - [Background](#background)
   - [Basic](#basic)
   - [Boon](#boon)
   - [Class](#class)
   - [Class Ability](#class-ability)
   - [Deity](#deity)
   - [Effect](#effect)
   - [Gem](#gem)
   - [Language](#language)
   - [NPC Attack](#npc-attack)
   - [NPC Feature](#npc-feature)
   - [NPC Special Attack](#npc-special-attack)
   - [Patron](#patron)
   - [Potion](#potion)
   - [Property](#property)
   - [Scroll](#scroll)
   - [Spell](#spell)
   - [Talent](#talent)
   - [Wand](#wand)
   - [Weapon](#weapon)
5. [Enums and Constants](#enums-and-constants)
6. [Active Effect Keys and Predefined Effects](#active-effect-keys-and-predefined-effects)
7. [Socket Events](#socket-events)
8. [Document-Level API](#document-level-api)
9. [System Defaults](#system-defaults)
10. [Compendium Packs](#compendium-packs)

---

## System Metadata

| Key | Value |
|-----|-------|
| `id` | `shadowdark` |
| `title` | Shadowdark RPG |
| `version` | 4.0.6 |
| `minimum Foundry` | v13 |
| `verified Foundry` | v14 |
| `initiative formula` | `@initiative` (derived from DEX mod + AE bonuses) |
| `primary token attribute` | `attributes.hp` |
| `grid distance` | 5 ft |
| `socket` | `true` — channel: `system.shadowdark` |

Actor types registered: `Player`, `NPC`, `Light`

Item types registered: `Ancestry`, `Armor`, `Background`, `Basic`, `Boon`, `Class`, `Class Ability`, `Deity`, `Effect`, `Gem`, `Language`, `NPC Attack`, `NPC Feature`, `NPC Special Attack`, `Patron`, `Potion`, `Property`, `Scroll`, `Spell`, `Talent`, `Wand`, `Weapon`

---

## Actors

All actor system data models extend `foundry.abstract.TypeDataModel`. The document class is `ActorSD`, which extends `foundry.documents.Actor`.

### ActorBaseSD (shared base)

All actor types inherit these fields. Defined in `system/src/models/_ActorBaseSD.mjs`.

**Schema fields:**

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `attributes.ac.value` | `NumberField` (integer) | `10` | min: 0. For Player, derived from equipped armor + AEs. |
| `attributes.hp.value` | `NumberField` (integer) | `0` | min: 0. Current HP. |
| `attributes.hp.max` | `NumberField` (integer) | `0` | min: 0. Maximum HP. |
| `notes` | `HTMLField` | `""` | Freeform HTML notes field. |

**Computed/derived (not stored):**

- `roll.initiative.bonus` — integer, AE-driven, used to build initiative formula `d20±bonus`
- `roll.initiative.advantage` — integer, AE-driven

**Key methods:**

| Method | Description |
|--------|-------------|
| `getPhysicalItems(group=true)` | Returns carried (non-stashed) physical items sorted by user order. |
| `getSlotUsage()` | Returns `{coins, gear, gems, treasure, total}` slot counts. |
| `getStashedItems()` | Returns stashed items. |
| `rollStatCheck(abilityId, config)` | Rolls a d20 stat check for the given ability key. Fires hook `SD-Stat-Check`. |

**Getters:**

| Getter | Player | NPC |
|--------|--------|-----|
| `isPC` | `true` | `false` |
| `isNPC` | `false` | `true` |
| `isMonster` | `false` | `true` |

**Slot calculation rules:**
- First 100 coins are free to carry (`FREE_COIN_CARRY = 100`). Every additional 100 coins cost 1 slot.
- 10 gems share 1 slot (`GEMS_PER_SLOT = 10`).
- Items track `slots.free_carry` (first N copies of this item are free), `slots.per_slot` (quantity per slot), and `slots.slots_used` (slots per unit).

---

### Player

Extends: `ActorBaseSD`
Model file: `system/src/models/PlayerSD.mjs`

**Additional schema fields:**

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `alignment` | `StringField` | `"neutral"` | Choices: see [Alignments enum](#alignments). |
| `level.value` | `NumberField` (integer) | `0` | min: 0. Character level. |
| `level.xp` | `NumberField` (integer) | `0` | min: 0. Experience points. |
| `ancestry` | `DocumentUUIDField` | `null` | UUID reference to an Ancestry item. |
| `background` | `DocumentUUIDField` | `null` | UUID reference to a Background item. |
| `class` | `DocumentUUIDField` | `null` | UUID reference to a Class item. |
| `deity` | `DocumentUUIDField` | `null` | UUID reference to a Deity item. |
| `patron` | `DocumentUUIDField` | `null` | UUID reference to a Patron item. |
| `languages` | `ArrayField<DocumentUUIDField>` | `[]` | Array of Language item UUIDs. |
| `coins.gp` | `NumberField` (integer) | `0` | min: 0. Gold pieces. |
| `coins.sp` | `NumberField` (integer) | `0` | min: 0. Silver pieces. |
| `coins.cp` | `NumberField` (integer) | `0` | min: 0. Copper pieces. |
| `luck.remaining` | `NumberField` (integer) | `0` | min: 0. Used in Pulp Mode only. |
| `luck.available` | `BooleanField` | `false` | Standard mode luck token status. |
| `renown` | `NumberField` (integer) | `0` | No minimum enforced. |
| `slots` | `NumberField` (integer) | `10` | min: 10. Gear slots; reset to 10 in `prepareBaseData`, then STR bonus applied. |
| `abilities.str` | `EmbeddedDataField<attributeModel>` | `{value: 10}` | See ability model below. |
| `abilities.int` | `EmbeddedDataField<attributeModel>` | `{value: 10}` | |
| `abilities.dex` | `EmbeddedDataField<attributeModel>` | `{value: 10}` | |
| `abilities.wis` | `EmbeddedDataField<attributeModel>` | `{value: 10}` | |
| `abilities.con` | `EmbeddedDataField<attributeModel>` | `{value: 10}` | |
| `abilities.cha` | `EmbeddedDataField<attributeModel>` | `{value: 10}` | |

**Ability model (`attributeModel`):**

Each ability key (`str`, `int`, `dex`, `wis`, `con`, `cha`) holds:

| Sub-field | Type | Default | Notes |
|-----------|------|---------|-------|
| `value` | `NumberField` (integer) | `10` | min: 0. Raw ability score. |
| `.mod` (computed getter) | integer | — | `Math.min(4, Math.max(-4, Math.floor((value-10)/2)))`. Clamped to [-4, +4]. |

**Derived data (set in `prepareDerivedData`, not stored directly):**

| Field | Description |
|-------|-------------|
| `attributes.ac.value` | Calculated from best equipped armor + AEs. Unarmored: `10 + DEX mod`. |
| `attributes.ac.tooltips` | Human-readable breakdown string. |
| `slots` | `10 + max(0, STR score - 10)`, then further modified by AEs. |
| `spellcasting.classes` | Deduplicated sorted array of spellcasting class name slugs. |
| `spellcasting.allowAllItems` | Boolean coerced from AE-set value. |
| `spellcasting.itemAbility` | Validated ability key string, cleared if invalid. |

**Transient fields (set in `prepareBaseData`, not persisted):**

| Field | Description |
|-------|-------------|
| `spellcasting.classes` | `[]` — populated by class item AEs |
| `spellcasting.allowAllItems` | `false` |
| `spellcasting.itemAbility` | `""` — override ability key for spell item rolls |

**Getters:**

| Getter | Returns | Notes |
|--------|---------|-------|
| `isPC` | `true` | |
| `canUseMagicItems` | boolean | `isSpellCaster || spellcasting.allowAllItems` |
| `hasLuckToken` | boolean | Pulp Mode: `luck.remaining > 0`; Standard: `luck.available` |
| `isSpellCaster` | boolean | `spellcasting.classes.length > 0` |

**AC calculation logic:**
1. Collect all equipped armor items.
2. For main armor items (those with `ac.base > 0`): calculate `ac.base + ability_mod + ac.modifier`, apply item-specific AEs, pick the best single result.
3. For bonus armor items (shields, etc., with no `ac.base`): sum all `ac.modifier` values and item AEs.
4. If unarmored: apply `attributes.ac.unarmored` AE key to base `10 + DEX mod`.
5. Apply `attributes.ac.value` AE key to the total.

**Key methods:**

| Method | Description |
|--------|-------------|
| `addAncestry(item)` | Sets `system.ancestry` UUID. |
| `addBackground(item)` | Sets `system.background` UUID. |
| `addClass(item)` | Sets `system.class` UUID. |
| `addDeity(item)` | Sets `system.deity` UUID. |
| `addLanguage(item)` | Appends to `system.languages` array (no duplicates). |
| `addPatron(item)` | Sets `system.patron` UUID; errors if class doesn't require a patron. |
| `castSpell(spellUuid, config)` | Full spell casting flow. Fires hook `SD-Player-Spell`. |
| `rollAttack(weaponUuid, config)` | Full weapon attack flow. Fires hook `SD-Player-Attack`. |
| `useAbility(abilityUuid, config)` | Class ability use flow. Fires hook `SD-Player-classAbility`. |
| `usePotion(itemId)` | Confirms and consumes a potion item. |
| `useLuckToken(postToChat)` | Consumes a luck token (mode-aware). |
| `learnSpell(itemId)` | Scroll spell-learn flow with class check. DC: `LEARN_SPELL_DC = 15`. |
| `getAncestry()` | Resolves and returns the ancestry item. |
| `getClass()` | Resolves and returns the class item. |
| `getDeity()` | Resolves and returns the deity item. |
| `getPatron()` | Resolves and returns the patron item. |
| `getLanguageItems()` | Resolves and returns sorted language items. |
| `getEquippedShields()` | Returns equipped armor items with `isAShield` flag. |
| `getAttacks()` | Returns `{melee: [...], ranged: [...]}` attack configs for all equipped weapons. |
| `getClassAbilities()` | Returns class abilities grouped by `group` field, sorted alphabetically. |
| `getTalents(grouped)` | Returns talents grouped into `ancestry`, `class`, `level`. |
| `getTitle()` | Returns character title string from class title table based on level + alignment. |
| `openSpellBook()` | Opens spellbook dialog for the character's casting class(es). |
| `sellAllGems()` | Sells all gem items, adding their value to coins. |
| `sellAllTreasure()` | Sells all treasure items. |
| `sellItemById(itemId)` | Sells a single item by ID. |

---

### NPC

Extends: `ActorBaseSD`
Model file: `system/src/models/NpcSD.mjs`

**Additional schema fields:**

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `alignment` | `StringField` | `"neutral"` | Choices: see [Alignments enum](#alignments). |
| `level.value` | `NumberField` (integer) | `0` | min: 0. |
| `level.xp` | `NumberField` (integer) | `0` | min: 0. |
| `darkAdapted` | `BooleanField` | `false` | Whether the NPC is adapted to darkness. |
| `move` | `StringField` | `"near"` | Choices: see [NPC Moves enum](#npc-moves). |
| `moveNote` | `StringField` | `""` | Freeform note about movement. |
| `spellcasting.ability` | `StringField` | `""` | Spellcasting ability key. |
| `spellcasting.bonus` | `NumberField` (integer) | `0` | min: 0. Flat spellcasting bonus. |
| `spellcasting.attacks` | `NumberField` (integer) | `0` | min: 0. Number of spell attacks. |
| `abilities.str.mod` | `NumberField` (integer) | `0` | Stored directly as modifier (no score). |
| `abilities.int.mod` | `NumberField` (integer) | `0` | |
| `abilities.dex.mod` | `NumberField` (integer) | `0` | |
| `abilities.wis.mod` | `NumberField` (integer) | `0` | |
| `abilities.con.mod` | `NumberField` (integer) | `0` | |
| `abilities.cha.mod` | `NumberField` (integer) | `0` | |

**Note:** NPC abilities store only the modifier directly (not a raw score). This differs from Player, which stores a score and computes the modifier.

**Key methods:**

| Method | Description |
|--------|-------------|
| `rollAttack(attackId, config)` | Rolls an NPC Attack item. Fires hook `SD-NPC-Attack`. |
| `castSpell(spellUuid, config)` | NPC spell casting. Fires hook `SD-NPC-Spell-Cast`. |
| `rollHP()` | Rolls `{level}d8 + CON mod`, updates `hp.max` and `hp.value`. |
| `buildNpcAttackDisplays(itemId)` | Renders an NPC attack block as HTML for chat. |
| `buildNpcSpecialDisplays(itemId)` | Renders an NPC special attack block as HTML for chat. |

---

### Light (actor)

Registered type: `Light`
Uses base `ActorBaseSD` schema only.
Default token image: `icons/sundries/lights/torch-purple.webp`

---

## Shared Field Groups

Reusable field factory functions composed into multiple schemas.

### alignment()

Defined in: `system/src/models/_fields/actorFields.mjs`
Used by: Player, NPC, Class, Deity

| Field | Type | Default | Choices |
|-------|------|---------|---------| 
| `alignment` | `StringField` | `"neutral"` | `"lawful"`, `"neutral"`, `"chaotic"` |

---

### level()

Defined in: `system/src/models/_fields/actorFields.mjs`
Used by: Player, NPC

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `level.value` | `NumberField` (integer) | `0` | min: 0 |
| `level.xp` | `NumberField` (integer) | `0` | min: 0 |

---

### bonuses (NPC item bonus block)

Defined in: `system/src/models/_fields/bonuses.mjs`
Used by: NpcAttackSD

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `bonuses.acBonus` | `NumberField` (integer) | `0` | min: 0 |
| `bonuses.acBonusFromAttribute` | `ArrayField<StringField>` | `[]` | Attribute keys |
| `bonuses.advantage` | `ArrayField<StringField>` | `[]` | |
| `bonuses.armorMastery` | `ArrayField<StringField>` | `[]` | |
| `bonuses.backstabDie` | `NumberField` (integer) | `0` | min: 0 |
| `bonuses.critical.successThreshold` | `NumberField` (integer) | `20` | min: 0 |
| `bonuses.critical.failureThreshold` | `NumberField` (integer) | `1` | min: 0 |
| `bonuses.critical.multiplier` | `NumberField` (integer) | `2` | min: 1 |
| `bonuses.damageMultiplier` | `NumberField` (integer) | `1` | min: 1 |
| `bonuses.gearSlots` | `NumberField` (integer) | `0` | min: 0 |
| `bonuses.hauler` | `BooleanField` | `false` | |
| `bonuses.lightSource` | `StringField` | `""` | |
| `bonuses.meleeAttackBonus` | `NumberField` (integer) | `0` | min: 0 |
| `bonuses.meleeDamageBonus` | `NumberField` (integer) | `0` | min: 0 |
| `bonuses.rangedAttackBonus` | `NumberField` (integer) | `0` | min: 0 |
| `bonuses.rangedDamageBonus` | `NumberField` (integer) | `0` | min: 0 |
| `bonuses.spellcastingCheckBonus` | `NumberField` (integer) | `0` | min: 0 |
| `bonuses.spellcastingClasses` | `ArrayField<StringField>` | `[]` | |
| `bonuses.stoneSkinTalent` | `NumberField` (integer) | `0` | min: 0 |
| `bonuses.unarmoredAcBonus` | `NumberField` (integer) | `0` | min: 0 |
| `bonuses.weaponDamageDieD12` | `ArrayField<StringField>` | `[]` | |
| `bonuses.weaponDamageDieImprovementByProperty` | `ArrayField<StringField>` | `[]` | |
| `bonuses.weaponDamageExtraDieByProperty` | `ArrayField<StringField>` | `[]` | |
| `bonuses.weaponDamageExtraDieImprovementByProperty` | `ArrayField<StringField>` | `[]` | |
| `bonuses.weaponMastery` | `ArrayField<StringField>` | `[]` | |

---

### lightSource()

Defined in: `system/src/models/_fields/itemFields.mjs`
Used by: BasicSD, EffectSD

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `light.active` | `BooleanField` | `false` | Whether the light is currently on. |
| `light.hasBeenUsed` | `BooleanField` | `false` | |
| `light.isSource` | `BooleanField` | `false` | Whether this item acts as a light source. |
| `light.longevityMins` | `NumberField` (integer) | `60` | min: 0. Total burn time in minutes. |
| `light.remainingSecs` | `NumberField` (integer) | `3600` | min: 0. Remaining burn time in seconds. |
| `light.template` | `StringField` | `"torch"` | Choices: see [Light Source Templates enum](#light-source-templates). |

---

### languageChoices()

Defined in: `system/src/models/_fields/itemFields.mjs`
Used by: AncestrySD, ClassSD

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `languages.common` | `NumberField` (integer) | `0` | min: 0. Number of common languages granted. |
| `languages.rare` | `NumberField` (integer) | `0` | min: 0. Number of rare languages granted. |
| `languages.select` | `NumberField` (integer) | `0` | min: 0. Number of player-selectable languages. |
| `languages.selectOptions` | `ArrayField<StringField>` | `[]` | Options to choose from. |
| `languages.fixed` | `ArrayField<StringField>` | `[]` | Fixed languages automatically granted. |

---

### magic()

Defined in: `system/src/models/_fields/itemFields.mjs`
Used by: SpellSD, PotionSD

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `class` | `ArrayField<DocumentUUIDField>` | `[]` | Class item UUIDs this spell belongs to. |
| `damageType` | `StringField` | `"none"` | Choices: see [Spell Damage Types enum](#spell-damage-types). |
| `duration.type` | `StringField` | `"rounds"` | Choices: see [Spell Durations enum](#spell-durations). |
| `duration.value` | `StringField` | `"1"` | Duration count (string to allow formulas). |
| `formula` | `StringField` | `""` | Dice formula for damage/healing (e.g. `"2d6"`). |
| `range` | `StringField` | `"near"` | Choices: see [Spell Ranges enum](#spell-ranges). |
| `lost` | `BooleanField` | `false` | Whether the spell has been lost (failed cast). |

---

### ranges()

Defined in: `system/src/models/_fields/itemFields.mjs`
Used by: NpcAttackSD, NpcSpecialAttackSD

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `ranges` | `ArrayField<StringField>` | `[]` | Each element: choices from [Ranges enum](#ranges-1). |

---

## Items

All item system data models extend `foundry.abstract.TypeDataModel`. The document class is `ItemSD`, which extends `foundry.documents.Item`.

### BaseItemSD (shared base)

All item types inherit these fields. Defined in `system/src/models/items/_BaseItemSD.mjs`.

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `description` | `HTMLField` | `""` | Rich HTML description. |
| `source.title` | `StringField` | `""` | Source book/publication title. |
| `properties` | `ArrayField<DocumentUUIDField>` | `[]` | UUIDs of Property items attached to this item. |

**Getters:**

| Getter | Returns |
|--------|---------|
| `isPhysical` | `false` (overridden in PhysicalItemSD) |
| `propertyNames` | Array of slugified property names |

**Methods:**

| Method | Description |
|--------|-------------|
| `hasProperty(property)` | Returns `true` if a property with the given name (slugified) is attached. |
| `render(data, template)` | Renders the item as HTML for chat cards. |

---

### PhysicalItemSD (physical base)

Extends: `BaseItemSD`
Defined in: `system/src/models/items/_PhysicalItemSD.mjs`

All physical items additionally include:

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `broken` | `BooleanField` | `false` | Whether the item is broken. |
| `cost.cp` | `NumberField` (integer) | `0` | min: 0. Cost in copper pieces. |
| `cost.gp` | `NumberField` (integer) | `0` | min: 0. Cost in gold pieces. |
| `cost.sp` | `NumberField` (integer) | `0` | min: 0. Cost in silver pieces. |
| `equipped` | `BooleanField` | `false` | Whether the item is currently equipped. |
| `identification.description` | `StringField` | `""` | Description when unidentified. |
| `identification.identified` | `BooleanField` | `true` | Identified state. |
| `identification.name` | `StringField` | `""` | Name when unidentified. |
| `isAmmunition` | `BooleanField` | `false` | Whether this item is ammunition. |
| `magicItem` | `BooleanField` | `false` | Whether this is a magic item. |
| `quantity` | `NumberField` (integer) | `1` | min: 0. |
| `slots.free_carry` | `NumberField` (integer) | `0` | Number of this item carried for free. |
| `slots.per_slot` | `NumberField` (integer) | `1` | Quantity that fits in one slot. |
| `slots.slots_used` | `NumberField` (integer) | `1` | Gear slots used per unit. |
| `stashed` | `BooleanField` | `false` | Whether the item is stashed (not counted in carried gear). |

**Getters:**

| Getter | Returns | Notes |
|--------|---------|-------|
| `canBeEquipped` | `false` | Overridden to `true` in Armor and Weapon. |
| `hasMultiple` | boolean | `isAmmunition || slots.per_slot > 1` |
| `isPhysical` | `true` | |
| `isRollable` | `false` | Overridden in Weapon, Scroll, Wand, Spell. |
| `slotsUsed` | number | `Math.ceil(quantity / per_slot) * slots_used` |
| `isIdentified` | boolean | `identification.identified` |

---

### Ancestry

Extends: `BaseItemSD`
Model file: `system/src/models/items/AncestrySD.mjs`

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| *(from `languageChoices()`)* | — | — | See [languageChoices](#languagechoices). |
| `talents` | `ArrayField<DocumentUUIDField>` | `[]` | UUIDs of Talent items on the ancestry talent table. |
| `talentChoiceCount` | `NumberField` (integer) | `1` | min: 0. Number of talents the player chooses. |
| `nameTable` | `DocumentUUIDField` | `null` | UUID of a RollTable for random name generation. |
| `randomWeight` | `NumberField` (integer) | `1` | min: 1. Weight in random ancestry selection. |

---

### Armor

Extends: `PhysicalItemSD`
Model file: `system/src/models/items/ArmorSD.mjs`

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `ac.attribute` | `StringField` | `"dex"` | Ability modifier added to AC. Only `"dex"` is currently valid. Can be blank. |
| `ac.base` | `NumberField` (integer) | `0` | Base AC value. 0 means this is a bonus item (e.g. shield). |
| `ac.modifier` | `NumberField` (integer) | `0` | Static modifier added to AC. |
| `baseArmor` | `StringField` | `""` | Slug identifying the base armor type (used as AE selector). |

**Getters:**

| Getter | Returns | Notes |
|--------|---------|-------|
| `canBeEquipped` | `true` | |
| `isArmor` | `true` | |
| `isAShield` | boolean | `hasProperty("shield")` |

**AC formula:** `ac.base + abilities[ac.attribute].mod + ac.modifier`, then AEs applied.
Items with `ac.base === 0` are treated as bonus armor (shields). Items with `ac.base > 0` are main armor.

---

### Background

Extends: `BaseItemSD`
Model file: `system/src/models/items/BackgroundSD.mjs`

No additional fields beyond `BaseItemSD`.

---

### Basic

Extends: `PhysicalItemSD`
Model file: `system/src/models/items/BasicSD.mjs`

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| *(from `lightSource()`)* | — | — | See [lightSource](#lightsource). |
| `scroll` | `BooleanField` | `false` | Legacy field; prefer the Scroll item type. |
| `treasure` | `BooleanField` | `false` | Whether this item counts as treasure. |

---

### Boon

Extends: `BaseItemSD`
Model file: `system/src/models/items/BoonSD.mjs`

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `boonType` | `StringField` | `"oath"` | Choices: see [Boon Types enum](#boon-types). |
| `level` | `NumberField` (integer) | `0` | min: 0. Boon level or power tier. |

---

### Class

Extends: `BaseItemSD`
Model file: `system/src/models/items/ClassSD.mjs`

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| *(from `languageChoices()`)* | — | — | See [languageChoices](#languagechoices). |
| `alignment` | `StringField` | `"neutral"` | Required alignment for this class. Choices: see [Alignments enum](#alignments). |
| `allArmor` | `BooleanField` | `false` | Proficiency in all armor. |
| `allMeleeWeapons` | `BooleanField` | `false` | Proficiency in all melee weapons. |
| `allRangedWeapons` | `BooleanField` | `false` | Proficiency in all ranged weapons. |
| `allWeapons` | `BooleanField` | `false` | Proficiency in all weapons. |
| `armor` | `ArrayField<DocumentUUIDField>` | `[]` | Specific armor UUIDs this class can use. |
| `classAbilities` | `ArrayField<DocumentUUIDField>` | `[]` | UUIDs of Class Ability items granted automatically. |
| `classAbilityChoices` | `ArrayField<DocumentUUIDField>` | `[]` | UUIDs of Class Ability items available to choose from. |
| `classAbilityChoiceCount` | `NumberField` (integer) | `0` | min: 0. How many abilities the player picks. |
| `classTalentTable` | `DocumentUUIDField` | `null` | UUID of the RollTable for class talents. |
| `hitPoints` | `StringField` | `"d6"` | Hit die formula (e.g. `"d6"`, `"d8"`, `"d10"`). |
| `patron.required` | `BooleanField` | `false` | Whether this class requires a patron. |
| `patron.startingBoons` | `NumberField` (integer) | `0` | Boons granted at character creation. |
| `spellcasting.ability` | `StringField` | `""` | Ability key used for spell checks. Blank = non-casting. Choices: see [Ability Keys](#ability-keys). |
| `spellcasting.baseDifficulty` | `NumberField` (integer) | `10` | min: 0. Base spell DC. |
| `spellcasting.class` | `StringField` | `""` | Internal spellcasting class identifier string. |
| `spellcasting.spellsknown` | `SchemaField` | — | Nested object: `spellsknown[level][tier]` = count. Levels 1–10, tiers 1–5. |
| `talents` | `ArrayField<DocumentUUIDField>` | `[]` | UUIDs of Talent items granted automatically. |
| `talentChoices` | `ArrayField<DocumentUUIDField>` | `[]` | UUIDs of Talent items available to choose from. |
| `talentChoiceCount` | `NumberField` (integer) | `0` | min: 0. |
| `titles` | `ArrayField<SchemaField>` | `[]` | Title range entries (see below). |
| `weapons` | `ArrayField<DocumentUUIDField>` | `[]` | Specific weapon UUIDs this class can use. |

**Title entry schema:**

| Sub-field | Type | Notes |
|-----------|------|-------|
| `from` | `NumberField` (integer, min: 0) | Min level for this title. |
| `to` | `NumberField` (integer, min: 0) | Max level for this title. |
| `lawful` | `StringField` | Title for lawful characters. |
| `neutral` | `StringField` | Title for neutral characters. |
| `chaotic` | `StringField` | Title for chaotic characters. |

**Getters:**

| Getter | Returns | Notes |
|--------|---------|-------|
| `isCastingClass` | boolean | `spellcasting.ability !== ""` |

---

### Class Ability

Extends: `BaseItemSD`
Model file: `system/src/models/items/ClassAbilitySD.mjs`

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `ability` | `StringField` | `""` | Ability key for the activation roll. Blank = no roll required. Choices: see [Ability Keys](#ability-keys). |
| `group` | `StringField` | `""` | Display grouping label on the character sheet. |
| `dc` | `NumberField` (integer) | `10` | min: 0. Difficulty class for the ability roll. |
| `limitedUses` | `BooleanField` | `false` | Whether this ability has limited uses per rest/day. |
| `loseOnFailure` | `BooleanField` | `true` | Whether the ability is marked `lost` on a failed roll. |
| `lost` | `BooleanField` | `false` | Whether the ability has been used up / lost. |
| `uses.available` | `NumberField` (integer) | `0` | min: 0. Remaining uses. |
| `uses.max` | `NumberField` (integer) | `0` | min: 0. Maximum uses. |

---

### Deity

Extends: `BaseItemSD`
Model file: `system/src/models/items/DeitySD.mjs`

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `alignment` | `StringField` | `"neutral"` | Deity's alignment. Choices: see [Alignments enum](#alignments). |

---

### Effect

Extends: `BaseItemSD`
Model file: `system/src/models/items/EffectSD.mjs`

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| *(from `lightSource()`)* | — | — | See [lightSource](#lightsource). |
| `duration.type` | `StringField` | `"rounds"` | Choices: see [Effect Durations enum](#effect-durations). |
| `duration.value` | `NumberField` (integer) | `1` | Duration count. |
| `category` | `StringField` | `"effect"` | Choices: `"effect"`, `"condition"`. |
| `effectPanel.show` | `BooleanField` | `true` | Whether to show this effect in the effect panel. |
| `start.combatTime` | `NumberField` | `null` | Combat round/turn when effect started (format: `"round.turn"`). |
| `start.value` | `NumberField` | `0` | World time (seconds) when effect was created. |
| `tokenIcon.show` | `BooleanField` | `true` | Whether to show the effect icon on tokens. |

**Computed on `ItemSD` document:**

| Property | Description |
|----------|-------------|
| `totalDuration` | Seconds. `Infinity` for unlimited/focus/permanent; `0` for instant; else `value * DURATION_UNITS[type]`. |
| `remainingDuration` | `{expired: bool, remaining: number, progress: number}` or `false` for non-Effect items. For `"rounds"` type, uses combat tracker; for time types, uses world time. |

---

### Gem

Extends: `PhysicalItemSD`
Model file: `system/src/models/items/GemSD.mjs`

No additional fields beyond `PhysicalItemSD`.

**Getters:**

| Getter | Returns |
|--------|---------|
| `isGem` | `true` |

Gems are counted separately for encumbrance: 10 gems per gear slot (`GEMS_PER_SLOT = 10`).

---

### Language

Extends: `BaseItemSD`
Model file: `system/src/models/items/LanguageSD.mjs`

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `rarity` | `StringField` | `"common"` | Choices: `"common"`, `"rare"`. |

---

### NPC Attack

Extends: `BaseItemSD`
Model file: `system/src/models/items/NpcAttackSD.mjs`

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| *(from `ranges()`)* | — | — | See [ranges](#ranges). |
| `attack.num` | `NumberField` (integer) | `1` | min: 1. Number of attacks per action. |
| `bonuses.attackBonus` | `NumberField` (integer) | `0` | min: 0. Flat attack roll bonus. |
| `bonuses.critical.failureThreshold` | `NumberField` (integer) | `1` | Critical failure threshold. |
| `bonuses.critical.multiplier` | `NumberField` (integer) | `2` | Crit damage multiplier. |
| `bonuses.critical.successThreshold` | `NumberField` (integer) | `20` | Critical success threshold. |
| `bonuses.damageBonus` | `NumberField` (integer) | `0` | min: 0. Flat damage bonus. |
| `damage.numDice` | `NumberField` (integer) | `1` | min: 1. |
| `damage.special` | `StringField` | `""` | Comma-separated list of special feature names whose descriptions are appended in chat. |
| `damage.value` | `StringField` | `""` | Dice formula string (e.g. `"1d8"`). |

---

### NPC Feature

Extends: `BaseItemSD`
Model file: `system/src/models/items/NpcFeatureSD.mjs`

No additional fields beyond `BaseItemSD`. NPC Features are descriptive text blocks attached to NPC actors and referenced by NPC Attack items via `damage.special`.

**Getters:**

| Getter | Returns |
|--------|---------|
| `isNPCFeature` | `true` |

---

### NPC Special Attack

Extends: `BaseItemSD`
Model file: `system/src/models/items/NpcSpecialAttackSD.mjs`

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| *(from `ranges()`)* | — | — | See [ranges](#ranges). |
| `attack.num` | `NumberField` (integer) | `1` | min: 1. Number of attacks per action. |
| `bonuses.attackBonus` | `NumberField` (integer) | `0` | min: 0. |

---

### Patron

Extends: `BaseItemSD`
Model file: `system/src/models/items/PatronSD.mjs`

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `boonTable` | `DocumentUUIDField` | `null` | UUID of a RollTable for patron boons. |

---

### Potion

Extends: `PhysicalItemSD`
Model file: `system/src/models/items/PotionSD.mjs`

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| *(from `magic()`)* | — | — | See [magic](#magic). Includes `class`, `damageType`, `duration`, `formula`, `range`, `lost`. |
| `magicItem` | `BooleanField` | `true` | Always true for potions. |
| `spellName` | `StringField` | `""` | Display name of the potion's spell effect. |

---

### Property

Extends: `BaseItemSD`
Model file: `system/src/models/items/PropertySD.mjs`

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `itemType` | `StringField` | `"armor"` | Choices: `"armor"`, `"weapon"`. |

Properties are tag items attached to weapons/armor via their `properties` array. The name slug is used as an AE selector.

---

### Scroll

Extends: `PhysicalItemSD`
Model file: `system/src/models/items/ScrollSD.mjs`

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `spellUuid` | `DocumentUUIDField` | `null` | UUID of the Spell item this scroll contains. |

`magicItem` is always forced to `true` in `prepareBaseData`.

**Getters:**

| Getter | Returns |
|--------|---------|
| `isRollable` | `true` |
| `isScroll` | `true` |

---

### Spell

Extends: `BaseItemSD`
Model file: `system/src/models/items/SpellSD.mjs`

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| *(from `magic()`)* | — | — | See [magic](#magic). Includes `class`, `damageType`, `duration`, `formula`, `range`, `lost`. |
| `tier` | `NumberField` (integer) | `1` | Spell tier (1–5 in standard rules). |

**Derived (computed, not stored):**

| Field | Value | Notes |
|-------|-------|-------|
| `dc` | `tier + 10` | Difficulty class for the spell check. |

**Getters:**

| Getter | Returns |
|--------|---------|
| `isRollable` | `true` |
| `isSpell` | `true` |

---

### Talent

Extends: `BaseItemSD`
Model file: `system/src/models/items/TalentSD.mjs`

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `level` | `NumberField` (integer) | `0` | min: 0. Level at which this talent was obtained. |
| `talentClass` | `StringField` | `"level"` | Choices: see [Talent Classes enum](#talent-classes). |

---

### Wand

Extends: `PhysicalItemSD`
Model file: `system/src/models/items/WandSD.mjs`

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `broken` | `BooleanField` | `false` | Whether the wand is broken. |
| `spells` | `ArrayField<SchemaField>` | `[]` | Array of spell slot objects (see below). |

**Spell slot entry schema:**

| Sub-field | Type | Default | Notes |
|-----------|------|---------|-------|
| `uuid` | `DocumentUUIDField` | `null` | UUID of the Spell item. |
| `lost` | `BooleanField` | `false` | Whether this spell has been lost. |

`magicItem` is always forced to `true` in `prepareBaseData`.

**Getters:**

| Getter | Returns |
|--------|---------|
| `isRollable` | `true` |
| `isWand` | `true` |

---

### Weapon

Extends: `PhysicalItemSD`
Model file: `system/src/models/items/WeaponSD.mjs`

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `ammoClass` | `StringField` | `""` | Ammunition class key. Non-empty = consumes matching ammo. |
| `baseWeapon` | `StringField` | `""` | Slug identifying the base weapon type (used as AE selector). |
| `damage.oneHanded` | `StringField` | `""` | Damage die key for one-handed use (e.g. `"d6"`). See [Weapon Base Damage enum](#weapon-base-damage). |
| `damage.twoHanded` | `StringField` | `""` | Damage die key for two-handed use. |
| `handedness` | `StringField` | `""` | Choices: `"1h"`, `"2h"`. Auto-determined in `prepareBaseData` if blank. |
| `range` | `StringField` | `"close"` | Choices: see [Ranges enum](#ranges-1). |
| `type` | `StringField` | `"melee"` | Choices: `"melee"`, `"ranged"`. |

**Handedness auto-determination:** Set to `"2h"` if the weapon has the `two-handed` property OR if `damage.oneHanded` is empty and `damage.twoHanded` is not. Otherwise defaults to `"1h"`.

**Getters:**

| Getter | Returns | Notes |
|--------|---------|-------|
| `canBeEquipped` | `true` | |
| `isFinesse` | boolean | `hasProperty("finesse")` |
| `isRollable` | `true` | |
| `isThrown` | boolean | `hasProperty("thrown")` |
| `isVersatile` | boolean | `hasProperty("versatile")` |
| `isWeapon` | `true` | |

**Attack type resolution:** Melee uses STR mod by default; uses DEX if `finesse` and DEX mod > STR mod. Ranged always uses DEX mod. Thrown weapons generate both melee and ranged attack options.

---

## Enums and Constants

All defined in `system/src/config.mjs` as `CONFIG.SHADOWDARK.*`.

### Ability Keys

```
str   — Strength
int   — Intelligence
dex   — Dexterity
wis   — Wisdom
con   — Constitution
cha   — Charisma
```

Order: `["str", "int", "dex", "wis", "con", "cha"]`

Modifier formula: `Math.min(4, Math.max(-4, Math.floor((score - 10) / 2)))`
Range: -4 (score 1–2) to +4 (score 18+)

---

### Alignments

| Key | Display |
|-----|---------|
| `lawful` | Lawful |
| `neutral` | Neutral |
| `chaotic` | Chaotic |

---

### Dice

All dice: `d2  d4  d6  d8  d10  d12  d20`

Damage dice (weapon damage): `d4  d6  d8  d10  d12`

---

### Weapon Base Damage

| Key | Formula |
|-----|---------|
| `1` | `"1"` (flat 1 damage) |
| `d2` | `"1d2"` |
| `d4` | `"1d4"` |
| `d6` | `"1d6"` |
| `d8` | `"1d8"` |
| `d10` | `"1d10"` |
| `d12` | `"1d12"` |

---

### Weapon Types

`melee` | `ranged`

---

### Ranges

Used for weapon ranges and NPC attack ranges:

| Key | Meaning |
|-----|---------|
| `close` | Close |
| `near` | Near |
| `far` | Far |
| `nearLine` | Near (line) |

---

### Spell Ranges

| Key | Meaning |
|-----|---------|
| `self` | Self |
| `touch` | Touch |
| `close` | Close |
| `near` | Near |
| `doubleNear` | Double near |
| `far` | Far |
| `oneMile` | One mile |
| `samePlane` | Same plane |
| `unlimited` | Unlimited |

---

### Spell Damage Types

| Key | Meaning |
|-----|---------|
| `none` | None |
| `damage` | Damage |
| `healing` | Healing |

---

### Spell Durations

| Key | Variable? | Notes |
|-----|-----------|-------|
| `focus` | No | Ends when caster stops concentrating |
| `instant` | No | Instantaneous |
| `rounds` | Yes | Combat rounds |
| `turns` | Yes | 10-minute turns |
| `days` | Yes | Days |
| `realTime` | Yes | Real-world time |
| `permanent` | No | Permanent |

Variable durations require a numeric `duration.value`; non-variable durations ignore it.

---

### Effect Durations

| Key | Seconds multiplier |
|-----|-------------------|
| `instant` | 0 |
| `seconds` | 1 |
| `rounds` | 6 |
| `minutes` | 60 |
| `turns` | 600 |
| `hours` | 3600 |
| `days` | 86400 |
| `focus` | Infinity |
| `permanent` | Infinity |
| `unlimited` | Infinity |

---

### Effect Categories

`effect` | `condition`

---

### Boon Types

`blessing` | `oath` | `secret`

---

### Talent Classes

| Key | Notes |
|-----|-------|
| `ancestry` | Gained from ancestry. |
| `class` | Gained from class. |
| `level` | Gained at level-up. |
| `patronBoon` | Gained from patron boon; displayed in the "level" section. |

---

### Language Rarity

`common` | `rare`

---

### Property Types

`armor` | `weapon`

---

### NPC Moves

| Key | Meaning |
|-----|---------|
| `none` | None |
| `close` | Close |
| `near` | Near |
| `doubleNear` | Double near |
| `tripleNear` | Triple near |
| `far` | Far |
| `special` | Special (see moveNote) |

---

### Light Source Templates

| Key | Meaning |
|-----|---------|
| `lantern` | Lantern |
| `lightSpellDouble` | Light spell (double near) |
| `lightSpellNear` | Light spell (near) |
| `torch` | Torch |

Light brightness/radius data is loaded from `systems/shadowdark/assets/mappings/map-light-sources.json`.

---

### Official Sources

| Key | Label |
|-----|-------|
| `core-rules` | Core Rules |
| `quickstart` | Quickstart |
| `bard-and-ranger` | Bard & Ranger |
| `cursed-scroll-1` … `cursed-scroll-6` | Cursed Scroll 1–6 |

---

## Active Effect Keys and Predefined Effects

The system uses Foundry's Active Effects system with a custom multi-key lookup engine (`_getActiveEffectKeys`). Effect keys target `system.*` paths and can use item-specific selectors.

### Effect Key Resolution

When looking up an AE key, the engine expands the search:

1. Base key (e.g. `system.roll.melee.bonus.sword-name`)
2. For melee/ranged roll keys, also checks `system.roll.attack.*`
3. For stat roll keys (`system.roll.stat.X`), also checks `system.roll.stat.all`
4. If an item is provided, adds item-specific selector keys:
   - `{base}.all`
   - `{base}.{property-slug}` for each property
   - `{base}.{baseArmor}` or `{base}.{baseWeapon}`
   - `{base}.{item-name-slug}`
5. The `.this` suffix matches AEs on the triggering item itself

### Stored Effect Shape (Foundry v14)

The vendored system source (and the tables below) uses the pre-v14 `mode: CONST.ACTIVE_EFFECT_MODES.*` constants. Live v14 world data (observed on core 14.363, Shadowdark 4.0.6) stores changes differently:

- Changes live under `effect.system.changes`, **not** `effect.changes`.
- Each change has a lowercase string `type` instead of a numeric `mode`, plus a `phase`:

```json
{
  "name": "Mighty",
  "disabled": false,
  "transfer": true,
  "origin": "Compendium.shadowdark.talents.Item.LR6h4lXVXwx7AFQ6",
  "system": {
    "changes": [
      {"key": "system.roll.melee.bonus.all", "type": "add", "value": 1, "phase": "initial", "priority": null}
    ]
  }
}
```

Observed `type` values: `add`, `subtract`. Others presumably mirror the mode names in lowercase (`multiply`, `override`, …) but have not been verified. `value` may be a number or a roll-data formula string such as `1+floor(@level.value/2)`.

Effects appear in two places in an actor's source data: `actor.effects[]` (on the actor itself) and `actor.items[].effects[]` (transferred from embedded items such as talents). Both come back in a single `Actor` get over the socket.

### Effect Modes

| Mode | Behavior |
|------|----------|
| `ADD` | Numerically adds; string values concatenated. |
| `MULTIPLY` | Multiplies the current value. |
| `OVERRIDE` | Replaces the current value entirely. |

### Predefined Effect Templates (`CONFIG.SHADOWDARK.PREDEFINED_EFFECTS`)

| Key | Effect Key | Mode | Default Value | Notes |
|-----|-----------|------|---------------|-------|
| `abilityImprovementStr` | `system.abilities.str.value` | ADD | 1 | |
| `abilityImprovementInt` | `system.abilities.int.value` | ADD | 1 | |
| `abilityImprovementDex` | `system.abilities.dex.value` | ADD | 1 | |
| `abilityImprovementWis` | `system.abilities.wis.value` | ADD | 1 | |
| `abilityImprovementCon` | `system.abilities.con.value` | ADD | 1 | |
| `abilityImprovementCha` | `system.abilities.cha.value` | ADD | 1 | |
| `permanentAbilityStr` | `system.abilities.str.value` | OVERRIDE | 18 | |
| `permanentAbilityInt` | `system.abilities.int.value` | OVERRIDE | 18 | |
| `permanentAbilityDex` | `system.abilities.dex.value` | OVERRIDE | 18 | |
| `permanentAbilityWis` | `system.abilities.wis.value` | OVERRIDE | 18 | |
| `permanentAbilityCon` | `system.abilities.con.value` | OVERRIDE | 18 | |
| `permanentAbilityCha` | `system.abilities.cha.value` | OVERRIDE | 18 | |
| `acBonus` | `system.attributes.ac.value` | ADD | 1 | |
| `acBonusFromAttribute` | `system.attributes.ac.value` | ADD | `system.attributes.REPLACEME.mod` | Replace REPLACEME with ability key. |
| `unarmoredAcBonus` | `system.attributes.ac.unarmored` | ADD | 1 | Only applies when unarmored. |
| `armorMastery` | `system.attributes.ac.REPLACEME` | ADD | 1 | Replace REPLACEME with armor type slug. |
| `stoneSkinTalent` | `system.attributes.ac.value` | ADD | `2+floor(@level.value/2)` | Formula using roll data. |
| `additionalGearSlots` | `system.slots` | ADD | 1 | |
| `meleeAttackBonus` | `system.roll.melee.bonus.all` | ADD | 1 | |
| `meleeDamageBonus` | `system.roll.melee.damage.all` | ADD | 1 | |
| `rangedAttackBonus` | `system.roll.ranged.bonus.all` | ADD | 1 | |
| `rangedDamageBonus` | `system.roll.ranged.damage.all` | ADD | 1 | |
| `weaponAttackBonus` | `system.roll.attack.bonus.this` | ADD | 1 | On the weapon item itself. |
| `weaponDamageBonus` | `system.roll.attack.damage.this` | ADD | 1 | On the weapon item itself. |
| `weaponDamageDieD12` | `system.roll.attack.upgrade-damage-die.REPLACEME` | ADD | 4 | Upgrades die by N steps toward d12. |
| `weaponDamageDieImprovementByProperty` | `system.roll.attack.upgrade-damage-die.REPLACEME` | ADD | 1 | |
| `damageMultiplier` | `system.roll.attack.damage.this` | MULTIPLY | 2 | |
| `weaponDamageMultiplier` | `system.roll.attack.damage.this` | OVERRIDE | 2 | |
| `criticalSuccessThreshold` | `system.roll.attack.critical-success.this` | OVERRIDE | 18 | |
| `criticalFailureThreshold` | `system.roll.attack.critical-failure.this` | OVERRIDE | 3 | |
| `critMultiplier` | `system.roll.attack.critical-multiplier.this` | OVERRIDE | 4 | |
| `spellCastingBonus` | `system.roll.spell.advantage.all` | ADD | 1 | |
| `spellAdvantage` | `system.roll.spell.advantage.REPLACEME` | ADD | 1 | Replace REPLACEME with spell slug. |
| `spellDamageBonus` | `system.roll.spell.damage` | ADD | 1 | |
| `spellcastingClasses` | `system.spellcasting.classes` | ADD | `REPLACEME` | Grants spellcasting ability for a class. |
| `hpAdvantage` | `system.roll.hp.advantage` | ADD | 1 | |
| `initAdvantage` | `system.roll.initiative.advantage` | ADD | 1 | |
| `lightSource` | `system.light.template` | OVERRIDE | `REPLACEME` | Replace with light template key. |
| `weaponMastery` | `system.bonuses.weaponMastery` | ADD | 1 | |

---

## Socket Events

Channel: `system.shadowdark`

All events are objects with a `type` string property.

### Event: `createCharacter`

**Direction:** Any client → GM only

| Field | Type | Notes |
|-------|------|-------|
| `payload.characterData` | object | Actor data for the new character. |
| `payload.characterItems` | array | Item data array for the new character. |
| `payload.userId` | string | User ID of the requesting player. |
| `payload.level0` | boolean | Whether to create a level-0 character. |

### Event: `openNewCharacter`

**Direction:** GM → specific client

| Field | Type | Notes |
|-------|------|-------|
| `payload.userId` | string | Target user ID. |
| `payload.actorId` | string | Actor ID of the created character. |

### Event: `dropLightSourceOnScene`

**Direction:** Any client → GM only

| Field | Type | Notes |
|-------|------|-------|
| `data.item` | object | Item data. |
| `data.itemOwner` | object | Owner actor data. |
| `data.actorData` | object | Actor data for the light token to create. |
| `data.dropData` | object | Drop coordinates/scene data. |
| `data.speaker` | object | Chat speaker data. |

### Event: `pickupLightSourceFromScene`

**Direction:** Any client → GM only

| Field | Type | Notes |
|-------|------|-------|
| `data.character` | object | Character actor data. |
| `data.lightActor` | object | Light actor being picked up. |
| `data.speaker` | object | Chat speaker data. |

### Event: `toggleLightSource`

**Direction:** Any client → GM only

| Field | Type | Notes |
|-------|------|-------|
| `data.actor` | object | Actor data. |
| `data.item` | object | Light source item data. |

---

## Document-Level API

### ActorSD (extends `foundry.documents.Actor`)

| Method | Description |
|--------|-------------|
| `applyDamage(amount, multiplier=1)` | Applies damage/healing. Multiplier: 1=damage, -1=healing, 0.5=resistance. Clamps to [0, max HP]. Sets defeated status at 0 HP. |
| `ammunitionItems(key?)` | Returns carried physical items where `isAmmunition=true` and `quantity>0`. Optionally filtered by `name.slugify() === key`. |
| `getCanvasToken()` | Returns the first owned token on the current scene linked to this actor. |
| `getRollData()` | Returns `{...this.system}` modified by `_modifyRollData` (adds `initiative` formula). |
| `getActiveLightSources()` | Returns items where `isActiveLight()` is true, sorted by name. |
| `toggleLight(active, itemId)` | Turns a light source on or off. |
| `turnLightOn(itemId)` | Loads light data from `map-light-sources.json` and updates token light. |
| `turnLightOff()` | Sets token light to `{dim:0, bright:0}`. |
| `buildOptionsForSkipPrompt(event)` | Returns `{skipPrompt: bool, adv: number}` from modifier keys: Shift/Alt/Ctrl skip prompt; Alt=advantage (+1), Ctrl/Meta=disadvantage (-1). |
| `isClaimedByUser()` | Returns true if any user has this actor as their character. |

**Token defaults (set in `_preCreate`):**

| Actor type | `actorLink` | `sight.enabled` |
|-----------|-------------|-----------------|
| `Player` | `true` | `true` |
| `NPC`, `Light` | `false` | `false` |

---

### ItemSD (extends `foundry.documents.Item`)

| Member | Description |
|--------|-------------|
| `typeSlug` (getter) | `this.type.slugify()` |
| `usesAmmunition` (getter) | True when: auto-consume ammo setting on, item is owned by a Player actor, type is Weapon, and `ammoClass !== ""`. |
| `totalDuration` (getter) | Computed total duration in seconds. Only meaningful for Effect items. |
| `remainingDuration` (getter) | `false` for non-Effect items; otherwise `{expired, remaining, progress}`. |
| `isLight()` | `["Basic","Effect"].includes(type) && system.light.isSource` |
| `isActiveLight()` | `isLight() && system.light.active` |
| `isSpell()` | `["Scroll","Spell","Wand"].includes(type)` |
| `reduceAmmunition(amount)` | Decrements `system.quantity` by amount (min 0). |
| `setLightRemaining(seconds)` | Updates `system.light.remainingSecs`. |
| `npcAttackRangesDisplay()` | Returns comma-joined localized range strings for NPC attacks. |
| `getPropertyItems()` | Resolves and returns all attached Property item documents. |
| `availableAmmunition()` | Returns matching ammunition items from the actor. |

---

## System Defaults

| Constant | Value | Description |
|----------|-------|-------------|
| `BASE_ARMOR_CLASS` | `10` | Unarmored base AC. |
| `GEAR_SLOTS` | `10` | Default gear slots for a Player. |
| `GEMS_PER_SLOT` | `10` | Gems that fit in one gear slot. |
| `FREE_COIN_CARRY` | `100` | Coins carried for free (first 100 cost 0 slots). |
| `LEARN_SPELL_DC` | `15` | DC for learning a spell from a scroll. |
| `LIGHT_TRACKER_UPDATE_INTERVAL_SECS` | `30` | How often the light tracker updates. |

---

## Compendium Packs

| Pack name | Label | Type |
|-----------|-------|------|
| `ancestries` | Ancestries | Item |
| `backgrounds` | Backgrounds | Item |
| `class-abilities` | Class Abilities | Item |
| `classes` | Classes | Item |
| `conditions` | Conditions | Item |
| `documentation` | Documentation | JournalEntry |
| `gear` | Gear | Item |
| `languages` | Languages | Item |
| `macros` | Macros | Macro |
| `magic-items` | Magic Items | Item |
| `monsters` | Monsters | Actor |
| `patrons-and-deities` | Patrons and Deities | Item |
| `properties` | Properties | Item |
| `quickstart-adventures` | Quickstart Adventures | Adventure |
| `quickstart-guides` | Quickstart Guides | JournalEntry |
| `quickstart-pregens` | Quickstart Pregens | Actor |
| `rollable-tables` | Rollable Tables | RollTable |
| `solodark-journals` | SoloDark | JournalEntry |
| `spell-effects` | Spell Effects | Item |
| `spells` | Spells | Item |
| `talents` | Talents | Item |

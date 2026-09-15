# Transferring Pokemon from 3DS to Switch

Research checked 15 September 2026. These are feasibility findings, not a tested implementation. The workspace had no existing files or research convention.

## Existing pieces

- PKSM already reads cartridge and installed-game saves on a 3DS with custom firmware. It can run as a `.cia` home-menu application or a `.3dsx` homebrew application. This establishes a practical foundation for the proposed custom 3DS app. [PKSM basics](https://github.com/FlagBrew/PKSM/wiki/Basics)
- PKSM can export an individual Pokemon to a `.pkx` file on the SD card. [PKSM storage](https://github.com/FlagBrew/PKSM/wiki/Storage)
- PKSM already exchanges saves with Checkpoint over a network. Its documentation describes sending an edited save back as a backup that Checkpoint can restore. That is save editing, not a Pokemon link-trade implementation. [PKSM basics](https://github.com/FlagBrew/PKSM/wiki/Basics)
- PKSM's FAQ lists Let's Go and Sword/Shield bridge support, describes Switch save-size problems, and says there are no plans for Scarlet/Violet support. Its documented support must therefore be checked against the exact game and save version before building on it. [PKSM FAQ](https://github.com/FlagBrew/PKSM/wiki/FAQs)
- PKHeX supports individual Pokemon files and conversion between generations. Its C# conversion code implements sequential older-generation conversions, HOME-format conversion, species/form restrictions, and separate forced backwards conversions. [PKHeX](https://github.com/kwsch/PKHeX), [EntityConverter source](https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/PKM/Util/Conversion/EntityConverter.cs)
- PKSM-Core provides the existing C++ save-editing code used by PKSM. It is GPL-3.0, as is PKSM. A 3DS implementation should evaluate this before rewriting the parsers. A desktop bridge could evaluate PKHeX.Core instead. The architectural recommendations here are inferences from the libraries' existing roles. [PKSM-Core](https://github.com/FlagBrew/PKSM-Core), [PKSM](https://github.com/FlagBrew/PKSM)

## What an unmodified Switch changes

The receiver is the hard part. A 3DS can export a file, but a retail Switch game needs a communication endpoint it already understands.

The public `frlg-ldn-trade` project documents end-to-end `.pk3` trades with FireRed/LeafGreen on a real Switch. It requires Linux, Python 3.12+, a compatible Wi-Fi card, Switch keys, and a Switch game with the Direct Corner unlocked. The project has tested specific Wi-Fi chipsets and reports failures with others. This proves a specific game's local-wireless trade endpoint can be implemented outside a Switch. It does not establish support for Sword/Shield, Scarlet/Violet, or the 3DS Wi-Fi hardware. [Project README](https://github.com/tornadus/frlg-ldn-trade/blob/main/README.md)

Inference: the practical architecture to investigate is a 3DS exporter communicating over ordinary Wi-Fi to a Linux bridge. The bridge would convert the Pokemon and implement the target Switch game's trade protocol. A direct 3DS-to-Switch implementation requires separate proof that the 3DS networking hardware and software can implement the required low-level communication. No source checked here demonstrates that.

FireRed/LeafGreen uses generation-3 entities. A Pokemon from generation 6 or 7 cannot simply be renamed to `.pk3`. PKHeX's source explicitly distinguishes forced backwards conversion and sanitizes incompatible fields. Inference: using this FRLG endpoint for 3DS-era Pokemon would lose information or reject unsupported species, and would not preserve the normal forward-transfer history. It is unsuitable as a general replacement for Bank. [EntityConverter source](https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/PKM/Util/Conversion/EntityConverter.cs)

## If a modified Switch is acceptable

Inference: a smaller implementation could export from the 3DS, convert on a desktop or supported library, and import into a backed-up Switch save. PKSM's Checkpoint bridge demonstrates related save exchange, although current game support is limited. Alternatively, a second modified Switch could receive the Pokemon and a human could trade it through the game's normal local-trade interface to the user's retail Switch. Exact game compatibility remains a test requirement. [PKSM FAQ](https://github.com/FlagBrew/PKSM/wiki/FAQs)

SysBot.NET demonstrates automated trading using a real Switch with `sys-botbase`. It does not remove the need for a modified Switch and should not be described as a PC pretending to be a Switch. [SysBot.NET](https://github.com/kwsch/SysBot.NET)

Automation adds a transport complication. The Pokemon Automation project documents that local communication interrupts the network connection used by sys-botbase; its ldn-mitm workaround affects the ability to connect to an ordinary second Switch. Manual local trading or a separately validated USB approach avoids promising an unsupported network setup. [Pokemon Automation sys-botbase guide](https://pokemonautomation.github.io/SetupGuide/Controllers/Controller-sys-botbase.html)

## HOME and the official route

Bank service ends on 26 February 2027 at 03:00 UTC. The official notice says Bank-to-HOME transfers end with it. This is a confirmed shutdown date, not the older advice that no shutdown date has been announced. [Pokemon Support notice](https://support.pokemon.com/hc/fr/articles/52629477077012-Banque-Pok%C3%A9mon-et-Pok%C3%A9mon-HOME)

Bank-to-HOME currently requires a paid HOME Premium Plan. [Pokemon Support connection guide](https://support.pokemon.com/hc/en-us/articles/360038131072-About-connecting-Pok%C3%A9mon-HOME-to-different-games)

PKSM explicitly does not transfer directly to Bank or HOME. [PKSM FAQ](https://github.com/FlagBrew/PKSM/wiki/FAQs)

Creating a valid game-format record is different from creating HOME's server-side history. PKHeX's maintainer states that Pokemon crossing generations through routes that require HOME cannot legitimately lack a HOME tracker. The program can flag missing trackers, and its other maintainer explains that local legality checks cannot certify a Pokemon's unedited provenance. A custom transfer tool must not promise HOME acceptance merely because a local trade or PKHeX check succeeds. [Maintainer discussion](https://github.com/kwsch/PKHeX/discussions/4124)

## Suggested first experiment

These steps are recommendations, not completed tests.

1. Fix one source game and one destination game, and decide whether the receiving Switch must remain unmodified.
2. Export one Pokemon with PKSM and retain the original save and entity file.
3. Validate conversion into that exact destination format while preserving available identity, trainer, ribbon, and encounter data.
4. Prove the destination can receive that file. For a retail Switch and a modern game, this is the main research milestone, before building a polished 3DS interface.
5. Add a 3DS selection screen and ordinary network transfer only after receipt works.
6. Keep exports recoverable. For a future move operation, delete the source only after verified receipt and a retained backup.

Open questions include target-game trade protocol coverage, 3DS low-level Wi-Fi feasibility, future HOME acceptance, species/form limits, and exact implementation effort. The checked sources do not support a reliable schedule for a new modern-game trade emulator.

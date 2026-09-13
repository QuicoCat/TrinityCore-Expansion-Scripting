# Vanilla-era content on master: first repair batch

Target: Vanilla-era content in its modern retail form. This work does not restore
pre-Cataclysm maps, quests, or encounter versions.

Base: `scripted-master` at `e7d162e1112d440cfda517a8ba53e04e88ad9896`.
Working branch: `expansion/01-classic`.

## Blackwing Lair changes

| Area | Defect found in the base revision | Change |
| --- | --- | --- |
| Razorgore egg count | Starting the event after incrementing the counter erased the first egg when the first destruction started the event. | Start first, then count. Retain the existing threshold of 15 eggs. |
| Egg event state | No `GetData` override and no `DONE` handler; the orb could not detect phase two. | Expose the event state, record completion, and ignore further egg notifications after completion. |
| Repeated start | Another `IN_PROGRESS` notification reset progress and scheduled additional waves. | Ignore repeated starts. |
| Wipe during transition | Reset canceled waves but left the delayed phase-two callback queued. | Cancel both queued event types. |
| Orb access | No explicit guard for a completed encounter or dead Razorgore. | Reject charm attempts in those states and during phase two. |
| Reload after Razorgore | Egg creation checked Firemaw's completion state. | Check Razorgore's completion state. |
| Nefarian wipe delay | Unsigned timer decremented during combat and could wrap; a later wipe could inherit the wrong delay. | Start a fresh 30-second timer upon reaching home, tick only while pending, and expire once. Clean up constructs before setting the encounter to FAIL. |

The 15-egg threshold, spell IDs, combat rotations, 30-second Nefarian delay, and
instance's existing Nefarius respawn interval are inherited from this fork. This
batch repairs internal state handling; it does not independently establish their
accuracy against a current retail capture.

## Validation

Run from the repository root:

```sh
python3 tests/scripts/test_blackwing_lair.py -v
git diff --check
```

The two regression suites compile and execute the changed C++ method bodies,
using small fake engine collaborators. They cover first and final eggs, repeated
starts, duplicate completion notifications, reset during the transition delay,
missing boss lookup, orb guards, egg creation after completion, long combat,
timer expiry, re-engagement, and subsequent wipes.

Both suites passed on the changed sources. Both compiled but failed assertions
on the original base revision. These tests do not compile entire translation
units or validate movement, spell execution, database data, or live encounters.

Full server build was not run: CMake is unavailable in the editing environment.
No world database or game client was available. No database changes were applied.

## Required server checks

Build this branch with the toolchain used for your master server. On a test
instance with its matching world database:

1. Use the orb and destroy all 15 eggs. Verify that phase two starts after the
   final egg, charm ends, and no new add waves spawn.
2. Verify that the orb cannot charm Razorgore during phase two or after his death.
3. Reset before the last egg and during the one-second transition delay. Verify
   that a fresh attempt starts correctly and no stale phase-two event fires.
4. Kill Razorgore, leave Firemaw alive, and reload the saved instance. Verify that
   Razorgore's eggs do not reappear.
5. Fight Nefarian for longer than 30 seconds, wipe, and verify the reset fires
   once, 30 seconds after he reaches home. Verify construct cleanup and the
   existing Nefarius respawn behavior.
6. Repeat after a re-engagement to check that the next wipe gets a fresh delay.

Existing script bindings should be checked in the actual world database. The
following queries are read-only; script registration alone does not prove that
the deployed database uses it:

```sql
SELECT map, script FROM instance_template WHERE map = 469;
SELECT entry, AIName, ScriptName FROM creature_template WHERE entry IN (12435, 11583, 10162);
SELECT entry, ScriptName FROM gameobject_template WHERE entry = 177808;
SELECT spell_id, ScriptName FROM spell_script_names WHERE spell_id = 19873;
```

Expected script names respectively: `instance_blackwing_lair`;
`boss_razorgore`, `boss_nefarian`, `boss_victor_nefarius`;
`go_orb_of_domination`; and `spell_egg_event`.

## Remaining scope

This is a first repair batch, not completion of Vanilla-era scripting. No global
completion percentage has been established. Quests, outdoor NPCs, other dungeons,
loot, achievements, and the full database have not been audited.

Source inspection also found explicitly unfinished work in Ayamiss's swarmer
movement, the Bug Trio's Devour behavior, and Razorgore's phase-one death and orb
spell handling. Nefarian's class-call switch has no cases for Monk, Demon Hunter,
or Evoker. These are investigation candidates: verify intended retail behavior
and spell/data support before implementing them. None is claimed fixed here.

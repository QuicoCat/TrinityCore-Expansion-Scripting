#!/usr/bin/env python3
"""Run isolated C++ regressions against the actual encounter method bodies.

Requires Python 3 and a C++17 compiler (CXX, default c++). Engine collaborators
are small fakes: this checks state transitions, not full server integration.
Pass --source-root to verify another checkout, including the pre-fix revision.
"""

import argparse
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
BWL = Path("src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingLair")


def block(source, signature):
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end].replace(" override", "")


def run_cpp(source):
    with tempfile.TemporaryDirectory(prefix="bwl-regression-") as directory:
        path = Path(directory)
        (path / "test.cpp").write_text(source)
        compilation = subprocess.run(
            [os.environ.get("CXX", "c++"), "-std=c++17", "-Wall", "-Wextra",
             "-Werror", str(path / "test.cpp"), "-o", str(path / "test")],
            capture_output=True, text=True,
        )
        if compilation.returncode:
            raise AssertionError(compilation.stderr)
        execution = subprocess.run([str(path / "test")], capture_output=True, text=True)
        if execution.returncode:
            raise AssertionError(execution.stderr)


class BlackwingLairRegression(unittest.TestCase):
    def test_razorgore_progression_and_orb(self):
        source = (ROOT / BWL / "instance_blackwing_lair.cpp").read_text()
        header = (ROOT / BWL / "blackwing_lair.h").read_text()
        states = (ROOT / "src/server/game/Instances/InstanceScript.h").read_text()
        orb = (ROOT / BWL / "boss_razorgore.cpp").read_text()
        enums = "\n".join(block(header, "enum " + name) + ";" for name in
                          ("BWLEncounter", "BWLGameObjectIds", "BWLEvents", "BWLMisc"))
        enums += block(states, "enum EncounterState") + ";"
        get_data = (block(source, "uint32 GetData(uint32") if "uint32 GetData(uint32" in source
                    else "uint32 GetData(uint32) const { return 0; }")  # ZoneScript default
        run_cpp(r'''
#include <cassert>
#include <chrono>
#include <cstdint>
#include <map>
#include <vector>
using uint32 = std::uint32_t;
using uint8 = std::uint8_t;
using namespace std::chrono_literals;
''' + enums + r'''
struct ObjectGuid { using LowType = uint32; };
struct Player;
struct Creature
{
    bool alive = true;
    int attacks = 0, auraRemovals = 0;
    bool IsAlive() const { return alive; }
    void Attack(Player*, bool) { ++attacks; }
    void RemoveAurasDueToSpell(int) { ++auraRemovals; }
};
struct Player { int casts = 0; void CastSpell(Creature*, int) { ++casts; } };
struct GameObject { void DespawnOrUnsummon() { } };
struct Map { GameObject* GetGameObject(ObjectGuid const&) { return nullptr; } };
struct Events
{
    std::multimap<uint32, std::chrono::milliseconds> pending;
    void ScheduleEvent(uint32 id, std::chrono::milliseconds delay) { pending.emplace(id, delay); }
    void CancelEvent(uint32 id) { pending.erase(id); }
};
struct Fixture
{
    uint8 _eggCount = 0;
    uint32 _eggEvent = NOT_STARTED;
    Events _events;
    std::vector<ObjectGuid> _drakonicBonesList;
    Map map;
    Map* instance = &map;
    Creature razor;
    bool loaded = true;
    uint32 bosses[8] = {};
    Creature* GetCreature(uint32) { return loaded ? &razor : nullptr; }
    uint32 GetBossState(uint32 id) const { return bosses[id]; }
    void DoRemoveAurasDueToSpellOnPlayers(int, bool, bool) { }
''' + get_data + block(source, "void SetData(uint32") +
            block(source, "uint32 GetGameObjectEntry(") + r'''
};
constexpr int SPELL_MINDCONTROL = 42013;
struct Orb
{
    Fixture* instance;
''' + block(orb, "bool OnGossipHello(Player*") + r'''
};
int main()
{
    Fixture f;
    Orb orb{&f};
    Player player;
    orb.OnGossipHello(&player);
    assert(player.casts == 1);
    f.SetData(DATA_EGG_EVENT, SPECIAL);
    assert(f._eggCount == 1);
    assert(f.GetData(DATA_EGG_EVENT) == IN_PROGRESS);
    assert(f._events.pending.count(EVENT_RAZOR_SPAWN) == 1);
    f.SetData(DATA_EGG_EVENT, IN_PROGRESS);
    assert(f._eggCount == 1);  // Repeated start must not erase progress or duplicate waves.
    assert(f._events.pending.count(EVENT_RAZOR_SPAWN) == 1);
    for (int i = 1; i < 14; ++i)
        f.SetData(DATA_EGG_EVENT, SPECIAL);
    assert(f.GetData(DATA_EGG_EVENT) == IN_PROGRESS);
    assert(f._events.pending.count(EVENT_RAZOR_PHASE_TWO) == 0);
    f.SetData(DATA_EGG_EVENT, SPECIAL);
    assert(f.GetData(DATA_EGG_EVENT) == DONE);
    assert(f._events.pending.count(EVENT_RAZOR_PHASE_TWO) == 1);
    assert(f._events.pending.count(EVENT_RAZOR_SPAWN) == 0);
    orb.OnGossipHello(&player);
    assert(player.casts == 1);  // No charm in phase two.
    for (int i = 0; i < 300; ++i)
        f.SetData(DATA_EGG_EVENT, SPECIAL);
    assert(f._eggCount == 15);
    assert(f._events.pending.count(EVENT_RAZOR_PHASE_TWO) == 1);
    f.SetData(DATA_EGG_EVENT, NOT_STARTED);
    assert(f._eggCount == 0 && f.GetData(DATA_EGG_EVENT) == NOT_STARTED);
    assert(f._events.pending.empty());  // Wipe during the phase-transition delay.
    f.loaded = false;
    for (int i = 0; i < 15; ++i)
        f.SetData(DATA_EGG_EVENT, SPECIAL);
    assert(f.GetData(DATA_EGG_EVENT) == DONE);
    f.loaded = true;
    f.SetData(DATA_EGG_EVENT, NOT_STARTED);
    f.bosses[DATA_RAZORGORE_THE_UNTAMED] = DONE;
    orb.OnGossipHello(&player);
    assert(player.casts == 1);  // Completed encounter cannot be charmed.
    assert(f.GetGameObjectEntry(0, GO_BLACK_DRAGON_EGG) == 0);
    assert(f.GetGameObjectEntry(0, GO_PORTCULLIS_RAZORGORE) == GO_PORTCULLIS_RAZORGORE);
    f.bosses[DATA_RAZORGORE_THE_UNTAMED] = NOT_STARTED;
    f.bosses[DATA_FIREMAW] = DONE;
    assert(f.GetGameObjectEntry(0, GO_BLACK_DRAGON_EGG) == GO_BLACK_DRAGON_EGG);
    f.razor.alive = false;
    orb.OnGossipHello(&player);
    assert(player.casts == 1);
}
''')

    def test_nefarian_wipe_timer(self):
        source = (ROOT / BWL / "boss_nefarian.cpp").read_text().split("struct boss_nefarian :", 1)[1]
        update = block(source, "void UpdateAI(uint32 diff)")
        # Execute the real reset/victim gate; spell rotation is outside this regression.
        update = update.split("events.Update(diff);", 1)[0] + "}"
        run_cpp(r'''
#include <cassert>
#include <cstdint>
using uint32 = std::uint32_t;
constexpr int DATA_NEFARIAN = 7, FAIL = 2, ACTION_BONE_CONSTRUCT_DESPAWN = 1;
struct AI { int cleanups = 0; void DoAction(int) { ++cleanups; } };
struct Unit
{
    AI ai;
    bool IsAIEnabled() const { return true; }
    AI* GetAI() { return &ai; }
};
struct TempSummon { Unit owner; Unit* GetSummonerUnit() { return &owner; } };
struct Creature { TempSummon temp; TempSummon* ToTempSummon() { return &temp; } };
struct Instance
{
    int failures = 0;
    void SetBossState(int, int) { ++failures; }
};
struct Fixture
{
    bool _despawn = false, _phase3 = false, _sayLowHealth = false, victim = false;
    uint32 _despawnTimer = 0;
    Creature creature;
    Creature* me = &creature;
    Instance state;
    Instance* instance = &state;
    bool UpdateVictim() const { return victim; }
''' + block(source, "void Initialize()") + block(source, "void JustReachedHome()") + update + r'''
};
int main()
{
    Fixture f;
    f.Initialize();
    f.victim = true;
    f.UpdateAI(45000);  // A long active encounter cannot consume or underflow the timer.
    assert(f._despawnTimer == 30000 && f.state.failures == 0);
    f.victim = false;
    f.JustReachedHome();
    f.UpdateAI(29999);
    assert(f.state.failures == 0);
    f.UpdateAI(1);
    assert(f.state.failures == 1 && f.creature.temp.owner.ai.cleanups == 1);
    f.UpdateAI(60000);
    assert(f.state.failures == 1);  // Timeout fires only once.
    f.JustReachedHome();
    f.UpdateAI(10000);
    f.victim = true;
    f.UpdateAI(1);  // Re-engagement cancels this pending reset.
    assert(!f._despawn);
    f.victim = false;
    f.JustReachedHome();
    f.UpdateAI(29999);
    assert(f.state.failures == 1);  // A subsequent wipe gets the full delay.
    f.UpdateAI(1000);  // Oversized tick still expires without unsigned wraparound.
    assert(f.state.failures == 2 && f.creature.temp.owner.ai.cleanups == 2);
}
''')


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path)
    options, remaining = parser.parse_known_args()
    if options.source_root:
        ROOT = options.source_root.resolve()
    unittest.main(argv=[__file__, *remaining])

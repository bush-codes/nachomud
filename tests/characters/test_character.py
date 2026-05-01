"""Tests for character.py — character construction with stats + race + class."""
from __future__ import annotations

import pytest

from nachomud.characters.character import (
    caster_mod,
    class_attack_bonus,
    class_damage_mod,
    create_character,
    save_throw_bonus,
    spell_attack,
    spell_save_dc,
)
from nachomud.rules.stats import Stats


def _standard() -> Stats:
    return Stats(STR=15, DEX=14, CON=13, INT=12, WIS=10, CHA=8)


# ── Construction ──

def test_create_l1_warrior():
    a = create_character("Aric", "Human", "Warrior", _standard())
    assert a.name == "Aric"
    assert a.agent_class == "Warrior"
    assert a.race == "Human"
    assert a.level == 1


def test_dwarf_warrior_hp():
    s = Stats(STR=15, DEX=12, CON=14, INT=8, WIS=10, CHA=13)
    a = create_character("Aric", "Dwarf", "Warrior", s)
    # Dwarf gives +2 CON, +1 STR. Final CON 16, mod +3. d10 + 3 = 13.
    assert a.stats["CON"] == 16
    assert a.hp == 13
    assert a.max_hp == 13


def test_dwarf_warrior_ac():
    # DEX 12 mod +1; chainmail base 16, max_dex 2
    s = Stats(STR=15, DEX=12, CON=14, INT=8, WIS=10, CHA=13)
    a = create_character("Aric", "Dwarf", "Warrior", s)
    assert a.ac == 17


def test_dwarf_warrior_attack_bonus():
    # STR 16 mod +3, prof +2 = +5
    s = Stats(STR=15, DEX=12, CON=14, INT=8, WIS=10, CHA=13)
    a = create_character("Aric", "Dwarf", "Warrior", s)
    assert class_attack_bonus(a) == 5
    assert class_damage_mod(a) == 3


def test_elf_mage_uses_int_for_spells():
    s = Stats(STR=8, DEX=14, CON=12, INT=15, WIS=13, CHA=10)
    a = create_character("Lyria", "Elf", "Mage", s)
    # Elf +2 DEX, +1 INT → INT 16, mod +3
    assert a.stats["INT"] == 16
    assert caster_mod(a) == 3
    # Spell DC = 8 + prof 2 + INT 3 + ring spell_dc_bonus 1 = 14
    assert spell_save_dc(a) == 14


def test_human_paladin_uses_cha_for_spells():
    s = Stats(STR=15, DEX=10, CON=13, INT=8, WIS=12, CHA=14)
    a = create_character("Aldric", "Human", "Paladin", s)
    # Human +1 all → CHA 15, mod +2
    assert a.stats["CHA"] == 15
    assert caster_mod(a) == 2


def test_halfling_rogue_finesse_uses_dex():
    s = Stats(STR=8, DEX=15, CON=14, INT=13, WIS=10, CHA=12)
    a = create_character("Shade", "Halfling", "Rogue", s)
    # Halfling +2 DEX, +1 CHA → DEX 17, mod +3
    # Daggers are finesse, so attack uses DEX
    assert a.stats["DEX"] == 17
    assert class_attack_bonus(a) == 5  # DEX +3 + prof +2
    assert class_damage_mod(a) == 4   # DEX +3 + venom ring +1


def test_ranger_bow_uses_dex():
    s = Stats(STR=12, DEX=15, CON=13, INT=8, WIS=14, CHA=10)
    a = create_character("Finn", "Elf", "Ranger", s)
    # Bow is ranged, so DEX
    # Elf +2 DEX, +1 INT → DEX 17 mod +3
    assert class_attack_bonus(a) == 5  # DEX +3 + prof +2


# ── Resources ──

def test_warrior_has_ap():
    a = create_character("Kael", "Human", "Warrior", _standard())
    assert a.ap == 10
    assert a.max_ap == 10
    assert a.mp == 0


def test_mage_has_mp():
    a = create_character("Lyria", "Human", "Mage", _standard())
    assert a.mp == 25
    assert a.max_mp == 25
    assert a.ap == 0


# ── Abilities at L1 ──

def test_l1_warrior_starting_abilities():
    a = create_character("Kael", "Human", "Warrior", _standard())
    assert "attack" in a.abilities
    assert "defend" in a.abilities
    assert "cleave" not in a.abilities  # unlocks at L5


def test_l3_warrior_unlocks_taunt():
    a = create_character("Kael", "Human", "Warrior", _standard(), level=3)
    assert "taunt" in a.abilities


def test_l5_warrior_unlocks_cleave():
    a = create_character("Kael", "Human", "Warrior", _standard(), level=5)
    assert "cleave" in a.abilities
    assert "taunt" in a.abilities  # carries over


def test_l7_warrior_full_kit():
    a = create_character("Kael", "Human", "Warrior", _standard(), level=7)
    for ab in ["attack", "defend", "taunt", "cleave", "rally"]:
        assert ab in a.abilities


# ── Saves ──

def test_warrior_str_save_proficient():
    s = Stats(STR=15, DEX=12, CON=14, INT=8, WIS=10, CHA=13)
    a = create_character("Kael", "Human", "Warrior", s)
    # Human +1 → STR 16 mod +3, prof +2, Iron Band ring save_bonus +1 = +6
    assert save_throw_bonus(a, "STR") == 6


def test_warrior_dex_save_not_proficient():
    s = Stats(STR=15, DEX=12, CON=14, INT=8, WIS=10, CHA=13)
    a = create_character("Kael", "Human", "Warrior", s)
    # Human +1 → DEX 13 mod +1, no prof, Iron Band ring +1 = +2
    assert save_throw_bonus(a, "DEX") == 2


# ── Validation ──

def test_unknown_class_raises():
    with pytest.raises(ValueError):
        create_character("X", "Human", "Necromancer", _standard())


def test_unknown_race_raises():
    with pytest.raises(ValueError):
        create_character("X", "Tiefling", "Warrior", _standard())


# ── Higher level HP scaling ──

def test_l3_warrior_hp_scales():
    s = Stats(STR=15, DEX=12, CON=14, INT=8, WIS=10, CHA=13)
    a = create_character("Aric", "Dwarf", "Warrior", s, level=3)
    # L1 = 13, L2 = +9 (avg 5+1+CON3) = 22, L3 = +9 = 31
    assert a.hp == 31

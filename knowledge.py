"""Small, read-only SeerAPI knowledge layer for AstrBot function tools.

The upstream plugin and SeerAPI model code define the SQLite schema.  The
double-type arithmetic follows upstream core/type_calc.py; missing relations
are reported as unknown rather than silently treated as neutral.
"""
from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any


_MARKUP = re.compile(r"\[(?:/?color(?:=[^]]+)?|sprite name=[^]]+)\]")
_HP_FRACTION = re.compile(r"(自身|对手)?体力(不低于|不高于|低于|高于)(?:最大体力的?)?(\d+)/(\d+)")


def _clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", _MARKUP.sub("", (text or "").replace("|", "；"))).strip()


def _query(text: str) -> str:
    return (text or "").strip()[:80]


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def evaluate_hp_conditions(text: str, own_hp_percent: float | None) -> list[dict[str, Any]]:
    """Evaluate only explicit self-HP comparisons; never infer a whole effect."""
    result = []
    for match in _HP_FRACTION.finditer(_clean(text)):
        actor, operator, numerator, denominator = match.groups()
        n, d = int(numerator), int(denominator)
        if not d:
            verdict = "UNKNOWN"
        elif actor == "对手" or own_hp_percent is None:
            verdict = "UNKNOWN"
        else:
            left = own_hp_percent / 100
            right = n / d
            comparisons = {"低于": left < right, "高于": left > right,
                           "不低于": left >= right, "不高于": left <= right}
            verdict = "满足" if comparisons[operator] else "不满足"
        result.append({"原文条件": match.group(), "当前自身体力百分比": own_hp_percent,
                       "判定": verdict, "范围": "仅此明确的体力比较条件"})
    if re.search(r"(?:自身)?(?:满体力|满血)时", _clean(text)):
        result.append({"原文条件": "满体力时", "当前自身体力百分比": own_hp_percent,
                       "判定": "UNKNOWN" if own_hp_percent is None else
                       ("满足" if own_hp_percent == 100 else "不满足"),
                       "范围": "仅此明确的体力比较条件"})
    return result


class KnowledgeStore:
    def __init__(self, db_path: str | Path, alias_path: str | Path | None = None):
        self.db_path = Path(db_path)
        self.alias_path = Path(alias_path) if alias_path else None
        self._relations: tuple[tuple[int, int], dict[tuple[int, int], float]] | None = None

    def _connect(self) -> sqlite3.Connection:
        if not self.db_path.is_file():
            raise FileNotFoundError("SeerAPI SQLite 缓存尚未下载；请检查插件数据同步配置")
        db = sqlite3.connect(f"file:{self.db_path.resolve().as_posix()}?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        return db

    @staticmethod
    def _missing(kind: str, query: str) -> dict[str, Any]:
        return {"status": "not_found", "kind": kind, "query": query, "message": "本地 SeerAPI 数据未找到精确对象；不要猜测"}

    @staticmethod
    def _ambiguous(kind: str, query: str, rows: list[sqlite3.Row]) -> dict[str, Any]:
        return {"status": "ambiguous", "kind": kind, "query": query,
                "candidates": [{"id": r["id"], "name": r["name"]} for r in rows[:8]],
                "message": "请用户补充 ID 或完整名称"}

    def _find_pet(self, db: sqlite3.Connection, text: str) -> dict[str, Any]:
        name = _query(text)
        if not name:
            return self._missing("pet", name)
        if name.isdecimal():
            row = db.execute("SELECT id,name,type_id FROM pet WHERE id=?", (int(name),)).fetchone()
            return _row(row) or self._missing("pet", name)
        rows = db.execute("SELECT id,name,type_id FROM pet WHERE name=? ORDER BY id LIMIT 9", (name,)).fetchall()
        if len(rows) == 1:
            return dict(rows[0])
        if len(rows) > 1:
            return self._ambiguous("pet", name, rows)
        if self.alias_path and self.alias_path.is_file():
            try:
                alias = sqlite3.connect(f"file:{self.alias_path.resolve().as_posix()}?mode=ro", uri=True)
                try:
                    ids = [r[0] for r in alias.execute("SELECT target_id FROM pet_aliases WHERE name=? LIMIT 9", (name,))]
                finally:
                    alias.close()
                if ids:
                    rows = db.execute("SELECT id,name,type_id FROM pet WHERE id IN (" +
                                      ",".join("?" for _ in ids) + ") ORDER BY id LIMIT 9", ids).fetchall()
                    if len(rows) == 1:
                        return dict(rows[0])
                    if rows:
                        return self._ambiguous("pet", name, rows)
            except sqlite3.Error:
                pass
        rows = db.execute("SELECT id,name,type_id FROM pet WHERE name LIKE ? ESCAPE '\\' ORDER BY id LIMIT 9",
                          ("%" + name.replace("%", "\\%").replace("_", "\\_") + "%",)).fetchall()
        if len(rows) == 1:
            return dict(rows[0])
        return self._ambiguous("pet", name, rows) if rows else self._missing("pet", name)

    def _aliases_for_pet(self, pet_id: int) -> list[str]:
        if not self.alias_path or not self.alias_path.is_file():
            return []
        try:
            with closing(sqlite3.connect(f"file:{self.alias_path.resolve().as_posix()}?mode=ro", uri=True)) as alias:
                return [r[0] for r in alias.execute(
                    "SELECT name FROM pet_aliases WHERE target_id=? ORDER BY name LIMIT 12", (pet_id,))]
        except sqlite3.Error:
            return []

    def _find_type(self, db: sqlite3.Connection, text: str) -> dict[str, Any]:
        name = _query(text)
        if name.endswith("系"):
            name = name[:-1]
        if name.isdecimal():
            row = db.execute("SELECT id,name,primary_id,secondary_id FROM element_type_combination WHERE id=?", (int(name),)).fetchone()
            return _row(row) or self._missing("type", name)
        rows = db.execute("SELECT id,name,primary_id,secondary_id FROM element_type_combination WHERE name=? LIMIT 9", (name,)).fetchall()
        if len(rows) == 1:
            return dict(rows[0])
        if len(rows) > 1:
            return self._ambiguous("type", name, rows)
        compact = re.sub(r"[\s·・/]+", "", name)
        if compact != name or len(name) > 1:
            rows = db.execute("SELECT id,name,primary_id,secondary_id FROM element_type_combination "
                              "WHERE replace(name,' ','')=? LIMIT 9", (compact,)).fetchall()
            if len(rows) == 1:
                return dict(rows[0])
            if len(rows) > 1:
                return self._ambiguous("type", name, rows)
        base = db.execute("SELECT id FROM element_type WHERE name=?", (name,)).fetchone()
        if base:
            row = db.execute("SELECT id,name,primary_id,secondary_id FROM element_type_combination WHERE primary_id=? AND secondary_id IS NULL LIMIT 1", (base[0],)).fetchone()
            if row:
                return dict(row)
        return self._missing("type", name)

    def _find_subject_type(self, db: sqlite3.Connection, text: str) -> dict[str, Any]:
        typ = self._find_type(db, text)
        if "id" in typ:
            return typ
        pet = self._find_pet(db, text)
        if pet.get("status") == "ambiguous":
            return pet
        if "id" in pet:
            combo = db.execute("SELECT id,name,primary_id,secondary_id FROM element_type_combination WHERE id=?", (pet["type_id"],)).fetchone()
            if combo:
                return {**dict(combo), "source_pet": {"id": pet["id"], "name": pet["name"]}}
        return typ

    def _find_skill(self, db: sqlite3.Connection, text: str, pet_id: int | None = None) -> dict[str, Any]:
        name = _query(text)
        if not name:
            return self._missing("skill", name)
        sql = "SELECT s.* FROM skill s"
        params: list[Any] = []
        if pet_id is not None:
            sql += " JOIN skillinpetorm l ON l.skill_id=s.id WHERE l.pet_id=? AND "
            params.append(pet_id)
        else:
            sql += " WHERE "
        sql += "s.id=?" if name.isdecimal() else "s.name=?"
        params.append(int(name) if name.isdecimal() else name)
        rows = db.execute(sql + " ORDER BY s.id LIMIT 9", params).fetchall()
        if len(rows) == 1:
            return dict(rows[0])
        if rows:
            return self._ambiguous("skill", name, rows)
        return self._missing("skill", name)

    def pet_profile(self, query: str) -> dict[str, Any]:
        try:
            with closing(self._connect()) as db:
                pet = self._find_pet(db, query)
                if "id" not in pet:
                    return pet
                typ = db.execute("SELECT name FROM element_type_combination WHERE id=?", (pet["type_id"],)).fetchone()
                stats = db.execute("SELECT atk,\"def\",sp_atk,sp_def,spd,hp FROM pet_base_stats WHERE id=?", (pet["id"],)).fetchone()
                skills = db.execute("SELECT COUNT(*) FROM skillinpetorm WHERE pet_id=?", (pet["id"],)).fetchone()[0]
                soulmarks = db.execute("SELECT COUNT(*) FROM petsoulmarklink WHERE pet_id=?", (pet["id"],)).fetchone()[0]
                return {"status": "ok", "source": "SeerAPI SQLite", "pet_id": pet["id"], "name": pet["name"],
                        "aliases": self._aliases_for_pet(pet["id"]),
                        "type": typ[0] if typ else None, "type_id": pet["type_id"],
                        "base_stats": dict(stats) if stats else None, "skill_count": skills,
                        "recorded_soulmark_count": soulmarks}
        except (FileNotFoundError, sqlite3.Error) as exc:
            return {"status": "unavailable", "message": str(exc)}

    def pet_skills(self, query: str, offset: int = 0, limit: int = 30) -> dict[str, Any]:
        try:
            with closing(self._connect()) as db:
                pet = self._find_pet(db, query)
                if "id" not in pet:
                    return pet
                offset, limit = max(0, int(offset)), min(50, max(1, int(limit)))
                total = db.execute("SELECT COUNT(*) FROM skillinpetorm WHERE pet_id=?", (pet["id"],)).fetchone()[0]
                rows = db.execute("SELECT s.id,s.name,s.power,s.max_pp,s.priority,t.name AS type_name,l.learning_level,l.is_fifth "
                                  "FROM skillinpetorm l JOIN skill s ON s.id=l.skill_id "
                                  "LEFT JOIN element_type_combination t ON t.id=s.type_id "
                                  "WHERE l.pet_id=? ORDER BY l.is_fifth DESC,l.learning_level,s.id LIMIT ? OFFSET ?",
                                  (pet["id"], limit, offset)).fetchall()
                return {"status": "ok", "source": "SeerAPI SQLite", "pet_id": pet["id"], "name": pet["name"],
                        "total": total, "offset": offset, "next_offset": offset + len(rows) if offset + len(rows) < total else None,
                        "skills": [dict(r) for r in rows]}
        except (FileNotFoundError, sqlite3.Error, ValueError) as exc:
            return {"status": "unavailable", "message": str(exc)}

    def soulmarks(self, query: str, own_hp_percent: float | None = None) -> dict[str, Any]:
        if own_hp_percent is not None and not 0 <= own_hp_percent <= 100:
            return {"status": "invalid", "message": "自身体力百分比须在 0 到 100 之间"}
        try:
            with closing(self._connect()) as db:
                pet = self._find_pet(db, query)
                if "id" not in pet:
                    return pet
                rows = db.execute("SELECT s.id,s.desc,s.analyze_desc,s.pve_effective,s.intensified,s.is_adv "
                                  "FROM soulmark s JOIN petsoulmarklink l ON l.soulmark_id=s.id "
                                  "WHERE l.pet_id=? ORDER BY s.id LIMIT 12", (pet["id"],)).fetchall()
                data = []
                for row in rows:
                    desc = _clean(row["analyze_desc"] or row["desc"])
                    data.append({"id": row["id"], "original_description": desc[:1400],
                                 "pve_effective": None if row["pve_effective"] is None else bool(row["pve_effective"]),
                                 "intensified": bool(row["intensified"]), "is_adv": bool(row["is_adv"]),
                                 "hp_condition_checks": evaluate_hp_conditions(desc, own_hp_percent) if own_hp_percent is not None else []})
                return {"status": "ok", "source": "SeerAPI SQLite", "pet_id": pet["id"], "name": pet["name"],
                        "soulmarks": data, "note": "pve_effective=null 表示数据层无法判断；体力判定仅覆盖原文明确条件"}
        except (FileNotFoundError, sqlite3.Error) as exc:
            return {"status": "unavailable", "message": str(exc)}

    def skill_detail(self, skill_query: str, pet_query: str = "", own_hp_percent: float | None = None) -> dict[str, Any]:
        if own_hp_percent is not None and not 0 <= own_hp_percent <= 100:
            return {"status": "invalid", "message": "自身体力百分比须在 0 到 100 之间"}
        try:
            with closing(self._connect()) as db:
                pet_id = None
                if pet_query.strip():
                    pet = self._find_pet(db, pet_query)
                    if "id" not in pet:
                        return pet
                    pet_id = pet["id"]
                skill = self._find_skill(db, skill_query, pet_id)
                if "id" not in skill:
                    return skill
                typ = db.execute("SELECT name FROM element_type_combination WHERE id=?", (skill["type_id"],)).fetchone()
                rows = db.execute("SELECT e.effect_id,e.info,e.analyze_info,t.pve_effective "
                                  "FROM skilleffectlink l JOIN skill_effect_in_use e ON e.id=l.effect_in_use_id "
                                  "LEFT JOIN skill_effect_type t ON t.id=e.effect_id "
                                  "WHERE l.skill_id=? ORDER BY e.id LIMIT 20", (skill["id"],)).fetchall()
                effects = []
                for row in rows:
                    desc = _clean(row["analyze_info"] or row["info"])
                    effects.append({"effect_id": row["effect_id"], "original_description": desc[:800],
                                    "pve_effective": None if row["pve_effective"] is None else bool(row["pve_effective"]),
                                    "hp_condition_checks": evaluate_hp_conditions(desc, own_hp_percent) if own_hp_percent is not None else []})
                return {"status": "ok", "source": "SeerAPI SQLite", "skill_id": skill["id"], "name": skill["name"],
                        "type": typ[0] if typ else None, "power": skill["power"], "max_pp": skill["max_pp"],
                        "accuracy": skill["accuracy"], "priority": skill["priority"],
                        "original_info": _clean(skill["info"]), "effects": effects,
                        "note": "效果说明与明确条件不等于完整服务器结算规则"}
        except (FileNotFoundError, sqlite3.Error) as exc:
            return {"status": "unavailable", "message": str(exc)}

    def _relation_map(self, db: sqlite3.Connection) -> dict[tuple[int, int], float]:
        stat = self.db_path.stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
        if self._relations and self._relations[0] == stamp:
            return self._relations[1]
        rows = db.execute("SELECT source_id,target_id,multiple FROM elementtyperelationorm").fetchall()
        table = {(r[0], r[1]): float(r[2]) for r in rows}
        self._relations = (stamp, table)
        return table

    @staticmethod
    def _mixed(c1: float, c2: float) -> float:
        # Mirrors upstream core/type_calc.py, not Pokemon's product rule.
        total = c1 + c2
        if c1 == 2 and c2 == 2:
            return total
        if 0 in (c1, c2):
            return total / 4
        return total / 2

    def _multiplier(self, table: dict[tuple[int, int], float], attacker: dict, defender: dict) -> tuple[float, list[dict]]:
        def single(a: int, d: int) -> float:
            if (a, d) not in table:
                raise KeyError(f"缺少单属性关系 {a}->{d}")
            components.append({"attack_type_id": a, "defense_type_id": d, "multiple": table[(a, d)]})
            return table[(a, d)]
        components: list[dict] = []
        a1, a2 = attacker["primary_id"], attacker["secondary_id"]
        d1, d2 = defender["primary_id"], defender["secondary_id"]
        if a2 is None and d2 is None:
            return single(a1, d1), components
        if a2 is None:
            return self._mixed(single(a1, d1), single(a1, d2)), components
        if d2 is None:
            return self._mixed(single(a1, d1), single(a2, d1)), components
        left = self._mixed(single(a1, d1), single(a2, d1))
        right = self._mixed(single(a1, d2), single(a2, d2))
        return (left + right) / 2, components

    def matchup(self, attacker_query: str, defender_query: str, skill_query: str = "") -> dict[str, Any]:
        try:
            with closing(self._connect()) as db:
                attacker = self._find_subject_type(db, attacker_query)
                defender = self._find_subject_type(db, defender_query)
                if "id" not in attacker:
                    return attacker
                if "id" not in defender:
                    return defender
                skill_name = None
                if skill_query.strip():
                    pet_id = attacker.get("source_pet", {}).get("id")
                    skill = self._find_skill(db, skill_query, pet_id)
                    if "id" not in skill:
                        return skill
                    combo = db.execute("SELECT id,name,primary_id,secondary_id FROM element_type_combination WHERE id=?", (skill["type_id"],)).fetchone()
                    if not combo:
                        return self._missing("skill_type", skill_query)
                    attacker = dict(combo)
                    skill_name = skill["name"]
                value, components = self._multiplier(self._relation_map(db), attacker, defender)
                return {"status": "ok", "source": "SeerAPI SQLite + upstream type_calc formula",
                        "attacking_type": attacker["name"], "defending_type": defender["name"],
                        "attacking_skill": skill_name, "multiple": value, "component_relations": components,
                        "scope": "基础属性克制；不包含技能特效、魂印、场地或战斗临时修正"}
        except (FileNotFoundError, sqlite3.Error, KeyError) as exc:
            return {"status": "unknown", "message": str(exc)}

    def type_profile(self, subject_query: str, mode: str = "attack") -> dict[str, Any]:
        if mode not in ("attack", "defense"):
            return {"status": "invalid", "message": "mode 只能是 attack 或 defense"}
        try:
            with closing(self._connect()) as db:
                subject = self._find_subject_type(db, subject_query)
                if "id" not in subject:
                    return subject
                table = self._relation_map(db)
                combos = [dict(r) for r in db.execute("SELECT id,name,primary_id,secondary_id FROM element_type_combination WHERE secondary_id IS NULL")]
                values = []
                for combo in combos:
                    try:
                        mult, _ = self._multiplier(table, subject, combo) if mode == "attack" else self._multiplier(table, combo, subject)
                    except KeyError:
                        continue
                    if mult > 1 or mult == 0:
                        values.append({"type": combo["name"], "multiple": mult})
                values.sort(key=lambda x: (-x["multiple"], x["type"]))
                return {"status": "ok", "source": "SeerAPI SQLite + upstream type_calc formula",
                        "subject": subject["name"], "mode": mode, "total_matches": len(values),
                        "matchups": values, "truncated": False,
                        "scope": "基础属性关系；技能属性可能不同于精灵本身"}
        except (FileNotFoundError, sqlite3.Error) as exc:
            return {"status": "unavailable", "message": str(exc)}

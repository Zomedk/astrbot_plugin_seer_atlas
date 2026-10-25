"""AstrBot LLM tools backed by local, read-only Seer SQLite databases."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.core.star.star_tools import StarTools

from .knowledge import KnowledgeStore


class SeerAtlas(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        data_dir = Path(StarTools.get_data_dir("astrbot_plugin_seer_atlas"))
        self.database_path = data_dir / "seerapi.sqlite"
        self.alias_path = data_dir / "aliases.sqlite"
        self.knowledge = KnowledgeStore(self.database_path, self.alias_path)
        self.recent_pets: dict[str, tuple[float, str]] = {}

    @staticmethod
    def _conversation_key(event: AstrMessageEvent) -> str:
        sender = event.get_sender_id() if hasattr(event, "get_sender_id") else ""
        return f"{event.unified_msg_origin}:{sender}"

    def _pet_query(self, event: AstrMessageEvent, query: str) -> str:
        if query.strip():
            return query.strip()
        item = self.recent_pets.get(self._conversation_key(event))
        return item[1] if item and time.monotonic() - item[0] < 600 else ""

    def _remember_pet(self, event: AstrMessageEvent, result: dict) -> None:
        if result.get("status") == "ok" and "pet_id" in result:
            if len(self.recent_pets) >= 128:
                oldest = min(self.recent_pets, key=lambda key: self.recent_pets[key][0])
                self.recent_pets.pop(oldest, None)
            self.recent_pets[self._conversation_key(event)] = (time.monotonic(), str(result["pet_id"]))

    async def _run(self, function, *args, **kwargs) -> str:
        if not self.database_path.is_file():
            return json.dumps({
                "status": "unavailable",
                "message": "本地 SeerAPI 数据库缺失；请将 seerapi.sqlite 上传至 AstrBot 的 data/plugin_data/astrbot_plugin_seer_atlas/ 目录。",
            }, ensure_ascii=False)
        result = await asyncio.to_thread(function, *args, **kwargs)
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"))

    @filter.llm_tool(name="seer_pet_profile")
    async def pet_profile(self, event: AstrMessageEvent, pet_query: str = ""):
        """仅在用户询问赛尔号精灵资料时查询；普通聊天无需调用。支持连续追问。

        Args:
            pet_query(string): 精灵正式名称、别名或 ID；连续追问可留空。
        """
        query = self._pet_query(event, pet_query)
        result = await self._run(self.knowledge.pet_profile, query)
        self._remember_pet(event, json.loads(result))
        return result

    @filter.llm_tool(name="seer_pet_skills")
    async def pet_skills(self, event: AstrMessageEvent, pet_query: str = "", offset: int = 0):
        """仅在用户询问某只赛尔号精灵有哪些技能时查询；结果分页返回。

        Args:
            pet_query(string): 精灵正式名称、别名或 ID；连续追问可留空。
            offset(number): 技能列表起始位置，首查为 0，后续使用 next_offset。
        """
        query = self._pet_query(event, pet_query)
        result = await self._run(self.knowledge.pet_skills, query, offset, 20)
        self._remember_pet(event, json.loads(result))
        return result

    @filter.llm_tool(name="seer_skill_detail")
    async def skill_detail(self, event: AstrMessageEvent, skill_query: str,
                           pet_query: str = "", own_hp_percent: float = -1):
        """仅在用户询问赛尔号具体技能、效果原文或明确体力条件时查询。

        Args:
            skill_query(string): 技能正式名称或 ID。
            pet_query(string): 可选精灵名称或 ID，用于限定同名技能。
            own_hp_percent(number): 可选自身当前体力百分比，未知填 -1，满血填 100。
        """
        hp = None if own_hp_percent < 0 else own_hp_percent
        result = await self._run(self.knowledge.skill_detail, skill_query, pet_query, hp)
        return result

    @filter.llm_tool(name="seer_soulmark")
    async def soulmark(self, event: AstrMessageEvent, pet_query: str = "",
                       own_hp_percent: float = -1):
        """仅在用户询问赛尔号魂印原文、PVE 标志或明确体力条件时查询。

        Args:
            pet_query(string): 精灵正式名称、别名或 ID；连续追问可留空。
            own_hp_percent(number): 可选自身当前体力百分比，未知填 -1，满血填 100。
        """
        query = self._pet_query(event, pet_query)
        hp = None if own_hp_percent < 0 else own_hp_percent
        result = await self._run(self.knowledge.soulmarks, query, hp)
        self._remember_pet(event, json.loads(result))
        return result

    @filter.llm_tool(name="seer_type_matchup")
    async def type_matchup(self, event: AstrMessageEvent, defender_query: str,
                           attacker_query: str = "", skill_query: str = ""):
        """仅在用户问赛尔号 A 打 B 的基础属性倍率时调用，使用计算结果回答。

        Args:
            defender_query(string): 防守精灵名称、ID 或属性名称。
            attacker_query(string): 攻击精灵名称、ID 或属性名称；连续追问可留空。
            skill_query(string): 可选技能名称或 ID；传入时使用技能属性计算。
        """
        attacker = self._pet_query(event, attacker_query)
        result = await self._run(self.knowledge.matchup, attacker, defender_query, skill_query)
        return result

    @filter.llm_tool(name="seer_type_profile")
    async def type_profile(self, event: AstrMessageEvent, subject_query: str = "", mode: str = "attack"):
        """仅在用户问赛尔号某精灵或属性克制谁、被谁克制时调用。

        Args:
            subject_query(string): 精灵名称、ID 或属性名称；连续追问可留空。
            mode(string): attack 表示它打别人，defense 表示别人打它。
        """
        subject = self._pet_query(event, subject_query)
        result = await self._run(self.knowledge.type_profile, subject, mode)
        return result

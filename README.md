# 赛尔星图 · AstrBot 插件

面向 AstrBot 工具调用的赛尔号轻量知识插件。提供精灵名称与别名、属性、技能、魂印原文及基础属性克制查询。默认只输出文字，不启动 Playwright 或 Chromium，也不需要向游戏服务器发请求。

## 安装

在 AstrBot「插件」页面通过仓库地址安装：

```text
https://github.com/Zomedk/astrbot_plugin_seer_atlas
```

AstrBot 根据 `requirements.txt` 安装 `aiohttp`。插件首次启动时会从 SeerAPI 的公开 GitHub Release 下载 SQLite 数据库到 AstrBot 的持久化 `plugin_data/astrbot_plugin_seer_atlas/` 目录。别名库来自 ironsbot 的公开 Release，下载失败不影响正式名称和 ID 查询。数据库已存在时不会重复下载；如需更新数据，可在停用插件后替换该目录里的 `seerapi.sqlite` 和 `aliases.sqlite`。如果服务器无法访问 GitHub，可先在其他设备下载这两个文件，再手动放到上述目录，并关闭 `auto_download`。

仓库不包含 SQLite 数据、精灵素材、浏览器、客户端文件或研究输出。

## 工具

插件向 AstrBot 的 LLM 提供六个工具：

| 工具 | 用途 |
| --- | --- |
| `seer_pet_profile` | 精灵名称、别名、属性与基本资料 |
| `seer_pet_skills` | 精灵技能列表，支持分页 |
| `seer_skill_detail` | 技能基础数值、效果原文和明确体力条件 |
| `seer_soulmark` | 魂印原文、数据源中的 PVE 标志和明确体力条件 |
| `seer_type_matchup` | 单属性与双属性的基础克制倍率，可按技能属性计算 |
| `seer_type_profile` | 某精灵或属性的基础克制对象 |

在 AstrBot 中启用插件，并给使用的 LLM / 人格开启这些工具后，可以直接问「雷伊是什么属性？」「它有哪些技能？」「雷伊的某个技能打某精灵几倍克制？」。工具说明限定在赛尔号资料问题时调用；普通聊天无需调用。连续追问的最近精灵按会话和发送者保存 10 分钟，仅存在内存中。

## 范围与限制

- 克制倍率沿用 SeerAPI 现有属性关系与双属性计算方式，按技能查询时使用技能属性。技能特效、魂印、场地、临时修正不在倍率中。
- `pve_effective` 是数据源字段；为空时返回未知。魂印和技能效果的解释以原文为准。
- 体力判断仅处理原文明确出现的自身满血或自身体力分数比较条件，不能据此断言整个效果必然发动。
- 数据随公开数据库版本变化；查不到、重名或缺少关系时返回明确状态，不由模型补猜。
- 插件不实现战斗模拟，也不连接赛尔号正式服务器。

## 来源与许可

本项目基于 [astrbot_plugin_seer_info](https://github.com/MengNianxiaoyao/astrbot_plugin_seer_info) 的数据源配置与插件思路改造，并使用 [SeerAPI](https://github.com/SeerAPI/seerapi) 的 SQLite 数据结构及属性计算规则。原插件采用 GPL-3.0，本项目保留同一许可证，详见 [LICENSE](LICENSE)。SeerAPI 项目采用 MIT 许可证；运行时数据库和可选别名库由其各自发布方提供。

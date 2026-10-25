# 赛尔星图 · AstrBot 插件

面向 AstrBot 工具调用的赛尔号轻量知识插件。提供精灵名称与别名、属性、技能、魂印原文及基础属性克制查询。插件只读取服务器上的 SQLite 文件，不在运行时联网下载数据，也不需要浏览器、Playwright 或本地大模型。

## 安装与数据库

在 AstrBot「插件」页面安装：

```text
https://github.com/Zomedk/astrbot_plugin_seer_atlas
```

在运行 AstrBot 的服务器上，将 SeerAPI 数据库放在 AstrBot 的持久化数据目录：

```text
data/plugin_data/astrbot_plugin_seer_atlas/seerapi.sqlite
```

可选别名库放在同目录，文件名为 `aliases.sqlite`。没有别名库时，正式名称和 ID 查询仍可用。具体绝对路径取决于 AstrBot 的数据目录；本机部署示例为 `/root/data/plugin_data/astrbot_plugin_seer_atlas/`。插件对数据库使用 SQLite 只读连接。

数据库可以在另一台能访问 GitHub Release 的电脑上下载、校验，然后用 SCP 传到服务器。例如：

```powershell
scp.exe .\seerapi-data.sqlite root@服务器地址:/root/data/plugin_data/astrbot_plugin_seer_atlas/seerapi.sqlite
scp.exe .\aliases-data.sqlite root@服务器地址:/root/data/plugin_data/astrbot_plugin_seer_atlas/aliases.sqlite
```

主库来源：[SeerAPI api-data 发布页](https://github.com/SeerAPI/api-data/releases)。可选别名库来源：[ironsbot 发布页](https://github.com/Nattsu39/ironsbot/releases)。传输后建议核对 SHA-256 和 `PRAGMA quick_check`，再重载插件。仓库的 `.gitignore` 排除数据库；**GitHub 仓库不包含任何数据库文件**。

## 工具

| 工具 | 用途 |
| --- | --- |
| `seer_pet_profile` | 精灵名称、别名、属性与基本资料 |
| `seer_pet_skills` | 精灵技能列表，支持分页 |
| `seer_skill_detail` | 技能基础数值、效果原文和明确体力条件 |
| `seer_soulmark` | 魂印原文、数据源中的 PVE 标志和明确体力条件 |
| `seer_type_matchup` | 单属性与双属性的基础克制倍率，可按技能属性计算 |
| `seer_type_profile` | 某精灵或属性的基础克制对象 |

在 AstrBot 中给使用的 LLM / 人格开启这些工具后，可以问「雷伊是什么属性？」「它有哪些技能？」「雷伊的某个技能打某精灵几倍克制？」。工具说明限定在赛尔号资料问题时调用；普通聊天无需调用。连续追问的最近精灵按会话和发送者保存 10 分钟，仅存在内存中。

## 范围与限制

- 克制倍率沿用 SeerAPI 现有属性关系与双属性计算方式，按技能查询时使用技能属性。技能特效、魂印、场地、临时修正不在倍率中。
- `pve_effective` 是数据源字段；为空时返回未知。魂印和技能效果的解释以原文为准。
- 体力判断仅处理原文明确出现的自身满血或自身体力分数比较条件，不能据此断言整个效果必然发动。
- 数据随本地 SQLite 版本变化；查不到、重名或缺少关系时返回明确状态，不由模型补猜。
- 插件不实现战斗模拟，也不连接赛尔号正式服务器。

## 来源与许可

本项目基于 [astrbot_plugin_seer_info](https://github.com/MengNianxiaoyao/astrbot_plugin_seer_info) 的数据源配置与插件思路改造，并使用 [SeerAPI](https://github.com/SeerAPI/seerapi) 的 SQLite 数据结构及属性计算规则。原插件采用 GPL-3.0，本项目保留同一许可证，详见 [LICENSE](LICENSE)。SeerAPI 项目采用 MIT 许可证；本地数据库由用户自行取得。

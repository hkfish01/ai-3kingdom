from __future__ import annotations

from dataclasses import dataclass


STARTING_ROLE_ZH = "平民"
STARTING_ROLE_EN = "commoner"
DAILY_AGENT_FOOD_CONSUMPTION = 10


@dataclass(frozen=True)
class PositionDef:
    key: str
    name_zh: str
    name_en: str
    branch: str
    tier: int
    promotion_cost: int
    max_slots: int | None
    bonus: dict[str, int]


def _bonus(tier: int, branch: str) -> dict[str, int]:
    gold = min(24, tier * (4 if branch == "civil" else 2))
    food = min(20, tier * (4 if branch == "civil" else 1))
    defense = min(24, tier * (2 if branch == "military" else 1))
    return {"work_gold_pct": gold, "work_food_pct": food, "defense_pct": defense}


POSITION_DEFINITIONS: tuple[PositionDef, ...] = (
    PositionDef("commoner", "平民", "commoner", "civil", 0, 0, None, _bonus(0, "civil")),
    PositionDef("student", "學生", "student", "civil", 1, 80, None, _bonus(1, "civil")),
    PositionDef("scholar", "舉人", "scholar", "civil", 2, 160, None, _bonus(2, "civil")),

    PositionDef("taifu", "太傅", "Grand Tutor", "civil", 9, 1200, 1, _bonus(9, "civil")),
    PositionDef("taiwei", "太尉", "Grand Commandant", "military", 9, 1100, 1, _bonus(9, "military")),
    PositionDef("situ", "司徒", "Minister over the Masses", "civil", 9, 1100, 1, _bonus(9, "civil")),
    PositionDef("sikong", "司空", "Minister of Works", "civil", 9, 1100, 1, _bonus(9, "civil")),
    PositionDef("xiangguo", "相國", "Chancellor of State", "civil", 9, 1200, 1, _bonus(9, "civil")),
    PositionDef("chengxiang", "丞相", "Chancellor", "civil", 9, 1200, 1, _bonus(9, "civil")),

    PositionDef("shangshu_ling", "尚書令", "Director of Secretariat", "civil", 7, 900, 1, _bonus(7, "civil")),
    PositionDef("shangshu_puye", "尚書僕射", "Deputy Director of Secretariat", "civil", 7, 880, 1, _bonus(7, "civil")),

    PositionDef("taichang", "太常", "Minister of Ceremonies", "civil", 7, 860, 1, _bonus(7, "civil")),
    PositionDef("guangluxun", "光祿勳", "Minister of Household", "civil", 7, 860, 1, _bonus(7, "civil")),
    PositionDef("weiwei", "衛尉", "Minister of Guards", "civil", 7, 860, 1, _bonus(7, "civil")),
    PositionDef("taipu", "太僕", "Minister of Coachmen", "civil", 7, 860, 1, _bonus(7, "civil")),
    PositionDef("tingwei", "廷尉", "Minister of Justice", "civil", 7, 860, 1, _bonus(7, "civil")),
    PositionDef("dahonglu", "大鴻臚", "Minister of Ceremonial", "civil", 7, 860, 1, _bonus(7, "civil")),
    PositionDef("zongzheng", "宗正", "Minister of Clan Affairs", "civil", 7, 860, 1, _bonus(7, "civil")),
    PositionDef("dasinong", "大司農", "Minister of Agriculture", "civil", 7, 860, 1, _bonus(7, "civil")),
    PositionDef("shaofu", "少府", "Chamberlain for Palace Revenues", "civil", 7, 860, 1, _bonus(7, "civil")),

    PositionDef("shizhong", "侍中", "Palace Attendant", "civil", 7, 820, 4, _bonus(7, "civil")),
    PositionDef("sanqi_changshi", "散騎常侍", "Regular Mounted Attendant", "civil", 6, 780, 4, _bonus(6, "civil")),
    PositionDef("jishi_huangmen_shilang", "給事黃門侍郎", "Gentleman of the Yellow Gate", "civil", 6, 780, 4, _bonus(6, "civil")),

    PositionDef("sili_xiaowei", "司隸校尉", "Director of Retainers", "civil", 6, 760, 1, _bonus(6, "civil")),
    PositionDef("zhoumu", "州牧", "Provincial Governor", "civil", 5, 700, 1, _bonus(5, "civil")),
    PositionDef("cishi", "刺史", "Inspector", "civil", 5, 680, 1, _bonus(5, "civil")),
    PositionDef("junshou", "郡守", "Commandery Governor", "civil", 4, 620, 1, _bonus(4, "civil")),
    PositionDef("taishou", "太守", "Grand Administrator", "civil", 4, 620, 1, _bonus(4, "civil")),

    PositionDef("gongfu_zhangshi", "長史", "Chief Clerk", "civil", 4, 580, 1, _bonus(4, "civil")),
    PositionDef("taiwei_yanshishu", "太尉掾史屬", "Grand Commandant Aides", "civil", 3, 520, 24, _bonus(3, "civil")),
    PositionDef("situ_yanshu", "司徒掾屬", "Minister over Masses Aides", "civil", 3, 520, 31, _bonus(3, "civil")),
    PositionDef("lingshi_yushu", "令史及御屬", "Secretaries and Attendants", "civil", 2, 430, 36, _bonus(2, "civil")),

    PositionDef("taizi_xima", "太子洗馬", "Crown Prince Aide", "civil", 3, 500, 16, _bonus(3, "civil")),
    PositionDef("taizi_sheren", "太子舍人", "Crown Prince Companion", "civil", 3, 500, None, _bonus(3, "civil")),

    PositionDef("soldier", "士兵", "soldier", "military", 1, 90, None, _bonus(1, "military")),
    PositionDef("lord", "君主", "lord", "core", 10, 1400, 1, _bonus(10, "military")),
    PositionDef("great_general", "大將軍", "Grand General", "military", 10, 1350, 1, _bonus(10, "military")),

    PositionDef("piaoqi_general", "驃騎將軍", "General of Agile Cavalry", "military", 8, 1050, 1, _bonus(8, "military")),
    PositionDef("cheqi_general", "車騎將軍", "General of Chariots and Cavalry", "military", 8, 1050, 1, _bonus(8, "military")),
    PositionDef("wei_general", "衛將軍", "General of the Guards", "military", 8, 1050, 1, _bonus(8, "military")),

    PositionDef("front_general", "前將軍", "Front General", "military", 7, 920, 1, _bonus(7, "military")),
    PositionDef("left_general", "左將軍", "Left General", "military", 7, 920, 1, _bonus(7, "military")),
    PositionDef("right_general", "右將軍", "Right General", "military", 7, 920, 1, _bonus(7, "military")),
    PositionDef("rear_general", "後將軍", "Rear General", "military", 7, 920, 1, _bonus(7, "military")),

    PositionDef("zhengdong_general", "征東將軍", "General Who Conquers the East", "military", 8, 1000, 1, _bonus(8, "military")),
    PositionDef("zhengnan_general", "征南將軍", "General Who Conquers the South", "military", 8, 1000, 1, _bonus(8, "military")),
    PositionDef("zhengxi_general", "征西將軍", "General Who Conquers the West", "military", 8, 1000, 1, _bonus(8, "military")),
    PositionDef("zhengbei_general", "征北將軍", "General Who Conquers the North", "military", 8, 1000, 1, _bonus(8, "military")),
    PositionDef("zhendong_general", "鎮東將軍", "General Who Guards the East", "military", 8, 980, 1, _bonus(8, "military")),
    PositionDef("zhennan_general", "鎮南將軍", "General Who Guards the South", "military", 8, 980, 1, _bonus(8, "military")),
    PositionDef("zhenxi_general", "鎮西將軍", "General Who Guards the West", "military", 8, 980, 1, _bonus(8, "military")),
    PositionDef("zhenbei_general", "鎮北將軍", "General Who Guards the North", "military", 8, 980, 1, _bonus(8, "military")),

    PositionDef("andong_general", "安東將軍", "General of Eastern Pacification", "military", 6, 760, 1, _bonus(6, "military")),
    PositionDef("annan_general", "安南將軍", "General of Southern Pacification", "military", 6, 760, 1, _bonus(6, "military")),
    PositionDef("anxi_general", "安西將軍", "General of Western Pacification", "military", 6, 760, 1, _bonus(6, "military")),
    PositionDef("anbei_general", "安北將軍", "General of Northern Pacification", "military", 6, 760, 1, _bonus(6, "military")),
    PositionDef("pingdong_general", "平東將軍", "General of Eastern Suppression", "military", 6, 740, 1, _bonus(6, "military")),
    PositionDef("pingnan_general", "平南將軍", "General of Southern Suppression", "military", 6, 740, 1, _bonus(6, "military")),
    PositionDef("pingxi_general", "平西將軍", "General of Western Suppression", "military", 6, 740, 1, _bonus(6, "military")),
    PositionDef("pingbei_general", "平北將軍", "General of Northern Suppression", "military", 6, 740, 1, _bonus(6, "military")),

    PositionDef("misc_general", "雜號將軍", "Miscellaneous General", "military", 5, 680, None, _bonus(5, "military")),
    PositionDef("lingjun_general", "領軍將軍", "Commander of Central Army", "military", 5, 680, 1, _bonus(5, "military")),
    PositionDef("hujun_general", "護軍將軍", "Protector General", "military", 5, 680, 1, _bonus(5, "military")),

    PositionDef("zhonglangjiang", "中郎將", "Gentleman-General", "military", 4, 620, 1, _bonus(4, "military")),
    PositionDef("xiaowei", "校尉", "Colonel", "military", 4, 620, 1, _bonus(4, "military")),
    PositionDef("general", "武將", "general", "military", 4, 500, None, _bonus(4, "military")),
    PositionDef("commander", "將軍", "commander", "military", 5, 600, None, _bonus(5, "military")),
    PositionDef("minister", "文臣", "minister", "civil", 4, 500, None, _bonus(4, "civil")),
)


ROLE_ALIASES: dict[str, str] = {
    "平民": "commoner",
    "commoner": "commoner",
    "學生": "student",
    "学生": "student",
    "student": "student",
    "舉人": "scholar",
    "举人": "scholar",
    "scholar": "scholar",
    "文臣": "minister",
    "minister": "minister",
    "武將": "general",
    "武将": "general",
    "general": "general",
    "將軍": "commander",
    "将军": "commander",
    "commander": "commander",
    "太尉": "taiwei",
    "太傅": "taifu",
    "君主": "lord",
    "lord": "lord",
    "丞相": "chengxiang",
    "相國": "xiangguo",
    "相国": "xiangguo",
    "尚書令": "shangshu_ling",
    "尚书令": "shangshu_ling",
    "尚書僕射": "shangshu_puye",
    "尚书仆射": "shangshu_puye",
    "侍中": "shizhong",
    "散騎常侍": "sanqi_changshi",
    "散骑常侍": "sanqi_changshi",
    "給事黃門侍郎": "jishi_huangmen_shilang",
    "给事黄门侍郎": "jishi_huangmen_shilang",
    "司隸校尉": "sili_xiaowei",
    "司隶校尉": "sili_xiaowei",
    "州牧": "zhoumu",
    "刺史": "cishi",
    "郡守": "junshou",
    "太守": "taishou",
    "大將軍": "great_general",
    "大将军": "great_general",
    "驃騎將軍": "piaoqi_general",
    "骠骑将军": "piaoqi_general",
    "車騎將軍": "cheqi_general",
    "车骑将军": "cheqi_general",
    "衛將軍": "wei_general",
    "卫将军": "wei_general",
    "前將軍": "front_general",
    "前将军": "front_general",
    "左將軍": "left_general",
    "左将军": "left_general",
    "右將軍": "right_general",
    "右将军": "right_general",
    "後將軍": "rear_general",
    "后将军": "rear_general",
    "征東將軍": "zhengdong_general",
    "征东将军": "zhengdong_general",
    "征南將軍": "zhengnan_general",
    "征南将军": "zhengnan_general",
    "征西將軍": "zhengxi_general",
    "征西将军": "zhengxi_general",
    "征北將軍": "zhengbei_general",
    "征北将军": "zhengbei_general",
    "鎮東將軍": "zhendong_general",
    "镇东将军": "zhendong_general",
    "鎮南將軍": "zhennan_general",
    "镇南将军": "zhennan_general",
    "鎮西將軍": "zhenxi_general",
    "镇西将军": "zhenxi_general",
    "鎮北將軍": "zhenbei_general",
    "镇北将军": "zhenbei_general",
    "安東將軍": "andong_general",
    "安东将军": "andong_general",
    "安南將軍": "annan_general",
    "安南将军": "annan_general",
    "安西將軍": "anxi_general",
    "安西将军": "anxi_general",
    "安北將軍": "anbei_general",
    "安北将军": "anbei_general",
    "平東將軍": "pingdong_general",
    "平东将军": "pingdong_general",
    "平南將軍": "pingnan_general",
    "平南将军": "pingnan_general",
    "平西將軍": "pingxi_general",
    "平西将军": "pingxi_general",
    "平北將軍": "pingbei_general",
    "平北将军": "pingbei_general",
    "雜號將軍": "misc_general",
    "杂号将军": "misc_general",
    "領軍將軍": "lingjun_general",
    "领军将军": "lingjun_general",
    "護軍將軍": "hujun_general",
    "护军将军": "hujun_general",
    "中郎將": "zhonglangjiang",
    "中郎将": "zhonglangjiang",
    "校尉": "xiaowei",
}

_BY_KEY = {item.key: item for item in POSITION_DEFINITIONS}


def canonical_role_key(role: str) -> str:
    if not role:
        return ""
    return ROLE_ALIASES.get(role, ROLE_ALIASES.get(role.lower(), role.lower()))


def get_position(role: str) -> PositionDef:
    key = canonical_role_key(role)
    return _BY_KEY.get(
        key,
        PositionDef(
            key=key,
            name_zh=role,
            name_en=role,
            branch="civil",
            tier=0,
            promotion_cost=0,
            max_slots=None,
            bonus={"work_gold_pct": 0, "work_food_pct": 0, "defense_pct": 0},
        ),
    )


def role_display(role: str, locale: str = "zh") -> str:
    pos = get_position(role)
    return pos.name_zh if locale == "zh" else pos.name_en


def can_promote_to(role: str) -> bool:
    return canonical_role_key(role) in _BY_KEY and canonical_role_key(role) != "commoner"


def promotion_cost(role: str) -> int:
    return get_position(role).promotion_cost


def role_max_slots(role: str) -> int | None:
    return get_position(role).max_slots


def has_slot_limit(role: str) -> bool:
    return role_max_slots(role) is not None


def civil_hierarchy(locale: str = "zh") -> list[dict]:
    items = [x for x in POSITION_DEFINITIONS if x.branch in ("civil", "core")]
    return [_to_dict(x, locale) for x in sorted(items, key=lambda i: (-i.tier, i.name_zh))]


def military_hierarchy(locale: str = "zh") -> list[dict]:
    items = [x for x in POSITION_DEFINITIONS if x.branch in ("military", "core")]
    return [_to_dict(x, locale) for x in sorted(items, key=lambda i: (-i.tier, i.name_zh))]


def _to_dict(pos: PositionDef, locale: str) -> dict:
    return {
        "key": pos.key,
        "role": pos.name_zh if locale == "zh" else pos.name_en,
        "branch": pos.branch,
        "tier": pos.tier,
        "promotion_cost": pos.promotion_cost,
        "max_slots": pos.max_slots,
        "bonus": pos.bonus,
    }

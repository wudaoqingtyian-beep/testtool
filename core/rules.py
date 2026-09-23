# -*- coding: utf-8 -*-
"""
rules.py —— 规则引擎（数据工厂的心脏）

职责：
    把模板里写的占位符（如 ${phone}、${int(18,60)}）渲染成真实数据。

设计说明（面试话术锚点）：
    采用「策略模式 + 注册表」：所有生成规则都是函数，统一注册进 RULES 字典。
    新增规则只需定义函数并用 @register 装饰器注册，不需要改动渲染引擎，
    符合开闭原则（对扩展开放、对修改关闭）。
"""
import re
import random
import string
import uuid as uuid_lib
from datetime import datetime, timedelta

from faker import Faker

# Faker 中文实例：生成符合中国习惯的姓名、手机号、身份证等
fake = Faker("zh_CN")


# ======================================================================
# 一、规则注册表（策略模式）
# ======================================================================

# 全局规则字典：key = 规则名，value = 生成函数
# 渲染引擎根据占位符里的规则名来这里查找并调用
RULES = {}


def register(name):
    """注册装饰器：把函数登记进规则表，方便后续按名字分发调用。

    用法示例：
        @register("phone")
        def _phone(): ...
    """
    def wrapper(func):
        RULES[name] = func
        return func
    return wrapper


# ======================================================================
# 内置规则实现（每个函数就是一个"策略"）
# ======================================================================

@register("phone")
def _phone():
    """随机生成一个格式合法的中国手机号（Faker 本地化）"""
    return fake.phone_number()


@register("email")
def _email():
    """随机生成一个邮箱地址"""
    return fake.email()


@register("name")
def _name():
    """随机生成一个中文姓名"""
    return fake.name()


@register("idcard")
def _idcard():
    """随机生成一个校验位合法的身份证号（仅用于测试造数）"""
    return fake.ssn()


@register("uuid")
def _uuid():
    """生成 UUID，适合做订单号等全局唯一标识"""
    return str(uuid_lib.uuid4())


@register("random_str")
def _random_str(length=8):
    """生成指定长度的随机字母数字串，参数 length 可从模板传入"""
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choices(chars, k=int(length)))


@register("int")
def _int(min_val, max_val):
    """生成 [min_val, max_val] 范围内的随机整数"""
    return random.randint(int(min_val), int(max_val))


@register("decimal")
def _decimal(min_val, max_val, digits=2):
    """生成范围内的随机小数，默认保留 2 位（金额常用）"""
    val = random.uniform(float(min_val), float(max_val))
    return round(val, int(digits))


@register("enum")
def _enum(*options):
    """从给定选项中随机选一个，适合状态类字段（如订单状态）"""
    return random.choice(list(options))


@register("sequence")
def _sequence(prefix="", digits=6):
    """递增序列号生成器：保证同一批造数中不重复（如 USER000001）"""
    # 用函数属性做简单自增计数器，跨多次调用持续递增
    _sequence.n += 1
    return f"{prefix}{str(_sequence.n).zfill(int(digits))}"
_sequence.n = 0  # 初始化计数器


@register("datetime_recent")
def _datetime_recent(days=30, fmt="%Y-%m-%d %H:%M:%S"):
    """生成最近 N 天内的随机时间；参数支持 '30' 或 '30d' 两种写法"""
    # 兼容 '30d' 这种带单位后缀的写法（模板里更直观）
    days = str(days).strip().rstrip("dD")
    delta = timedelta(
        days=random.uniform(0, float(days)),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
        seconds=random.randint(0, 59),
    )
    return (datetime.now() - delta).strftime(fmt)


@register("bool")
def _bool():
    """随机生成布尔值（数据库中常转为 0/1，模板按需处理）"""
    return random.choice([True, False])


@register("address")
def _address():
    """随机生成一个中文地址"""
    return fake.address()


@register("company")
def _company():
    """随机生成一个公司名称"""
    return fake.company()


@register("ipv4")
def _ipv4():
    """随机生成一个 IPv4 地址"""
    return fake.ipv4()


@register("ref")
def _ref(model_field):
    """引用依赖模型的字段值（占位：由 generator 在调度时动态注入）

    说明：
        ${ref(User.id)} 表示"取本次造数中 User 模型已生成记录的 id"。
        真正的取值逻辑在 generator.py 里（外键回填），这里只负责注册占位，
        保证 loader 校验占位符时能通过。
    """
    # 该规则由 generator 特殊处理，正常情况下不应走到这里
    raise RuntimeError("ref 规则应由生成调度器处理，请检查依赖配置")


# ======================================================================
# 渲染引擎：解析占位符并调用规则
# ======================================================================

# 匹配 ${规则名(参数,参数...)} 的正则：
#   规则名 = 字母开头的单词；参数 = 括号内逗号分隔的任意文本（可为空）
PLACEHOLDER_PATTERN = re.compile(r"\$\{(\w+)(?:\(([^)]*)\))?\}")


def render(value, context=None):
    """把模板字段值中的所有占位符替换为真实数据。

    参数:
        value: 模板里的字段值，可能是字符串（含占位符）、数字或布尔
        context: 可选的上下文字典，目前预留给依赖回填（generator 使用）

    返回:
        渲染后的值。纯占位符（整串只有一个占位符）时返回原生类型
        （如 int/bool），混排字符串则拼接为字符串。

    示例:
        render("${int(18,60)}") -> 35
        render("auto_${random_str(8)}") -> "auto_x3k9d2m1"
    """
    context = context or {}

    # 非字符串类型（数字、布尔等）不需要渲染，直接返回
    if not isinstance(value, str):
        return value

    # 快速通道：没有占位符直接返回原值
    if "${" not in value:
        return value

    def _replace(match):
        """正则替换回调：解析单个占位符并调用对应规则"""
        rule_name = match.group(1)          # 规则名，如 "int"
        raw_args = match.group(2) or ""     # 参数串，如 "18,60"

        # 规则名必须已注册，否则说明模板写错了，直接报错提示
        if rule_name not in RULES:
            raise ValueError(f"未知规则 '{rule_name}'，可用规则: {sorted(RULES)}")

        # 解析参数：按逗号切分并去掉首尾空白
        args = [a.strip() for a in raw_args.split(",") if a.strip()]

        # 特殊规则 ref：交给上下文里的处理器处理（由 generator 注入）
        if rule_name == "ref" and "ref_resolver" in context:
            return context["ref_resolver"](args[0])

        # 返回原生类型（int/float/str），由外层决定是否转字符串
        return RULES[rule_name](*args)

    # 整串恰好是一个占位符 → 返回函数原生返回值（保留 int 等类型）
    whole = PLACEHOLDER_PATTERN.fullmatch(value.strip())
    if whole:
        return _replace(whole)

    # 混合字符串（如 "auto_${random_str(8)}"）→ 逐个替换，结果统一转 str 保证可拼接
    return PLACEHOLDER_PATTERN.sub(lambda m: str(_replace(m)), value)
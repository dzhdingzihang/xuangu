#!/usr/bin/env python3
"""
Local intelligent stock selector.

It intentionally prefers "no recommendation" over weak signals. The model is a
decision-support tool, not a guarantee of profit.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import http.server
import json
import math
import os
import pathlib
import re
import socketserver
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from zoneinfo import ZoneInfo

import requests


ROOT = pathlib.Path(__file__).resolve().parent
STATIC = ROOT / "static"
CACHE = ROOT / "data"
PICKS = CACHE / "picks"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
CN_TZ = ZoneInfo("Asia/Shanghai")
MODEL_VERSION = "smart-selector-2026-06-21.3-large-ai-universe"
FORECAST_TRADE_DAYS = 10
FORECAST_LABEL = "未来2周"
SERENITY_SKILL_DIR = pathlib.Path.home() / ".agents" / "skills" / "serenity-skill"

for path in (CACHE, PICKS):
    path.mkdir(parents=True, exist_ok=True)


CHAN_RULES = {
    "source": "缠中说禅 PDF",
    "principles": [
        "不预测空间，只在买点出现时介入，卖点或风控出现时退出。",
        "第二类买点适合用大级别确认、次级别精确买入。",
        "第三类买点是离开中枢后的回试不破，短线更重视效率。",
        "没有趋势，没有背驰；背驰只作为转折确认，不单独追涨。",
        "风险不可消灭，只能通过系统、仓位和退出条件约束。",
    ],
    "quant_mapping": [
        "女上位: MA5 > MA10，且最好 MA10 > MA20。",
        "二买: 多头均线后第一次回踩 MA5/MA10 不破并重新收回，优先选择偏离 MA10 不大的标的。",
        "三买: 突破近 20 日箱体或中枢后，回踩不跌回箱体上沿；只突破不回踩不追。",
        "背驰: 价格创新低但 MACD 柱改善，作为二买/反转加分。",
        "卖点/风控: 涨停后大幅高开不追；跌破 MA10 或买入后两日未兑现强度时退出。",
    ],
}


CZSC_RULES = {
    "source": "waditu/czsc",
    "principles": [
        "参考 czsc 的分型、笔、中枢、信号-事件-交易框架，将单一均线信号升级为结构组合评分。",
        "两周持有更重视日线中枢突破后的回踩确认、MA20/MA30 趋势、箱体位置和背驰风险。",
        "若运行环境安装了 czsc，可进一步接入原生分型/笔/中枢；当前模型内置轻量近似，不依赖扩展成功。",
    ],
}


UZI_RULES = {
    "source": "wbh604/UZI-Skill",
    "principles": [
        "加重 UZI 的多维评分、评审团共识、游资射程、杀猪盘检测和定性风险门控。",
        "推荐度以指定价格买入后未来2周能否上涨为目标，实时价、买点纪律和下行空间直接参与评分。",
        "优先选择有趋势结构、流动性承接、题材一致性和评审团共识的股票；对模板化推广、过热追高、融资/稀释和单一催化叙事重罚。",
    ],
}


THEME_KEYWORDS = [
    "先进封装",
    "存储芯片",
    "HBM",
    "CPO",
    "光模块",
    "800G",
    "1.6T",
    "AI算力",
    "算力",
    "英伟达",
    "服务器电源",
    "数据中心",
    "液冷",
    "PCB",
    "半导体",
    "机器人",
    "人形机器人",
    "低空经济",
    "商业航天",
]


SERENITY_RULES = {
    "source": "yan-labs/serenity-aleabitoreddit",
    "principles": [
        "沿 hyperscaler AI capex 向上游追溯，而不是只买最显眼的下游龙头。",
        "优先寻找光通信/CPO、InP/化合物半导体、HBM/存储、电力/数据中心里的供应瓶颈。",
        "小市值、低关注度、供给受限、被机构定价滞后的上游环节获得更高权重。",
        "有 Mag7/头部云厂商客户、签约收入或明确量产/资格认证进展时加权。",
        "大额 ATM/持续稀释、弱交易对手、单一客户断供风险、已被情绪追高时降权。",
        "按 Serenity Skill 六步法复核：需求去噪、财务映射、错误分类小盘、错误定价验证、验证链、alpha 五维评分。",
    ],
    "calibration": "该因子来自公开研究框架，作为产业链权重，不是自动买入信号；仍需通过价格结构和风控过滤。",
}


SERENITY_UNIVERSES = {
    "a_share": [
        {"symbol": "300308", "name": "中际旭创", "role": "高速光模块/AI 数据中心", "themes": ["CPO", "800G/1.6T", "AI算力"], "lens": {"bottleneck": 7, "upstream": 6, "capex": 9, "customer": 7, "smallcap": 2, "financing": 5, "catalyst": 6}},
        {"symbol": "300502", "name": "新易盛", "role": "高速光模块/海外云厂商链", "themes": ["光模块", "800G", "AI算力"], "lens": {"bottleneck": 7, "upstream": 6, "capex": 9, "customer": 7, "smallcap": 3, "financing": 5, "catalyst": 6}},
        {"symbol": "300394", "name": "天孚通信", "role": "光器件/光引擎上游", "themes": ["光器件", "CPO", "硅光"], "lens": {"bottleneck": 8, "upstream": 8, "capex": 8, "customer": 6, "smallcap": 4, "financing": 5, "catalyst": 5}},
        {"symbol": "002281", "name": "光迅科技", "role": "光通信器件/模块", "themes": ["光模块", "硅光", "国产替代"], "lens": {"bottleneck": 6, "upstream": 6, "capex": 7, "customer": 5, "smallcap": 5, "financing": 5, "catalyst": 4}},
        {"symbol": "688498", "name": "源杰科技", "role": "激光芯片/光通信上游", "themes": ["激光芯片", "CPO", "化合物半导体"], "lens": {"bottleneck": 9, "upstream": 9, "capex": 7, "customer": 4, "smallcap": 7, "financing": 4, "catalyst": 5}},
        {"symbol": "000988", "name": "华工科技", "role": "光模块/激光加工", "themes": ["光模块", "激光", "数据中心"], "lens": {"bottleneck": 5, "upstream": 5, "capex": 7, "customer": 5, "smallcap": 4, "financing": 5, "catalyst": 4}},
        {"symbol": "300570", "name": "太辰光", "role": "光器件/连接器", "themes": ["光器件", "数据中心", "CPO"], "lens": {"bottleneck": 6, "upstream": 7, "capex": 7, "customer": 4, "smallcap": 7, "financing": 4, "catalyst": 4}},
        {"symbol": "002463", "name": "沪电股份", "role": "AI 服务器 PCB", "themes": ["PCB", "AI服务器", "数据中心"], "lens": {"bottleneck": 6, "upstream": 5, "capex": 8, "customer": 6, "smallcap": 4, "financing": 5, "catalyst": 5}},
        {"symbol": "300476", "name": "胜宏科技", "role": "AI PCB/算力硬件", "themes": ["PCB", "AI服务器", "英伟达链"], "lens": {"bottleneck": 6, "upstream": 5, "capex": 8, "customer": 6, "smallcap": 4, "financing": 5, "catalyst": 5}},
        {"symbol": "688008", "name": "澜起科技", "role": "内存接口/HBM 相关", "themes": ["HBM", "存储芯片", "AI服务器"], "lens": {"bottleneck": 7, "upstream": 7, "capex": 8, "customer": 5, "smallcap": 3, "financing": 6, "catalyst": 5}},
        {"symbol": "300475", "name": "香农芯创", "role": "存储/HBM 产业链", "themes": ["HBM", "存储芯片"], "lens": {"bottleneck": 5, "upstream": 5, "capex": 7, "customer": 3, "smallcap": 6, "financing": 4, "catalyst": 4}},
        {"symbol": "603019", "name": "中科曙光", "role": "AI 服务器/国产算力", "themes": ["AI服务器", "算力", "数据中心"], "lens": {"bottleneck": 4, "upstream": 3, "capex": 7, "customer": 5, "smallcap": 2, "financing": 5, "catalyst": 4}},
        {"symbol": "601138", "name": "工业富联", "role": "AI 服务器制造", "themes": ["AI服务器", "英伟达链"], "lens": {"bottleneck": 4, "upstream": 3, "capex": 8, "customer": 7, "smallcap": 0, "financing": 6, "catalyst": 4}},
        {"symbol": "002518", "name": "科士达", "role": "数据中心电源/储能", "themes": ["数据中心电源", "电力", "AI算力"], "lens": {"bottleneck": 5, "upstream": 5, "capex": 7, "customer": 4, "smallcap": 6, "financing": 5, "catalyst": 4}},
        {"symbol": "002837", "name": "英维克", "role": "数据中心温控/液冷", "themes": ["液冷", "数据中心", "AI算力"], "lens": {"bottleneck": 5, "upstream": 5, "capex": 7, "customer": 5, "smallcap": 5, "financing": 5, "catalyst": 5}},
    ],
    "hk": [
        {"symbol": "0981.HK", "name": "中芯国际", "role": "先进制程/国产晶圆代工", "themes": ["半导体", "AI芯片", "国产替代"], "lens": {"bottleneck": 6, "upstream": 7, "capex": 7, "customer": 5, "smallcap": 1, "financing": 5, "catalyst": 4}},
        {"symbol": "1347.HK", "name": "华虹半导体", "role": "特色工艺/功率半导体代工", "themes": ["半导体", "功率器件"], "lens": {"bottleneck": 5, "upstream": 6, "capex": 5, "customer": 4, "smallcap": 3, "financing": 5, "catalyst": 3}},
        {"symbol": "2018.HK", "name": "瑞声科技", "role": "光学/声学/精密制造", "themes": ["光学", "AI终端"], "lens": {"bottleneck": 4, "upstream": 4, "capex": 4, "customer": 5, "smallcap": 3, "financing": 5, "catalyst": 3}},
        {"symbol": "2382.HK", "name": "舜宇光学科技", "role": "光学零部件/车载与手机镜头", "themes": ["光学", "机器人视觉", "AI终端"], "lens": {"bottleneck": 5, "upstream": 5, "capex": 4, "customer": 5, "smallcap": 2, "financing": 5, "catalyst": 3}},
        {"symbol": "0763.HK", "name": "中兴通讯", "role": "通信设备/数据中心网络", "themes": ["通信设备", "AI网络"], "lens": {"bottleneck": 4, "upstream": 4, "capex": 5, "customer": 5, "smallcap": 2, "financing": 5, "catalyst": 3}},
        {"symbol": "0728.HK", "name": "中国电信", "role": "云/算力基础设施", "themes": ["云计算", "数据中心", "算力"], "lens": {"bottleneck": 3, "upstream": 2, "capex": 5, "customer": 4, "smallcap": 0, "financing": 6, "catalyst": 2}},
        {"symbol": "1024.HK", "name": "快手-W", "role": "AI 应用/内容平台", "themes": ["AI应用", "互联网"], "lens": {"bottleneck": 2, "upstream": 1, "capex": 4, "customer": 3, "smallcap": 1, "financing": 5, "catalyst": 3}},
        {"symbol": "0700.HK", "name": "腾讯控股", "role": "云/AI 应用/互联网平台", "themes": ["AI应用", "云计算"], "lens": {"bottleneck": 2, "upstream": 1, "capex": 5, "customer": 4, "smallcap": 0, "financing": 7, "catalyst": 3}},
    ],
    "us": [
        {"symbol": "SIVE.ST", "name": "Sivers Semiconductors", "role": "CPO CW/DFB 激光器", "themes": ["CPO", "Photonics", "merchant laser"], "lens": {"bottleneck": 10, "upstream": 10, "capex": 9, "customer": 7, "smallcap": 8, "financing": 4, "catalyst": 8}},
        {"symbol": "AAOI", "name": "Applied Optoelectronics", "role": "美国光模块/激光器", "themes": ["1.6T", "Photonics", "AI datacenter"], "lens": {"bottleneck": 8, "upstream": 7, "capex": 9, "customer": 8, "smallcap": 6, "financing": 1, "catalyst": 7}},
        {"symbol": "LITE", "name": "Lumentum", "role": "OCS/光器件/CPO", "themes": ["CPO", "OCS", "Google TPU"], "lens": {"bottleneck": 8, "upstream": 7, "capex": 9, "customer": 8, "smallcap": 3, "financing": 5, "catalyst": 5}},
        {"symbol": "COHR", "name": "Coherent", "role": "多元光子/激光/材料", "themes": ["Photonics", "CPO", "materials"], "lens": {"bottleneck": 7, "upstream": 7, "capex": 8, "customer": 7, "smallcap": 2, "financing": 5, "catalyst": 4}},
        {"symbol": "AXTI", "name": "AXT", "role": "InP/GaAs 衬底", "themes": ["InP substrate", "compound semi"], "lens": {"bottleneck": 10, "upstream": 10, "capex": 8, "customer": 5, "smallcap": 9, "financing": 3, "catalyst": 6}},
        {"symbol": "SOI", "name": "Solaris Energy Infrastructure", "role": "AI 电力/能源基础设施", "themes": ["power", "grid", "AI datacenter"], "lens": {"bottleneck": 7, "upstream": 6, "capex": 8, "customer": 5, "smallcap": 6, "financing": 5, "catalyst": 5}},
        {"symbol": "NBIS", "name": "Nebius", "role": "neocloud/AI 云", "themes": ["neocloud", "AI datacenter"], "lens": {"bottleneck": 5, "upstream": 3, "capex": 8, "customer": 8, "smallcap": 5, "financing": 8, "catalyst": 6}},
        {"symbol": "MU", "name": "Micron", "role": "HBM/DRAM/NAND", "themes": ["HBM", "memory"], "lens": {"bottleneck": 7, "upstream": 6, "capex": 8, "customer": 6, "smallcap": 1, "financing": 6, "catalyst": 5}},
        {"symbol": "SNDK", "name": "Sandisk", "role": "NAND/存储周期", "themes": ["NAND", "memory"], "lens": {"bottleneck": 6, "upstream": 5, "capex": 6, "customer": 4, "smallcap": 4, "financing": 5, "catalyst": 5}},
        {"symbol": "VST", "name": "Vistra", "role": "AI 电力/核电受益", "themes": ["power", "grid", "AI datacenter"], "lens": {"bottleneck": 6, "upstream": 5, "capex": 7, "customer": 5, "smallcap": 1, "financing": 6, "catalyst": 4}},
        {"symbol": "CEG", "name": "Constellation Energy", "role": "AI 电力/核电 PPA", "themes": ["power", "nuclear", "AI datacenter"], "lens": {"bottleneck": 6, "upstream": 5, "capex": 7, "customer": 6, "smallcap": 0, "financing": 6, "catalyst": 4}},
        {"symbol": "IREN", "name": "IREN", "role": "AI 数据中心/矿企转型", "themes": ["neocloud", "AI datacenter"], "lens": {"bottleneck": 4, "upstream": 2, "capex": 7, "customer": 4, "smallcap": 5, "financing": -5, "catalyst": 3}},
        {"symbol": "CRWV", "name": "CoreWeave", "role": "GPU 云/AI 基建", "themes": ["neocloud", "GPU cloud"], "lens": {"bottleneck": 4, "upstream": 2, "capex": 8, "customer": 6, "smallcap": 1, "financing": -3, "catalyst": 4}},
    ],
}

SERENITY_A_BY_CODE = {item["symbol"]: item for item in SERENITY_UNIVERSES["a_share"]}

SERENITY_MARKET_POLICY = {
    "a_share": {
        "lens_weight": 1.25,
        "chan_weight": 0.75,
        "hard_penalty": 8,
        "threshold": 62,
        "ma10_limit": 12.0,
        "pct5_limit": 20.0,
        "change_limit": 10.5,
    },
    "hk": {
        "lens_weight": 1.0,
        "chan_weight": 0.86,
        "hard_penalty": 9,
        "threshold": 64,
        "ma10_limit": 10.0,
        "pct5_limit": 16.0,
        "change_limit": 8.5,
    },
    "us": {
        "lens_weight": 1.0,
        "chan_weight": 0.86,
        "hard_penalty": 9,
        "threshold": 66,
        "ma10_limit": 10.0,
        "pct5_limit": 22.0,
        "change_limit": 14.0,
    },
}

HK_BROAD_UNIVERSE = [
    {"symbol": "0005.HK", "name": "汇丰控股", "role": "金融/高流动性权重", "themes": ["金融", "高股息"]},
    {"symbol": "0011.HK", "name": "恒生银行", "role": "金融/本地银行", "themes": ["金融", "高股息"]},
    {"symbol": "0388.HK", "name": "香港交易所", "role": "交易所/市场活跃度", "themes": ["金融科技", "港股活跃度"]},
    {"symbol": "0939.HK", "name": "建设银行", "role": "银行/高股息", "themes": ["金融", "高股息"]},
    {"symbol": "1398.HK", "name": "工商银行", "role": "银行/高股息", "themes": ["金融", "高股息"]},
    {"symbol": "2318.HK", "name": "中国平安", "role": "保险/金融权重", "themes": ["保险", "金融"]},
    {"symbol": "1299.HK", "name": "友邦保险", "role": "保险/消费金融", "themes": ["保险", "金融"]},
    {"symbol": "0941.HK", "name": "中国移动", "role": "运营商/算力基础设施", "themes": ["云计算", "算力", "高股息"]},
    {"symbol": "0992.HK", "name": "联想集团", "role": "AI PC/服务器", "themes": ["AI终端", "服务器"]},
    {"symbol": "1810.HK", "name": "小米集团-W", "role": "AI终端/智能汽车", "themes": ["AI终端", "汽车电子"]},
    {"symbol": "3690.HK", "name": "美团-W", "role": "本地生活/AI应用", "themes": ["互联网", "AI应用"]},
    {"symbol": "9618.HK", "name": "京东集团-SW", "role": "电商/物流科技", "themes": ["互联网", "物流科技"]},
    {"symbol": "9988.HK", "name": "阿里巴巴-W", "role": "云/AI应用/电商", "themes": ["云计算", "AI应用"]},
    {"symbol": "9999.HK", "name": "网易-S", "role": "游戏/AI内容", "themes": ["AI应用", "游戏"]},
    {"symbol": "9888.HK", "name": "百度集团-SW", "role": "AI模型/自动驾驶", "themes": ["AI应用", "自动驾驶"]},
    {"symbol": "6618.HK", "name": "京东健康", "role": "互联网医疗", "themes": ["AI医疗", "互联网"]},
    {"symbol": "9626.HK", "name": "哔哩哔哩-W", "role": "内容平台/AI应用", "themes": ["AI应用", "互联网"]},
    {"symbol": "9992.HK", "name": "泡泡玛特", "role": "消费/出海", "themes": ["消费", "出海"]},
    {"symbol": "1211.HK", "name": "比亚迪股份", "role": "新能源车/电池", "themes": ["新能源车", "电池"]},
    {"symbol": "9866.HK", "name": "蔚来-SW", "role": "新能源车", "themes": ["新能源车", "智能驾驶"]},
    {"symbol": "2015.HK", "name": "理想汽车-W", "role": "新能源车/智能驾驶", "themes": ["新能源车", "智能驾驶"]},
    {"symbol": "9868.HK", "name": "小鹏汽车-W", "role": "新能源车/智能驾驶", "themes": ["新能源车", "智能驾驶"]},
    {"symbol": "2333.HK", "name": "长城汽车", "role": "汽车/出海", "themes": ["汽车", "出海"]},
    {"symbol": "0175.HK", "name": "吉利汽车", "role": "汽车/智能化", "themes": ["汽车", "智能驾驶"]},
    {"symbol": "0883.HK", "name": "中国海洋石油", "role": "能源/高股息", "themes": ["能源", "高股息"]},
    {"symbol": "0857.HK", "name": "中国石油股份", "role": "能源/高股息", "themes": ["能源", "高股息"]},
    {"symbol": "1088.HK", "name": "中国神华", "role": "煤炭/电力", "themes": ["电力", "高股息"]},
    {"symbol": "2899.HK", "name": "紫金矿业", "role": "铜金矿/资源", "themes": ["资源", "铜"]},
    {"symbol": "1919.HK", "name": "中远海控", "role": "航运/周期", "themes": ["航运", "周期"]},
    {"symbol": "2319.HK", "name": "蒙牛乳业", "role": "消费", "themes": ["消费"]},
    {"symbol": "2020.HK", "name": "安踏体育", "role": "消费/服饰", "themes": ["消费", "出海"]},
    {"symbol": "2331.HK", "name": "李宁", "role": "消费/服饰", "themes": ["消费"]},
    {"symbol": "2269.HK", "name": "药明生物", "role": "创新药/CXO", "themes": ["创新药", "医疗"]},
    {"symbol": "1177.HK", "name": "中国生物制药", "role": "创新药", "themes": ["创新药", "医疗"]},
    {"symbol": "1093.HK", "name": "石药集团", "role": "创新药", "themes": ["创新药", "医疗"]},
    {"symbol": "2359.HK", "name": "药明康德", "role": "CXO", "themes": ["创新药", "医疗"]},
    {"symbol": "3759.HK", "name": "康龙化成", "role": "CXO", "themes": ["创新药", "医疗"]},
    {"symbol": "0268.HK", "name": "金蝶国际", "role": "企业软件/AI应用", "themes": ["AI应用", "软件"]},
    {"symbol": "0020.HK", "name": "商汤-W", "role": "AI模型/视觉", "themes": ["AI应用", "机器视觉"]},
    {"symbol": "1347.HK", "name": "华虹半导体", "role": "特色工艺/功率半导体", "themes": ["半导体", "功率器件"]},
]

US_BROAD_UNIVERSE = [
    {"symbol": "NVDA", "name": "NVIDIA", "role": "GPU/AI算力核心", "themes": ["AI芯片", "GPU", "AI datacenter"]},
    {"symbol": "AMD", "name": "AMD", "role": "GPU/CPU/AI服务器", "themes": ["AI芯片", "GPU"]},
    {"symbol": "AVGO", "name": "Broadcom", "role": "ASIC/网络/AI连接", "themes": ["ASIC", "AI网络", "半导体"]},
    {"symbol": "MRVL", "name": "Marvell", "role": "数据中心网络/ASIC", "themes": ["AI网络", "ASIC"]},
    {"symbol": "TSM", "name": "TSMC", "role": "先进制程代工", "themes": ["半导体", "AI芯片"]},
    {"symbol": "ASML", "name": "ASML", "role": "EUV设备", "themes": ["半导体设备", "上游瓶颈"]},
    {"symbol": "AMAT", "name": "Applied Materials", "role": "半导体设备", "themes": ["半导体设备"]},
    {"symbol": "LRCX", "name": "Lam Research", "role": "半导体设备", "themes": ["半导体设备"]},
    {"symbol": "KLAC", "name": "KLA", "role": "检测设备", "themes": ["半导体设备"]},
    {"symbol": "ARM", "name": "Arm", "role": "CPU IP/AI终端", "themes": ["AI芯片", "IP"]},
    {"symbol": "SMCI", "name": "Super Micro Computer", "role": "AI服务器", "themes": ["AI服务器", "AI datacenter"]},
    {"symbol": "DELL", "name": "Dell", "role": "AI服务器", "themes": ["AI服务器"]},
    {"symbol": "HPE", "name": "HPE", "role": "服务器/网络", "themes": ["AI服务器", "网络"]},
    {"symbol": "ANET", "name": "Arista Networks", "role": "AI数据中心交换机", "themes": ["AI网络", "数据中心"]},
    {"symbol": "CSCO", "name": "Cisco", "role": "网络设备", "themes": ["AI网络"]},
    {"symbol": "ORCL", "name": "Oracle", "role": "云/数据库/AI基建", "themes": ["云计算", "AI datacenter"]},
    {"symbol": "MSFT", "name": "Microsoft", "role": "云/AI应用", "themes": ["云计算", "AI应用"]},
    {"symbol": "GOOGL", "name": "Alphabet", "role": "云/TPU/AI应用", "themes": ["云计算", "AI芯片"]},
    {"symbol": "META", "name": "Meta", "role": "AI capex/广告", "themes": ["AI应用", "AI datacenter"]},
    {"symbol": "AMZN", "name": "Amazon", "role": "AWS/AI云", "themes": ["云计算", "AI datacenter"]},
    {"symbol": "AAPL", "name": "Apple", "role": "AI终端", "themes": ["AI终端", "消费电子"]},
    {"symbol": "TSLA", "name": "Tesla", "role": "自动驾驶/机器人", "themes": ["自动驾驶", "机器人"]},
    {"symbol": "PLTR", "name": "Palantir", "role": "AI软件/政府企业", "themes": ["AI应用", "软件"]},
    {"symbol": "SNOW", "name": "Snowflake", "role": "数据云", "themes": ["AI应用", "数据"]},
    {"symbol": "DDOG", "name": "Datadog", "role": "云监控/AI运维", "themes": ["软件", "AI应用"]},
    {"symbol": "NET", "name": "Cloudflare", "role": "边缘云/AI网络", "themes": ["云计算", "AI网络"]},
    {"symbol": "CRWD", "name": "CrowdStrike", "role": "AI安全", "themes": ["网络安全", "AI应用"]},
    {"symbol": "PANW", "name": "Palo Alto Networks", "role": "网络安全", "themes": ["网络安全", "AI应用"]},
    {"symbol": "NOW", "name": "ServiceNow", "role": "企业AI流程", "themes": ["AI应用", "软件"]},
    {"symbol": "ADBE", "name": "Adobe", "role": "生成式AI软件", "themes": ["AI应用", "软件"]},
    {"symbol": "CRM", "name": "Salesforce", "role": "企业AI软件", "themes": ["AI应用", "软件"]},
    {"symbol": "MDB", "name": "MongoDB", "role": "AI应用数据层", "themes": ["数据", "软件"]},
    {"symbol": "RBLX", "name": "Roblox", "role": "AI内容/平台", "themes": ["AI应用", "内容"]},
    {"symbol": "APP", "name": "AppLovin", "role": "AI广告", "themes": ["AI应用", "广告"]},
    {"symbol": "TTD", "name": "The Trade Desk", "role": "广告科技", "themes": ["AI应用", "广告"]},
    {"symbol": "QCOM", "name": "Qualcomm", "role": "AI终端芯片", "themes": ["AI终端", "半导体"]},
    {"symbol": "TXN", "name": "Texas Instruments", "role": "模拟芯片", "themes": ["半导体", "工业"]},
    {"symbol": "ADI", "name": "Analog Devices", "role": "模拟芯片", "themes": ["半导体", "工业"]},
    {"symbol": "ON", "name": "ON Semiconductor", "role": "功率半导体/汽车", "themes": ["功率器件", "汽车电子"]},
    {"symbol": "MPWR", "name": "Monolithic Power", "role": "AI服务器电源芯片", "themes": ["电源", "AI服务器"]},
    {"symbol": "ALAB", "name": "Astera Labs", "role": "AI连接/CXL", "themes": ["AI网络", "半导体"]},
    {"symbol": "GFS", "name": "GlobalFoundries", "role": "特色工艺代工", "themes": ["半导体"]},
    {"symbol": "INTC", "name": "Intel", "role": "CPU/晶圆代工", "themes": ["半导体", "AI芯片"]},
    {"symbol": "WDC", "name": "Western Digital", "role": "存储/NAND", "themes": ["存储", "AI datacenter"]},
    {"symbol": "STX", "name": "Seagate", "role": "HDD/数据中心存储", "themes": ["存储", "AI datacenter"]},
    {"symbol": "CLS", "name": "Celestica", "role": "AI服务器/电子制造", "themes": ["AI服务器", "制造"]},
    {"symbol": "FLEX", "name": "Flex", "role": "电子制造/AI硬件", "themes": ["AI服务器", "制造"]},
    {"symbol": "JBL", "name": "Jabil", "role": "电子制造", "themes": ["AI服务器", "制造"]},
    {"symbol": "ETN", "name": "Eaton", "role": "数据中心电力", "themes": ["电力", "AI datacenter"]},
    {"symbol": "PWR", "name": "Quanta Services", "role": "电网建设", "themes": ["电力", "AI datacenter"]},
    {"symbol": "GEV", "name": "GE Vernova", "role": "电力设备", "themes": ["电力", "AI datacenter"]},
    {"symbol": "NRG", "name": "NRG Energy", "role": "电力", "themes": ["电力", "AI datacenter"]},
    {"symbol": "TLN", "name": "Talen Energy", "role": "AI电力/核电", "themes": ["电力", "核电"]},
    {"symbol": "OKLO", "name": "Oklo", "role": "核能/小堆", "themes": ["核电", "电力"]},
    {"symbol": "SMR", "name": "NuScale Power", "role": "小型核反应堆", "themes": ["核电", "电力"]},
    {"symbol": "CCJ", "name": "Cameco", "role": "铀/核燃料", "themes": ["核电", "资源"]},
    {"symbol": "APLD", "name": "Applied Digital", "role": "AI数据中心", "themes": ["neocloud", "AI datacenter"]},
    {"symbol": "CORZ", "name": "Core Scientific", "role": "AI数据中心/矿企转型", "themes": ["neocloud", "AI datacenter"]},
    {"symbol": "CIFR", "name": "Cipher Mining", "role": "AI数据中心/矿企转型", "themes": ["neocloud", "AI datacenter"]},
    {"symbol": "HUT", "name": "Hut 8", "role": "AI数据中心/矿企转型", "themes": ["neocloud", "AI datacenter"]},
    {"symbol": "RIOT", "name": "Riot Platforms", "role": "电力/矿企转型", "themes": ["neocloud", "电力"]},
    {"symbol": "IONQ", "name": "IonQ", "role": "量子计算", "themes": ["量子计算", "AI应用"]},
    {"symbol": "QBTS", "name": "D-Wave Quantum", "role": "量子计算", "themes": ["量子计算"]},
    {"symbol": "RGTI", "name": "Rigetti Computing", "role": "量子计算", "themes": ["量子计算"]},
    {"symbol": "RKLB", "name": "Rocket Lab", "role": "商业航天", "themes": ["商业航天"]},
    {"symbol": "ASTS", "name": "AST SpaceMobile", "role": "卫星通信", "themes": ["商业航天", "通信"]},
    {"symbol": "ACHR", "name": "Archer Aviation", "role": "eVTOL", "themes": ["低空经济", "航空"]},
    {"symbol": "JOBY", "name": "Joby Aviation", "role": "eVTOL", "themes": ["低空经济", "航空"]},
    {"symbol": "ISRG", "name": "Intuitive Surgical", "role": "手术机器人", "themes": ["机器人", "医疗"]},
    {"symbol": "TER", "name": "Teradyne", "role": "测试设备/机器人", "themes": ["机器人", "半导体设备"]},
    {"symbol": "ROK", "name": "Rockwell Automation", "role": "工业自动化", "themes": ["机器人", "工业"]},
]

HK_AI_EXPANSION_UNIVERSE = [
    {"symbol": "0522.HK", "name": "ASMPT", "role": "半导体封装设备/先进封装", "themes": ["半导体设备", "先进封装", "AI芯片"]},
    {"symbol": "0285.HK", "name": "比亚迪电子", "role": "AI终端/电子制造", "themes": ["AI终端", "消费电子", "机器人"]},
    {"symbol": "1478.HK", "name": "丘钛科技", "role": "摄像头模组/机器视觉", "themes": ["机器视觉", "AI终端", "机器人视觉"]},
    {"symbol": "1882.HK", "name": "海天国际", "role": "工业设备/自动化制造", "themes": ["机器人", "工业自动化"]},
    {"symbol": "3888.HK", "name": "金山软件", "role": "办公软件/AI应用", "themes": ["AI应用", "软件", "办公AI"]},
    {"symbol": "0772.HK", "name": "阅文集团", "role": "AI内容/IP平台", "themes": ["AI应用", "内容", "游戏"]},
    {"symbol": "0777.HK", "name": "网龙", "role": "教育科技/AI内容", "themes": ["AI教育", "AI应用", "游戏"]},
    {"symbol": "2400.HK", "name": "心动公司", "role": "游戏/AI内容生产", "themes": ["AI应用", "游戏", "内容"]},
    {"symbol": "9698.HK", "name": "万国数据-SW", "role": "数据中心/云基础设施", "themes": ["数据中心", "云计算", "AI datacenter"]},
    {"symbol": "6682.HK", "name": "第四范式", "role": "企业AI平台", "themes": ["AI应用", "大模型", "企业软件"]},
    {"symbol": "2158.HK", "name": "医渡科技", "role": "AI医疗/医疗数据", "themes": ["AI医疗", "数据", "AI应用"]},
    {"symbol": "6608.HK", "name": "百融云-W", "role": "金融AI/决策智能", "themes": ["AI应用", "金融科技", "数据"]},
    {"symbol": "9923.HK", "name": "移卡", "role": "支付科技/AI营销", "themes": ["金融科技", "AI应用"]},
    {"symbol": "9990.HK", "name": "祖龙娱乐", "role": "游戏/AI内容", "themes": ["游戏", "AI应用", "内容"]},
    {"symbol": "6610.HK", "name": "飞天云动", "role": "AR/VR内容与营销", "themes": ["AI应用", "空间计算", "内容"]},
    {"symbol": "9880.HK", "name": "优必选", "role": "人形机器人/服务机器人", "themes": ["机器人", "人形机器人", "AI终端"]},
]

US_AI_EXPANSION_UNIVERSE = [
    {"symbol": "VRT", "name": "Vertiv", "role": "AI数据中心电源/散热", "themes": ["电力", "液冷", "AI datacenter"]},
    {"symbol": "FIX", "name": "Comfort Systems", "role": "数据中心机电工程", "themes": ["电力", "数据中心", "AI datacenter"]},
    {"symbol": "MOD", "name": "Modine", "role": "数据中心热管理", "themes": ["液冷", "热管理", "AI datacenter"]},
    {"symbol": "EQIX", "name": "Equinix", "role": "数据中心REIT", "themes": ["数据中心", "云计算"]},
    {"symbol": "DLR", "name": "Digital Realty", "role": "数据中心REIT", "themes": ["数据中心", "云计算"]},
    {"symbol": "CDNS", "name": "Cadence", "role": "EDA/芯片设计软件", "themes": ["EDA", "AI芯片", "软件"]},
    {"symbol": "SNPS", "name": "Synopsys", "role": "EDA/IP/芯片设计软件", "themes": ["EDA", "AI芯片", "软件"]},
    {"symbol": "KEYS", "name": "Keysight", "role": "高速通信/半导体测试", "themes": ["测试设备", "AI网络", "半导体设备"]},
    {"symbol": "ONTO", "name": "Onto Innovation", "role": "先进封装检测量测", "themes": ["半导体设备", "先进封装"]},
    {"symbol": "CAMT", "name": "Camtek", "role": "先进封装检测", "themes": ["半导体设备", "先进封装", "AI芯片"]},
    {"symbol": "ACLS", "name": "Axcelis", "role": "离子注入设备", "themes": ["半导体设备", "功率器件"]},
    {"symbol": "AEHR", "name": "Aehr Test Systems", "role": "功率半导体/SiC测试", "themes": ["半导体设备", "功率器件"]},
    {"symbol": "FORM", "name": "FormFactor", "role": "晶圆探针卡/测试", "themes": ["半导体设备", "测试设备"]},
    {"symbol": "TSEM", "name": "Tower Semiconductor", "role": "特色工艺代工", "themes": ["半导体", "模拟芯片"]},
    {"symbol": "CRDO", "name": "Credo Technology", "role": "高速互连/SerDes/AEC", "themes": ["AI网络", "数据中心", "半导体"]},
    {"symbol": "MCHP", "name": "Microchip", "role": "MCU/连接芯片", "themes": ["半导体", "工业"]},
    {"symbol": "NXPI", "name": "NXP", "role": "汽车/边缘AI芯片", "themes": ["汽车电子", "AI终端", "半导体"]},
    {"symbol": "STM", "name": "STMicroelectronics", "role": "功率/汽车半导体", "themes": ["功率器件", "汽车电子"]},
    {"symbol": "SITM", "name": "SiTime", "role": "精密时钟芯片", "themes": ["半导体", "AI网络"]},
    {"symbol": "IOT", "name": "Samsara", "role": "工业物联网/AI车队", "themes": ["AI应用", "工业软件", "物联网"]},
    {"symbol": "AI", "name": "C3.ai", "role": "企业AI应用", "themes": ["AI应用", "软件"]},
    {"symbol": "SOUN", "name": "SoundHound AI", "role": "语音AI", "themes": ["AI应用", "语音AI"]},
    {"symbol": "BBAI", "name": "BigBear.ai", "role": "国防/决策AI", "themes": ["AI应用", "国防科技"]},
    {"symbol": "PATH", "name": "UiPath", "role": "RPA/企业自动化", "themes": ["AI应用", "自动化", "软件"]},
    {"symbol": "TEM", "name": "Tempus AI", "role": "AI医疗数据", "themes": ["AI医疗", "数据", "AI应用"]},
    {"symbol": "SYM", "name": "Symbotic", "role": "仓储机器人", "themes": ["机器人", "自动化"]},
    {"symbol": "SERV", "name": "Serve Robotics", "role": "配送机器人", "themes": ["机器人", "自动驾驶"]},
    {"symbol": "FIG", "name": "Figma", "role": "AI设计协作软件", "themes": ["AI应用", "软件", "设计工具"]},
]

HK_TECH_AI_EXTRA_ROWS = [
    ("01385.HK", "上海复旦", "FPGA/集成电路设计", ["半导体", "AI芯片", "国产替代"]),
    ("01415.HK", "高伟电子", "摄像头模组/AI终端", ["机器视觉", "AI终端"]),
    ("01523.HK", "珩湾科技", "网络设备/边缘连接", ["AI网络", "物联网"]),
    ("01675.HK", "亚信科技", "通信软件/运营商AI", ["AI应用", "软件", "通信"]),
    ("01860.HK", "汇量科技", "AI广告/营销科技", ["AI应用", "广告"]),
    ("01896.HK", "猫眼娱乐", "AI内容/票务平台", ["AI应用", "内容"]),
    ("02013.HK", "微盟集团", "SaaS/AI营销", ["AI应用", "软件", "广告"]),
    ("02121.HK", "创新奇智", "工业AI平台", ["AI应用", "工业软件"]),
    ("02192.HK", "医脉通", "医疗数据/AI医疗", ["AI医疗", "数据"]),
    ("02252.HK", "微创机器人-B", "手术机器人", ["机器人", "AI医疗"]),
    ("02369.HK", "酷派集团", "智能终端", ["AI终端", "消费电子"]),
    ("02390.HK", "知乎-W", "AI内容社区", ["AI应用", "内容"]),
    ("02423.HK", "贝壳-W", "居住科技/AI服务", ["AI应用", "互联网"]),
    ("02498.HK", "速腾聚创", "激光雷达/机器人视觉", ["机器视觉", "自动驾驶", "机器人"]),
    ("02518.HK", "汽车之家-S", "汽车互联网/智能车生态", ["AI应用", "汽车电子"]),
    ("02618.HK", "京东物流", "物流自动化/机器人", ["机器人", "物流科技", "AI应用"]),
    ("00327.HK", "百富环球", "支付终端/金融科技", ["金融科技", "AI终端"]),
    ("00354.HK", "中国软件国际", "软件外包/AI应用", ["AI应用", "软件"]),
    ("00552.HK", "中国通信服务", "通信工程/数据中心服务", ["数据中心", "通信", "AI网络"]),
    ("00669.HK", "创科实业", "智能工具/工业自动化", ["机器人", "工业自动化"]),
    ("00696.HK", "中国民航信息网络", "航空IT/数据平台", ["AI应用", "数据"]),
    ("00856.HK", "伟仕佳杰", "ICT分销/企业IT", ["云计算", "AI服务器"]),
    ("00909.HK", "明源云", "地产SaaS/企业软件", ["AI应用", "软件"]),
    ("01119.HK", "创梦天地", "游戏/AI内容", ["游戏", "AI应用"]),
    ("01137.HK", "香港科技探索", "电商科技/物流", ["互联网", "物流科技"]),
    ("01263.HK", "柏能集团", "显卡/AI硬件", ["AI服务器", "GPU", "硬件"]),
    ("01316.HK", "耐世特", "智能转向/汽车电子", ["汽车电子", "自动驾驶"]),
    ("01797.HK", "东方甄选", "AI内容电商", ["AI应用", "内容", "电商"]),
    ("01833.HK", "平安好医生", "AI医疗/互联网医疗", ["AI医疗", "互联网"]),
    ("02096.HK", "先声药业", "AI制药/创新药", ["AI医疗", "创新药"]),
    ("02160.HK", "心通医疗-B", "医疗器械/机器人手术生态", ["AI医疗", "医疗器械"]),
    ("02171.HK", "科济药业-B", "创新药/细胞治疗", ["AI医疗", "创新药"]),
    ("02269.HK", "药明合联", "生物偶联药/CXO", ["AI医疗", "创新药"]),
    ("02357.HK", "中航科工", "航空科技/高端制造", ["商业航天", "工业自动化"]),
    ("02402.HK", "亿华通", "氢能/车载系统", ["汽车电子", "能源科技"]),
    ("02469.HK", "粉笔", "AI教育", ["AI教育", "AI应用"]),
    ("02500.HK", "启明医疗-B", "医疗器械", ["AI医疗", "医疗器械"]),
    ("02552.HK", "华领医药-B", "AI医疗/创新药", ["AI医疗", "创新药"]),
    ("03347.HK", "泰格医药", "CXO/临床数据", ["AI医疗", "创新药"]),
    ("03606.HK", "福耀玻璃", "汽车电子/智能车供应链", ["汽车电子", "智能驾驶"]),
    ("03690.HK", "美团-W", "AI应用/本地生活", ["AI应用", "互联网"]),
    ("03759.HK", "康龙化成", "CXO/AI制药", ["AI医疗", "创新药"]),
    ("06060.HK", "众安在线", "保险科技/AI风控", ["金融科技", "AI应用"]),
    ("06098.HK", "碧桂园服务", "服务机器人/物联网", ["机器人", "物联网"]),
    ("06160.HK", "百济神州", "创新药/AI研发", ["AI医疗", "创新药"]),
    ("06618.HK", "京东健康", "AI医疗/互联网医疗", ["AI医疗", "互联网"]),
    ("06690.HK", "海尔智家", "智能家居/AI终端", ["AI终端", "物联网"]),
    ("06855.HK", "亚盛医药-B", "创新药/AI研发", ["AI医疗", "创新药"]),
    ("09618.HK", "京东集团-SW", "AI零售/物流科技", ["AI应用", "物流科技"]),
    ("09626.HK", "哔哩哔哩-W", "AI内容/社区", ["AI应用", "内容"]),
    ("09666.HK", "金科服务", "智慧社区/物联网", ["物联网", "AI应用"]),
    ("09698.HK", "万国数据-SW", "数据中心", ["数据中心", "AI datacenter"]),
    ("09868.HK", "小鹏汽车-W", "自动驾驶/机器人汽车", ["自动驾驶", "AI终端"]),
    ("09866.HK", "蔚来-SW", "智能车/自动驾驶", ["自动驾驶", "AI终端"]),
    ("09888.HK", "百度集团-SW", "大模型/自动驾驶", ["大模型", "自动驾驶", "AI应用"]),
    ("09899.HK", "云音乐", "AI内容/音乐平台", ["AI应用", "内容"]),
    ("09926.HK", "康方生物", "创新药/AI医疗", ["AI医疗", "创新药"]),
    ("09959.HK", "联易融科技-W", "供应链金融科技", ["金融科技", "AI应用"]),
    ("09961.HK", "携程集团-S", "AI旅行/互联网平台", ["AI应用", "互联网"]),
    ("09966.HK", "康宁杰瑞制药-B", "创新药", ["AI医疗", "创新药"]),
    ("09969.HK", "诺诚健华", "创新药", ["AI医疗", "创新药"]),
    ("09995.HK", "荣昌生物", "创新药", ["AI医疗", "创新药"]),
    ("09988.HK", "阿里巴巴-W", "云/大模型/电商AI", ["云计算", "大模型", "AI应用"]),
    ("09999.HK", "网易-S", "游戏/AI内容", ["游戏", "AI应用"]),
    ("08083.HK", "中国有赞", "SaaS/AI营销", ["AI应用", "软件", "广告"]),
    ("08088.HK", "八零八八投资", "科技投资", ["科技投资"]),
    ("08110.HK", "中国科技产业集团", "科技产业", ["科技投资"]),
    ("08158.HK", "中国再生医学", "医疗科技", ["AI医疗"]),
    ("08267.HK", "蓝港互动", "游戏/AI内容", ["游戏", "AI应用"]),
    ("08357.HK", "REPUBLIC HC", "医疗科技", ["AI医疗"]),
    ("08446.HK", "ITP HOLDINGS", "企业IT服务", ["软件", "AI应用"]),
    ("08475.HK", "千盛集团控股", "数字营销", ["AI应用", "广告"]),
    ("08606.HK", "倢冠控股", "IT解决方案", ["软件", "云计算"]),
    ("09633.HK", "农夫山泉", "智能消费供应链", ["消费科技"]),
    ("09668.HK", "渤海银行", "金融科技", ["金融科技"]),
    ("09699.HK", "顺丰同城", "即时物流/自动化", ["物流科技", "AI应用"]),
    ("09896.HK", "名创优品", "智能零售/出海", ["消费科技", "AI应用"]),
    ("09922.HK", "九毛九", "智能餐饮供应链", ["消费科技"]),
    ("09930.HK", "宏信建发", "工业数字化", ["工业软件", "物联网"]),
    ("09960.HK", "康圣环球", "医疗检测数据", ["AI医疗", "数据"]),
    ("09987.HK", "百胜中国", "智能餐饮/供应链", ["AI应用", "消费科技"]),
    ("09990.HK", "祖龙娱乐", "游戏/AI内容", ["游戏", "AI应用"]),
    ("09997.HK", "康基医疗", "医疗器械/手术生态", ["AI医疗", "医疗器械"]),
    ("02486.HK", "普乐师集团控股", "数字营销/数据服务", ["AI应用", "广告"]),
    ("02505.HK", "EDA集团控股", "跨境电商科技", ["AI应用", "电商"]),
    ("02533.HK", "黑芝麻智能", "自动驾驶AI芯片", ["AI芯片", "自动驾驶", "汽车电子"]),
    ("02536.HK", "经纬天地", "电信网络支持", ["AI网络", "通信"]),
    ("02545.HK", "中赣通信", "通信工程/算力网络", ["AI网络", "通信"]),
    ("02556.HK", "迈富时", "营销SaaS/AI销售", ["AI应用", "软件", "广告"]),
    ("02577.HK", "英诺赛科", "功率半导体/GaN", ["功率器件", "半导体"]),
]

US_TECH_AI_EXTRA_ROWS = [
    ("ADI", "Analog Devices", "模拟芯片/工业AI", ["半导体", "工业"]),
    ("AIP", "Arteris", "芯片互连IP", ["AI芯片", "IP", "半导体"]),
    ("ALGM", "Allegro MicroSystems", "汽车/工业传感芯片", ["汽车电子", "半导体"]),
    ("AMBA", "Ambarella", "边缘AI视觉芯片", ["AI芯片", "机器视觉"]),
    ("APPF", "AppFolio", "垂直SaaS/AI应用", ["AI应用", "软件"]),
    ("ARBE", "Arbe Robotics", "4D雷达/自动驾驶", ["自动驾驶", "机器视觉"]),
    ("ARQQ", "Arqit Quantum", "量子安全", ["量子计算", "网络安全"]),
    ("ARW", "Arrow Electronics", "半导体/电子元器件分销", ["半导体", "硬件"]),
    ("ASAN", "Asana", "AI协作软件", ["AI应用", "软件"]),
    ("ASPI", "ASP Isotopes", "核燃料/同位素", ["核电", "资源"]),
    ("ATKR", "Atkore", "电气基础设施", ["电力", "数据中心"]),
    ("ATMU", "Atmus Filtration", "工业设备", ["工业自动化"]),
    ("AVT", "Avnet", "电子元器件分销", ["半导体", "硬件"]),
    ("AXON", "Axon", "AI执法/视觉数据", ["AI应用", "机器视觉"]),
    ("BKSY", "BlackSky", "卫星数据/AI地理智能", ["商业航天", "AI应用"]),
    ("BL", "BlackLine", "财务自动化软件", ["AI应用", "软件"]),
    ("BOX", "Box", "企业内容AI", ["AI应用", "软件"]),
    ("CFLT", "Confluent", "实时数据流平台", ["数据", "AI应用"]),
    ("CGNX", "Cognex", "机器视觉", ["机器视觉", "机器人"]),
    ("CHKP", "Check Point", "网络安全", ["网络安全", "AI应用"]),
    ("CIEN", "Ciena", "光网络/数据中心互联", ["AI网络", "光通信"]),
    ("CLBT", "Cellebrite", "数据取证AI", ["AI应用", "网络安全"]),
    ("CMBM", "Cambium Networks", "无线网络设备", ["AI网络", "通信"]),
    ("CNXC", "Concentrix", "AI客服/外包", ["AI应用", "软件"]),
    ("COMP", "Compass", "房地产科技/AI经纪", ["AI应用", "软件"]),
    ("COUP", "Coupa Software", "企业采购AI", ["AI应用", "软件"]),
    ("COUR", "Coursera", "AI教育", ["AI教育", "AI应用"]),
    ("CPNG", "Coupang", "电商/物流科技", ["AI应用", "物流科技"]),
    ("DASH", "DoorDash", "本地生活/配送AI", ["AI应用", "物流科技"]),
    ("DBX", "Dropbox", "企业内容AI", ["AI应用", "软件"]),
    ("DOCN", "DigitalOcean", "云计算/AI开发", ["云计算", "AI应用"]),
    ("DOCU", "DocuSign", "AI合同软件", ["AI应用", "软件"]),
    ("DOMO", "Domo", "BI/数据应用", ["数据", "AI应用"]),
    ("DUOL", "Duolingo", "AI教育", ["AI教育", "AI应用"]),
    ("DV", "DoubleVerify", "广告验证AI", ["AI应用", "广告"]),
    ("DXCM", "Dexcom", "医疗传感/AI健康", ["AI医疗", "传感器"]),
    ("ENPH", "Enphase", "电力电子/能源管理", ["电力", "能源科技"]),
    ("ENVX", "Enovix", "先进电池/AI终端", ["AI终端", "电池"]),
    ("ESTC", "Elastic", "搜索/安全/AI数据", ["数据", "AI应用"]),
    ("EXTR", "Extreme Networks", "企业网络", ["AI网络", "通信"]),
    ("FIVN", "Five9", "AI客服云", ["AI应用", "软件"]),
    ("FLYW", "Flywire", "支付科技", ["金融科技", "AI应用"]),
    ("FROG", "JFrog", "DevOps/AI软件供应链", ["软件", "AI应用"]),
    ("FTNT", "Fortinet", "网络安全硬件", ["网络安全", "AI网络"]),
    ("GDDY", "GoDaddy", "AI建站/中小企业软件", ["AI应用", "软件"]),
    ("GTLB", "GitLab", "AI代码/DevOps", ["AI应用", "软件"]),
    ("GWRE", "Guidewire", "保险软件AI", ["AI应用", "金融科技"]),
    ("HCP", "HashiCorp", "云基础设施软件", ["云计算", "软件"]),
    ("HIMS", "Hims & Hers", "AI医疗/数字健康", ["AI医疗", "AI应用"]),
    ("HOOD", "Robinhood", "金融科技/AI交易体验", ["金融科技", "AI应用"]),
    ("HUBS", "HubSpot", "AI营销SaaS", ["AI应用", "软件", "广告"]),
    ("INOD", "Innodata", "AI数据服务", ["数据", "AI应用"]),
    ("INST", "Instructure", "AI教育软件", ["AI教育", "软件"]),
    ("INTA", "Intapp", "专业服务AI软件", ["AI应用", "软件"]),
    ("IRDM", "Iridium", "卫星通信", ["商业航天", "通信"]),
    ("IRTC", "iRhythm", "AI医疗监测", ["AI医疗", "传感器"]),
    ("ITRI", "Itron", "电网物联网", ["物联网", "电力"]),
    ("JAMF", "Jamf", "终端管理/企业IT", ["软件", "AI终端"]),
    ("KC", "Kingsoft Cloud", "云计算/AI云", ["云计算", "AI datacenter"]),
    ("KD", "Kyndryl", "企业IT/AI服务", ["AI应用", "云计算"]),
    ("KLIC", "Kulicke & Soffa", "先进封装设备", ["半导体设备", "先进封装"]),
    ("LASR", "nLIGHT", "工业激光/光子", ["光通信", "工业自动化"]),
    ("LAW", "CS Disco", "法律AI软件", ["AI应用", "软件"]),
    ("LIDR", "AEye", "激光雷达", ["机器视觉", "自动驾驶"]),
    ("LIF", "Life360", "位置数据/家庭AI", ["AI应用", "数据"]),
    ("LSPD", "Lightspeed", "零售SaaS/AI营销", ["AI应用", "软件"]),
    ("MANH", "Manhattan Associates", "供应链软件", ["物流科技", "AI应用"]),
    ("MBLY", "Mobileye", "自动驾驶视觉", ["自动驾驶", "机器视觉"]),
    ("MNDY", "Monday.com", "AI协作软件", ["AI应用", "软件"]),
    ("MOB", "Mobilicom", "无人系统通信", ["机器人", "通信"]),
    ("MSTR", "MicroStrategy", "数据分析/数字资产", ["数据", "AI应用"]),
    ("NCNO", "nCino", "银行SaaS/AI金融", ["金融科技", "AI应用"]),
    ("NICE", "NICE", "AI客服/合规分析", ["AI应用", "软件"]),
    ("NTNX", "Nutanix", "混合云基础设施", ["云计算", "AI datacenter"]),
    ("NVTS", "Navitas", "GaN功率半导体", ["功率器件", "半导体"]),
    ("OLO", "Olo", "餐饮SaaS/AI运营", ["AI应用", "软件"]),
    ("OSIS", "OSI Systems", "安检/机器视觉", ["机器视觉", "国防科技"]),
    ("PAYC", "Paycom", "AI人力资源软件", ["AI应用", "软件"]),
    ("PAYO", "Payoneer", "跨境支付科技", ["金融科技", "AI应用"]),
    ("PCOR", "Procore", "建筑SaaS/AI项目管理", ["AI应用", "软件"]),
    ("PD", "PagerDuty", "AI运维", ["AI应用", "软件"]),
    ("PINS", "Pinterest", "AI推荐/广告", ["AI应用", "广告"]),
    ("PRCH", "Porch", "垂直软件/数据", ["AI应用", "软件"]),
    ("PRGS", "Progress Software", "企业软件/AI应用", ["AI应用", "软件"]),
    ("PSFE", "Paysafe", "支付科技", ["金融科技", "AI应用"]),
    ("PTC", "PTC", "工业软件/数字孪生", ["工业软件", "AI应用"]),
    ("PUBM", "PubMatic", "广告科技AI", ["AI应用", "广告"]),
    ("QUBT", "Quantum Computing", "量子计算", ["量子计算"]),
    ("RDW", "Redwire", "空间基础设施", ["商业航天", "国防科技"]),
    ("REKR", "Rekor", "道路视觉AI", ["机器视觉", "AI应用"]),
    ("RPD", "Rapid7", "网络安全AI", ["网络安全", "AI应用"]),
    ("RXT", "Rackspace", "云托管/AI服务", ["云计算", "AI应用"]),
    ("S", "SentinelOne", "AI网络安全", ["网络安全", "AI应用"]),
    ("SAIL", "SailPoint", "身份安全AI", ["网络安全", "AI应用"]),
    ("SATS", "EchoStar", "卫星通信", ["商业航天", "通信"]),
    ("SE", "Sea", "电商/游戏/金融科技", ["AI应用", "游戏", "金融科技"]),
    ("SHOP", "Shopify", "AI电商SaaS", ["AI应用", "软件", "电商"]),
    ("SKYT", "SkyWater", "特色工艺代工", ["半导体", "AI芯片"]),
    ("SLAB", "Silicon Labs", "IoT芯片", ["物联网", "半导体"]),
    ("SMTC", "Semtech", "连接芯片/LoRa", ["物联网", "半导体"]),
    ("SPT", "Sprout Social", "AI社媒营销", ["AI应用", "广告"]),
    ("SPSC", "SPS Commerce", "供应链SaaS", ["物流科技", "软件"]),
    ("SQ", "Block", "金融科技/AI支付", ["金融科技", "AI应用"]),
    ("SSNC", "SS&C", "金融软件/自动化", ["金融科技", "软件"]),
    ("STEM", "Stem", "AI储能/电力调度", ["电力", "AI应用"]),
    ("TDY", "Teledyne", "传感器/机器视觉", ["机器视觉", "国防科技"]),
    ("TEAM", "Atlassian", "AI协作/DevOps", ["AI应用", "软件"]),
    ("TOST", "Toast", "餐饮SaaS/AI运营", ["AI应用", "软件"]),
    ("TRMB", "Trimble", "工业定位/数字化", ["工业软件", "物联网"]),
    ("TWLO", "Twilio", "AI通信云", ["AI应用", "通信"]),
    ("U", "Unity", "3D/AI内容工具", ["AI应用", "游戏", "内容"]),
    ("UPST", "Upstart", "AI信贷", ["金融科技", "AI应用"]),
    ("VRNS", "Varonis", "数据安全AI", ["网络安全", "数据"]),
    ("WIX", "Wix", "AI建站", ["AI应用", "软件"]),
    ("WK", "Workiva", "AI合规软件", ["AI应用", "软件"]),
    ("XMTR", "Xometry", "制造业AI平台", ["工业软件", "AI应用"]),
    ("YEXT", "Yext", "AI搜索/知识库", ["AI应用", "软件"]),
    ("YOU", "Clear Secure", "身份认证/安全", ["网络安全", "AI应用"]),
    ("ZI", "ZoomInfo", "销售数据AI", ["数据", "AI应用"]),
    ("ZS", "Zscaler", "云安全AI", ["网络安全", "云计算"]),
    ("AVAV", "AeroVironment", "无人机/国防机器人", ["机器人", "国防科技", "商业航天"]),
    ("KTOS", "Kratos Defense", "无人系统/国防AI", ["国防科技", "机器人"]),
    ("LHX", "L3Harris", "国防通信/传感器", ["国防科技", "通信", "机器视觉"]),
    ("OKTA", "Okta", "身份安全AI", ["网络安全", "AI应用"]),
    ("RBRK", "Rubrik", "数据安全/AI备份", ["网络安全", "数据"]),
    ("WDAY", "Workday", "AI人力资源软件", ["AI应用", "软件"]),
    ("VEEV", "Veeva", "生命科学云/AI医疗数据", ["AI医疗", "软件"]),
    ("HQY", "HealthEquity", "医疗金融科技", ["AI医疗", "金融科技"]),
    ("RAMP", "LiveRamp", "数据协作/广告AI", ["数据", "广告", "AI应用"]),
    ("BILL", "BILL Holdings", "中小企业AI财务", ["金融科技", "AI应用"]),
    ("AFRM", "Affirm", "AI信贷/消费金融", ["金融科技", "AI应用"]),
    ("SOFI", "SoFi", "金融科技/AI银行", ["金融科技", "AI应用"]),
    ("VERX", "Vertex", "税务自动化软件", ["AI应用", "软件"]),
    ("WOLF", "Wolfspeed", "SiC功率半导体", ["功率器件", "半导体"]),
    ("POWI", "Power Integrations", "电源芯片", ["功率器件", "AI服务器"]),
    ("DIOD", "Diodes", "分立器件/汽车电子", ["半导体", "汽车电子"]),
    ("LSCC", "Lattice Semiconductor", "FPGA/边缘AI", ["AI芯片", "FPGA", "AI终端"]),
    ("RMBS", "Rambus", "内存接口/HBM链", ["HBM", "AI芯片", "半导体"]),
    ("PI", "Impinj", "RFID/物联网芯片", ["物联网", "半导体"]),
    ("QRVO", "Qorvo", "射频芯片/连接", ["半导体", "通信"]),
    ("SWKS", "Skyworks", "射频芯片/AI终端", ["AI终端", "半导体"]),
    ("OLED", "Universal Display", "OLED材料/AI终端", ["AI终端", "材料"]),
    ("ENTG", "Entegris", "半导体材料/洁净供应链", ["半导体设备", "材料"]),
    ("MKSI", "MKS Instruments", "半导体设备子系统", ["半导体设备", "光子"]),
    ("COHU", "Cohu", "半导体测试设备", ["半导体设备", "测试设备"]),
    ("VECO", "Veeco", "半导体设备/先进封装", ["半导体设备", "先进封装"]),
    ("UCTT", "Ultra Clean", "半导体设备供应链", ["半导体设备", "制造"]),
]


def rows_to_universe(rows: list[tuple[str, str, str, list[str]]]) -> list[dict]:
    return [{"symbol": symbol, "name": name, "role": role, "themes": themes} for symbol, name, role, themes in rows]


def inferred_lens(item: dict, market_key: str) -> dict:
    themes = " ".join(item.get("themes") or [])
    role = item.get("role", "")
    text = f"{themes} {role}".lower()
    lens = {
        "bottleneck": 3,
        "upstream": 2,
        "capex": 4,
        "customer": 4,
        "smallcap": 1 if market_key in ("hk", "us") else 3,
        "financing": 6,
        "catalyst": 2,
    }
    if any(key.lower() in text for key in ["cpo", "photonics", "光模块", "光子", "inp", "激光", "ai网络"]):
        lens.update({"bottleneck": 7, "upstream": 7, "capex": 8, "catalyst": 5})
    if any(key.lower() in text for key in ["hbm", "memory", "存储", "nand", "dram"]):
        lens.update({"bottleneck": 6, "upstream": 5, "capex": 8, "catalyst": 4})
    if any(key.lower() in text for key in ["ai芯片", "gpu", "asic", "半导体", "euv", "设备", "eda", "先进封装", "测试设备"]):
        lens.update({"bottleneck": max(lens["bottleneck"], 6), "upstream": max(lens["upstream"], 5), "capex": max(lens["capex"], 8), "catalyst": max(lens["catalyst"], 4)})
    if any(key.lower() in text for key in ["ai服务器", "datacenter", "数据中心", "云计算", "neocloud", "液冷", "热管理"]):
        lens.update({"capex": max(lens["capex"], 8), "customer": max(lens["customer"], 6), "catalyst": max(lens["catalyst"], 5)})
    if any(key.lower() in text for key in ["电力", "power", "grid", "核电", "nuclear"]):
        lens.update({"bottleneck": max(lens["bottleneck"], 6), "upstream": max(lens["upstream"], 5), "capex": max(lens["capex"], 7), "catalyst": max(lens["catalyst"], 4)})
    if any(key.lower() in text for key in ["ai应用", "software", "软件", "广告", "内容", "ai医疗", "金融科技", "设计工具"]):
        lens.update({"customer": max(lens["customer"], 6), "catalyst": max(lens["catalyst"], 3)})
    if any(key.lower() in text for key in ["机器人", "自动化", "机器视觉", "人形机器人"]):
        lens.update({"bottleneck": max(lens["bottleneck"], 5), "customer": max(lens["customer"], 5), "smallcap": max(lens["smallcap"], 4), "catalyst": max(lens["catalyst"], 4)})
    if any(key.lower() in text for key in ["小堆", "量子", "evtol", "商业航天", "矿企转型", "空间计算"]):
        lens.update({"smallcap": max(lens["smallcap"], 6), "catalyst": max(lens["catalyst"], 5), "financing": min(lens["financing"], 4)})
    if item.get("symbol") in {"SIVE.ST", "AXTI", "OKLO", "SMR", "QBTS", "RGTI", "ACHR", "JOBY"}:
        lens["smallcap"] = max(lens["smallcap"], 7)
    return lens


def normalize_universe_item(item: dict, market_key: str) -> dict:
    normalized = dict(item)
    normalized["symbol"] = str(normalized.get("symbol") or "").upper()
    normalized.setdefault("name", normalized["symbol"])
    normalized.setdefault("role", "")
    normalized.setdefault("themes", [])
    if not normalized.get("lens"):
        normalized["lens"] = inferred_lens(normalized, market_key)
    return normalized


def market_universe(market_key: str) -> list[dict]:
    extras = {
        "hk": HK_BROAD_UNIVERSE + HK_AI_EXPANSION_UNIVERSE + rows_to_universe(HK_TECH_AI_EXTRA_ROWS),
        "us": US_BROAD_UNIVERSE + US_AI_EXPANSION_UNIVERSE + rows_to_universe(US_TECH_AI_EXTRA_ROWS),
    }.get(market_key, [])
    merged: dict[str, dict] = {}
    for item in SERENITY_UNIVERSES.get(market_key, []) + extras:
        normalized = normalize_universe_item(item, market_key)
        symbol = normalized.get("symbol")
        if not symbol:
            continue
        if symbol in merged:
            themes = list(dict.fromkeys((merged[symbol].get("themes") or []) + (normalized.get("themes") or [])))
            merged[symbol].update({key: value for key, value in normalized.items() if value not in ("", None, [])})
            merged[symbol]["themes"] = themes
        else:
            merged[symbol] = normalized
    return list(merged.values())


def now_cn() -> dt.datetime:
    return dt.datetime.now(CN_TZ)


def is_trade_weekday(day: dt.date) -> bool:
    return day.weekday() < 5


def previous_weekday(day: dt.date) -> dt.date:
    day -= dt.timedelta(days=1)
    while not is_trade_weekday(day):
        day -= dt.timedelta(days=1)
    return day


def next_weekday(day: dt.date) -> dt.date:
    day += dt.timedelta(days=1)
    while not is_trade_weekday(day):
        day += dt.timedelta(days=1)
    return day


def market_session(market_key: str, moment: dt.datetime | None = None) -> dict:
    moment = moment or now_cn()
    minutes = moment.hour * 60 + moment.minute
    if not is_trade_weekday(moment.date()):
        return {"session": "closed", "label": "休市", "market": market_key}
    if market_key == "a_share":
        if 9 * 60 + 15 <= minutes < 9 * 60 + 30:
            return {"session": "pre", "label": "集合竞价", "market": market_key}
        if 9 * 60 + 30 <= minutes < 11 * 60 + 30 or 13 * 60 <= minutes < 15 * 60:
            return {"session": "regular", "label": "盘中", "market": market_key}
        if 15 * 60 <= minutes < 15 * 60 + 30:
            return {"session": "post", "label": "盘后", "market": market_key}
        return {"session": "closed", "label": "非交易时段", "market": market_key}
    if market_key == "hk":
        if 9 * 60 <= minutes < 9 * 60 + 30:
            return {"session": "pre", "label": "盘前", "market": market_key}
        if 9 * 60 + 30 <= minutes < 12 * 60 or 13 * 60 <= minutes < 16 * 60:
            return {"session": "regular", "label": "盘中", "market": market_key}
        if 16 * 60 <= minutes < 16 * 60 + 10:
            return {"session": "post", "label": "盘后", "market": market_key}
        return {"session": "closed", "label": "非交易时段", "market": market_key}
    return {"session": "unknown", "label": "实时", "market": market_key}


def yahoo_session_from_meta(meta: dict) -> dict:
    periods = meta.get("currentTradingPeriod") or {}
    now_ts = int(time.time())
    for key, label in (("pre", "盘前"), ("regular", "盘中"), ("post", "盘后")):
        period = periods.get(key) or {}
        start = int(period.get("start") or 0)
        end = int(period.get("end") or 0)
        if start and end and start <= now_ts <= end:
            return {"session": key, "label": label}
    return {"session": "closed", "label": "非交易时段"}


def add_trade_weekdays(day: dt.date, count: int) -> dt.date:
    for _ in range(count):
        day = next_weekday(day)
    return day


def default_signal_date(today: dt.date | None = None) -> dt.date:
    current = now_cn()
    today = today or current.date()
    if today > current.date():
        return previous_weekday(today)
    if not is_trade_weekday(today):
        return previous_weekday(today)
    if current.time() < dt.time(15, 30):
        return previous_weekday(today)
    return today


def default_target_date() -> dt.date:
    current = now_cn()
    today = current.date()
    if not is_trade_weekday(today):
        return next_weekday(today)
    return today


def snapshot_slug(moment: dt.datetime | None = None) -> str:
    moment = moment or now_cn()
    return moment.strftime("%H%M%S")


def parse_cache_name(path: pathlib.Path) -> tuple[str, str, str] | None:
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})(?:_(\d{6}))?\.json", path.name)
    if not match:
        return None
    return match.group(1), match.group(2), match.group(3) or "000000"


def summarize_decision(decision: dict) -> dict:
    primary = decision.get("primary") or decision.get("blocked_candidate")
    summary = {
        "action": decision.get("action"),
        "title": decision.get("title"),
        "message": decision.get("message"),
        "has_primary": bool(decision.get("primary")),
    }
    if primary:
        range_obj = primary.get("estimated_2w_range") or primary.get("estimated_2d_range") or {}
        summary.update(
            {
                "code": primary.get("code"),
                "name": primary.get("name"),
                "confidence": primary.get("recommendation_degree") or primary.get("confidence"),
                "recommendation_degree": primary.get("recommendation_degree") or primary.get("confidence"),
                "estimated_2w_range": range_obj.get("text"),
                "estimated_2d_range": range_obj.get("text"),
                "entry_price": primary.get("entry_price") or primary.get("price"),
                "current_change_pct": primary.get("current_change_pct") or primary.get("change_pct"),
                "realtime_session": ((primary.get("realtime") or {}).get("session_label")),
                "risk_count": len(primary.get("risk_flags") or []),
                "hard_risk_count": primary.get("hard_risk_count", 0),
                "blocker_level": blocker_level(decision, primary),
                "score": primary.get("score"),
                "reason_tags": primary.get("reason_tags"),
            }
        )
    return summary


def summarize_pick(pick: dict) -> dict:
    decision = pick.get("decision") or {}
    summary = {
        "target_date": pick.get("target_date"),
        "signal_date": pick.get("signal_date"),
        "generated_at": pick.get("generated_at"),
        "generated_label": pick.get("generated_label"),
        "snapshot_key": pick.get("snapshot_key"),
        "forecast_end_date": pick.get("forecast_end_date"),
        "forecast_horizon": pick.get("forecast_horizon"),
        "model_version": pick.get("model_version"),
        **summarize_decision(decision),
    }
    markets = pick.get("markets") or {}
    if markets:
        summary["markets"] = {
            key: summarize_decision((section or {}).get("decision") or {})
            for key, section in markets.items()
        }
    return summary


def blocker_level(decision: dict, primary: dict | None = None) -> str:
    if decision.get("primary"):
        return "pass"
    message = decision.get("message") or ""
    hard = safe_float((primary or {}).get("hard_risk_count"))
    risk_count = len((primary or {}).get("risk_flags") or [])
    if "指数环境触发高风险拦截" in message or hard >= 2 or risk_count >= 5:
        return "hard_block"
    if "推荐度低于" in message or "预估下行空间" in message:
        return "soft_block"
    return "no_signal"


def history_payload(limit: int = 30) -> dict:
    rows = []
    for path in PICKS.glob("*.json"):
        parsed = parse_cache_name(path)
        if not parsed:
            continue
        try:
            pick = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        summary = summarize_pick(pick)
        summary["cache_key"] = path.name
        rows.append(summary)
    rows.sort(key=lambda item: (item.get("target_date") or "", item.get("generated_at") or ""), reverse=True)

    latest = None
    latest_path = PICKS / "latest.json"
    if latest_path.exists():
        try:
            latest_pick = json.loads(latest_path.read_text(encoding="utf-8"))
            latest = summarize_pick(latest_pick)
        except Exception:
            latest = None
    return {
        "ok": True,
        "time": now_cn().isoformat(timespec="seconds"),
        "latest": latest,
        "history": rows[:limit],
    }


def load_pick_snapshot(snapshot_key: str) -> dict | None:
    if not snapshot_key or "/" in snapshot_key or not snapshot_key.endswith(".json"):
        return None
    path = PICKS / snapshot_key
    if not path.exists() or not parse_cache_name(path):
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def safe_float(value, default: float = 0.0) -> float:
    try:
        if value in (None, "", "-"):
            return default
        return float(value)
    except Exception:
        return default


def market_prefix(code: str) -> str:
    if code.startswith(("6", "9")):
        return "sh"
    if code.startswith(("8", "4")):
        return "bj"
    return "sz"


def eastmoney_secid(code: str) -> str:
    return ("1." if code.startswith(("6", "9")) else "0.") + code


def http_get_json(url: str, params: dict | None = None, timeout: int = 14) -> dict:
    response = requests.get(
        url,
        params=params,
        headers={"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def serenity_source_status() -> dict:
    status = {
        "repo": "yan-labs/serenity-aleabitoreddit",
        "checked_at": now_cn().isoformat(timespec="seconds"),
        "latest_commit": None,
        "latest_commit_date": None,
        "tweet_archive_span": None,
        "note": "每日生成快照时查询 Serenity repo；若源仓库更新，需复核因子映射后再改变权重。",
    }
    try:
        req = urllib.request.Request(
            "https://api.github.com/repos/yan-labs/serenity-aleabitoreddit/commits/main",
            headers={"User-Agent": UA, "Accept": "application/vnd.github+json"},
        )
        commit = json.loads(urllib.request.urlopen(req, timeout=12).read().decode("utf-8"))
        status["latest_commit"] = (commit.get("sha") or "")[:12]
        status["latest_commit_date"] = (((commit.get("commit") or {}).get("committer") or {}).get("date"))
    except Exception as exc:
        status["note"] = f"Serenity repo 查询失败，沿用内置因子；错误: {exc}"
    try:
        req = urllib.request.Request(
            "https://raw.githubusercontent.com/yan-labs/serenity-aleabitoreddit/main/README.md",
            headers={"User-Agent": UA},
        )
        readme = urllib.request.urlopen(req, timeout=12).read().decode("utf-8", "ignore")
        match = re.search(r"spanning\s+\*\*([^*]+)\*\*", readme)
        if match:
            status["tweet_archive_span"] = match.group(1).strip()
    except Exception:
        pass
    return status


def load_ths_hot(date_text: str) -> list[dict]:
    url = (
        "http://zx.10jqka.com.cn/event/api/getharden/"
        f"date/{date_text}/orderby/date/orderway/desc/charset/GBK/"
    )
    response = requests.get(url, headers={"User-Agent": UA}, timeout=12)
    response.raise_for_status()
    data = response.json()
    if data.get("errocode", 0) != 0:
        return []
    return data.get("data") or []


def find_hot_pool(signal_day: dt.date) -> tuple[str, list[dict]]:
    day = signal_day
    for _ in range(8):
        if is_trade_weekday(day):
            date_text = day.isoformat()
            try:
                rows = load_ths_hot(date_text)
                if rows:
                    return date_text, rows
            except Exception:
                pass
        day = previous_weekday(day)
    return signal_day.isoformat(), []


def load_broad_market_pool(limit: int = 300, relaxed: bool = False) -> list[dict]:
    rows: list[dict] = []
    page_size = 80
    pages = max(1, min(5, math.ceil(limit / page_size)))
    fields = "f2,f3,f6,f8,f12,f14,f20,f21,f23"
    for page in range(1, pages + 1):
        try:
            data = http_get_json(
                "https://push2.eastmoney.com/api/qt/clist/get",
                {
                    "pn": str(page),
                    "pz": str(page_size),
                    "po": "1",
                    "np": "1",
                    "fltt": "2",
                    "invt": "2",
                    "fid": "f6",
                    "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
                    "fields": fields,
                },
                timeout=12,
            )
        except Exception:
            continue
        for item in (data.get("data") or {}).get("diff", []) or []:
            code = str(item.get("f12") or "")
            name = str(item.get("f14") or "")
            if not code or "ST" in name.upper() or code.startswith(("8", "4", "9")):
                continue
            change_pct = safe_float(item.get("f3"))
            amount_yi = safe_float(item.get("f6")) / 100000000
            turnover_pct = safe_float(item.get("f8"))
            price = safe_float(item.get("f2"))
            pb = safe_float(item.get("f23"))
            min_amount = 3 if relaxed else 5
            if price <= 0 or amount_yi < min_amount:
                continue
            if relaxed:
                if change_pct < -4.5 or change_pct >= 8.8:
                    continue
                if turnover_pct < 0.5 or turnover_pct > 22:
                    continue
            else:
                if change_pct < 0.8 or change_pct >= 8.8:
                    continue
                if turnover_pct < 1.2 or turnover_pct > 18:
                    continue
            if pb > 18:
                continue
            rows.append(
                {
                    "code": code,
                    "reason": "全市场流动性候选" if relaxed else "全市场稳健候选",
                    "source": "eastmoney_broad",
                    "broad_amount_yi": round(amount_yi, 2),
                    "broad_change_pct": change_pct,
                    "broad_turnover_pct": turnover_pct,
                }
            )
            if len(rows) >= limit:
                return rows
        time.sleep(0.1)
    return rows


def merge_candidate_pools(event_rows: list[dict], broad_rows: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for row in broad_rows + event_rows:
        code = row.get("code")
        if not code:
            continue
        if code not in merged:
            merged[code] = dict(row)
            continue
        previous_reason = merged[code].get("reason") or ""
        current_reason = row.get("reason") or ""
        if current_reason and current_reason not in previous_reason:
            merged[code]["reason"] = "、".join([part for part in [previous_reason, current_reason] if part])
        merged[code].update({key: value for key, value in row.items() if value not in ("", None)})
    return list(merged.values())


def cached_a_share_pool(limit: int = 300) -> list[dict]:
    merged: dict[str, dict] = {}
    paths = sorted(PICKS.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in paths[:220]:
        try:
            pick = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        section = ((pick.get("markets") or {}).get("a_share") or {})
        decision = section.get("decision") or pick.get("decision") or {}
        rows = [decision.get("primary"), decision.get("blocked_candidate"), *((decision.get("watchlist") or []))]
        for row in rows:
            if not row:
                continue
            code = str(row.get("code") or "")
            if not code or code.startswith(("8", "4", "9")):
                continue
            merged.setdefault(
                code,
                {
                    "code": code,
                    "reason": row.get("reason_tags") or "历史候选池复扫",
                    "source": "cached_history_pool",
                },
            )
            if len(merged) >= limit:
                return list(merged.values())
    return list(merged.values())


def tencent_quote(codes: list[str]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    session = market_session("a_share")
    for start in range(0, len(codes), 70):
        batch = codes[start : start + 70]
        prefixed = [market_prefix(code) + code for code in batch]
        url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        raw = urllib.request.urlopen(req, timeout=16).read().decode("gbk", "ignore")
        for line in raw.strip().split(";"):
            if not line.strip() or "=\"" not in line:
                continue
            key = line.split("=")[0].split("_")[-1]
            vals = line.split('"')[1].split("~")
            if len(vals) < 53:
                continue
            code = key[2:]
            result[code] = {
                "code": code,
                "name": vals[1],
                "price": safe_float(vals[3]),
                "current_price": safe_float(vals[3]),
                "entry_price": safe_float(vals[3]),
                "last_close": safe_float(vals[4]),
                "open": safe_float(vals[5]),
                "change_pct": safe_float(vals[32]),
                "current_change_pct": safe_float(vals[32]),
                "high": safe_float(vals[33]),
                "low": safe_float(vals[34]),
                "amount_wan": safe_float(vals[37]),
                "turnover_pct": safe_float(vals[38]),
                "pe_ttm": safe_float(vals[39]),
                "amplitude_pct": safe_float(vals[43]),
                "mcap_yi": safe_float(vals[44]),
                "float_mcap_yi": safe_float(vals[45]),
                "pb": safe_float(vals[46]),
                "limit_up": safe_float(vals[47]),
                "limit_down": safe_float(vals[48]),
                "vol_ratio": safe_float(vals[49]),
                "pe_static": safe_float(vals[52]),
                "realtime": {
                    "price": safe_float(vals[3]),
                    "change_pct": safe_float(vals[32]),
                    "session": session["session"],
                    "session_label": session["label"],
                    "source": "Tencent realtime quote",
                    "updated_at": now_cn().isoformat(timespec="seconds"),
                },
            }
        time.sleep(0.12)
    return result


def index_quotes() -> dict:
    mapping = {
        "sh000001": "上证指数",
        "sz399001": "深证成指",
        "sz399006": "创业板指",
        "sh000300": "沪深300",
    }
    url = "https://qt.gtimg.cn/q=" + ",".join(mapping)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        raw = urllib.request.urlopen(req, timeout=12).read().decode("gbk", "ignore")
    except Exception:
        return {"items": [], "risk": "unknown", "risk_note": "指数接口暂不可用"}

    items = []
    for line in raw.strip().split(";"):
        if not line.strip() or "=\"" not in line:
            continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < 33:
            continue
        items.append({"code": key, "name": vals[1], "change_pct": safe_float(vals[32])})
    negatives = sum(1 for item in items if item["change_pct"] < -0.7)
    gem = next((item for item in items if item["code"] == "sz399006"), None)
    if negatives >= 3 or (gem and gem["change_pct"] < -1.2):
        risk = "high"
        note = "主要指数偏弱，早盘不宜硬追强势股。"
    elif negatives >= 2:
        risk = "medium"
        note = "指数分歧，降低仓位或等待确认。"
    else:
        risk = "normal"
        note = "指数环境未触发系统性风险拦截。"
    return {"items": items, "risk": risk, "risk_note": note}


def daily_dragon_tiger(date_text: str) -> dict[str, dict]:
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    params = {
        "reportName": "RPT_DAILYBILLBOARD_DETAILSNEW",
        "columns": "ALL",
        "filter": f"(TRADE_DATE>='{date_text}')(TRADE_DATE<='{date_text}')",
        "pageNumber": "1",
        "pageSize": "500",
        "sortColumns": "BILLBOARD_NET_AMT",
        "sortTypes": "-1",
        "source": "WEB",
        "client": "WEB",
    }
    try:
        data = http_get_json(url, params=params, timeout=18)
        rows = ((data.get("result") or {}).get("data")) or []
    except Exception:
        rows = []
    by_code: dict[str, dict] = {}
    for row in rows:
        code = row.get("SECURITY_CODE") or ""
        if not code:
            continue
        item = by_code.setdefault(
            code,
            {
                "net_buy_wan": 0.0,
                "buy_wan": 0.0,
                "sell_wan": 0.0,
                "reason": row.get("EXPLANATION", ""),
                "records": 0,
            },
        )
        item["records"] += 1
        item["net_buy_wan"] += safe_float(row.get("BILLBOARD_NET_AMT")) / 10000
        item["buy_wan"] += safe_float(row.get("BILLBOARD_BUY_AMT")) / 10000
        item["sell_wan"] += safe_float(row.get("BILLBOARD_SELL_AMT")) / 10000
    return by_code


def industry_heat() -> dict:
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1",
        "pz": "100",
        "po": "1",
        "np": "1",
        "fltt": "2",
        "invt": "2",
        "fs": "m:90+t:2",
        "fields": "f2,f3,f4,f12,f13,f14,f104,f105,f128,f136,f140,f141,f207",
    }
    try:
        data = http_get_json(url, params=params, timeout=14)
        rows = (data.get("data") or {}).get("diff") or []
    except Exception:
        rows = []
    top = []
    for idx, item in enumerate(rows[:12], 1):
        top.append(
            {
                "rank": idx,
                "name": item.get("f14", ""),
                "change_pct": safe_float(item.get("f3")),
                "leader": item.get("f140", ""),
                "leader_change": safe_float(item.get("f136")),
                "up_count": item.get("f104", 0),
                "down_count": item.get("f105", 0),
            }
        )
    return {"top": top, "total": len(rows)}


def baidu_stock_kline(code: str, limit: int = 70) -> list[dict]:
    url = "https://finance.pae.baidu.com/selfselect/getstockquotation"
    params = {
        "all": "1",
        "isIndex": "false",
        "isBk": "false",
        "isBlock": "false",
        "isFutures": "false",
        "isStock": "true",
        "newFormat": "1",
        "group": "quotation_kline_ab",
        "finClientType": "pc",
        "code": code,
        "ktype": "1",
    }
    headers = {
        "User-Agent": UA,
        "Accept": "application/vnd.finance-web.v1+json",
        "Origin": "https://gushitong.baidu.com",
        "Referer": "https://gushitong.baidu.com/",
    }
    try:
        response = requests.get(url, params=params, headers=headers, timeout=12)
        response.raise_for_status()
        data = response.json()
        market = (((data.get("Result") or {}).get("newMarketData") or {}).get("marketData")) or ""
    except Exception:
        return []
    rows = []
    for line in market.split(";")[-limit:]:
        parts = line.split(",")
        if len(parts) < 18:
            continue
        rows.append(
            {
                "date": parts[1],
                "open": safe_float(parts[2]),
                "close": safe_float(parts[3]),
                "volume": safe_float(parts[4]),
                "high": safe_float(parts[5]),
                "low": safe_float(parts[6]),
                "amount": safe_float(parts[7]),
                "amplitude": 0.0,
                "change_pct": safe_float(str(parts[9]).replace("%", "")),
                "turnover": safe_float(parts[10]),
                "ma5": safe_float(parts[12]),
                "ma10": safe_float(parts[14]),
                "ma20": safe_float(parts[16]),
            }
        )
    return rows


def eastmoney_stock_kline(code: str, limit: int = 70) -> list[dict]:
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": eastmoney_secid(code),
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",
        "fqt": "1",
        "end": "20500101",
        "lmt": str(limit),
    }
    try:
        data = http_get_json(url, params=params, timeout=5)
        klines = ((data.get("data") or {}).get("klines")) or []
    except Exception:
        return []
    rows = []
    for line in klines:
        parts = line.split(",")
        if len(parts) < 11:
            continue
        rows.append(
            {
                "date": parts[0],
                "open": safe_float(parts[1]),
                "close": safe_float(parts[2]),
                "high": safe_float(parts[3]),
                "low": safe_float(parts[4]),
                "volume": safe_float(parts[5]),
                "amount": safe_float(parts[6]),
                "amplitude": safe_float(parts[7]),
                "change_pct": safe_float(parts[8]),
                "turnover": safe_float(parts[10]),
            }
        )
    return rows


def tencent_stock_kline(code: str, limit: int = 70) -> list[dict]:
    symbol = market_prefix(code) + code
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    params = {"param": f"{symbol},day,,,{limit},qfq"}
    try:
        response = requests.get(
            url,
            params=params,
            headers={"User-Agent": UA, "Referer": "https://gu.qq.com/"},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        payload = ((data.get("data") or {}).get(symbol) or {})
        klines = payload.get("qfqday") or payload.get("day") or []
    except Exception:
        return []
    rows = []
    for idx, parts in enumerate(klines[-limit:]):
        if len(parts) < 6:
            continue
        close = safe_float(parts[2])
        prev_close = rows[-1]["close"] if rows else close
        high = safe_float(parts[3])
        low = safe_float(parts[4])
        rows.append(
            {
                "date": parts[0],
                "open": safe_float(parts[1]),
                "close": close,
                "high": high,
                "low": low,
                "volume": safe_float(parts[5]),
                "amount": 0,
                "amplitude": pct_change(high, low) if low else 0,
                "change_pct": pct_change(close, prev_close),
                "turnover": 0,
            }
        )
    return rows


def stock_kline(code: str, limit: int = 70) -> list[dict]:
    rows = baidu_stock_kline(code, limit)
    if rows:
        return rows
    rows = eastmoney_stock_kline(code, limit)
    if rows:
        return rows
    return tencent_stock_kline(code, limit)


def cached_market_kline(market_key: str, symbol: str) -> list[dict]:
    symbol = str(symbol or "").upper()
    if not symbol:
        return []
    paths = sorted(PICKS.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in paths[:180]:
        try:
            pick = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        section = ((pick.get("markets") or {}).get(market_key) or {})
        decision = section.get("decision") or {}
        rows = [decision.get("primary"), decision.get("blocked_candidate"), *((decision.get("watchlist") or []))]
        for row in rows:
            if not row:
                continue
            code = str(row.get("code") or row.get("symbol") or "").upper()
            if code == symbol and row.get("kline"):
                return row["kline"]
    return []


def yahoo_chart_kline(symbol: str, limit: int = 90) -> list[dict]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}"
    params = {"range": "6mo", "interval": "1d", "includePrePost": "false"}
    try:
        req = urllib.request.Request(
            url + "?" + urllib.parse.urlencode(params),
            headers={"User-Agent": UA, "Accept": "application/json"},
        )
        raw = urllib.request.urlopen(req, timeout=6).read().decode("utf-8", "ignore")
        data = json.loads(raw)
        result = ((data.get("chart") or {}).get("result") or [None])[0]
        if not result:
            return []
        timestamps = result.get("timestamp") or []
        quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        volumes = quote.get("volume") or []
    except Exception:
        return []

    rows = []
    for idx, ts in enumerate(timestamps):
        try:
            close = closes[idx]
            high = highs[idx]
            low = lows[idx]
            open_ = opens[idx]
        except Exception:
            continue
        if close in (None, 0) or high in (None, 0) or low in (None, 0):
            continue
        prev_close = rows[-1]["close"] if rows else close
        rows.append(
            {
                "date": dt.datetime.fromtimestamp(ts, CN_TZ).date().isoformat(),
                "open": safe_float(open_),
                "close": safe_float(close),
                "high": safe_float(high),
                "low": safe_float(low),
                "volume": safe_float(volumes[idx] if idx < len(volumes) else 0),
                "amount": 0,
                "amplitude": pct_change(high, low) if low else 0,
                "change_pct": pct_change(close, prev_close),
                "turnover": 0,
            }
        )
    return rows[-limit:]


def yahoo_kline_map(symbols: list[str], limit: int = 90) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    unique = list(dict.fromkeys(symbols))
    if not unique:
        return result
    workers = min(12, max(1, len(unique)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(yahoo_chart_kline, symbol, limit): symbol for symbol in unique}
        for future in concurrent.futures.as_completed(futures):
            symbol = futures[future]
            try:
                rows = future.result()
            except Exception:
                rows = []
            if rows:
                result[symbol] = rows
    return result


def yahoo_realtime_quote(symbol: str, timeout: int = 6) -> dict:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}"
    params = {"range": "1d", "interval": "1m", "includePrePost": "true"}
    try:
        req = urllib.request.Request(
            url + "?" + urllib.parse.urlencode(params),
            headers={"User-Agent": UA, "Accept": "application/json"},
        )
        raw = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")
        data = json.loads(raw)
        result = ((data.get("chart") or {}).get("result") or [None])[0]
        if not result:
            return {}
        meta = result.get("meta") or {}
        quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        closes = quote.get("close") or []
        timestamps = result.get("timestamp") or []
    except Exception:
        return {}

    last_price = 0.0
    last_ts = 0
    for idx in range(len(closes) - 1, -1, -1):
        close = closes[idx]
        if close not in (None, 0):
            last_price = safe_float(close)
            last_ts = int(timestamps[idx]) if idx < len(timestamps) else 0
            break
    regular_price = safe_float(meta.get("regularMarketPrice"))
    price = last_price or regular_price
    previous_close = safe_float(meta.get("chartPreviousClose") or meta.get("previousClose"))
    change_pct = pct_change(price, previous_close) if price and previous_close else 0.0
    session = yahoo_session_from_meta(meta)
    updated_at = (
        dt.datetime.fromtimestamp(last_ts, CN_TZ).isoformat(timespec="seconds")
        if last_ts
        else now_cn().isoformat(timespec="seconds")
    )
    if not price:
        return {}
    return {
        "price": round(price, 4),
        "change_pct": round(change_pct, 2),
        "previous_close": previous_close,
        "currency": meta.get("currency") or "",
        "session": session["session"],
        "session_label": session["label"],
        "source": "Yahoo 1m includePrePost",
        "updated_at": updated_at,
    }


def yahoo_realtime_quotes(symbols: list[str]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    if not symbols:
        return result
    workers = min(8, max(1, len(symbols)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(yahoo_realtime_quote, symbol, 6): symbol for symbol in symbols}
        for future in concurrent.futures.as_completed(futures):
            symbol = futures[future]
            try:
                quote = future.result()
            except Exception:
                quote = {}
            if quote:
                result[symbol] = quote
    return result


def ema(values: list[float], span: int) -> list[float]:
    if not values:
        return []
    alpha = 2 / (span + 1)
    out = [values[0]]
    for value in values[1:]:
        out.append(alpha * value + (1 - alpha) * out[-1])
    return out


def macd_hist(closes: list[float]) -> list[float]:
    e12 = ema(closes, 12)
    e26 = ema(closes, 26)
    dif = [a - b for a, b in zip(e12, e26)]
    dea = ema(dif, 9)
    return [(d - signal) * 2 for d, signal in zip(dif, dea)]


def runtime_research_status() -> dict:
    status = {
        "czsc": {"installed": False, "version": None, "mode": "builtin-lightweight"},
        "uzi_skill": {"installed": True, "mode": "methodology-weighted", "repo": "wbh604/UZI-Skill"},
        "serenity_skill": serenity_skill_status(),
    }
    try:
        import czsc  # type: ignore

        status["czsc"] = {
            "installed": True,
            "version": getattr(czsc, "__version__", "unknown"),
            "mode": "optional-runtime-detected",
        }
    except Exception:
        pass
    return status


def serenity_skill_status() -> dict:
    skill_file = SERENITY_SKILL_DIR / "SKILL.md"
    references = SERENITY_SKILL_DIR / "references"
    reference_files = []
    if references.exists():
        reference_files = sorted(path.name for path in references.iterdir() if path.is_file())[:8]
    return {
        "installed": skill_file.exists(),
        "mode": "skill-weighted" if skill_file.exists() else "built-in-lens",
        "path": str(SERENITY_SKILL_DIR),
        "references": reference_files,
    }


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def pct_change(current: float, base: float) -> float:
    if not base:
        return 0.0
    return (current / base - 1) * 100


def czsc_structure_score(kline: list[dict]) -> dict:
    if len(kline) < 45:
        return {"score": 0.0, "signals": [], "warnings": [], "metrics": {}}
    closes = [x["close"] for x in kline]
    highs = [x["high"] for x in kline]
    lows = [x["low"] for x in kline]
    last = kline[-1]
    ma20 = mean(closes[-20:])
    ma30 = mean(closes[-30:])
    ma60 = mean(closes[-60:]) if len(closes) >= 60 else mean(closes)
    box_high = max(highs[-45:-10])
    box_low = min(lows[-45:-10])
    recent_low = min(lows[-8:])
    pct_20d = pct_change(closes[-1], closes[-21]) if len(closes) >= 21 else 0
    score = 0.0
    signals: list[str] = []
    warnings: list[str] = []
    if closes[-1] > ma20 > ma30:
        score += 12
        signals.append("CZSC近似: 日线趋势维持在 MA20/MA30 上方")
    if ma30 >= ma60 * 0.985:
        score += 7
        signals.append("CZSC近似: 中期均线未走坏，适合两周窗口")
    if closes[-1] > box_high * 1.01 and recent_low > box_high * 0.97:
        score += 16
        signals.append("CZSC近似: 突破中枢后回踩未破")
    elif box_low <= closes[-1] <= box_high and closes[-1] > (box_low + box_high) / 2:
        score += 6
        signals.append("CZSC近似: 中枢上半区震荡，等待向上离开")
    if pct_20d > 35:
        score -= 14
        warnings.append(f"20日涨幅 {pct_20d:.1f}%，两周追高风险上升")
    if closes[-1] < ma20 * 0.97:
        score -= 12
        warnings.append("跌破 MA20，未来两周趋势延续性不足")
    return {
        "score": round(score, 2),
        "signals": signals[:4],
        "warnings": warnings[:4],
        "metrics": {
            "ma20": round(ma20, 3),
            "ma30": round(ma30, 3),
            "ma60": round(ma60, 3),
            "box_high_45d": round(box_high, 3),
            "box_low_45d": round(box_low, 3),
            "pct_20d": round(pct_20d, 2),
        },
    }


def uzi_risk_score(candidate: dict, quote: dict, risk_flags: list[str], market_key: str) -> dict:
    score = 0.0
    reasons: list[str] = []
    warnings: list[str] = []
    change = quote.get("change_pct", 0.0)
    pct_5d = quote.get("pct_5d", 0.0)
    vol_ratio = quote.get("vol_ratio", 0.0)
    amount_yi = quote.get("amount_yi", 0.0)
    if 0 <= pct_5d <= (14 if market_key == "us" else 10):
        score += 8
        reasons.append("UZI风控: 近5日未明显透支，仍有两周弹性")
    if change > (12 if market_key == "us" else 8.5):
        score -= 12
        warnings.append("UZI风控: 单日涨幅过大，疑似已被抢跑")
    if pct_5d > (28 if market_key == "us" else 18):
        score -= 14
        warnings.append("UZI风控: 5日涨幅过热，避免追高接盘")
    if vol_ratio and vol_ratio > 3.5:
        score -= 8
        warnings.append("UZI风控: 量能异常放大，分歧风险升高")
    if market_key == "a_share" and amount_yi and amount_yi < 3:
        score -= 8
        warnings.append("UZI风控: A股成交额偏低，承接不足")
    if len(risk_flags) >= 3:
        score -= 8
        warnings.append("UZI风控: 风险标签过多")
    if not warnings:
        score += 6
        reasons.append("UZI风控: 未触发杀猪盘/过热式硬拦截")
    return {"score": round(score, 2), "signals": reasons[:4], "warnings": warnings[:4]}


def uzi_panel_score(candidate: dict, quote: dict, chan: dict, czsc: dict, risk_flags: list[str], market_key: str) -> dict:
    """Lightweight UZI-Skill style investor-panel scoring for a two-week entry."""
    metrics = chan.get("metrics") or {}
    lens = candidate.get("lens") or {}
    setup_flags = metrics.get("setup_flags") or []
    distance_ma10 = safe_float(metrics.get("distance_ma10_pct"))
    distance_ma20 = safe_float(metrics.get("distance_ma20_pct"))
    pct_5d = safe_float(quote.get("pct_5d"))
    change = safe_float(quote.get("change_pct"))
    amount_yi = safe_float(quote.get("amount_yi"))
    vol_ratio = safe_float(quote.get("vol_ratio"))
    score = 0.0
    signals: list[str] = []
    warnings: list[str] = []
    votes = {"bull": 0, "neutral": 0, "bear": 0}

    if setup_flags:
        score += 16
        votes["bull"] += 2
        signals.append("UZI评审团: 买点纪律通过，存在二买/三买或回踩确认")
    else:
        score -= 16
        votes["bear"] += 2
        warnings.append("UZI评审团: 没有明确买点确认，容易变成情绪追涨")

    if -2 <= distance_ma10 <= 6 and distance_ma20 > -3:
        score += 12
        votes["bull"] += 1
        signals.append("UZI评审团: 买入价靠近持股线，未来2周风控半径可控")
    elif distance_ma10 > (9 if market_key != "us" else 11):
        score -= 14
        votes["bear"] += 1
        warnings.append(f"UZI评审团: 买入价偏离 MA10 {distance_ma10:.1f}%，性价比下降")
    else:
        votes["neutral"] += 1

    amount_floor = 3.0 if market_key == "a_share" else 0.0
    if market_key != "a_share" or amount_yi >= amount_floor:
        score += 8
        votes["bull"] += 1
        signals.append("UZI评审团: 流动性承接达到最低要求")
    else:
        score -= 12
        votes["bear"] += 1
        warnings.append("UZI评审团: 成交额不足，真实买入后滑点和回撤风险偏高")

    if 0.75 <= vol_ratio <= 2.8:
        score += 7
        votes["bull"] += 1
        signals.append("UZI评审团: 量能温和，未出现失控式爆量")
    elif vol_ratio > 3.5:
        score -= 12
        votes["bear"] += 1
        warnings.append("UZI评审团: 爆量分歧，可能是派发或一致性过热")

    if pct_5d > (20 if market_key == "us" else 14) or change > (12 if market_key == "us" else 8.8):
        score -= 16
        votes["bear"] += 2
        warnings.append("UZI评审团: 价格已被抢跑，不符合指定价买入后再赚两周的钱")
    elif -3 <= pct_5d <= (12 if market_key != "us" else 18):
        score += 10
        votes["bull"] += 1
        signals.append("UZI评审团: 近5日涨幅未透支，仍有两周赔率")

    if lens:
        if safe_float(lens.get("catalyst")) >= 5 or safe_float(lens.get("customer")) >= 6:
            score += 7
            votes["bull"] += 1
            signals.append("UZI评审团: 产业催化或客户链路能支撑两周持有叙事")
        if safe_float(lens.get("financing")) < 0:
            score -= 10
            votes["bear"] += 1
            warnings.append("UZI评审团: 融资/稀释压力削弱两周上涨质量")

    if len(risk_flags) >= 4:
        score -= 12
        votes["bear"] += 1
        warnings.append("UZI评审团: 风险标签过多，宁可少赚也不追")
    elif len(risk_flags) <= 1:
        score += 6
        votes["bull"] += 1
        signals.append("UZI评审团: 风险标签少，满足保守买入偏好")

    return {
        "score": round(score, 2),
        "signals": signals[:5],
        "warnings": warnings[:5],
        "votes": votes,
        "summary": f"多 {votes['bull']} / 中 {votes['neutral']} / 空 {votes['bear']}",
    }


def chan_signal(kline: list[dict]) -> dict:
    if len(kline) < 32:
        return {
            "score": 0,
            "signals": [],
            "warnings": ["K线样本不足，缠论结构信号降权"],
            "metrics": {},
        }

    closes = [x["close"] for x in kline]
    lows = [x["low"] for x in kline]
    highs = [x["high"] for x in kline]
    vols = [x["volume"] for x in kline]
    last = kline[-1]
    ma5 = mean(closes[-5:])
    ma10 = mean(closes[-10:])
    ma20 = mean(closes[-20:])
    ma30 = mean(closes[-30:])
    hist = macd_hist(closes)
    distance_ma5 = pct_change(last["close"], ma5)
    distance_ma10 = pct_change(last["close"], ma10)
    distance_ma20 = pct_change(last["close"], ma20)
    pct_3d = pct_change(last["close"], closes[-4]) if len(closes) >= 4 else 0.0
    pct_5d = pct_change(last["close"], closes[-6]) if len(closes) >= 6 else 0.0
    pct_10d = pct_change(last["close"], closes[-11]) if len(closes) >= 11 else 0.0
    day_range = max(last["high"] - last["low"], 0.001)
    close_position = (last["close"] - last["low"]) / day_range
    upper_shadow_pct = pct_change(last["high"], last["close"])
    last_change = last.get("change_pct", 0.0)

    score = 0.0
    signals: list[str] = []
    warnings: list[str] = []
    setup_flags: list[str] = []

    if ma5 > ma10:
        score += 6
        signals.append("女上位: MA5 在 MA10 之上")
    if last["close"] > ma5 > ma10 > ma20:
        score += 8
        signals.append("多头排列: 收盘价站上 MA5/10/20")
    if last["close"] >= ma10 * 0.985:
        score += 6
        signals.append("持股线: 未有效跌破 MA10")
    else:
        warnings.append("收盘价跌破 MA10，两周趋势风险偏高")
        score -= 10

    recent_pullback = min(lows[-6:-1]) <= ma10 * 1.025
    recover_ma5 = last["close"] > ma5 and last["close"] > closes[-2]
    if ma5 > ma10 and recent_pullback and recover_ma5:
        score += 22
        setup_flags.append("second_buy")
        signals.append("二买近似: 多头后回踩 MA5/MA10 并重新收回")

    box_high = max(highs[-25:-5])
    box_low = min(lows[-25:-5])
    recent_low = min(lows[-5:])
    if last["close"] > box_high * 1.01 and recent_low > box_high * 0.985:
        score += 18
        setup_flags.append("third_buy")
        signals.append("三买近似: 突破近 20 日中枢后回试不破")
    elif last["close"] >= max(highs[-21:-1]) * 0.995:
        score += 2
        warnings.append("只接近或突破 20 日高点，未出现明确回踩确认")

    if len(hist) > 28:
        prev_window = list(range(max(0, len(lows) - 28), max(0, len(lows) - 12)))
        recent_window = list(range(max(0, len(lows) - 12), len(lows)))
        if prev_window and recent_window:
            prev_low_i = min(prev_window, key=lambda i: lows[i])
            recent_low_i = min(recent_window, key=lambda i: lows[i])
            if lows[recent_low_i] <= lows[prev_low_i] * 1.01 and hist[recent_low_i] > hist[prev_low_i]:
                score += 9
                signals.append("MACD背驰改善: 低点附近绿柱力度收敛")

    if len(hist) > 8 and last["close"] >= max(highs[-21:-1]) * 0.995:
        if hist[-1] < hist[-2] < hist[-3] and hist[-1] > 0:
            score -= 12
            warnings.append("新高附近 MACD 柱缩短，谨防短线顶背驰")

    if last["volume"] > 0 and mean(vols[-6:-1]) > 0:
        vol_ratio = last["volume"] / mean(vols[-6:-1])
        if 1.05 <= vol_ratio <= 2.6:
            score += min(8, vol_ratio * 3)
            signals.append(f"量能确认: 较 5 日均量 {vol_ratio:.1f} 倍")
        elif vol_ratio > 2.6:
            warnings.append("放量偏猛，次日容易分歧")
            score -= min(18, (vol_ratio - 2.6) * 5)
    else:
        vol_ratio = 0

    if not setup_flags:
        score -= 16
        warnings.append("没有二买/三买确认，容易变成追涨交易")
    if distance_ma10 > 9:
        score -= min(26, (distance_ma10 - 9) * 2.2)
        warnings.append(f"偏离 MA10 {distance_ma10:.1f}%，追高风险上升")
    elif 0 <= distance_ma10 <= 5:
        score += 8
        signals.append("成本位置: 距 MA10 不远，两周风控更可控")
    if pct_5d > 18:
        score -= min(24, (pct_5d - 18) * 1.2)
        warnings.append(f"5 日累计涨幅 {pct_5d:.1f}%，短线兑现压力偏大")
    if last_change >= 9.5:
        score -= 14
        warnings.append("信号日接近涨停，次日追高性价比下降")
    if upper_shadow_pct > 3.5 and close_position < 0.68:
        score -= 10
        warnings.append("上影线较长，资金分歧偏大")

    return {
        "score": round(score, 2),
        "signals": signals[:6],
        "warnings": warnings[:5],
        "metrics": {
            "ma5": round(ma5, 3),
            "ma10": round(ma10, 3),
            "ma20": round(ma20, 3),
            "ma30": round(ma30, 3),
            "box_high": round(box_high, 3),
            "box_low": round(box_low, 3),
            "volume_ratio_5d": round(vol_ratio, 2),
            "distance_ma5_pct": round(distance_ma5, 2),
            "distance_ma10_pct": round(distance_ma10, 2),
            "distance_ma20_pct": round(distance_ma20, 2),
            "pct_3d": round(pct_3d, 2),
            "pct_5d": round(pct_5d, 2),
            "pct_10d": round(pct_10d, 2),
            "close_position": round(close_position, 2),
            "upper_shadow_pct": round(upper_shadow_pct, 2),
            "setup_flags": setup_flags,
            "last_kline_date": last["date"],
        },
    }


def theme_score(reason: str) -> tuple[float, list[str]]:
    hits = [kw for kw in THEME_KEYWORDS if kw in reason]
    return min(22.0, len(hits) * 4.5), hits


def preliminary_score(hot: dict, quote: dict, dragon: dict | None) -> dict:
    reason = hot.get("reason") or ""
    t_score, tags = theme_score(reason)
    amount_yi = quote["amount_wan"] / 10000
    turnover = quote["turnover_pct"]
    change_pct = quote["change_pct"]
    score = 0.0
    if 1.5 <= change_pct <= 7.5:
        score += 14 + change_pct * 1.1
    elif 7.5 < change_pct <= 11:
        score += 18 - (change_pct - 7.5) * 1.4
    elif 11 < change_pct <= 16:
        score += 8 - (change_pct - 11) * 1.8
    elif change_pct > 16:
        score -= min(22, (change_pct - 16) * 2.8)
    else:
        score += max(change_pct, -6) * 1.2
    score += min(max(math.log10(max(amount_yi, 0.2)) * 12, 0), 24)
    score += max(0, 14 - abs(turnover - 9) * 0.9)
    if 0.8 <= quote["vol_ratio"] <= 2.4:
        score += 8 - abs(quote["vol_ratio"] - 1.4) * 2
    elif quote["vol_ratio"] > 2.4:
        score -= min(16, (quote["vol_ratio"] - 2.4) * 5)
    score += t_score

    dtb_net = 0.0
    if dragon:
        dtb_net = dragon.get("net_buy_wan", 0.0)
        if dtb_net > 0:
            score += min(math.log10(dtb_net + 1) * 4.8, 18)
        else:
            score -= 8

    risk_flags = []
    if quote["limit_up"] and abs(quote["price"] - quote["limit_up"]) < 0.02:
        risk_flags.append("信号日涨停，次日追高风险")
        score -= 12
        if abs(quote["open"] - quote["limit_up"]) < 0.02 and abs(quote["low"] - quote["limit_up"]) < 0.02:
            risk_flags.append("一字涨停，次日可买性差")
            score -= 22
    if change_pct >= 18.5:
        risk_flags.append("20cm 大涨后，两周持有回撤风险高")
        score -= 12
    elif change_pct >= 9.5:
        risk_flags.append("10cm 涨停后，隔日接力不确定")
        score -= 8
    if turnover > 24:
        risk_flags.append("换手过高，分歧剧烈")
        score -= 14
    elif turnover > 18:
        risk_flags.append("换手偏高，次日易分歧")
        score -= 7
    if amount_yi < 2:
        risk_flags.append("成交额不足 2 亿")
        score -= 8
    if quote["float_mcap_yi"] > 2500 and t_score < 9:
        risk_flags.append("流通市值偏大，涨幅弹性受限")
        score -= 22
    elif quote["float_mcap_yi"] > 1300 and t_score < 9:
        risk_flags.append("流通市值偏大，涨幅弹性受限")
        score -= 12

    return {
        "pre_score": round(score, 2),
        "theme_tags": tags,
        "theme_score": round(t_score, 2),
        "dragon_net_wan": round(dtb_net, 1),
        "risk_flags": risk_flags,
    }


def candidate_confidence(score: float, risk_count: int, market_risk: str) -> int:
    confidence = 50 + (score - 82) * 0.24
    confidence -= min(risk_count * 2.7, 18)
    if market_risk == "medium":
        confidence -= 5
    elif market_risk == "high":
        confidence -= 12
    return int(max(35, min(90, round(confidence))))


def estimate_range(confidence: int, technical: float, theme: float, risk_count: int) -> dict:
    if confidence < 58:
        low, high = -6.0, 3.0
    else:
        low = max(-5.0, -3.2 + (confidence - 60) * 0.05 - risk_count * 0.35)
        high = 3.2 + (confidence - 58) * 0.28 + technical * 0.035 + theme * 0.06
        high = min(high, 18.0)
    return {
        "low_pct": round(low, 1),
        "high_pct": round(high, 1),
        "text": f"{low:+.1f}% ~ {high:+.1f}%",
    }


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def serenity_alpha_profile(candidate: dict) -> dict:
    lens = candidate.get("lens") or {}
    bottleneck = safe_float(lens.get("bottleneck"))
    upstream = safe_float(lens.get("upstream"))
    capex = safe_float(lens.get("capex"))
    customer = safe_float(lens.get("customer"))
    smallcap = safe_float(lens.get("smallcap"))
    financing = safe_float(lens.get("financing"))
    catalyst = safe_float(lens.get("catalyst"))
    certainty = clamp((bottleneck + capex + max(customer, 0)) / 6, 0, 5)
    clarity = clamp((bottleneck + upstream) / 4, 0, 5)
    purity = clamp((bottleneck + upstream + max(smallcap, 0)) / 6, 0, 5)
    elasticity = clamp((max(smallcap, 0) + bottleneck + max(catalyst, 0)) / 6, 0, 5)
    timeframe = clamp((max(catalyst, 0) + capex + max(financing, 0)) / 6, 0, 5)
    score = round(mean([certainty, clarity, purity, elasticity, timeframe]) * 20, 2)
    rating = "强" if score >= 80 else "中" if score >= 60 else "弱" if score >= 40 else "无"
    warnings = []
    if certainty < 2.5:
        warnings.append("Serenity Skill: 需求或卡位确定性不足")
    if timeframe < 2.5:
        warnings.append("Serenity Skill: relabel 时间窗不够清晰")
    if financing <= 1:
        warnings.append("Serenity Skill: 融资/稀释压力需要验证")
    return {
        "score": score,
        "rating": rating,
        "dimensions": {
            "certainty": round(certainty, 2),
            "clarity": round(clarity, 2),
            "purity": round(purity, 2),
            "elasticity": round(elasticity, 2),
            "timeframe": round(timeframe, 2),
        },
        "warnings": warnings,
    }


def serenity_lens_score(candidate: dict) -> tuple[float, list[str], list[str], dict]:
    lens = candidate.get("lens") or {}
    score = 0.0
    reasons: list[str] = []
    risks: list[str] = []
    bottleneck = safe_float(lens.get("bottleneck"))
    upstream = safe_float(lens.get("upstream"))
    capex = safe_float(lens.get("capex"))
    customer = safe_float(lens.get("customer"))
    smallcap = safe_float(lens.get("smallcap"))
    financing = safe_float(lens.get("financing"))
    catalyst = safe_float(lens.get("catalyst"))

    score += bottleneck * 2.3 + upstream * 1.8 + capex * 1.8 + customer * 1.4 + smallcap * 1.1
    score += financing * 1.4 + catalyst * 1.3
    alpha = serenity_alpha_profile(candidate)
    score += alpha["score"] * 0.22
    if bottleneck >= 8:
        reasons.append("Serenity因子: 上游瓶颈/稀缺供给突出")
    if upstream >= 7:
        reasons.append("Serenity因子: 位于 AI capex 更上游环节")
    if capex >= 8:
        reasons.append("Serenity因子: 直接受益数据中心/AI capex")
    if customer >= 7:
        reasons.append("Serenity因子: 具备头部客户或潜在 Mag7 链路")
    if smallcap >= 6:
        reasons.append("Serenity因子: 市值弹性相对更高")
    if catalyst >= 6:
        reasons.append("Serenity因子: 存在量产/合同/政策/指数等催化线索")
    if alpha["score"] >= 60:
        reasons.append(f"Serenity Skill: alpha五维评级{alpha['rating']}，分数 {alpha['score']:.1f}")
    risks.extend(alpha["warnings"])
    if financing < 0:
        risks.append("Serenity风险: 融资质量/稀释压力较弱")
        score += financing * 2.0
    elif financing <= 2:
        risks.append("Serenity风险: 需重点跟踪 ATM/稀释或债务压力")
        score -= 4
    return round(score, 2), reasons, risks, alpha


def serenity_confidence(score: float, risk_count: int, market_key: str) -> int:
    base = 48 + (score - 82) * 0.27
    base -= min(risk_count * 3.2, 20)
    if market_key in ("hk", "us"):
        base -= 1
    return int(max(35, min(90, round(base))))


def serenity_estimate_range(confidence: int, score: float, risk_count: int, market_key: str) -> dict:
    if confidence < 58:
        low, high = (-8.0, 4.0) if market_key == "us" else (-6.0, 3.2)
    else:
        vol_boost = 1.2 if market_key == "us" else 0.4
        low = -4.2 - risk_count * 0.45 - vol_boost
        high = 4.0 + (confidence - 58) * 0.34 + max(score - 90, 0) * 0.045 + vol_boost
        high = min(high, 24.0 if market_key == "us" else 18.0)
    return {"low_pct": round(low, 1), "high_pct": round(high, 1), "text": f"{low:+.1f}% ~ {high:+.1f}%"}


def quote_from_kline(kline: list[dict]) -> dict:
    if not kline:
        return {}
    last = kline[-1]
    closes = [row["close"] for row in kline]
    volumes = [row.get("volume", 0) for row in kline]
    return {
        "price": last["close"],
        "change_pct": last.get("change_pct", 0.0),
        "volume": last.get("volume", 0.0),
        "vol_ratio": (last.get("volume", 0.0) / mean(volumes[-6:-1])) if mean(volumes[-6:-1]) > 0 else 0,
        "pct_5d": pct_change(closes[-1], closes[-6]) if len(closes) >= 6 else 0,
        "pct_10d": pct_change(closes[-1], closes[-11]) if len(closes) >= 11 else 0,
    }


def compact_kline(kline: list[dict], limit: int = 32) -> list[dict]:
    rows = []
    for row in kline[-limit:]:
        rows.append(
            {
                "date": row.get("date"),
                "open": round(safe_float(row.get("open")), 4),
                "high": round(safe_float(row.get("high")), 4),
                "low": round(safe_float(row.get("low")), 4),
                "close": round(safe_float(row.get("close")), 4),
                "volume": round(safe_float(row.get("volume")), 2),
                "change_pct": round(safe_float(row.get("change_pct")), 2),
            }
        )
    return rows


def live_stock_payload(market_key: str, code: str) -> dict:
    if not code:
        raise ValueError("缺少股票代码")
    if market_key == "a_share":
        quote = (tencent_quote([code]) or {}).get(code) or {}
        kline = stock_kline(code, 70)
        if not quote and not kline:
            raise ValueError("实时行情源暂不可用")
        latest = kline[-1] if kline else {}
        price = safe_float(quote.get("price")) or safe_float(latest.get("close"))
        change_pct = safe_float(quote.get("change_pct")) or safe_float(latest.get("change_pct"))
        return {
            "ok": True,
            "market": market_key,
            "code": code,
            "name": quote.get("name", ""),
            "price": price,
            "current_price": price,
            "realtime_price": price,
            "change_pct": change_pct,
            "current_change_pct": change_pct,
            "volume": safe_float(quote.get("volume")) or safe_float(latest.get("volume")),
            "session_label": (quote.get("realtime") or {}).get("session_label", "实时/延时"),
            "source": (quote.get("realtime") or {}).get("source", "Tencent realtime quote"),
            "updated_at": now_cn().isoformat(timespec="seconds"),
            "kline": compact_kline(kline, 70),
        }
    kline = yahoo_chart_kline(code, 90)
    realtime = yahoo_realtime_quote(code)
    if not realtime and not kline:
        raise ValueError("实时行情源暂不可用")
    latest = kline[-1] if kline else {}
    price = safe_float(realtime.get("price")) or safe_float(latest.get("close"))
    change_pct = safe_float(realtime.get("change_pct")) or safe_float(latest.get("change_pct"))
    return {
        "ok": True,
        "market": market_key,
        "code": code,
        "name": realtime.get("name", ""),
        "price": price,
        "current_price": price,
        "realtime_price": price,
        "change_pct": change_pct,
        "current_change_pct": change_pct,
        "volume": safe_float(realtime.get("volume")) or safe_float(latest.get("volume")),
        "session_label": realtime.get("session_label", "实时/延时"),
        "source": realtime.get("source", "Yahoo chart quote"),
        "updated_at": now_cn().isoformat(timespec="seconds"),
        "kline": compact_kline(kline, 70),
    }


def score_serenity_candidates(market_key: str, candidates: list[dict]) -> dict:
    policy = SERENITY_MARKET_POLICY.get(market_key, SERENITY_MARKET_POLICY["hk"])
    realtime_map = yahoo_realtime_quotes([item["symbol"] for item in candidates]) if market_key in ("hk", "us") else {}
    kline_map = yahoo_kline_map([item["symbol"] for item in candidates]) if market_key in ("hk", "us") else {}
    final = []
    for candidate in candidates:
        symbol = candidate["symbol"]
        if market_key == "a_share":
            kline = stock_kline(symbol)
        else:
            kline = kline_map.get(symbol) or cached_market_kline(market_key, symbol)
        if len(kline) < 32:
            continue
        quote = quote_from_kline(kline)
        if not quote or quote["price"] <= 0:
            continue
        realtime = (realtime_map.get(symbol) or {}) if market_key in ("hk", "us") else {}
        entry_price = safe_float(realtime.get("price")) or quote["price"]
        current_change_pct = safe_float(realtime.get("change_pct")) if realtime else quote["change_pct"]
        live_quote = {
            **quote,
            "price": entry_price,
            "entry_price": entry_price,
            "current_price": entry_price,
            "change_pct": current_change_pct,
            "current_change_pct": current_change_pct,
            "realtime": realtime
            or {
                "price": quote["price"],
                "change_pct": quote["change_pct"],
                "session": market_session(market_key)["session"],
                "session_label": market_session(market_key)["label"],
                "source": "Daily kline fallback",
                "updated_at": now_cn().isoformat(timespec="seconds"),
            },
        }
        chan = chan_signal(kline)
        czsc = czsc_structure_score(kline)
        metrics = chan.get("metrics") or {}
        lens_score, lens_reasons, lens_risks, alpha_profile = serenity_lens_score(candidate)
        setup_flags = metrics.get("setup_flags") or []
        risk_flags = list(lens_risks) + chan["warnings"] + czsc["warnings"]
        uzi = uzi_risk_score(candidate, {**live_quote, "amount_yi": 0}, risk_flags, market_key)
        uzi_panel = uzi_panel_score(candidate, {**live_quote, "amount_yi": 0}, chan, czsc, risk_flags, market_key)
        risk_flags.extend(uzi_panel["warnings"])
        risk_flags.extend(uzi["warnings"])
        total = (
            lens_score * (policy["lens_weight"] * 0.85)
            + chan["score"] * (policy["chan_weight"] * 0.65)
            + czsc["score"] * 0.7
            + uzi["score"] * 1.2
            + uzi_panel["score"] * 1.45
        )
        hard_risks = 0
        if not setup_flags:
            hard_risks += 1
        if metrics.get("distance_ma10_pct", 0) > policy["ma10_limit"]:
            hard_risks += 1
            risk_flags.append("偏离 MA10 过大，不适合追涨")
        if quote["pct_5d"] > policy["pct5_limit"]:
            hard_risks += 1
            risk_flags.append(f"5日涨幅 {quote['pct_5d']:.1f}%，短线兑现压力高")
        if current_change_pct > policy["change_limit"]:
            hard_risks += 1
            risk_flags.append("实时涨幅过大，当前价格追高风险")
        if quote["vol_ratio"] > 3:
            risk_flags.append("放量过猛，容易出现分歧")
            total -= 5
        if hard_risks:
            total -= hard_risks * policy["hard_penalty"]
        confidence = serenity_confidence(total, len(risk_flags), market_key)
        est = serenity_estimate_range(confidence, total, len(risk_flags), market_key)
        stop_loss = entry_price * (0.925 if market_key == "us" else 0.94)
        take_profit = entry_price * (1 + min(est["high_pct"], 12) / 100)
        reasons = []
        reasons.extend(lens_reasons[:4])
        if candidate.get("themes"):
            reasons.append("产业链主题: " + "、".join(candidate["themes"][:4]))
        reasons.extend(chan["signals"][:4])
        reasons.extend(czsc["signals"][:3])
        reasons.extend(uzi_panel["signals"][:3])
        reasons.extend(uzi["signals"][:2])
        reasons.append(f"实时买入价: {entry_price:.3f}，{live_quote['realtime']['session_label']} {current_change_pct:+.2f}%；5日 {quote['pct_5d']:+.2f}%，未来2周观察")
        final.append(
            {
                "code": symbol,
                "symbol": symbol,
                "name": candidate["name"],
                "market_key": market_key,
                "role": candidate.get("role", ""),
                "price": round(entry_price, 3),
                "entry_price": round(entry_price, 3),
                "signal_price": round(quote["price"], 3),
                "change_pct": round(current_change_pct, 2),
                "signal_change_pct": round(quote["change_pct"], 2),
                "current_change_pct": round(current_change_pct, 2),
                "realtime": live_quote["realtime"],
                "amount_yi": 0,
                "turnover_pct": 0,
                "vol_ratio": round(quote["vol_ratio"], 2),
                "float_mcap_yi": 0,
                "reason_tags": "、".join(candidate.get("themes") or []),
                "theme_tags": candidate.get("themes") or [],
                "score": round(total, 2),
                "pre_score": lens_score,
                "chan_score": chan["score"],
                "czsc_score": czsc["score"],
                "uzi_score": uzi["score"],
                "uzi_panel_score": uzi_panel["score"],
                "uzi_panel": uzi_panel,
                "setup_flags": setup_flags,
                "hard_risk_count": hard_risks,
                "confidence": confidence,
                "recommendation_degree": confidence,
                "estimated_2w_range": est,
                "estimated_2d_range": est,
                "stop_loss": round(stop_loss, 3),
                "take_profit_reference": round(take_profit, 3),
                "dragon_net_wan": 0,
                "dragon_reason": "",
                "reasons": reasons[:8],
                "risk_flags": risk_flags[:7],
                "kline": compact_kline(kline),
                "chan": chan,
                "czsc": czsc,
                "uzi": uzi,
                "serenity": {
                    "score": lens_score,
                    "role": candidate.get("role", ""),
                    "principles": lens_reasons,
                    "risks": lens_risks,
                    "alpha_profile": alpha_profile,
                    "policy": policy,
                },
            }
        )
        time.sleep(0.08)
    final.sort(key=lambda item: (item.get("hard_risk_count", 0), -item["confidence"], -item["score"]))
    return {"candidates": final, "raw_pool_size": len(candidates), "scored_size": len(final)}


def make_serenity_decision(candidates: list[dict], market_key: str) -> dict:
    if not candidates:
        return {
            "action": "NO_TRADE",
            "title": "无推荐",
            "message": "该市场没有足够完整的行情或结构信号，未来2周暂不推荐。",
            "primary": None,
            "watchlist": [],
        }
    primary = candidates[0]
    blockers = []
    threshold = SERENITY_MARKET_POLICY.get(market_key, SERENITY_MARKET_POLICY["hk"])["threshold"]
    if primary["confidence"] < threshold:
        blockers.append(f"推荐度低于 {threshold}")
    if primary.get("hard_risk_count", 0) >= 2:
        blockers.append("硬风险项过多")
    if primary["estimated_2w_range"]["low_pct"] <= (-7.0 if market_key == "us" else -5.5):
        blockers.append("预估下行空间偏大")
    if len(primary["risk_flags"]) >= 4:
        blockers.append("风险标签过多")
    if blockers:
        return {
            "action": "NO_TRADE",
            "title": "无推荐",
            "message": "；".join(blockers),
            "primary": None,
            "blocked_candidate": primary,
            "watchlist": candidates[:8],
        }
    return {
        "action": "BUY_CANDIDATE",
        "title": "两周推荐",
        "message": "实时买入价、UZI评审团、CZSC结构和产业链因子同时通过两周上涨阈值。",
        "primary": primary,
        "watchlist": candidates[1:9],
    }


def score_candidates(signal_date: str, hot_rows: list[dict], market: dict) -> dict:
    codes = [row.get("code") for row in hot_rows if row.get("code")]
    quotes = tencent_quote(codes)
    dragon_map = daily_dragon_tiger(signal_date)

    preliminary = []
    for hot in hot_rows:
        code = hot.get("code") or ""
        quote = quotes.get(code)
        if not quote or quote["price"] <= 0:
            continue
        name = quote["name"]
        if "ST" in name.upper() or code.startswith(("8", "4", "9")):
            continue
        pre = preliminary_score(hot, quote, dragon_map.get(code))
        preliminary.append({"hot": hot, "quote": quote, **pre})

    preliminary.sort(key=lambda item: item["pre_score"], reverse=True)
    final = []
    max_kline_checks = int(os.environ.get("CHAN_MAX_KLINE_CHECKS", "36"))
    for item in preliminary[:max_kline_checks]:
        quote = item["quote"]
        code = quote["code"]
        kline = stock_kline(code)
        chan = chan_signal(kline)
        czsc = czsc_structure_score(kline)
        metrics = chan.get("metrics") or {}
        serenity_candidate = SERENITY_A_BY_CODE.get(code)
        if serenity_candidate:
            serenity_score, serenity_reasons, serenity_risks, serenity_alpha = serenity_lens_score(serenity_candidate)
        else:
            serenity_score, serenity_reasons, serenity_risks, serenity_alpha = 0.0, [], [], {}
        risk_flags = list(item["risk_flags"]) + serenity_risks + chan["warnings"] + czsc["warnings"]
        quote_for_uzi = {
            "change_pct": quote["change_pct"],
            "current_change_pct": quote.get("current_change_pct", quote["change_pct"]),
            "price": quote["price"],
            "entry_price": quote["price"],
            "pct_5d": metrics.get("pct_5d", 0.0),
            "vol_ratio": quote["vol_ratio"],
            "amount_yi": quote["amount_wan"] / 10000,
        }
        uzi = uzi_risk_score(serenity_candidate or {}, quote_for_uzi, risk_flags, "a_share")
        uzi_panel = uzi_panel_score(serenity_candidate or {}, quote_for_uzi, chan, czsc, risk_flags, "a_share")
        risk_flags.extend(uzi_panel["warnings"])
        risk_flags.extend(uzi["warnings"])
        total = (
            item["pre_score"] * 0.75
            + chan["score"] * 0.55
            + czsc["score"] * 0.75
            + serenity_score * 0.45
            + uzi["score"] * 1.2
            + uzi_panel["score"] * 1.55
        )
        setup_flags = metrics.get("setup_flags") or []
        hard_risks = 0
        if not setup_flags:
            hard_risks += 1
        if metrics.get("distance_ma10_pct", 0) > 10:
            hard_risks += 1
        if quote["change_pct"] >= 9.5:
            hard_risks += 1
        if quote["turnover_pct"] > 24:
            hard_risks += 1
        if quote["vol_ratio"] > 3:
            hard_risks += 1
        if quote["turnover_pct"] > 24 and quote["change_pct"] >= 19:
            risk_flags.append("20cm 高换手，仅适合观察分歧承接")
        if hard_risks:
            total -= hard_risks * 8
        confidence = candidate_confidence(total, len(risk_flags), market.get("risk", "unknown"))
        est = estimate_range(confidence, chan["score"] + czsc["score"], item["theme_score"] + serenity_score, len(risk_flags))
        stop_loss = max(quote["limit_down"], quote["price"] * 0.94)
        take_profit = quote["price"] * (1 + min(est["high_pct"], 18) / 100)
        reasons = []
        reasons.extend(serenity_reasons[:3])
        if item["theme_tags"]:
            reasons.append("题材命中: " + "、".join(item["theme_tags"][:5]))
        if item["dragon_net_wan"] > 0:
            reasons.append(f"龙虎榜净买入约 {item['dragon_net_wan']:.0f} 万")
        reasons.extend(chan["signals"][:4])
        reasons.extend(czsc["signals"][:3])
        reasons.extend(uzi_panel["signals"][:3])
        reasons.extend(uzi["signals"][:2])
        reasons.append(
            f"实时买入价: {quote['price']:.2f}，{quote['realtime']['session_label']} {quote['change_pct']:+.2f}%；成交 {quote['amount_wan']/10000:.1f} 亿，未来2周观察"
        )
        final.append(
            {
                "code": code,
                "name": quote["name"],
                "price": quote["price"],
                "entry_price": quote["entry_price"],
                "signal_price": quote["last_close"],
                "change_pct": quote["change_pct"],
                "current_change_pct": quote["current_change_pct"],
                "signal_change_pct": quote["change_pct"],
                "realtime": quote["realtime"],
                "amount_yi": round(quote["amount_wan"] / 10000, 2),
                "turnover_pct": quote["turnover_pct"],
                "vol_ratio": quote["vol_ratio"],
                "float_mcap_yi": quote["float_mcap_yi"],
                "reason_tags": item["hot"].get("reason", ""),
                "theme_tags": item["theme_tags"],
                "score": round(total, 2),
                "pre_score": item["pre_score"],
                "chan_score": chan["score"],
                "czsc_score": czsc["score"],
                "serenity_score": serenity_score,
                "uzi_score": uzi["score"],
                "uzi_panel_score": uzi_panel["score"],
                "uzi_panel": uzi_panel,
                "setup_flags": setup_flags,
                "hard_risk_count": hard_risks,
                "confidence": confidence,
                "recommendation_degree": confidence,
                "estimated_2w_range": est,
                "estimated_2d_range": est,
                "stop_loss": round(stop_loss, 2),
                "take_profit_reference": round(take_profit, 2),
                "dragon_net_wan": item["dragon_net_wan"],
                "dragon_reason": (dragon_map.get(code) or {}).get("reason", ""),
                "reasons": reasons[:7],
                "risk_flags": risk_flags[:6],
                "kline": compact_kline(kline),
                "chan": chan,
                "czsc": czsc,
                "uzi": uzi,
                "serenity": {
                    "score": serenity_score,
                    "role": serenity_candidate.get("role", "") if serenity_candidate else "",
                    "principles": serenity_reasons,
                    "risks": serenity_risks,
                    "alpha_profile": serenity_alpha,
                },
            }
        )

    final.sort(
        key=lambda item: (
            item.get("hard_risk_count", 0),
            -item["confidence"],
            -item["score"],
        )
    )
    return {
        "candidates": final,
        "raw_pool_size": len(hot_rows),
        "scored_size": len(final),
        "dragon_count": len(dragon_map),
    }


def make_decision(candidates: list[dict], market: dict) -> dict:
    if not candidates:
        return {
            "action": "NO_TRADE",
            "title": "无推荐",
            "message": "没有足够强的候选池，未来2周暂不推荐。",
            "primary": None,
            "watchlist": [],
        }
    candidates = sorted(candidates, key=lambda item: (item.get("hard_risk_count", 0), -item["confidence"], -item["score"]))
    primary = candidates[0]
    blockers = []
    if market.get("risk") == "high":
        blockers.append("指数环境触发高风险拦截")
    if primary["confidence"] < 64:
        blockers.append("推荐度低于 64")
    if primary.get("hard_risk_count", 0) >= 2:
        blockers.append("硬风险项过多，不适合未来2周持有")
    if len(primary["risk_flags"]) >= 3:
        blockers.append("候选股风险标签过多")
    if primary["amount_yi"] < 2.5:
        blockers.append("成交额不足，承接不够")
    if primary["change_pct"] >= 9.5:
        blockers.append("信号日已接近涨停，次日追高性价比不足")
    if primary["estimated_2w_range"]["low_pct"] <= -5.5:
        blockers.append("预估下行空间过大")

    if blockers:
        return {
            "action": "NO_TRADE",
            "title": "无推荐",
            "message": "；".join(blockers),
            "primary": None,
            "blocked_candidate": primary,
            "watchlist": candidates[:8],
        }
    return {
        "action": "BUY_CANDIDATE",
        "title": "两周推荐",
        "message": "满足实时买入价下未来2周上涨的买点纪律、资金承接和 UZI 风控阈值。",
        "primary": primary,
        "watchlist": candidates[1:9],
    }


def run_selector(date_text: str | None = None, force: bool = False) -> dict:
    target_day = dt.date.fromisoformat(date_text) if date_text else default_target_date()
    signal_day = default_signal_date(target_day)
    generated_at = now_cn()
    run_slug = snapshot_slug(generated_at)
    cache_key = f"{target_day.isoformat()}_{signal_day.isoformat()}_{run_slug}.json"
    cache_path = PICKS / cache_key
    if not force:
        latest_path = PICKS / "latest.json"
        if latest_path.exists():
            cached = json.loads(latest_path.read_text(encoding="utf-8"))
            if cached.get("model_version") == MODEL_VERSION and cached.get("target_date") == target_day.isoformat():
                return cached

    hot_date, event_rows = find_hot_pool(signal_day)
    broad_rows = load_broad_market_pool()
    broad_mode = "momentum"
    if not broad_rows:
        broad_rows = load_broad_market_pool(relaxed=True)
        broad_mode = "liquidity_fallback"
    cached_rows = cached_a_share_pool()
    hot_rows = merge_candidate_pools(event_rows, broad_rows + cached_rows)
    market = index_quotes()
    industries = industry_heat()
    scored = score_candidates(hot_date, hot_rows, market)
    decision = make_decision(scored["candidates"], market)
    hk_universe = market_universe("hk")
    us_universe = market_universe("us")
    hk_scored = score_serenity_candidates("hk", hk_universe)
    us_scored = score_serenity_candidates("us", us_universe)
    hk_decision = make_serenity_decision(hk_scored["candidates"], "hk")
    us_decision = make_serenity_decision(us_scored["candidates"], "us")
    forecast_end = add_trade_weekdays(target_day, FORECAST_TRADE_DAYS)
    market_sections = {
        "a_share": {
            "key": "a_share",
            "label": "A股",
            "description": "A股实时价 + UZI评审团/风控重权重 + CZSC结构 + Serenity AI 上游瓶颈。",
            "decision": decision,
            "stats": {
                "raw_pool_size": scored["raw_pool_size"],
                "universe_size": scored["raw_pool_size"],
                "event_pool_size": len(event_rows),
                "broad_pool_size": len(broad_rows),
                "cached_pool_size": len(cached_rows),
                "broad_pool_mode": broad_mode,
                "scored_size": scored["scored_size"],
                "dragon_count": scored["dragon_count"],
            },
        },
        "hk": {
            "key": "hk",
            "label": "港股",
            "description": "港股实时价/盘前盘后状态 + UZI评审团 + 两周趋势结构和风险过滤。",
            "decision": hk_decision,
            "stats": {
                "raw_pool_size": hk_scored["raw_pool_size"],
                "universe_size": len(hk_universe),
                "event_pool_size": 0,
                "broad_pool_size": 0,
                "scored_size": hk_scored["scored_size"],
                "dragon_count": 0,
            },
        },
        "us": {
            "key": "us",
            "label": "美股",
            "description": "美股盘前/盘中/盘后实时价 + UZI评审团 + CPO/光子、HBM、neocloud、电力瓶颈。",
            "decision": us_decision,
            "stats": {
                "raw_pool_size": us_scored["raw_pool_size"],
                "universe_size": len(us_universe),
                "event_pool_size": 0,
                "broad_pool_size": 0,
                "scored_size": us_scored["scored_size"],
                "dragon_count": 0,
            },
        },
    }
    result = {
        "model_version": MODEL_VERSION,
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "generated_label": generated_at.strftime("%Y-%m-%d %H:%M"),
        "snapshot_key": cache_key,
        "target_date": target_day.isoformat(),
        "next_trade_date": forecast_end.isoformat(),
        "forecast_end_date": forecast_end.isoformat(),
        "forecast_horizon": f"{FORECAST_TRADE_DAYS}个交易日 / 约2周",
        "signal_date": hot_date,
        "holding_plan": "按实时/盘前盘中盘后买入价进入未来2周观察窗口；若跌破止损线、MA20失守或推荐度显著下降，提前退出。",
        "decision": decision,
        "markets": market_sections,
        "market": market,
        "industry_heat": industries,
        "stats": {
            "hot_pool_size": scored["raw_pool_size"],
            "event_pool_size": len(event_rows),
            "broad_pool_size": len(broad_rows),
            "cached_pool_size": len(cached_rows),
            "broad_pool_mode": broad_mode,
            "scored_size": scored["scored_size"],
            "dragon_count": scored["dragon_count"],
        },
        "chan_rules": CHAN_RULES,
        "czsc_rules": CZSC_RULES,
        "uzi_rules": UZI_RULES,
        "serenity_rules": SERENITY_RULES,
        "live_quote_policy": {
            "objective": "以当前可成交参考价买入后，未来2周取得正收益；少赚可以，优先避免亏损。",
            "a_share": "腾讯财经实时行情；非交易时段保留最近行情并标注时段。",
            "hk_us": "Yahoo Finance 1分钟 includePrePost；美股尽量纳入盘前/盘中/盘后价格，港股按可得实时/收盘状态降级。",
        },
        "research_runtime": runtime_research_status(),
        "serenity_source": serenity_source_status(),
        "accuracy_note": (
            "推荐度是规则模型按实时买入价、两周趋势、产业链、CZSC结构、UZI评审团/风控和资金承接映射的先验估计；"
            "需要持续保存半小时快照后，用真实两周收益滚动校准。"
        ),
        "disclaimer": "本工具是量化决策辅助，不构成投资建议，不保证盈利。",
    }
    cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (PICKS / "latest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


class AppHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        clean = urllib.parse.urlparse(path).path
        if clean == "/":
            return str(STATIC / "index.html")
        if clean.startswith("/static/"):
            return str(ROOT / clean.lstrip("/"))
        return str(STATIC / clean.lstrip("/"))

    def send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/pick":
            query = urllib.parse.parse_qs(parsed.query)
            snapshot_key = query.get("snapshot", [""])[0]
            if snapshot_key:
                snapshot = load_pick_snapshot(snapshot_key)
                if snapshot:
                    self.send_json(snapshot)
                    return
                self.send_json({"error": "未找到指定历史快照"}, 404)
                return
            date_text = query.get("date", [None])[0]
            force = query.get("force", ["0"])[0] == "1"
            try:
                self.send_json(run_selector(date_text=date_text, force=force))
            except Exception as exc:
                self.send_json({"error": str(exc), "disclaimer": "数据源暂不可用，请稍后重试。"}, 500)
            return
        if parsed.path == "/api/history":
            query = urllib.parse.parse_qs(parsed.query)
            limit = int(query.get("limit", ["30"])[0])
            self.send_json(history_payload(limit=max(1, min(limit, 240))))
            return
        if parsed.path == "/api/live":
            query = urllib.parse.parse_qs(parsed.query)
            market_key = query.get("market", ["a_share"])[0]
            code = query.get("code", [""])[0]
            try:
                self.send_json(live_stock_payload(market_key, code))
            except Exception as exc:
                self.send_json({"error": "实时行情暂不可用", "detail": str(exc)}, 502)
            return
        if parsed.path == "/api/latest-summary":
            latest = PICKS / "latest.json"
            if not latest.exists():
                self.send_json({"error": "暂无历史决策缓存"}, 404)
                return
            payload = json.loads(latest.read_text(encoding="utf-8"))
            self.send_json({"ok": True, "time": now_cn().isoformat(timespec="seconds"), "latest": summarize_pick(payload)})
            return
        if parsed.path == "/api/latest":
            latest = PICKS / "latest.json"
            if not latest.exists():
                self.send_json({"error": "暂无历史决策缓存"}, 404)
                return
            payload = json.loads(latest.read_text(encoding="utf-8"))
            self.send_json(payload)
            return
        if parsed.path == "/api/status":
            latest = PICKS / "latest.json"
            payload = {
                "ok": True,
                "time": now_cn().isoformat(timespec="seconds"),
                "has_latest": latest.exists(),
                "latest_path": str(latest) if latest.exists() else None,
            }
            self.send_json(payload)
            return
        super().do_GET()


def scheduler_loop() -> None:
    last_run = ""
    update_slots = {
        (8, 58),
        (9, 58),
        (10, 58),
        (12, 58),
        (13, 58),
        (14, 58),
        (21, 28),
        (23, 58),
    }
    while True:
        current = now_cn()
        key = current.strftime("%Y-%m-%d %H:%M")
        in_update_window = current.weekday() < 5 and (current.hour, current.minute) in update_slots
        if in_update_window and key != last_run:
            last_run = key
            try:
                run_selector(date_text=current.date().isoformat(), force=True)
            except Exception as exc:
                log_path = CACHE / "scheduler-error.log"
                log_path.write_text(f"{current.isoformat()} {exc}\n", encoding="utf-8")
        time.sleep(20)


class ReusableThreadingTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


def serve(port: int, host: str) -> None:
    threading.Thread(target=scheduler_loop, daemon=True).start()
    with ReusableThreadingTCPServer((host, port), AppHandler) as httpd:
        print(f"Smart stock selector running at http://{host}:{port}")
        httpd.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8790")))
    parser.add_argument("--once", action="store_true", help="Run selector once and print JSON.")
    parser.add_argument("--date", help="Target date, YYYY-MM-DD.")
    parser.add_argument("--force", action="store_true", help="Ignore cache.")
    args = parser.parse_args()
    if args.once:
        print(json.dumps(run_selector(args.date, force=args.force), ensure_ascii=False, indent=2))
        return
    serve(args.port, args.host)


if __name__ == "__main__":
    main()

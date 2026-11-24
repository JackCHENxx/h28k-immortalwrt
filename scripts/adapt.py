#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
给一份干净的 ImmortalWrt 源码树补上 HINLINK H28K (RK3528) 支持。

设计目标是“上游变了也不会静默刷错”：
  * 上游若已收录 H28K，直接停下要求人工合并，不覆盖上游实现；
  * 板级 case 分支插到 case 顶部（而不是依赖某个相邻板子的字符串），上游调整板子顺序也不受影响；
  * dnsmasq 默认池按 section 改键值，模板缩进/顺序变化也能处理；
  * 所有关键项最后统一自检，任何一项不符就非零退出。

用法: python3 scripts/adapt.py <immortalwrt 源码目录>
"""

import argparse
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)

DTS_REL = "target/linux/rockchip/files/arch/arm64/boot/dts/rockchip/rk3528-hinlink-h28k.dts"
STAMP = ".h28k-kit.applied"

DEVICE_BLOCK = """define Device/hinlink_h28k
  $(Device/rk3528)
  DEVICE_VENDOR := HINLINK
  DEVICE_MODEL := H28K
  DEVICE_ALT0_VENDOR := LinkStar
  DEVICE_ALT0_MODEL := H28K
  DEVICE_DTS := rk3528-hinlink-h28k
  UBOOT_DEVICE_NAME := hinlink-h28k-rk3528
  DEVICE_PACKAGES := kmod-button-hotplug kmod-input-adc-keys kmod-r8169
endef
TARGET_DEVICES += hinlink_h28k

"""

UBOOT_BLOCK = """define U-Boot/hinlink-h28k-rk3528
  $(U-Boot/rk3528/Default)
  NAME:=HINLINK H28K
  BUILD_DEVICES:= \\
    hinlink_h28k
endef

"""

NET_ARM = """hinlink,h28k)
		ucidef_set_interface "lan" device "eth0" protocol "static" ipaddr "192.168.2.1" netmask "255.255.255.0"
		ucidef_set_interface "wan" device "eth1" protocol "dhcp"
		;;
"""

MAC_ARM = """hinlink,h28k)
		wan_mac=$(macaddr_generate_from_mmc_cid mmcblk0)
		lan_mac=$(macaddr_add "$wan_mac" 1)
		;;
"""

LED_ARM = """hinlink,h28k)
	ucidef_set_led_netdev "wan" "WAN" "blue:wan" "eth1"
	ucidef_set_led_netdev "lan" "LAN" "amber:lan" "eth0"
	;;
"""

AFF_ARM = """hinlink,h28k)
	set_interface_core 2 "eth0"
	set_interface_core 4 "eth1"
	;;
"""

UBOOT_PATCH_SRC = os.path.join(KIT, "patches", "uboot-board-rockchip-add-HINLINK-H28K.patch")

log = []


def note(msg):
    log.append(msg)
    print("[adapt] " + msg)


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def die(msg):
    sys.exit("[adapt] 失败: " + msg)


def insert_before(path, anchor, text, marker):
    body = read(path)
    if marker in body:
        note("跳过（已存在 %s）: %s" % (marker, os.path.relpath(path, SRC)))
        return
    if body.count(anchor) != 1:
        die("在 %s 中找不到唯一锚点 %r（上游已改动）" % (os.path.relpath(path, SRC), anchor))
    write(path, body.replace(anchor, text + anchor, 1))
    note("已插入 %s: %s" % (marker, os.path.relpath(path, SRC)))


def prepend_case_arm(path, arm, marker_regex):
    """把一条 case 分支插到第 occurrence 个 case 的第一条分支之前（先匹配先执行，最稳）。

    不依赖相邻板子的名字，所以上游增删板子、调整顺序都不会失配。
    """
    body = read(path)
    if re.search(marker_regex, body):
        note("跳过（已存在分支 %s）: %s" % (marker_regex, os.path.relpath(path, SRC)))
        return
    need = getattr(prepend_case_arm, "_occurrence", 1)
    matches = list(re.finditer(r'(?m)^\s*case\s+[^;\n]+?\s+in\s*$', body))
    if len(matches) < need:
        die("%s 里找不到第 %d 个 case 分支（上游结构变了）" % (os.path.relpath(path, SRC), need))
    match = matches[need - 1]
    line_end = body.find("\n", match.end())
    if line_end < 0:
        die("%s 的 case 行不完整" % os.path.relpath(path, SRC))
    body = body[:line_end + 1] + arm + body[line_end + 1:]
    write(path, body)
    note("已插入分支 %s: %s" % (marker_regex, os.path.relpath(path, SRC)))


def set_case_occurrence(n):
    prepend_case_arm._occurrence = n


def ensure_dhcp_pool(path, start=38, limit=206, lease="24h"):
    body = read(path)
    m = re.search(r"(?ms)^config dhcp lan\n.*?(?=^config |\Z)", body)
    if not m:
        die("dnsmasq 模板里找不到 config dhcp lan 段")
    block = m.group(0)

    def set_key(block, key, val):
        pat = r"(?m)^[ \t]*option %s\s+.*$" % re.escape(key)
        if re.search(pat, block):
            return re.sub(pat, "\toption %s\t%s" % (key, val), block, count=1)
        return block.rstrip("\n") + "\n\toption %s\t%s\n" % (key, val)

    new = block
    new = set_key(new, "start", start)
    new = set_key(new, "limit", limit)
    new = set_key(new, "leasetime", lease)
    if new != block:
        write(path, body[:m.start()] + new + body[m.end():])
        note("已改 dnsmasq 默认 DHCP 池: .%d-.%d, %s" % (start, start + limit - 1, lease))
    else:
        note("dnsmasq 默认 DHCP 池已是目标值")


def main():
    global SRC
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="ImmortalWrt 源码目录")
    ap.add_argument("--force", action="store_true", help="即使检测到上游已支持 H28K 也继续")
    args = ap.parse_args()
    SRC = os.path.abspath(args.src)

    target = os.path.join(SRC, "target/linux/rockchip")
    if not os.path.isdir(target):
        die("%s 不像 ImmortalWrt 源码树" % SRC)

    image_mk = os.path.join(target, "image/armv8.mk")
    uboot_mk = os.path.join(SRC, "package/boot/uboot-rockchip/Makefile")
    base_etc = os.path.join(target, "armv8/base-files/etc")

    # 0. 上游已收录则停下：宁可失败，也不要覆盖上游更新的板级实现
    stamped = os.path.exists(os.path.join(SRC, STAMP))
    ours_marker = 'ipaddr "192.168.2.1"' in read(os.path.join(base_etc, "board.d/02_network"))
    if not stamped and not ours_marker and re.search(r"(?m)^define Device/hinlink_h28k\b", read(image_mk)):
        if not args.force:
            die("上游 ImmortalWrt 已收录 H28K（出现 Device/hinlink_h28k）。"
                "本套件不应覆盖上游实现，请人工合并 dts/board.d/U-Boot 后再发布；"
                "确认要沿用本套件时加 --force。")
        note("检测到上游已支持 H28K，--force 继续覆盖")

    # 1. 内核设备树：上游已有就保留，避免把上游的修复覆盖掉
    dts_dst = os.path.join(SRC, DTS_REL)
    if os.path.exists(dts_dst) and not stamped and not ours_marker:
        note("已存在上游设备树，保留不覆盖: " + DTS_REL)
    else:
        os.makedirs(os.path.dirname(dts_dst), exist_ok=True)
        shutil.copyfile(os.path.join(KIT, "files/rk3528-hinlink-h28k.dts"), dts_dst)
        note("已投放内核设备树: " + DTS_REL)

    # 2. 目标 overlay + 通用 LuCI 应用
    overlay_src = os.path.join(KIT, "files/overlay")
    tuning_dst = os.path.join(target, "armv8/base-files/etc/uci-defaults/99-h28k-tuning")
    for root, _dirs, files in os.walk(overlay_src):
        for f in files:
            src_file = os.path.join(root, f)
            rel = os.path.relpath(src_file, overlay_src)
            dst_file = os.path.join(target, "armv8/base-files", rel)
            os.makedirs(os.path.dirname(dst_file), exist_ok=True)
            shutil.copyfile(src_file, dst_file)
            os.chmod(dst_file, 0o755 if os.access(src_file, os.X_OK) else 0o644)
    note("已投放目标 overlay: " + os.path.relpath(tuning_dst, SRC))

    legacy = os.path.join(SRC, "package", "luci-app-h28k-mode")
    if os.path.isdir(legacy):
        shutil.rmtree(legacy)
        note("已清理旧应用目录: package/luci-app-h28k-mode")

    pkg_src = os.path.join(KIT, "package", "luci-app-netmode")
    pkg_dst = os.path.join(SRC, "package", "luci-app-netmode")
    if os.path.isdir(pkg_dst):
        shutil.rmtree(pkg_dst)
    shutil.copytree(pkg_src, pkg_dst)
    note("已投放 LuCI 网络向导: package/luci-app-netmode")

    # 3. 镜像设备定义：锚点没了就追加到文件末尾（makefile 顺序不影响）
    body = read(image_mk)
    if "Device/hinlink_h28k" in body:
        note("跳过（已存在 设备定义）")
    elif "define Device/radxa_e20c\n" in body and body.count("define Device/radxa_e20c\n") == 1:
        write(image_mk, body.replace("define Device/radxa_e20c\n", DEVICE_BLOCK + "define Device/radxa_e20c\n", 1))
        note("已插入设备定义（radxa_e20c 之前）")
    else:
        write(image_mk, body + "\n" + DEVICE_BLOCK)
        note("已追加设备定义（文件末尾）")

    # 4. U-Boot 目标
    body = read(uboot_mk)
    if "U-Boot/hinlink-h28k-rk3528" not in body:
        if "define U-Boot/radxa-e20c-rk3528\n" in body:
            body = body.replace("define U-Boot/radxa-e20c-rk3528\n", UBOOT_BLOCK + "define U-Boot/radxa-e20c-rk3528\n", 1)
        else:
            anchor = "$(eval $(call BuildPackage/U-Boot))"
            if anchor not in body:
                die("U-Boot Makefile 结构变化：既没有 radxa-e20c 锚点，也没有 BuildPackage/U-Boot")
            body = body.replace(anchor, UBOOT_BLOCK + anchor, 1)
        write(uboot_mk, body)
        note("已插入 U-Boot 目标")
    else:
        note("跳过（已存在 U-Boot 目标）")

    body = read(uboot_mk)
    if "  hinlink-h28k-rk3528 \\\n" not in body:
        if "  radxa-e20c-rk3528 \\\n" in body:
            body = body.replace("  radxa-e20c-rk3528 \\\n", "  hinlink-h28k-rk3528 \\\n  radxa-e20c-rk3528 \\\n", 1)
        elif "UBOOT_TARGETS := \\\n" in body:
            body = body.replace("UBOOT_TARGETS := \\\n", "UBOOT_TARGETS := \\\n  hinlink-h28k-rk3528 \\\n", 1)
        else:
            die("UBOOT_TARGETS 列表结构变化，找不到插入点")
        write(uboot_mk, body)
        note("已加入 UBOOT_TARGETS 列表")

    # 5. U-Boot 板级补丁
    up_dir = os.path.join(SRC, "package/boot/uboot-rockchip/patches")
    if any("HINLINK-H28K" in f for f in os.listdir(up_dir)):
        note("跳过（U-Boot 补丁已存在）")
    else:
        for n in range(117, 200):
            dst = os.path.join(up_dir, "%03d-board-rockchip-add-HINLINK-H28K.patch" % n)
            if not os.path.exists(dst):
                shutil.copyfile(UBOOT_PATCH_SRC, dst)
                note("已加入 U-Boot 板级补丁: " + os.path.basename(dst))
                break
        else:
            die("U-Boot patches 目录里没有空号可用")

    # 6. base-files：网口 / MAC / LED / IRQ
    leds = os.path.join(base_etc, "board.d/01_leds")
    set_case_occurrence(1)
    prepend_case_arm(leds, LED_ARM, r'ucidef_set_led_netdev "wan" "WAN" "blue:wan" "eth1"')

    net = os.path.join(base_etc, "board.d/02_network")
    set_case_occurrence(1)
    prepend_case_arm(net, NET_ARM, r'ipaddr "192\.168\.2\.1"')
    set_case_occurrence(2)
    prepend_case_arm(net, MAC_ARM, r"hinlink,h28k\)\s*\n\s*wan_mac=\$\(macaddr_generate_from_mmc_cid mmcblk0\)")

    aff = os.path.join(base_etc, "hotplug.d/net/40-net-smp-affinity")
    set_case_occurrence(1)
    prepend_case_arm(aff, AFF_ARM, r'hinlink,h28k\)\s*\n\tset_interface_core 2 "eth0"')

    # 7. dnsmasq 默认 DHCP 池
    dhcp_tpl = os.path.join(SRC, "package/network/services/dnsmasq/files/dhcp.conf")
    ensure_dhcp_pool(dhcp_tpl)

    # 8. 自检
    net_txt = read(net)
    checks = {
        "设备定义": "Device/hinlink_h28k" in read(image_mk),
        "U-Boot 目标": "U-Boot/hinlink-h28k-rk3528" in read(uboot_mk),
        "U-Boot 列表": "  hinlink-h28k-rk3528 \\\n" in read(uboot_mk),
        "默认 IP": 'ipaddr "192.168.2.1"' in net_txt,
        "网口映射": 'device "eth0"' in net_txt and 'device "eth1"' in net_txt,
        "MAC 生成": re.search(r"hinlink,h28k\)[^\n]*\n[^\n]*macaddr_generate_from_mmc_cid", net_txt) is not None,
        "LED 配置": re.search(r"hinlink,h28k\)[^\n]*\n\s*ucidef_set_led_netdev \"wan\"", read(leds)) is not None,
        "IRQ 绑核": re.search(r"hinlink,h28k\)[^\n]*\n\tset_interface_core 2 \"eth0\"", read(aff)) is not None,
        "内核 dts": os.path.exists(dts_dst),
        "PCIe/USB 节点": "&pcie {" in read(dts_dst) and "&usb2phy {" in read(dts_dst),
        "WireGuard 预置": os.access(os.path.join(target, "armv8/base-files/etc/uci-defaults/98-wireguard"), os.X_OK),
        "开机调优": os.access(tuning_dst, os.X_OK),
        "网络向导弹出": os.path.exists(os.path.join(pkg_dst, "htdocs/luci-static/resources/view/netmode/guide.js")),
        "DHCP 池": re.search(r"(?m)^\toption start\s+38$", read(dhcp_tpl)) is not None
                   and re.search(r"(?m)^\toption limit\s+206$", read(dhcp_tpl)) is not None
                   and re.search(r"(?m)^\toption leasetime\s+24h$", read(dhcp_tpl)) is not None,
    }
    bad = [k for k, v in checks.items() if not v]
    print("\n[adapt] 自检: " + ", ".join("%s=%s" % (k, "OK" if v else "FAIL") for k, v in checks.items()))
    if bad:
        die("自检未通过: " + ", ".join(bad))

    with open(os.path.join(SRC, STAMP), "w", encoding="utf-8") as f:
        f.write("h28k-kit patched\n")
    print("[adapt] 完成：H28K 支持已就绪")


if __name__ == "__main__":
    main()

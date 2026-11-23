#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
给一份干净的 ImmortalWrt 源码树补上 HINLINK H28K (RK3528) 支持。

做的事（全部幂等，重复执行只会跳过）：
  1. 投放内核设备树 rk3528-hinlink-h28k.dts，并加内核 dts Makefile 补丁；
  2. 在 target/linux/rockchip/image/armv8.mk 增加 hinlink_h28k 设备定义；
  3. 在 package/boot/uboot-rockchip 增加 hinlink-h28k-rk3528 的 U-Boot 目标与补丁；
  4. 在 armv8 的 base-files 里登记 H28K 的 LAN/WAN 网口（含默认 IP 192.168.2.1）、LED 与 IRQ 绑核；
  5. 投放随套件自带的 LuCI 应用 package/luci-app-netmode（网络向导：一键主路由/旁路由）。

上游 ImmortalWrt 若某天自己收录了 H28K，脚本会自动跳过对应步骤。
用法: python3 scripts/adapt.py <immortalwrt 源码目录>
"""

import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)

DTS_REL = "target/linux/rockchip/files/arch/arm64/boot/dts/rockchip/rk3528-hinlink-h28k.dts"

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

# 独立网口定义：默认 LAN IP 直接落在 board.json 里（= 固件默认值）
H28K_NET_BLOCK = """hinlink,h28k)
		ucidef_set_interface "lan" device "eth0" protocol "static" ipaddr "192.168.2.1" netmask "255.255.255.0"
		ucidef_set_interface "wan" device "eth1" protocol "dhcp"
		;;
"""

UBOOT_BLOCK = """define U-Boot/hinlink-h28k-rk3528
  $(U-Boot/rk3528/Default)
  NAME:=HINLINK H28K
  BUILD_DEVICES:= \\
    hinlink_h28k
endef

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


def insert_before(path, anchor, text, marker):
    """在 anchor 之前插入 text；marker 已存在则跳过。anchor 找不到直接报错。"""
    body = read(path)
    if marker in body:
        note("跳过（已存在 %s）: %s" % (marker, os.path.relpath(path, SRC)))
        return
    if body.count(anchor) != 1:
        sys.exit("[adapt] 失败: 在 %s 中找不到唯一锚点 %r（上游可能已改动，请更新脚本）"
                 % (os.path.relpath(path, SRC), anchor))
    write(path, body.replace(anchor, text + anchor, 1))
    note("已插入 %s: %s" % (marker, os.path.relpath(path, SRC)))


def replace_once(path, old, new, marker):
    body = read(path)
    if marker in body:
        note("跳过（已存在 %s）: %s" % (marker, os.path.relpath(path, SRC)))
        return
    if body.count(old) != 1:
        sys.exit("[adapt] 失败: 在 %s 中找不到唯一锚点 %r（上游可能已改动，请更新脚本）"
                 % (os.path.relpath(path, SRC), old))
    write(path, body.replace(old, new, 1))
    note("已修改 %s: %s" % (marker, os.path.relpath(path, SRC)))


def main():
    global SRC
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="ImmortalWrt 源码目录")
    args = ap.parse_args()
    SRC = os.path.abspath(args.src)

    target = os.path.join(SRC, "target/linux/rockchip")
    if not os.path.isdir(target):
        sys.exit("[adapt] 失败: %s 不像 ImmortalWrt 源码树" % SRC)

    image_mk = os.path.join(target, "image/armv8.mk")
    uboot_mk = os.path.join(SRC, "package/boot/uboot-rockchip/Makefile")
    base_etc = os.path.join(target, "armv8/base-files/etc")

    # 1. 内核设备树（放目标树的 files/ 里，prepare 时会并入内核树，
    #    再由 image 系统用 Image/BuildDTB 直接编译，无需改内核 dts Makefile）
    dts_dst = os.path.join(SRC, DTS_REL)
    os.makedirs(os.path.dirname(dts_dst), exist_ok=True)
    shutil.copyfile(os.path.join(KIT, "files/rk3528-hinlink-h28k.dts"), dts_dst)
    note("已投放内核设备树: " + DTS_REL)

    # 1b. 目标 overlay：首次开机调优脚本（zram / swappiness / packet steering / flow offload）
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
    note("已投放目标 overlay（开机调优）: " + os.path.relpath(tuning_dst, SRC))

    # 1c. LuCI 网络向导（自有 app，等价 iStoreOS 的“网络向导”，不依赖其闭源 quickstart）
    # 清掉旧命名（<=v5 曾用 luci-app-h28k-mode），避免旧包残留
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

    # 2. 镜像设备定义
    insert_before(image_mk, "define Device/radxa_e20c\n", DEVICE_BLOCK, "Device/hinlink_h28k")

    # 3. U-Boot 目标
    if "U-Boot/hinlink-h28k-rk3528" not in read(uboot_mk):
        insert_before(uboot_mk, "define U-Boot/radxa-e20c-rk3528\n", UBOOT_BLOCK,
                      "define U-Boot/hinlink-h28k-rk3528")
    else:
        note("跳过（已存在 U-Boot 目标）")
    insert_before(uboot_mk, "  radxa-e20c-rk3528 \\\n", "  hinlink-h28k-rk3528 \\\n",
                  "\n  hinlink-h28k-rk3528 \\\n")

    # 4. U-Boot 板级补丁（defconfig + u-boot dts）
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
            sys.exit("[adapt] 失败: U-Boot patches 目录里没有空号可用")

    # 5. base-files：网口 / LED / IRQ 绑定
    leds = os.path.join(base_etc, "board.d/01_leds")
    insert_before(leds, "widora,mangopi-m28k)\n",
                  """hinlink,h28k)
	ucidef_set_led_netdev "wan" "WAN" "blue:wan" "eth1"
	ucidef_set_led_netdev "lan" "LAN" "amber:lan" "eth0"
	;;
""", "hinlink,h28k)")

    net = os.path.join(base_etc, "board.d/02_network")
    # H28K 用独立一条：把默认 LAN IP 直接写进 board.json（config_generate 读 board.json
    # 的 ipaddr 生成 /etc/config/network），即真正的“固件内置默认值”，不依赖首次开机脚本。
    if 'ucidef_set_interface "lan" device "eth0"' not in read(net):
        insert_before(net, "\tarmsom,sige3|\\\n\tfriendlyarm,nanopi-r5c|\\\n", H28K_NET_BLOCK,
                      '\thinlink,h28k)\n\t\tucidef_set_interface "lan"')
    # 再从共享 LAN/WAN 分组里摘掉 h28k，避免重复
    replace_once(net,
                 "\thinlink,h28k|\\\n\tradxa,e20c|\\\n",
                 "\tradxa,e20c|\\\n",
                 "\tnlnet,xiguapi-v3|\\\n\tradxa,e20c|\\\n")
    replace_once(net,
                 "\tmmbox,anas3035)\n",
                 "\tmmbox,anas3035|\\\n\thinlink,h28k)\n",
                 "\tmmbox,anas3035|\\\n\thinlink,h28k)\n")

    aff = os.path.join(base_etc, "hotplug.d/net/40-net-smp-affinity")
    replace_once(aff,
                 "nlnet,xiguapi-v3|\\\nradxa,e25|\\\n",
                 "nlnet,xiguapi-v3|\\\nhinlink,h28k|\\\nradxa,e25|\\\n",
                 "hinlink,h28k|\\\nradxa,e25|\\\n")

    # 5.5 DHCP 默认池：对齐 EdgeRouter（EdgeOS 默认 .38-.243、lease 86400=24h）
    #     直接改 dnsmasq 的默认模板，这样镜像装完就是这套值，恢复出厂也一致，
    #     不依赖首次开机脚本；99-h28k-tuning 里再写一遍只是兜底。
    dhcp_tpl = os.path.join(SRC, "package/network/services/dnsmasq/files/dhcp.conf")
    tpl = read(dhcp_tpl)
    if "\toption start \t38\n" not in tpl:
        new = tpl.replace(
            "\toption start \t100\n\toption limit\t150\n\toption leasetime\t12h\n",
            "\toption start \t38\n\toption limit\t206\n\toption leasetime\t24h\n")
        if new == tpl:
            sys.exit("[adapt] 失败: dnsmasq 默认模板结构与预期不符（无法改 DHCP 池）")
        write(dhcp_tpl, new)
        note("已改 dnsmasq 默认 DHCP 池: .38-.243, 24h")

    # 6. 自检
    checks = {
        "设备定义": "Device/hinlink_h28k" in read(image_mk),
        "U-Boot 目标": "U-Boot/hinlink-h28k-rk3528" in read(uboot_mk),
        "U-Boot 列表": "\n  hinlink-h28k-rk3528 \\\n" in read(uboot_mk),
        "网口配置": 'ipaddr "192.168.2.1"' in read(net),
        "默认 IP 非分组继承": "\thinlink,h28k|\\\n" not in read(net),
        "MAC 生成": "\tmmbox,anas3035|\\\n\thinlink,h28k)" in read(net),
        "LED 配置": "hinlink,h28k)" in read(leds),
        "IRQ 绑核": "hinlink,h28k|\\\nradxa,e25" in read(aff),
        "内核 dts": os.path.exists(dts_dst),
        "PCIe/USB 节点": "&pcie {" in read(dts_dst) and "&usb2phy {" in read(dts_dst),
        "WireGuard 预置": os.access(os.path.join(target, "armv8/base-files/etc/uci-defaults/98-wireguard"), os.X_OK),
        "开机调优": os.access(tuning_dst, os.X_OK),
        "网络向导弹出": os.path.exists(os.path.join(
            pkg_dst, "htdocs/luci-static/resources/view/netmode/guide.js")),
        "DHCP 池": "\toption start \t38\n" in read(dhcp_tpl) and "\toption limit\t206\n" in read(dhcp_tpl) and "\toption leasetime\t24h\n" in read(dhcp_tpl),
    }
    bad = [k for k, v in checks.items() if not v]
    print("\n[adapt] 自检: " + ", ".join("%s=%s" % (k, "OK" if v else "FAIL") for k, v in checks.items()))
    if bad:
        sys.exit("[adapt] 失败: " + ", ".join(bad))
    print("[adapt] 完成：H28K 支持已就绪")


if __name__ == "__main__":
    main()

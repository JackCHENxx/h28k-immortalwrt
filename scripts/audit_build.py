#!/usr/bin/env python3
"""构建前的静态审计：配置种子、WireGuard 防火墙、OpenClash 默认状态。

用法: audit_build.py <immortalwrt源树> <config种子> <variant>
失败时退出 1，build.sh 会在编译前中止。
"""
import re
import subprocess
import sys
from pathlib import Path

if len(sys.argv) != 4:
    sys.exit("用法: audit_build.py <src> <config-seed> <variant>")

src = Path(sys.argv[1])
seed = Path(sys.argv[2])
variant = sys.argv[3]
kit = Path(__file__).resolve().parent.parent
errors = []


def fail(msg):
    errors.append(msg)
    print(f"[audit] FAIL: {msg}", file=sys.stderr)


def ok(msg):
    print(f"[audit] OK: {msg}")


def read(path):
    try:
        return Path(path).read_text(errors="replace")
    except OSError:
        return ""


def selected():
    text = read(seed)
    return {m.group(1) for m in re.finditer(r"^CONFIG_PACKAGE_([^=]+)=y$", text, re.M)}


pkgs = selected()
base_required = {
    "luci",
    "luci-app-netmode",
    "kmod-wireguard",
    "wireguard-tools",
    "luci-proto-wireguard",
    "owut",
}
for p in sorted(base_required - pkgs):
    fail(f"配置种子缺基础包 {p}")

experience_required = {
    "luci-theme-argon", "luci-app-argon-config",
    "autosamba", "luci-app-samba4", "luci-app-diskman", "luci-app-filemanager", "luci-app-minidlna",
    "luci-app-upnp", "luci-app-ddns", "luci-app-wol", "luci-app-sqm", "luci-app-mwan3",
    "luci-app-nlbwmon", "luci-app-vnstat2", "luci-app-statistics",
    "luci-app-frpc", "luci-app-frps", "luci-app-tailscale-community", "luci-app-zerotier",
    "luci-app-aria2", "luci-app-transmission", "luci-app-dockerman",
    "luci-app-openclash",
}
forbidden_any = {"luci-app-passwall", "luci-app-homeproxy"}  # 与 OpenClash 互斥
if variant == "experience":
    for p in sorted(experience_required - pkgs):
        fail(f"体验版缺插件 {p}")
    for p in sorted(forbidden_any & pkgs):
        fail(f"体验版不应同时装互斥代理插件 {p}")
else:
    for p in sorted({"luci-theme-argon", "luci-app-openclash", "luci-app-dockerman",
                     "autosamba", "luci-app-diskman", "luci-app-filemanager"} & pkgs):
        fail(f"默认版不应包含体验插件 {p}")

# 官方默认集是否仍在配置里
for p in ("default-settings", "autocore", "automount", "cpufreq"):
    if not (src / "feeds/base/emortal" / p).is_dir():
        fail(f"源码里找不到 emortal 包目录: {p}")
ok("配置种子包集合检查完成")

# WireGuard 后端：UCI 键名与防火墙三件套
wgctl = read(kit / "files/overlay/usr/bin/wgctl")
checks = {
    "DEFAULT_ADDR=10.0.0.1/24": "WireGuard 默认地址不是 10.0.0.1/24",
    "firewall.wg.masq=1": "WireGuard 缺 masq，客户端无法上网",
    "firewall.wg.mtu_fix=1": "WireGuard 缺 mtu_fix，LAN→WG 的 TCP 可能黑洞",
    "firewall.wg_lan": "WireGuard 缺 wg→lan 转发",
    "firewall.lan_wg": "WireGuard 缺 lan→wg 转发",
    "firewall.wg_wan": "WireGuard 缺 wg→wan 转发",
    "firewall.allow_wg": "WireGuard 缺 WAN 放行规则",
    "private_key": "WireGuard 缺正确 private_key 键名",
    "public_key": "WireGuard 缺正确 public_key 键名",
    "allowed_ips": "WireGuard 缺正确 allowed_ips 键名",
    "preshared_key": "WireGuard 缺正确 preshared_key 键名",
}
for needle, msg in checks.items():
    if needle not in wgctl:
        fail(msg)
if re.search(r"uci\s+(?:-q\s+)?delete\s+firewall\b", wgctl):
    fail("wgctl 出现删除整个 firewall 配置的危险操作")
if "uci set firewall.wg.forward=ACCEPT" not in wgctl:
    fail("WireGuard zone 的 forward 不是 ACCEPT")
ok("WireGuard 防火墙逻辑静态检查完成")

init = read(kit / "files/overlay/etc/uci-defaults/98-wireguard")
if "wgctl init" not in init:
    fail("98-wireguard 没有调用 wgctl init")
if not (kit / "files/overlay/etc/uci-defaults/98-wireguard").stat().st_mode & 0o111:
    fail("98-wireguard 没有执行权限")

guard = read(kit / "files/overlay/etc/uci-defaults/99-openclash-firewall-guard")
if "uci -q delete firewall.openclash" not in guard:
    fail("缺 OpenClash 防火墙 include 清理脚本")
if not (kit / "files/overlay/etc/uci-defaults/99-openclash-firewall-guard").stat().st_mode & 0o111:
    fail("99-openclash-firewall-guard 没有执行权限")

oc_cfg = read(src / "feeds/luci/applications/luci-app-openclash/root/etc/config/openclash")
if not re.search(r"option\s+enable\s+'0'", oc_cfg):
    fail("OpenClash 默认不是 enable=0，开机会改防火墙")
else:
    ok("OpenClash 默认关闭，只有启用时才接管 nftables")

# 脚本语法
for path in [
    kit / "build.sh",
    kit / "scripts/verify_image.sh",
    kit / "files/overlay/usr/bin/wgctl",
    kit / "files/overlay/etc/uci-defaults/98-wireguard",
    kit / "files/overlay/etc/uci-defaults/99-openclash-firewall-guard",
]:
    cmd = ["bash", "-n", str(path)] if path.suffix == ".sh" or path.name == "build.sh" else ["sh", "-n", str(path)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        fail(f"语法检查失败 {path}: {r.stderr.strip()}")

if errors:
    print(f"[audit] {len(errors)} 项失败，停止构建", file=sys.stderr)
    sys.exit(1)
print("[audit] 全部静态审计通过")

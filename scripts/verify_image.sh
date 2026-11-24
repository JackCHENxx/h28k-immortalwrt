#!/bin/bash
# 构建产物自检：不依赖真机，直接把镜像拆开检查关键假设。
# 用途：上游改了 dts/分区/包名/默认配置时，在发布前失败，而不是发出去才发现。
set -euo pipefail

IMG="${1:?用法: verify_image.sh <ext4-sysupgrade.img.gz>}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

fail() { echo "[verify] FAIL: $*" >&2; exit 1; }
ok() { echo "[verify] OK: $*"; }

# 1. 解压（镜像尾部带 sysupgrade metadata，gzip 会报 trailing garbage，忽略即可）
gzip -dc "$IMG" > "$WORK/disk.img" 2>/dev/null || true
[ -s "$WORK/disk.img" ] || fail "解压后镜像为空"

# 2. 分区表：boot 分区 + rootfs 分区（用 partx，不依赖 sfdisk）
partx -l "$WORK/disk.img" > "$WORK/parts.txt" 2>/dev/null || fail "读不到分区表"
part_line() { sed -n "s/^# $1: *\([0-9]*\)- *\([0-9]*\).*/\1 \2/p" "$WORK/parts.txt"; }
read -r START1 END1 <<< "$(part_line 1)"
read -r START2 END2 <<< "$(part_line 2)"
[ -n "${START1:-}" ] && [ -n "${START2:-}" ] || fail "分区表不是两分区布局"
SIZE1=$((END1 - START1 + 1))
SIZE2=$((END2 - START2 + 1))

# 3. U-Boot：sector 64 必须有内容（整盘镜像靠它启动）
dd if="$WORK/disk.img" bs=512 skip=64 count=1 status=none | od -An -tx1 | tr -d ' \n' > "$WORK/ub.txt"
UB=$(cat "$WORK/ub.txt")
[ -n "$UB" ] && [ "$UB" != "00000000000000000000000000000000" ] \
	|| fail "sector 64 没有 U-Boot"
ok "U-Boot 在 sector 64"

# 4. 内核分区里必须是我们这台设备的 dtb
dd if="$WORK/disk.img" of="$WORK/kernel.bin" bs=512 skip="$START1" count="$SIZE1" status=none
strings "$WORK/kernel.bin" > "$WORK/kernel.txt"
grep -q "hinlink_h28k device tree blob" "$WORK/kernel.txt" || fail "kernel 里没有 hinlink_h28k dtb"
grep -q "HINLINK H28K" "$WORK/kernel.txt" || fail "dtb 模型不是 HINLINK H28K"
ok "kernel FIT 含 HINLINK H28K dtb"

# 5. rootfs 大小（2GB 分区，允许 5% 误差）
[ "$((SIZE2 * 512))" -ge $((1900 * 1024 * 1024)) ] || fail "rootfs 分区只有 $((SIZE2 / 2048))MB，不是 2GB"
ok "rootfs 分区 $((SIZE2 / 2048))MB"

# 6. 拆 rootfs，查默认值/包/脚本
dd if="$WORK/disk.img" of="$WORK/rootfs.ext4" bs=512 skip="$START2" count="$SIZE2" status=none
debugfs -R "cat /etc/board.d/02_network" "$WORK/rootfs.ext4" 2>/dev/null > "$WORK/net.txt" || true
grep -q 'ipaddr "192.168.2.1"' "$WORK/net.txt" || fail "board.d 里没有 192.168.2.1"
grep -q 'device "eth1"' "$WORK/net.txt" || fail "board.d 里没有 eth1（WAN 口会消失）"
debugfs -R "cat /etc/config/dhcp" "$WORK/rootfs.ext4" 2>/dev/null > "$WORK/dhcp.txt" || true
dhcp_check() {
	local key=$1 want=$2
	grep -Eq "^[[:space:]]*option[[:space:]]+$key[[:space:]]+$want[[:space:]]*$" "$WORK/dhcp.txt" && return 0
	echo "[verify] /etc/config/dhcp 实际内容（节选）：" >&2
	grep -n "config dhcp lan" -A12 "$WORK/dhcp.txt" >&2 || true
	return 1
}
dhcp_check start 38 || fail "DHCP 池默认值不对"
dhcp_check limit 206 || fail "DHCP 池 limit 不对"
dhcp_check leasetime 24h || fail "DHCP 池租期不是 24h"
debugfs -R "cat /lib/apk/db/installed" "$WORK/rootfs.ext4" 2>/dev/null > "$WORK/pkgs.txt" || true
for pkg in kmod-wireguard wireguard-tools luci-proto-wireguard luci-app-netmode \
	owut ucode-mod-uclient; do
	grep -q "^P:$pkg$" "$WORK/pkgs.txt" || fail "缺包 $pkg"
done
debugfs -R "stat /etc/uci-defaults/98-wireguard" "$WORK/rootfs.ext4" >/dev/null 2>&1 \
	|| fail "缺 98-wireguard 首次开机脚本"
debugfs -R "stat /usr/bin/netmode" "$WORK/rootfs.ext4" >/dev/null 2>&1 \
	|| fail "缺 /usr/bin/netmode"
debugfs -R "stat /usr/bin/wgctl" "$WORK/rootfs.ext4" >/dev/null 2>&1 \
	|| fail "缺 /usr/bin/wgctl"
debugfs -R "cat /usr/bin/wgctl" "$WORK/rootfs.ext4" 2>/dev/null > "$WORK/wgctl.txt" || true
grep -q "DEFAULT_ADDR=10.0.0.1/24" "$WORK/wgctl.txt" \
	|| fail "WireGuard 默认地址不是 10.0.0.1/24"
grep -q "firewall.wg_wan" "$WORK/wgctl.txt" \
	|| fail "WireGuard 缺 wg→wan 转发，客户端无法上网"
grep -q "private_key" "$WORK/wgctl.txt" && grep -q "public_key" "$WORK/wgctl.txt" \
	|| fail "WireGuard 后端使用了错误的 UCI 键名"
debugfs -R "stat /www/luci-static/resources/view/netmode/wireguard.js" "$WORK/rootfs.ext4" >/dev/null 2>&1 \
	|| fail "缺 WireGuard 设置页面"
# 体验版额外校验：确认 Argon 主题和关键插件不是“只写进 config、没进镜像”
if [ -n "${EXPECT_EXTRA:-}" ]; then
	for pkg in $EXPECT_EXTRA; do
		grep -q "^P:$pkg$" "$WORK/pkgs.txt" || fail "缺体验版插件 $pkg"
	done
fi
if [ "${EXPECT_ARGON:-0}" = 1 ]; then
	debugfs -R "stat /etc/uci-defaults/30_luci-theme-argon" "$WORK/rootfs.ext4" >/dev/null 2>&1 \
		|| fail "缺 Argon 默认主题脚本（登录页仍是 bootstrap）"
fi
ok "默认 IP、DHCP 池、WireGuard、wgctl、设置页面均在镜像内"

echo "[verify] 全部通过: $IMG"

#!/usr/bin/env bash
# 一键构建 HINLINK H28K (RK3528) 的 ImmortalWrt 固件。
#
#   ./build.sh                         # 自动取 ImmortalWrt 最新 stable release 并全量编译
#   TAG=v25.12.2 ./build.sh            # 指定 release
#   JOBS=4 ./build.sh                  # 指定并行度（默认 nproc）
#   ./build.sh --prepare-only          # 只拉源码 + 打 H28K 补丁 + 生成 .config，不编译
#
# 产物: $OUT (默认 <kit>/out) 下的 *-hinlink_h28k-squashfs-sysupgrade.img.gz 及 sha256。
set -euo pipefail

REPO="${REPO:-https://github.com/immortalwrt/immortalwrt.git}"
KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TAG="${TAG:-}"
JOBS="${JOBS:-$(nproc)}"
SRC="${SRC:-$KIT_DIR/.build/immortalwrt}"
OUT="${OUT:-$KIT_DIR/out}"
PREPARE_ONLY=0

while [ $# -gt 0 ]; do
	case "$1" in
	--prepare-only) PREPARE_ONLY=1; shift ;;
	--tag) TAG="$2"; shift 2 ;;
	--src) SRC="$2"; shift 2 ;;
	--out) OUT="$2"; shift 2 ;;
	--jobs) JOBS="$2"; shift 2 ;;
	*) echo "未知参数: $1" >&2; exit 2 ;;
	esac
done

# 0. 主机依赖预检（U-Boot 的 RK3528 打包需要 pyelftools；缺了会在跑很久之后才失败）
python3 -c 'import elftools' 2>/dev/null || {
	echo "缺少 Python3 pyelftools：Ubuntu/Debian 请 sudo apt install python3-pyelftools，"
	echo "或 python3 -m pip install --break-system-packages pyelftools" >&2
	exit 1
}

log() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }

latest_tag() {
	git ls-remote --tags --refs "$REPO" 2>/dev/null \
		| awk '{print $2}' | sed 's#refs/tags/##' \
		| grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | sort -V | tail -1
}

[ -n "$TAG" ] || TAG="$(latest_tag)"
[ -n "$TAG" ] || { echo "取不到 ImmortalWrt 的 release tag，请手动指定 TAG=" >&2; exit 1; }
log "ImmortalWrt release: $TAG"

# 磁盘检查：全量编译需要 ~30GB
avail=$(df -Pk "$KIT_DIR" | awk 'NR==2{print int($4/1024/1024)}')
[ "$avail" -ge 20 ] || echo "警告: 可用空间仅 ${avail}GB，全量编译建议 >= 30GB"

# 1. 拉源码（浅克隆到指定 tag）
if [ -d "$SRC/.git" ]; then
	if [ "$(git -C "$SRC" describe --tags --exact-match 2>/dev/null || true)" = "$TAG" ]; then
		log "复用已有源码树: $SRC"
	else
		log "源码树版本不符，重新克隆: $SRC"
		rm -rf "$SRC"
	fi
fi
if [ ! -d "$SRC/.git" ]; then
	log "克隆 $REPO ($TAG)"
	mkdir -p "$(dirname "$SRC")"
	git clone --depth 1 --branch "$TAG" "$REPO" "$SRC"
fi

# 2. 打 H28K 适配补丁
log "补 H28K 设备支持"
python3 "$KIT_DIR/scripts/adapt.py" "$SRC"

# 3. feeds
if [ "${SKIP_FEEDS:-0}" = 1 ]; then
	log "跳过 feeds（SKIP_FEEDS=1，复用源码树里已有的 feeds）"
else
	log "更新 feeds"
	( cd "$SRC" && ./scripts/feeds update -a && ./scripts/feeds install -a )
fi

# 4. 生成 .config
log "写入 H28K 配置"
cp "$KIT_DIR/config/h28k.config" "$SRC/.config"
make -C "$SRC" defconfig
grep -q 'CONFIG_TARGET_rockchip_armv8_DEVICE_hinlink_h28k=y' "$SRC/.config" \
	|| { echo "配置里没有 hinlink_h28k 设备，补丁未生效" >&2; exit 1; }
grep -q 'CONFIG_PACKAGE_luci-app-h28k-mode=y' "$SRC/.config" \
	|| { echo "配置里没有 luci-app-h28k-mode，网络向导不会进固件" >&2; exit 1; }

[ "$PREPARE_ONLY" = 1 ] && { log "仅准备阶段完成: $SRC"; exit 0; }

# 5. 编译
log "开始编译 (jobs=$JOBS)，视机器性能约 1~4 小时"
make -C "$SRC" -j"$JOBS"

# 6. 收集产物
log "收集产物"
mkdir -p "$OUT"
find "$SRC/bin/targets/rockchip/armv8" -maxdepth 1 -name '*hinlink_h28k*' \
	\( -name '*.img.gz' -o -name '*.bin' -o -name '*.itb' -o -name '*.dtb' \) \
	-exec cp -f {} "$OUT"/ \;
( cd "$OUT" && sha256sum ./* > sha256sums.txt 2>/dev/null || true )
{
	echo "ImmortalWrt release: $TAG"
	echo "device: hinlink_h28k (HINLINK H28K / Seeed LinkStar H28K, RK3528)"
	echo "built: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
} > "$OUT/build-info.txt"

ls -lh "$OUT"
log "完成: $OUT"

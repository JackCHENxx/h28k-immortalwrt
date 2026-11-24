# HINLINK H28K / ImmortalWrt 自动构建

给 **HINLINK H28K**（也叫 Seeed LinkStar-H28K，RK3528，2×千兆口，2/4GB LPDDR4X + 8GB eMMC）编译 ImmortalWrt 固件，
版本跟随 ImmortalWrt 的**最新 stable release**（当前 `v25.12.2`，2026-09-06）。

## 为什么需要这一套补丁

ImmortalWrt 25.12.2 的 `rockchip/armv8` 已经有 RK3528 的 SoC 支持（内核 6.12 + U-Boot 2025.10，
现成设备只有 Radxa E20C、MangoPi M28C/M28K），但**没有收录 H28K**。
H28K 的板级支持目前只存在于 OpenWrt 主线（2026-01 合入）。所以这套工具做的是把 OpenWrt 主线的 H28K
支持**回移**到 ImmortalWrt release 分支上，再编译：

| 补丁 | 内容 |
| --- | --- |
| `files/rk3528-hinlink-h28k.dts` | 板级设备树：gmac1(RTL8211F)、PCIe 侧 RTL8111H、eMMC/SD、ADC 按键、三颗 LED、PWM 调压。放在目标树 `files/` 下，`prepare` 时并入内核树，由 image 系统的 `Image/BuildDTB` 直接编译，不用改内核 dts Makefile |
| `patches/uboot-board-rockchip-add-HINLINK-H28K.patch` | U-Boot defconfig + u-boot dts，新增 `hinlink-h28k-rk3528` 目标 |
| `scripts/adapt.py` 内联改动 | `armv8.mk` 设备定义、`uboot-rockchip/Makefile` 目标、`base-files` 的 LAN/WAN 网口（含默认 IP）、LED、IRQ 绑核 |
| `scripts/verify_image.sh` | 发布前拆镜像自检：U-Boot、dtb、分区、默认 IP、DHCP 池、包清单 |
| `files/overlay/etc/uci-defaults/99-h28k-tuning` | 首次开机调优：zram 按内存自适应（2GB→1.5G、4GB→3G）、swappiness 80、packet steering、flow offload，并预置旁路由/恢复备份按钮 |
| `files/overlay/usr/bin/netmode` | 向导后端脚本（`setup bypass/dhcp/pppoe`、`detect`、`bypass` / `router` / `lanip` / `dhcp` / `status`） |
| `files/overlay/usr/bin/wgctl` | WireGuard 后端（`init` / `status` / `apply` / `keygen` / `peer-add` / `peer-del` / `client-conf`），首次开机由 `98-wireguard` 调 `wgctl init` |
| `package/luci-app-netmode` | 自带 LuCI 应用：**网络 → 网络向导**（三种联网方式三步配置）与 **网络 → WireGuard 设置**（服务端参数、密钥、对端、客户端配置） |

`adapt.py` 是幂等的：重复执行只会跳过。如果哪天 ImmortalWrt 自己收录了 H28K，脚本会**主动停下**并要求人工合并，而不是覆盖上游实现；确认要沿用本套件时加 `--force`。

默认版固件保留 ImmortalWrt 官方 rockchip 目标默认安装的板级/emortal 能力（`default-settings-chn` 中文时区与国内源、`autocore`、`automount`、`luci-app-cpufreq`、`owut`）。注意 **Argon 主题、autosamba、diskman、filemanager 并不在官方默认清单里**；要一次体验这些插件，用上面的 `VARIANT=experience` 构建。

## 方式一：GitHub Actions（推荐，约 40–70 分钟出镜像）

1. 把本目录推到自己的仓库（`.github/workflows/build-h28k.yml` 必须一起推上去）。
2. Actions 里跑 `Build ImmortalWrt for HINLINK H28K`，`tag` 留空 = 自动取最新 release。
3. 跑完在 Artifacts 下拿 `immortalwrt-h28k`；同时会自动发一个 Release（指定 tag 就发到该 tag，否则更新 `h28k-latest`），Releases 页可直接下载，不用登录 Actions。
   工作流默认每周四自动跟一次最新 release。

每次编译前先跑一个 **preflight 指纹检查**：记录上游 tag、`feeds.conf.default` 里锁定的 5 个 feed commit、本仓库 commit 和配置种子哈希。定时任务如果发现指纹与 Release 里 `build-info.txt` 完全一致，就直接跳过编译，不消耗编译时间；上游或本仓库有变化才重建。需要强制重刷同一版本时，手动触发并勾选 `force`。

## 方式二：本机/服务器编译

```bash
./build.sh                 # 自动取最新 release，全量编译
TAG=v25.12.2 ./build.sh    # 指定版本
JOBS=8 ./build.sh          # 指定并行度
./build.sh --prepare-only  # 只准备源码 + 补丁 + .config，不编译
SKIP_FEEDS=1 ./build.sh    # 复用源码树里已装好的 feeds（重跑时省 10 分钟）
VARIANT=experience CONFIG_SEED=config/h28k-experience.config ./build.sh  # 全功能体验版
```

固件有两个 seed：

- `config/h28k.config`：官方 ImmortalWrt 默认集 + 本项目的 WireGuard/网络向导，适合长期稳定使用。
- `config/h28k-experience.config`：在默认集上追加 Argon 主题、Samba/autosamba、磁盘/文件管理、DLNA、UPnP、DDNS、WOL、SQM、mwan3、流量统计、frp、Tailscale、ZeroTier、Aria2、Transmission、Docker/Dockerman、OpenClash，适合先体验 ImmortalWrt 的完整插件生态。
  其中 OpenClash 默认 `enable=0`，只有手动启用才接管 nftables；首次开机脚本和每次开机的 `S18openclash-firewall-guard` 都会在未启用时清理它无条件写入的 `firewall.openclash` include，避免影响 fw4/WireGuard。PassWall/HomeProxy 与 OpenClash 互斥，未预装。

要求：Linux x86_64、≥4 核、≥4GB 内存（8GB 更稳）、≥30GB 磁盘；Ubuntu 装好
`build-essential clang flex bison gawk gettext git libncurses-dev libssl-dev python3 python3-setuptools python3-pyelftools swig python3-dev rsync unzip zlib1g-dev file wget cpio`。
源码树落在 `.build/immortalwrt`，产物收到 `out/`。

想要更多插件，改 `config/h28k.config` 往里加 `CONFIG_PACKAGE_xxx=y` 即可（也可以先 `--prepare-only`，
再 `make -C .build/immortalwrt menuconfig` 手动挑包，最后 `make -C .build/immortalwrt -j$(nproc)`）。

## 产物

```
immortalwrt-rockchip-armv8-hinlink_h28k-squashfs-sysupgrade.img.gz
```

这是一个自带 U-Boot 的完整卡镜像（U-Boot 落在 sector 64，32MiB 对齐），SD 卡和 eMMC 都能直接写。
默认分区 kernel 64MB / rootfs **2GB**（8GB eMMC 留足余量，剩余空间可在 LuCI 里扩 overlay），
LuCI 中文界面，**LAN `192.168.2.1`**（DHCP 池 192.168.2.38–243，租期 24h，对齐 EdgeRouter/EdgeOS 默认）。

## 默认 IP 192.168.2.1 是写进固件的，不是开机脚本改的

OpenWrt/ImmortalWrt 的 LAN 默认地址不是硬编码在某个配置文件里，而是开机时由
`package/base-files/files/bin/config_generate` 生成：它先读 `/etc/board.json` 里每张网卡的
`ipaddr` / `netmask`，取不到才回落到 `192.168.1.1`。`board.json` 则由
`/etc/board.d/02_network` 调 `ucidef_set_interface` 写出来。

所以 H28K 的默认地址直接写在 `02_network` 的板级条目里：

```sh
hinlink,h28k)
	ucidef_set_interface "lan" device "eth0" protocol "static" ipaddr "192.168.2.1" netmask "255.255.255.0"
	ucidef_set_interface "wan" device "eth1" protocol "dhcp"
	;;
```

结果就是：**刷完第一次开机就是 192.168.2.1，恢复出厂设置也还是 192.168.2.1**，
不依赖任何 `uci-defaults` 脚本（那种方式只在首次开机或 overlay 被重置时才跑，
从旧固件 sysupgrade 上来会保留旧 `network` 配置，看起来就"没生效"）。
`02_network` 只在开机 detect 阶段跑，板名不对的其它板子完全不受影响。

两个边界要知道：

- 已经跑过系统的机器升级，`/etc/config/network` 是已有的，不会被固件默认值覆盖（这是 OpenWrt 的正常行为，保护你的配置）；
- 旁路由脚本里 `netmode lanip 192.168.1.2` 改的是**当前运行配置**，不会改固件默认值，恢复出厂后仍回到 `192.168.2.1`。

## 默认调优（首次开机自动生效）

`files/overlay/etc/uci-defaults/99-h28k-tuning` 会在 H28K 首次开机时执行一次（其它板子自动跳过）：

| 项 | 值 | 理由 |
| --- | --- | --- |
| `system.zram_size_mb` | 2GB→1536；4GB→3072 | 按 `/proc/meminfo` 实测内存自适应；lzo-rle 约 2~2.5:1，只是容量上限，不预占内存 |
| `system.zram_priority` | 100 | 高于任何磁盘 swap，冷页优先压进内存 |
| `vm.swappiness` | 80 | 有 zram 时更积极换出冷数据；写入 `/etc/sysctl.d/90-h28k-zram.conf` |
| `network.packet_steering` | 1 | 四核 A53 上把网卡软中断分摊到多核（ImmortalWrt 默认只对 x86/mt7621/bcm53xx 开） |
| `firewall.@defaults[0].flow_offloading` | 1 | 软件快速路径（fw4），RK3528 上做 NAT 转发才跑得满千兆 |
| zram `mem_limit` | 内存的一半 | 2GB→1GB、4GB→2GB，极端不可压数据也不会把内存吃穿 |
| `dhcp.lan.start` / `limit` / `leasetime` | 38 / 206 / 24h | 地址池 `192.168.2.38–243`，与 EdgeRouter（EdgeOS）默认一致；同时写进 dnsmasq 默认模板，恢复出厂也是这套 |

注意：`flow_offloading=1` 和 SQM/QoS 流控冲突，以后要限速，在 LuCI「网络 → 防火墙」里关掉软件流量分载即可；
`system.zram_*` 改完 `/etc/init.d/zram restart` 生效，可 `zramctl` / `free -h` 核对。

## 网络向导（LuCI，仿 iStoreOS 三步流程）

刷好后 LuCI 里多出 **网络 → 网络向导**，流程和 iStoreOS 一样：**选联网方式 → 填参数 → 应用完成**。

第一步是三个大卡片（红 / 绿 / 蓝），点进去就是对应的参数页：

| 入口 | 做什么 | 底层命令 |
| --- | --- | --- |
| 宽带拨号连接（红） | WAN 口 PPPoE 拨号，本机做主路由，开 DHCP + NAT | `netmode setup pppoe <账号> <密码> [本机IP]` |
| 连接现有路由器（绿） | WAN 口 DHCP 自动获取 IP，本机做主路由，开 DHCP + NAT | `netmode setup dhcp [本机IP]` |
| 配置为旁路由（蓝） | LAN 静态、网关/DNS 指向主路由、关本机 DHCP/RA、禁 WAN、LAN 开 masq | `netmode setup bypass <主路由IP> [本机IP]` |

参数页会预填当前 LAN IP，旁路由的主路由地址会用 `netmode detect` 探测（优先取现有 LAN 网关，
其次取默认路由），探不到才回落到 `192.168.2.254`。应用后进完成页：显示本机地址、执行输出和下一步提示，
并提供「进入后台」/「再配置一次」。改过 LAN IP 的话，6 秒后自动跳到新地址。

旁路由模式下客户端要借道，需要把**主路由 DHCP 下发的网关和 DNS** 改成这台机器的 LAN IP；
或者只改需要走它的终端。主路由本身不用动。

> 为什么没直接装 iStoreOS 的 quickstart：它的 `quickstart` / `quickstart-netpolicy` / `luci-app-quickstart`
> 只有 KoolCenter 的预编译 ipk，源码不开，还绑着 iStoreOS 自己的 API。这里按同样的交互做了一个
> 纯 shell + LuCI JS 的实现，源码全部在 `package/luci-app-netmode` 里，可审计、可改。

命令行同样可用（向导页面就是调这些）：

```sh
netmode status
netmode detect                 # 探测上级网关
netmode setup bypass 192.168.2.254 192.168.2.1
netmode setup dhcp 192.168.2.1
netmode setup pppoe 宽带账号 宽带密码 192.168.2.1
netmode router                 # 只恢复主路由默认（WAN DHCP）
netmode lanip 192.168.1.2      # 只改 IP
netmode dhcp off               # 只关 DHCP
netmode restore                # 回到第一次改网络配置之前（失联自救）
```

每次真正改配置前，`netmode` 会把 `network` / `dhcp` / `firewall` / `netmode` 备份到 `/etc/netmode-backup`（只备份第一次，后续改动不会覆盖原始值）。改错 IP、旁路由切过去连不上时，SSH 进去执行 `netmode restore` 就能回滚；LuCI「系统 → 自定义命令」里也预置了「④ 恢复上次备份」。

典型旁路由接法（主路由同网段）：

1. 主路由（例如 `192.168.2.254`）保持拨号/上网不变；
2. H28K 用网线接到主路由的交换机侧，后台地址仍是 `192.168.2.1`；
3. 向导里选「配置为旁路由」，填主路由 IP，应用；
4. 把主路由 DHCP 下发的网关/DNS 改成 `192.168.2.1`，或只改需要走它的终端。

## WireGuard（内置服务端）

固件里已经带 `kmod-wireguard`、`wireguard-tools`、`luci-proto-wireguard`，第一次开机由 `98-wireguard` 预置一个**空服务端**：

| 项 | 值 |
| --- | --- |
| 接口 / 地址 | `wg0`，`10.0.0.1/24` |
| 监听 | UDP `51820`，MTU `1420` |
| 私钥 | `/etc/wireguard/wg0.key`（`600`，首次开机 `wg genkey` 生成） |
| 防火墙 | 新建 `wg` zone（`masq=1`）；`wg→lan`、`lan→wg`、`wg→wan` 三条 forwarding；WAN 放行 UDP 51820 |

它只建了服务端框架，**没有任何 peer**，所以默认谁都连不进来。

图形界面：LuCI「网络 → **WireGuard 设置**」，可以改启用状态、本机地址、UDP 端口、MTU，重新生成服务端密钥，增删对端，或直接填客户端名称/地址/公网地址生成一份 `wg.conf`（会同时把该客户端加入对端列表）。命令行等价入口是 `/usr/bin/wgctl`：

```
wgctl status
wgctl apply --address=10.0.0.1/24 --port=51820 --mtu=1420 --enabled=1
wgctl keygen
wgctl peer-add --name=phone --pubkey=<44位公钥> --allowedips=10.0.0.2/32 --keepalive=25
wgctl peer-del --name=phone
wgctl client-conf --name=phone --ip=10.0.0.2 --endpoint=<公网IP或域名> --port=51820 --dns=10.0.0.1
```

要让 VPN 客户端访问整个内网，客户端配置的 `AllowedIPs` 要包含 `192.168.2.0/24`；默认生成的客户端配置是全局代理（`0.0.0.0/0`），`wg` zone 做 masq 并通过 `wg→wan` 转发，客户端可以经本机上网。升级时如果保留了旧的 `/etc/config/network`，`wg0` 地址不会被覆盖；想统一到新默认值，删掉 `wg0` 后重跑 `wgctl init`，或在设置页里直接改地址。

注意两点：旁路由模式下 WAN 接口是禁用的，外网连不进来，这是预期行为；RK3528 上 WireGuard 走 ChaCha20/NEON，实测通常 200–400Mbps，跑满千兆不现实。

## 上游变了怎么自动处理

`adapt.py` 不是“按某几个字符串硬怼”，而是按结构定位，并且**宁可构建失败也不发错固件**：

| 上游变化 | 自动行为 |
| --- | --- |
| 新 release / 内核升级 | `build.sh` 每次取最新 stable tag、全新浅克隆，不依赖上次的源码树 |
| 上游自己收录了 H28K | 检测到 `Device/hinlink_h28k` 就**停止**并提示人工合并，不覆盖上游的 dts/board.d/U-Boot；确认要沿用本套件时加 `--force` |
| 板级 case 里增删板子/改顺序 | 分支插到 `case` 的第一条之前（先匹配先执行），不依赖相邻板子的字符串；`case $board in` 和 `case "$board" in` 两种写法都支持 |
| `02_network` 的 LAN/WAN 分组重排 | 自己的分支永远最先命中，不再需要从共享分组里“抠出来” |
| dnsmasq 模板缩进/顺序变化 | 按 `config dhcp lan` section 改 `start/limit/leasetime` 三个键，缺键就补，不整段替换 |
| 设备定义/U-Boot 锚点消失 | 设备定义退到文件末尾追加，U-Boot 定义退到 `BuildPackage/U-Boot` 之前，列表项退到 `UBOOT_TARGETS :=` 之后 |
| 包名/feed 变化 | `build.sh` 断言 `kmod-wireguard`、`wireguard-tools`、`luci-proto-wireguard`、`luci-app-netmode` 真的进了 `.config` |
| 分区/dtb/默认值被悄悄改坏 | `scripts/verify_image.sh` 在发布前拆镜像：U-Boot 在 sector 64、kernel 里是 `hinlink_h28k` dtb、rootfs 2048MB、board.d 里 `192.168.2.1` 和 `eth1`、DHCP 池 `.38–243/24h`、四个包和 `98-wireguard` 都在；任何一项不符，Release 不会发 |

每周四的 Actions 会先比对构建指纹；上游 release、feed 锁定 commit、本仓库 commit 和配置都没变时直接跳过，不重复编译。上游一改，最迟一周内会重新编译，并在“编译”或“校验镜像”这一步失败，而不是等你刷上去才发现网口没了。

## 刷机安全（重要）

- 这个目标的 `sysupgrade.img.gz` 是**整盘镜像**，U-Boot 在 sector 64 处（`u-boot-rockchip.bin`），刷机会连同 bootloader 一起写。**刷写过程中断电可能变砖**，务必接稳电源。
- 第一次建议先写到 **microSD 卡**上试（能否优先从 SD 启动取决于 BootROM 和现有 bootloader；不行就走 maskrom），确认能进系统、两个网口都在，再写 eMMC。eMMC 在系统里是 `/dev/mmcblk0`，SD 是 `/dev/mmcblk1`。
- 变砖恢复靠 Rockchip maskrom + `rkdeveloptool`（USB 连接、按板子丝印进 maskrom），刷回备份或本工程镜像；刷之前先完整备份原机 eMMC。
- 不要单独刷 U-Boot，也不要 `dd` 写 `/dev/mtdblock*`；只写 `/dev/mmcblk0` 或走 sysupgrade。
- 板级 dts 已补齐 `&pcie`、`&usb2phy`、`&combphy`、`&gpu` 节点（PCIe 上的 RTL8111H 就是 WAN 口 `eth1`），U-Boot 补丁与 OpenWrt 主线逐字节一致。
- 固件沿用官方默认的 **root 空密码**：刷完第一次进 LuCI 就设置密码，别把管理面直接暴露在不可信网络。
- WireGuard 首次开机会生成 `wg0` 并在 WAN 放行 UDP 51820；不需要时执行 `wgctl apply --enabled=0`，并删除 `firewall.allow_wg`。添加 peer 等于授予其访问整个 LAN 的权限，按需收紧 `wg` zone 的 input/forward。
- 体验版预装的服务（Docker、Samba、UPnP、frp、Tailscale、ZeroTier、Aria2、Transmission、DLNA）不会替你决定用途；不用就在 LuCI 停用，尤其不要把 UPnP 和 Samba 暴露到公网。

## 通用层与设备层（方便适配别的板子）

这套东西刻意拆成两层，换设备时只动设备层：

| 层 | 文件 | 是否设备相关 |
| --- | --- | --- |
| 通用网络逻辑 | `files/overlay/usr/bin/netmode` | 否。只读写 `network` / `dhcp` / `firewall` 的 UCI，接口名从配置里取 |
| 通用 LuCI 应用 | `package/luci-app-netmode` | 否。菜单「网络 → 网络向导」，三种联网方式 |
| 设备板级支持 | `files/rk3528-hinlink-h28k.dts`、`patches/uboot-*.patch`、`adapt.py` 里的 `Device/` 与 `board.d` 改动 | 是 |
| 设备默认参数 | `files/overlay/etc/uci-defaults/99-h28k-tuning`（内有 `board_name` 门禁） | 是 |

`netmode` 能用在任意 OpenWrt 上：`setup bypass/dhcp/pppoe`、`detect`、`lanip`、`dhcp on|off` 都只依赖标准 `lan`/`wan` 接口与 `firewall` 的 zone 名，不认具体网卡。旁路由的同网段校验也改成按 `network.lan.netmask` 计算，不再写死 `/24`。向导页面里的网口名字取自 `network.lan.device` / `network.wan.device`，不会硬编码 `eth0/eth1`。

兼容性：早期版本用的名字是 `h28k-mode` 和 `/etc/config/h28k`，现在留有 `/usr/bin/h28k-mode` 包装脚本；`netmode` 首次运行会自动把旧配置复制成 `netmode`，老脚本、老命令不用改。

要加第二块板子，按这个顺序即可：拷一份 dts 与 U-Boot 补丁 → 在 `armv8.mk` 加 `Device/xxx` → 在 `board.d/01_leds`、`02_network`（含 `ipaddr`）、`40-net-smp-affinity` 加条目 → 新增一个带 `board_name` 门禁的 `uci-defaults` → 在 `config/` 里加一份 seed。`netmode` 与 LuCI 应用不用动。

## 三种模式的参数清单（含防火墙）

向导做的事，等价于下面这些 UCI 项；都可以用 `uci show` 逐条核对。

**旁路由（`setup bypass <主路由IP> [本机IP]`）**

| 配置项 | 值 | 作用 |
| --- | --- | --- |
| `network.lan.proto` | 保持 `static` | LAN 口静态地址 |
| `network.lan.ipaddr` / `netmask` | 默认 `192.168.2.1` / `255.255.255.0`（可选改） | 与主路由同网段 |
| `network.lan.gateway` | 主路由 IP | 默认路由指向主路由 |
| `network.lan.dns` | 主路由 IP | 本机 dnsmasq 上游，经主路由解析 |
| `network.wan.disabled` | `1` | WAN 口不用，避免双默认路由 |
| `dhcp.lan.ignore` | `1` | 关 DHCPv4，避免和主路由抢着发地址 |
| `dhcp.lan.dhcpv6` / `dhcp.lan.ra` | `disabled` | 关 DHCPv6/RA，避免 IPv6 抢答 |
| `firewall` zone `lan`.`forward` | `ACCEPT` | 流量从 LAN 进、再从 LAN 出，必须允许同 zone 转发 |
| `firewall` zone `lan`.`masq` | `1` | LAN 侧 SNAT，保证回程也经过本机 |
| `firewall` zone `wan` | 不动（masq 仍 1，但口已 disabled） | — |

**主路由 · WAN 自动获取（`setup dhcp [本机IP]`）**

| 配置项 | 值 | 作用 |
| --- | --- | --- |
| `network.wan.proto` | `dhcp` | eth1 从上级获取地址 |
| `network.wan.disabled` | `0` | 启用 WAN |
| `network.wan.ipv6` | `1` | 允许 WAN 侧 IPv6 |
| `network.wan.username` / `password` | 删除 | 清掉可能残留的 PPPoE 凭据 |
| `network.wan6` | `proto dhcpv6`，`device @wan` | IPv6 跟随 WAN |
| `network.lan.gateway` / `dns` | 删除 | 本机自己拨号，不再指向别人 |
| `dhcp.lan.ignore` | `0` | 开 DHCPv4 |
| `dhcp.lan.dhcpv6` / `ra` | `server` | 开 DHCPv6/RA |
| `firewall` zone `lan`.`masq` | `0` | LAN 侧不做二次 NAT，只靠 wan 侧 masq |
| `firewall` zone `wan`.`masq` | `1` | 出口 NAT |
| `firewall` forwarding `lan→wan` | 确保存在（缺了就补） | 允许内网出外网 |

**主路由 · PPPoE（`setup pppoe <账号> <密码> [本机IP]`）**

与上面完全相同，区别只有：`network.wan.proto='pppoe'`、写入 `username`/`password`、`wan6` 挂到 `@wan`（走 IPv6CP）。
固件里已预置 `ppp` + `ppp-mod-pppoe` + `kmod-pppoe`，否则这条模式会拨不起来。

**所有模式都不动的东西**

- `network.lan.netmask` 仍为 `255.255.255.0`，DHCP 池固定为 `start 38 / limit 206`（`192.168.2.38–243`），租期 `24h`
- `firewall` 的 `defaults.input=REJECT`、`defaults.forward=REJECT` 不变，只靠 zone 的 `forward=ACCEPT` 放行 LAN
- `dhcp.@dnsmasq[0].dns_redirect=1`：所有打到本机的 DNS 都会被导向 dnsmasq（旁路由下也一样，客户端自定义 DNS 会被接管）
- `flow_offloading` / `packet_steering` 由开机调优脚本设置，切模式不改

**已知边界**

- 旁路由的 `/24` 同网段校验只在 `setup bypass` 里做；掩码不是 `/24` 的场景请先用 `netmode lanip` 配好 IP/掩码，再用 `netmode bypass <IP>`。
- 旁路由不接管 IPv6：主路由若直接给终端发 IPv6，那部分流量会绕过本机。
- 旁路由默认在 LAN 侧做 SNAT。想让上游看到真实客户端 IP，可执行
  `uci set firewall.@zone[0].masq='0'; uci commit firewall; /etc/init.d/firewall reload`（zone 序号以 `uci show firewall` 里 lan 那条为准），代价是回程不再经过本机。
- 切模式只 reload 服务，已建立的连接可能短暂中断；需要彻底断开就重启一次。

## 刷机（H28K）

1. **SD 卡**：`gunzip` 后得到 `.img`，用 balenaEtcher 或 `dd if=xxx.img of=/dev/sdX bs=4M conv=fsync` 写入 TF 卡，插卡上电即从 TF 启动（TF 优先于 eMMC）。
2. **写入 eMMC**（两种都行）：
   - 从 SD 卡启动进系统后，把 `.img` 传到 `/tmp`，执行 `dd if=/tmp/xxx.img of=/dev/mmcblk0 bs=4M conv=fsync`；
   - 或短接进 Maskrom，用 RKDevTool：Loader 选 `H28K-Boot-Loader.bin`，system 选解压后的 `.img`，点“执行”。
3. 网线接 **eth0（RTL8211F 那颗，靠 LAN）**，等 1–2 分钟，浏览器开 `192.168.2.1`。
   串口调试参数 `1500000 8N1`。

注意：

- 只用 Type-C 供电容易供电不足导致外设/网口起不来，建议用 DC 口供电。
- eMMC 里原有系统（iStoreOS/QWRT 等）会被整盘覆盖，先备份。
- 若 eMMC 启动失败，通常是 U-Boot 没写进 eMMC：从 SD 卡启动后重跑一次 `dd`，或用 Maskrom + RKDevTool 刷完整镜像。

## 验证记录（本目录已实测的部分）

- `adapt.py` 在 `v25.12.2` 干净源码树上执行通过，自检 16 项全 OK，重复执行全部跳过（幂等）。
- 调优脚本与 `netmode` 装进目标后权限均为 755，`sh -n` 语法检查通过；调优脚本只对 `hinlink,h28k` 执行。
- `.config` 里 `CONFIG_PACKAGE_luci-app-commands=y` 被 defconfig 保留，用于承载“系统 → 自定义命令”的四个一键按钮。
- `make defconfig` 接受 `CONFIG_TARGET_rockchip_armv8_DEVICE_hinlink_h28k=y`，设备 profile 被正确识别。
- 内核 `prepare`（6.12.103 + ImmortalWrt 全部回移补丁）通过；H28K 设备树用与 `Image/BuildDTB` 相同的
  cpp + dtc 流程编译成功（`rk3528-hinlink-h28k.dtb`，仅 rk3528.dtsi 自带 warning），
  dtb 内 gmac `phy-mode = "rgmii-id"`、eMMC `mmc-hs200-1_8v`、ADC 按键、lan/wan/status 三灯均在。
- U-Boot 2025.10 上 `package/boot/uboot-rockchip/prepare` 应用通过（`hinlink-h28k-rk3528_defconfig` 已生成）。
  单独验证：`patch -p1 --dry-run` 干净应用，`make hinlink-h28k-rk3528_defconfig` 正常出 `.config`
  （RK3528 / rockchip,rk3528-hinlink-h28k / SDHCI / DWC_ETH_QOS / 1500000 波特率均正确）。
- `./build.sh --prepare-only`（复用已有源码树）整条流程跑通：克隆/复用 → 补丁 → feeds → `.config` → 设备校验。
- 未在本机跑完整 `make`（本机只有 2 核 3GB，全量编译要数小时），完整编译请走 GitHub Actions 或自己的多核机器。

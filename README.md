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
| `files/overlay/etc/uci-defaults/99-h28k-tuning` | 首次开机调优：zram 1.5G、swappiness 80、packet steering、flow offload，并预置旁路由一键按钮 |
| `files/overlay/usr/bin/h28k-mode` | 向导后端脚本（`setup bypass/dhcp/pppoe`、`detect`、`bypass` / `router` / `lanip` / `dhcp` / `status`） |
| `package/luci-app-h28k-mode` | 自带 LuCI 应用：**网络 → 网络向导**，三步流程（选方式 → 填参数 → 完成），三种联网方式（宽带拨号 / 连现有路由 / 旁路由） |

`adapt.py` 是幂等的：重复执行只会跳过；如果哪天 ImmortalWrt 自己收录了 H28K，对应步骤会自动跳过，不用改脚本。

## 方式一：GitHub Actions（推荐，约 40–70 分钟出镜像）

1. 把本目录推到自己的仓库（`.github/workflows/build-h28k.yml` 必须一起推上去）。
2. Actions 里跑 `Build ImmortalWrt for HINLINK H28K`，`tag` 留空 = 自动取最新 release。
3. 跑完在 Artifacts 下拿 `immortalwrt-h28k`，里面就是 `.img.gz` + `sha256sums.txt` + `build-info.txt`。
   工作流默认每周一自动跟一次最新 release。

## 方式二：本机/服务器编译

```bash
./build.sh                 # 自动取最新 release，全量编译
TAG=v25.12.2 ./build.sh    # 指定版本
JOBS=8 ./build.sh          # 指定并行度
./build.sh --prepare-only  # 只准备源码 + 补丁 + .config，不编译
SKIP_FEEDS=1 ./build.sh    # 复用源码树里已装好的 feeds（重跑时省 10 分钟）
```

要求：Linux x86_64、≥4 核、≥4GB 内存（8GB 更稳）、≥30GB 磁盘；Ubuntu 装好
`build-essential clang flex bison gawk gettext git libncurses-dev libssl-dev python3 rsync unzip zlib1g-dev file wget cpio`。
源码树落在 `.build/immortalwrt`，产物收到 `out/`。

想要更多插件，改 `config/h28k.config` 往里加 `CONFIG_PACKAGE_xxx=y` 即可（也可以先 `--prepare-only`，
再 `make -C .build/immortalwrt menuconfig` 手动挑包，最后 `make -C .build/immortalwrt -j$(nproc)`）。

## 产物

```
immortalwrt-rockchip-armv8-hinlink_h28k-squashfs-sysupgrade.img.gz
```

这是一个自带 U-Boot 的完整卡镜像（U-Boot 落在 sector 64，32MiB 对齐），SD 卡和 eMMC 都能直接写。
默认分区 kernel 64MB / rootfs **2GB**（8GB eMMC 留足余量，剩余空间可在 LuCI 里扩 overlay），
LuCI 中文界面，**LAN `192.168.2.1`**（DHCP 池 192.168.2.100–249）。

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
- 旁路由脚本里 `h28k-mode lanip 192.168.1.2` 改的是**当前运行配置**，不会改固件默认值，恢复出厂后仍回到 `192.168.2.1`。

## 默认调优（首次开机自动生效）

`files/overlay/etc/uci-defaults/99-h28k-tuning` 会在 H28K 首次开机时执行一次（其它板子自动跳过）：

| 项 | 值 | 理由 |
| --- | --- | --- |
| `system.zram_size_mb` | 1536 | 2GB 内存给 1.5G 压缩 swap（lzo-rle 约 2~2.5:1，实际只吃掉约 600MB 内存），只是容量上限，不预占内存 |
| `system.zram_priority` | 100 | 高于任何磁盘 swap，冷页优先压进内存 |
| `vm.swappiness` | 80 | 有 zram 时更积极换出冷数据；写入 `/etc/sysctl.d/90-h28k-zram.conf` |
| `network.packet_steering` | 1 | 四核 A53 上把网卡软中断分摊到多核（ImmortalWrt 默认只对 x86/mt7621/bcm53xx 开） |
| `network.flow_offloading` | 1 | 软件快速路径，RK3528 上做 NAT 转发才跑得满千兆 |

注意：`flow_offloading=1` 和 SQM/QoS 流控冲突，以后要限速，在 LuCI「网络 → 防火墙」里关掉软件流量分载即可；
`system.zram_*` 改完 `/etc/init.d/zram restart` 生效，可 `zramctl` / `free -h` 核对。

## 网络向导（LuCI，仿 iStoreOS 三步流程）

刷好后 LuCI 里多出 **网络 → 网络向导**，流程和 iStoreOS 一样：**选联网方式 → 填参数 → 应用完成**。

第一步是三个大卡片（红 / 绿 / 蓝），点进去就是对应的参数页：

| 入口 | 做什么 | 底层命令 |
| --- | --- | --- |
| 宽带拨号连接（红） | WAN 口 PPPoE 拨号，本机做主路由，开 DHCP + NAT | `h28k-mode setup pppoe <账号> <密码> [本机IP]` |
| 连接现有路由器（绿） | WAN 口 DHCP 自动获取 IP，本机做主路由，开 DHCP + NAT | `h28k-mode setup dhcp [本机IP]` |
| 配置为旁路由（蓝） | LAN 静态、网关/DNS 指向主路由、关本机 DHCP/RA、禁 WAN、LAN 开 masq | `h28k-mode setup bypass <主路由IP> [本机IP]` |

参数页会预填当前 LAN IP，旁路由的主路由地址会用 `h28k-mode detect` 探测（优先取现有 LAN 网关，
其次取默认路由），探不到才回落到 `192.168.2.254`。应用后进完成页：显示本机地址、执行输出和下一步提示，
并提供「进入后台」/「再配置一次」。改过 LAN IP 的话，6 秒后自动跳到新地址。

旁路由模式下客户端要借道，需要把**主路由 DHCP 下发的网关和 DNS** 改成这台机器的 LAN IP；
或者只改需要走它的终端。主路由本身不用动。

> 为什么没直接装 iStoreOS 的 quickstart：它的 `quickstart` / `quickstart-netpolicy` / `luci-app-quickstart`
> 只有 KoolCenter 的预编译 ipk，源码不开，还绑着 iStoreOS 自己的 API。这里按同样的交互做了一个
> 纯 shell + LuCI JS 的实现，源码全部在 `package/luci-app-h28k-mode` 里，可审计、可改。

命令行同样可用（向导页面就是调这些）：

```sh
h28k-mode status
h28k-mode detect                 # 探测上级网关
h28k-mode setup bypass 192.168.2.254 192.168.2.1
h28k-mode setup dhcp 192.168.2.1
h28k-mode setup pppoe 宽带账号 宽带密码 192.168.2.1
h28k-mode router                 # 只恢复主路由默认（WAN DHCP）
h28k-mode lanip 192.168.1.2      # 只改 IP
h28k-mode dhcp off               # 只关 DHCP
```

典型旁路由接法（主路由同网段）：

1. 主路由（例如 `192.168.2.254`）保持拨号/上网不变；
2. H28K 用网线接到主路由的交换机侧，后台地址仍是 `192.168.2.1`；
3. 向导里选「配置为旁路由」，填主路由 IP，应用；
4. 把主路由 DHCP 下发的网关/DNS 改成 `192.168.2.1`，或只改需要走它的终端。

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

- `network.lan.netmask` 仍为 `255.255.255.0`，DHCP 池仍 `100–150`（`192.168.2.100–249`）
- `firewall` 的 `defaults.input=REJECT`、`defaults.forward=REJECT` 不变，只靠 zone 的 `forward=ACCEPT` 放行 LAN
- `dhcp.@dnsmasq[0].dns_redirect=1`：所有打到本机的 DNS 都会被导向 dnsmasq（旁路由下也一样，客户端自定义 DNS 会被接管）
- `flow_offloading` / `packet_steering` 由开机调优脚本设置，切模式不改

**已知边界**

- 旁路由的 `/24` 同网段校验只在 `setup bypass` 里做；掩码不是 `/24` 的场景请先用 `h28k-mode lanip` 配好 IP/掩码，再用 `h28k-mode bypass <IP>`。
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

- `adapt.py` 在 `v25.12.2` 干净源码树上执行通过，自检 9 项全 OK，重复执行全部跳过（幂等）。
- 调优脚本与 `h28k-mode` 装进目标后权限均为 755，`sh -n` 语法检查通过；调优脚本只对 `hinlink,h28k` 执行。
- `.config` 里 `CONFIG_PACKAGE_luci-app-commands=y` 被 defconfig 保留，用于承载“系统 → 自定义命令”的三个一键按钮。
- `make defconfig` 接受 `CONFIG_TARGET_rockchip_armv8_DEVICE_hinlink_h28k=y`，设备 profile 被正确识别。
- 内核 `prepare`（6.12.103 + ImmortalWrt 全部回移补丁）通过；H28K 设备树用与 `Image/BuildDTB` 相同的
  cpp + dtc 流程编译成功（`rk3528-hinlink-h28k.dtb`，仅 rk3528.dtsi 自带 warning），
  dtb 内 gmac `phy-mode = "rgmii-id"`、eMMC `mmc-hs200-1_8v`、ADC 按键、lan/wan/status 三灯均在。
- U-Boot 2025.10 上 `package/boot/uboot-rockchip/prepare` 应用通过（`hinlink-h28k-rk3528_defconfig` 已生成）。
  单独验证：`patch -p1 --dry-run` 干净应用，`make hinlink-h28k-rk3528_defconfig` 正常出 `.config`
  （RK3528 / rockchip,rk3528-hinlink-h28k / SDHCI / DWC_ETH_QOS / 1500000 波特率均正确）。
- `./build.sh --prepare-only`（复用已有源码树）整条流程跑通：克隆/复用 → 补丁 → feeds → `.config` → 设备校验。
- 未在本机跑完整 `make`（本机只有 2 核 3GB，全量编译要数小时），完整编译请走 GitHub Actions 或自己的多核机器。

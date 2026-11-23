#
# 网络向导：主路由 / 旁路由一键切换 + 网络参数配置（通用，任意 OpenWrt 设备可用）
#
# 独立 LuCI 应用（不依赖 feeds/luci 的 luci.mk），随 kit 一起编译。
# This is free software, licensed under the MIT License.
#

include $(TOPDIR)/rules.mk

PKG_NAME:=luci-app-netmode
PKG_VERSION:=1.0
PKG_RELEASE:=1
PKG_LICENSE:=MIT
PKG_MAINTAINER:=netmode kit

include $(INCLUDE_DIR)/package.mk

define Package/luci-app-netmode
  SECTION:=luci
  CATEGORY:=LuCI
  SUBMENU:=3. Applications
  TITLE:=网络向导（主路由/旁路由一键切换）
  DEPENDS:=+luci-base
  PKGARCH:=all
endef

define Package/luci-app-netmode/description
  通用网络向导页面：一键切换主路由/旁路由，直接改 LAN IP 与 DHCP。适用于任意 OpenWrt 设备。
endef

define Build/Compile
endef

define Package/luci-app-netmode/install
	$(INSTALL_DIR) $(1)/usr/share/luci/menu.d
	$(INSTALL_DIR) $(1)/usr/share/rpcd/acl.d
	$(INSTALL_DIR) $(1)/www/luci-static/resources/view/netmode
	$(CP) ./root/usr/share/luci/menu.d/luci-app-netmode.json $(1)/usr/share/luci/menu.d/
	$(CP) ./root/usr/share/rpcd/acl.d/luci-app-netmode.json $(1)/usr/share/rpcd/acl.d/
	$(CP) ./htdocs/luci-static/resources/view/netmode/guide.js $(1)/www/luci-static/resources/view/netmode/
endef

$(eval $(call BuildPackage,luci-app-netmode))

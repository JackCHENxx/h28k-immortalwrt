#
# H28K 网络向导：主路由 / 旁路由一键切换 + 网络参数配置
#
# 独立 LuCI 应用（不依赖 feeds/luci 的 luci.mk），随 kit 一起编译。
# This is free software, licensed under the MIT License.
#

include $(TOPDIR)/rules.mk

PKG_NAME:=luci-app-h28k-mode
PKG_VERSION:=1.0
PKG_RELEASE:=1
PKG_LICENSE:=MIT
PKG_MAINTAINER:=H28K kit

include $(INCLUDE_DIR)/package.mk

define Package/luci-app-h28k-mode
  SECTION:=luci
  CATEGORY:=LuCI
  SUBMENU:=3. Applications
  TITLE:=H28K 网络向导（主路由/旁路由一键切换）
  DEPENDS:=+luci-base
  PKGARCH:=all
endef

define Package/luci-app-h28k-mode/description
  给 HINLINK H28K 用的网络向导页面：一键切换主路由/旁路由，直接改 LAN IP 与 DHCP。
endef

define Build/Compile
endef

define Package/luci-app-h28k-mode/install
	$(INSTALL_DIR) $(1)/usr/share/luci/menu.d
	$(INSTALL_DIR) $(1)/usr/share/rpcd/acl.d
	$(INSTALL_DIR) $(1)/www/luci-static/resources/view/h28k_mode
	$(CP) ./root/usr/share/luci/menu.d/luci-app-h28k-mode.json $(1)/usr/share/luci/menu.d/
	$(CP) ./root/usr/share/rpcd/acl.d/luci-app-h28k-mode.json $(1)/usr/share/rpcd/acl.d/
	$(CP) ./htdocs/luci-static/resources/view/h28k_mode/guide.js $(1)/www/luci-static/resources/view/h28k_mode/
endef

$(eval $(call BuildPackage,luci-app-h28k-mode))

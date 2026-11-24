'use strict';

'require view';
'require fs';
'require uci';
'require ui';

var WGCTL = '/usr/bin/wgctl';

var CSS = [
	'.wg-page .wg-card{max-width:860px}',
	'.wg-page .wg-row{display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;margin:10px 0}',
	'.wg-page .wg-row .cbi-value{margin:0;flex:0 1 220px}',
	'.wg-page .wg-row .cbi-value-field{min-width:170px}',
	'.wg-page .wg-key{font-family:monospace;font-size:12px;word-break:break-all;background:#f6f8fa;',
	'border:1px solid #e3e8ee;border-radius:6px;padding:8px;margin:6px 0}',
	'.wg-page .wg-table{width:100%;border-collapse:collapse;margin:8px 0}',
	'.wg-page .wg-table th,.wg-page .wg-table td{border-bottom:1px solid #e3e8ee;padding:8px 6px;',
	'font-size:13px;text-align:left;vertical-align:top}',
	'.wg-page .wg-table td.mono{font-family:monospace;word-break:break-all}',
	'.wg-page .wg-note{background:#fff8e1;border-left:4px solid #f0b400;padding:10px 12px;',
	'border-radius:4px;margin:12px 0;font-size:13px;line-height:1.6}',
	'.wg-page .wg-out{background:#f6f8fa;border:1px solid #e3e8ee;border-radius:6px;padding:12px;',
	'margin:12px 0;white-space:pre-wrap;font-family:monospace;font-size:12px;line-height:1.55}',
	'.wg-page h3{margin-top:26px}'
].join('');

function run(args) {
	return fs.exec(WGCTL, args).then(function(res) {
		var out = ((res && res.stdout) || '').trim();
		if (res && typeof res.code === 'number' && res.code !== 0)
			throw new Error(((res && res.stderr) || '').trim() || out || ('wgctl 退出码 ' + res.code));
		return out;
	});
}

function notify(msg, type) {
	ui.addNotification(null, E('p', {}, msg), type || 'info');
}

function parseKV(text) {
	var out = {};
	(text || '').split(/\n/).forEach(function(line) {
		var i = line.indexOf('=');
		if (i > 0) out[line.slice(0, i)] = line.slice(i + 1);
	});
	return out;
}

function field(label, input, desc) {
	var kids = [ input ];
	if (desc) kids.push(E('div', { 'class': 'cbi-value-description' }, desc));
	return E('div', { 'class': 'cbi-value' }, [
		E('label', { 'class': 'cbi-value-title' }, label),
		E('div', { 'class': 'cbi-value-field' }, kids)
	]);
}

function textInput(value, placeholder, width) {
	return E('input', {
		'type': 'text', 'class': 'cbi-input-text', 'value': value || '',
		'placeholder': placeholder || '', 'style': 'width:' + (width || '16em')
	});
}

function checkBox(checked) {
	var box = E('input', { 'type': 'checkbox', 'class': 'cbi-input-checkbox' });
	if (checked) box.checked = true;
	return box;
}

function button(label, cls, fn) {
	return E('button', {
		'class': 'cbi-button ' + (cls || 'cbi-button-action'),
		'click': function() { return fn(); }
	}, label);
}

function reloadSoon() {
	window.setTimeout(function() { window.location.reload(); }, 1200);
}

return view.extend({
	load: function() {
		return Promise.all([
			uci.load('network'),
			uci.load('firewall'),
			run([ 'status' ]).catch(function(err) { return err.message || String(err); })
		]);
	},

	render: function(res) {
		this.st = parseKV(res[2]);
		this.peers = uci.sections('network', 'wireguard_wg0') || [];
		this.addr = this.st.address || '10.0.0.1/24';
		this.port = this.st.port || '51820';
		this.mtu = this.st.mtu || '1420';
		this.enabled = this.st.enabled == '1';
		this.out = '';

		var root = E('div', { 'class': 'cbi-map wg-page' });
		root.appendChild(E('style', {}, CSS));
		root.appendChild(E('h2', {}, _('WireGuard 设置')));
		root.appendChild(E('div', { 'class': 'cbi-map-descr' },
			_('服务端 wg0，默认 10.0.0.1/24、UDP 51820。客户端通过「生成客户端配置」加入；对端需要能访问本机 WAN 的 UDP 端口。')));

		root.appendChild(this.viewStatus());
		root.appendChild(this.viewServer());
		root.appendChild(this.viewPeers());
		root.appendChild(this.viewClient());

		return root;
	},

	viewStatus: function() {
		var up = this.st.up == '1';
		var pub = this.st.publickey || '';
		return E('div', { 'class': 'wg-note' }, [
			E('div', {}, _('运行状态：') + (up ? _('已启动') : _('未启动')) +
				_('；对端数：') + (this.st.peers || '0')),
			pub ? E('div', { 'class': 'wg-key' }, pub) : E('div', {}, _('尚未生成公钥'))
		]);
	},

	viewServer: function() {
		var self = this;
		var addr = textInput(self.addr, '10.0.0.1/24');
		var port = textInput(self.port, '51820', '8em');
		var mtu = textInput(self.mtu, '1420', '8em');
		var en = checkBox(self.enabled);

		var apply = function() {
			var a = (addr.value || '').trim(), p = (port.value || '').trim(), m = (mtu.value || '').trim();
			if (!/^\d{1,3}(\.\d{1,3}){3}\/\d{1,2}$/.test(a) || +a.split('/')[1] > 32) {
				notify(_('地址要写成 CIDR，例如 10.0.0.1/24'), 'error');
				return;
			}
			if (!/^\d+$/.test(p) || +p < 1 || +p > 65535) {
				notify(_('端口必须在 1–65535'), 'error');
				return;
			}
			if (!/^\d+$/.test(m) || +m < 1280 || +m > 1500) {
				notify(_('MTU 必须在 1280–1500'), 'error');
				return;
			}
			return run([ 'apply', '--address=' + a, '--port=' + p, '--mtu=' + m,
				'--enabled=' + (en.checked ? '1' : '0') ])
				.then(function(out) { notify(out || _('已保存'), 'info'); reloadSoon(); })
				.catch(function(err) { notify(err.message || String(err), 'error'); });
		};

		var regen = function() {
			if (!confirm(_('重新生成服务端私钥会让所有现有客户端立即失效，确定继续？'))) return;
			return run([ 'keygen' ])
				.then(function(out) { notify(out || _('已生成新密钥'), 'warning'); reloadSoon(); })
				.catch(function(err) { notify(err.message || String(err), 'error'); });
		};

		return E('div', { 'class': 'wg-card' }, [
			E('h3', {}, _('服务端参数')),
			E('div', { 'class': 'wg-row' }, [
				field(_('启用'), en),
				field(_('本机地址'), addr, _('默认 10.0.0.1/24')),
				field(_('UDP 端口'), port),
				field(_('MTU'), mtu)
			]),
			E('div', { 'class': 'wg-row' }, [
				button(_('保存并应用'), 'cbi-button-apply', apply),
				button(_('重新生成密钥'), 'cbi-button-reset', regen)
			]),
			E('div', { 'class': 'cbi-value-description' },
				_('保存后会重启 wg0（已有 VPN 连接会短暂中断）；端口变化会同步更新防火墙放行规则。'))
		]);
	},

	viewPeers: function() {
		var self = this;
		var rows = [
			E('tr', {}, [
				E('th', {}, _('名称')), E('th', {}, _('公钥')), E('th', {}, _('AllowedIPs')),
				E('th', {}, _('Endpoint')), E('th', {}, '')
			])
		];

		if (!self.peers.length) {
			rows.push(E('tr', {}, [ E('td', { 'colspan': 5 }, _('还没有对端')) ]));
		}

		self.peers.forEach(function(s) {
			var name = s['.name'] || '';
			var endpoint = uci.get('network', name, 'endpoint_host') || '';
			var eport = uci.get('network', name, 'endpoint_port') || '';
			if (endpoint && eport) endpoint += ':' + eport;

			var del = button(_('删除'), 'cbi-button-remove', function() {
				if (!confirm(_('删除对端 ') + name + _('？'))) return;
				return run([ 'peer-del', '--name=' + name.replace(/^peer_/, '') ])
					.then(function(out) { notify(out, 'info'); reloadSoon(); })
					.catch(function(err) { notify(err.message || String(err), 'error'); });
			});

			rows.push(E('tr', {}, [
				E('td', {}, name),
				E('td', { 'class': 'mono' }, uci.get('network', name, 'publickey') || ''),
				E('td', { 'class': 'mono' }, uci.get('network', name, 'allowedips') || ''),
				E('td', { 'class': 'mono' }, endpoint),
				E('td', {}, del)
			]));
		});

		var name = textInput('', 'peer1', '10em');
		var pub = textInput('', _('对方公钥'), '22em');
		var allowed = textInput('', '10.0.0.2/32', '12em');
		var keepalive = textInput('25', '25', '6em');
		var add = function() {
			var n = (name.value || '').trim(), p = (pub.value || '').trim(), a = (allowed.value || '').trim();
			if (!n || !p || !a) { notify(_('名称、公钥、AllowedIPs 都要填'), 'error'); return; }
			return run([ 'peer-add', '--name=' + n, '--pubkey=' + p,
				'--allowedips=' + a, '--keepalive=' + (keepalive.value || '') ])
				.then(function(out) { notify(out, 'info'); reloadSoon(); })
				.catch(function(err) { notify(err.message || String(err), 'error'); });
		};

		return E('div', { 'class': 'wg-card' }, [
			E('h3', {}, _('对端（已有客户端）')),
			E('table', { 'class': 'wg-table' }, rows),
			E('div', { 'class': 'wg-row' }, [
				field(_('名称'), name),
				field(_('公钥'), pub),
				field(_('AllowedIPs'), allowed),
				field(_('Keepalive'), keepalive)
			]),
			E('div', { 'class': 'wg-row' }, [
				button(_('添加对端'), 'cbi-button-add', add)
			]),
			E('div', { 'class': 'cbi-value-description' },
				_('对方已有密钥时用这里添加；要由本机生成客户端配置，用下面的「生成客户端配置」。'))
		]);
	},

	viewClient: function() {
		var self = this;
		var name = textInput('', 'phone', '10em');
		var ip = textInput('10.0.0.2', '10.0.0.2', '10em');
		var endpoint = textInput('', _('公网 IP 或域名'), '16em');
		var port = textInput(self.port || '51820', '51820', '7em');
		var dns = textInput('10.0.0.1', '10.0.0.1', '10em');
		var out = E('div', { 'class': 'wg-out', 'style': 'display:none' });

		var gen = function() {
			var n = (name.value || '').trim(), a = (ip.value || '').trim();
			var e = (endpoint.value || '').trim(), p = (port.value || '').trim();
			var d = (dns.value || '').trim();
			if (!n || !/^\d{1,3}(\.\d{1,3}){3}$/.test(a) || !e) {
				notify(_('客户端名称、地址、服务端地址都要填'), 'error');
				return;
			}
			return run([ 'client-conf', '--name=' + n, '--ip=' + a, '--endpoint=' + e,
				'--port=' + p, '--dns=' + d ])
				.then(function(text) {
					out.style.display = '';
					out.textContent = text;
					notify(_('已生成客户端配置，复制下面内容到客户端'), 'info');
				})
				.catch(function(err) { notify(err.message || String(err), 'error'); });
		};

		return E('div', { 'class': 'wg-card' }, [
			E('h3', {}, _('生成客户端配置')),
			E('div', { 'class': 'wg-row' }, [
				field(_('名称'), name),
				field(_('客户端地址'), ip),
				field(_('服务端地址'), endpoint),
				field(_('端口'), port),
				field(_('DNS'), dns)
			]),
			E('div', { 'class': 'wg-row' }, [
				button(_('生成配置'), 'cbi-button-add', gen)
			]),
			out,
			E('div', { 'class': 'cbi-value-description' },
				_('会同时把客户端加入对端列表；配置里的 AllowedIPs 为全局代理（0.0.0.0/0）。只访问内网时改客户端配置的 AllowedIPs 即可。'))
		]);
	}
});

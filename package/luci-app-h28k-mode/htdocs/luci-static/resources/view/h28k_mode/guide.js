'use strict';

'require view';
'require fs';
'require uci';
'require ui';

var SCRIPT = '/usr/bin/h28k-mode';

var CSS = [
	'.h28k-wizard .h28k-grid{display:flex;gap:16px;flex-wrap:wrap;margin:18px 0}',
	'.h28k-card{flex:1 1 210px;min-width:200px;border-radius:10px;padding:22px 18px;color:#fff;cursor:pointer;',
	'box-shadow:0 2px 8px rgba(0,0,0,.14);transition:transform .15s ease}',
	'.h28k-card:hover{transform:translateY(-2px)}',
	'.h28k-card h3{margin:0 0 8px;color:#fff;font-size:17px;font-weight:600}',
	'.h28k-card p{margin:0;color:#fff;opacity:.92;font-size:13px;line-height:1.55}',
	'.h28k-red{background:#e15b64}.h28k-green{background:#37b37a}.h28k-blue{background:#2f80ed}',
	'.h28k-steps{display:flex;gap:8px;margin:10px 0 22px;font-size:13px;flex-wrap:wrap}',
	'.h28k-step{padding:4px 12px;border-radius:14px;background:#eceff3;color:#66707d}',
	'.h28k-step.on{background:#2f80ed;color:#fff}',
	'.h28k-note{background:#fff8e1;border-left:4px solid #f0b400;padding:10px 12px;border-radius:4px;',
	'margin:14px 0;font-size:13px;line-height:1.6}',
	'.h28k-done{text-align:center;padding:24px 0}',
	'.h28k-ok{font-size:46px;line-height:1;color:#37b37a;margin-bottom:10px}',
	'.h28k-pre{background:#f6f8fa;border:1px solid #e3e8ee;border-radius:6px;padding:10px;',
	'margin:14px 0;white-space:pre-wrap;font-size:13px;line-height:1.6;text-align:left}',
	'.h28k-actions{display:flex;gap:10px;margin-top:18px;flex-wrap:wrap}'
].join('');

var CARDS = [
	{ kind: 'pppoe', cls: 'h28k-red', title: '宽带拨号连接',
	  desc: '用宽带账号密码拨号，本机做主路由（NAT + DHCP）' },
	{ kind: 'dhcp', cls: 'h28k-green', title: '连接现有路由器',
	  desc: 'WAN 口自动获取 IP，本机做主路由（NAT + DHCP）' },
	{ kind: 'bypass', cls: 'h28k-blue', title: '配置为旁路由',
	  desc: '网关与 DNS 指向主路由，本机只做网关、不发 DHCP' }
];

function run(args) {
	return fs.exec(SCRIPT, args).then(function(res) {
		return ((res && res.stdout) || '').trim();
	});
}

function ipv4ok(s) {
	var m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(s || '');
	return !!(m && [ m[1], m[2], m[3], m[4] ].every(function(x) {
		return +x >= 0 && +x <= 255;
	}));
}

function notify(msg, type) {
	ui.addNotification(null, E('p', {}, msg), type || 'info');
}

function field(label, input, desc) {
	var kids = [ input ];

	if (desc)
		kids.push(E('div', { 'class': 'cbi-value-description' }, desc));

	return E('div', { 'class': 'cbi-value' }, [
		E('label', { 'class': 'cbi-value-title' }, label),
		E('div', { 'class': 'cbi-value-field' }, kids)
	]);
}

function textInput(value, placeholder) {
	return E('input', {
		'type': 'text', 'class': 'cbi-input-text', 'value': value || '',
		'placeholder': placeholder || '', 'style': 'width:16em'
	});
}

return view.extend({
	load: function() {
		return Promise.all([
			uci.load('h28k'),
			uci.load('network'),
			uci.load('dhcp'),
			run([ 'status' ]).catch(function(err) { return err.message || String(err); }),
			run([ 'detect' ]).catch(function() { return ''; })
		]);
	},

	render: function(res) {
		this.status = res[3] || '';
		this.detect = (res[4] || '').trim();
		this.mode = uci.get('h28k', 'mode', 'mode') || 'router';
		this.upstream = uci.get('h28k', 'mode', 'upstream') || this.detect || '192.168.2.254';
		this.lanip = uci.get('network', 'lan', 'ipaddr') || '192.168.2.1';
		this.lastOut = '';

		var root = E('div', { 'class': 'cbi-map h28k-wizard' });
		this.root = root;
		this.paint('welcome');

		return root;
	},

	paint: function(step, kind) {
		var root = this.root;

		while (root.firstChild)
			root.removeChild(root.firstChild);

		root.appendChild(E('style', {}, CSS));

		if (step == 'welcome') {
			root.appendChild(this.viewWelcome());
		} else if (step == 'params') {
			root.appendChild(this.viewParams(kind));
		} else {
			root.appendChild(this.viewDone(kind));
		}
	},

	stepsBar: function(active) {
		var names = [ '1 选择联网方式', '2 填写参数', '3 完成' ];
		var bar = E('div', { 'class': 'h28k-steps' });

		for (var i = 0; i < names.length; i++)
			bar.appendChild(E('span', {
				'class': 'h28k-step' + (i + 1 == active ? ' on' : '')
			}, _(names[i])));

		return bar;
	},

	viewWelcome: function() {
		var self = this;
		var grid = E('div', { 'class': 'h28k-grid' });

		CARDS.forEach(function(c) {
			grid.appendChild(E('div', {
				'class': 'h28k-card ' + c.cls,
				'click': function() { self.paint('params', c.kind); }
			}, [
				E('h3', {}, _(c.title)),
				E('p', {}, _(c.desc))
			]));
		});

		return E('div', {}, [
			E('h2', {}, _('欢迎使用网络配置向导')),
			E('div', { 'class': 'cbi-map-descr' },
				_('选择一种联网方式开始。当前：') +
				(self.mode == 'bypass' ? _('旁路由') : _('主路由')) +
				'，LAN ' + self.lanip),
			grid,
			E('div', { 'class': 'h28k-note' },
				_('不确定选哪个：光猫要拨号就用「宽带拨号」；已有主路由、这台当二级路由用「连接现有路由器」；想让这台专门做网关/科学上网、由主路由发 DHCP，就用「配置为旁路由」。')),
			E('h3', {}, _('当前状态')),
			E('div', { 'class': 'h28k-pre' }, self.status)
		]);
	},

	viewParams: function(kind) {
		var self = this;
		var body = [], argsHint;

		if (kind == 'bypass') {
			var upInput = textInput(self.upstream, '192.168.2.254');
			var ipInput = textInput(self.lanip, '192.168.2.1');

			body.push(field(_('主路由地址'), upInput,
				_('主路由的 LAN IP。旁路由模式下，本机 LAN 网关与 DNS 都指向它。')));
			body.push(field(_('本机地址'), ipInput,
				_('要和主路由同网段，且不要和主路由/其它设备冲突。')));

			argsHint = _('应用后本机 DHCP 会关闭；请在主路由的 DHCP 设置里，把下发的网关和 DNS 改成这台机器的地址。');
			self._apply = function() {
				var up = (upInput.value || '').trim(), ip = (ipInput.value || '').trim();

				if (!ipv4ok(up)) { notify(_('主路由地址不是合法的 IPv4'), 'error'); return; }
				if (!ipv4ok(ip)) { notify(_('本机地址不是合法的 IPv4'), 'error'); return; }
				if (!confirm(_('将把本机配为旁路由（网关/DNS → ') + up + _('），继续？'))) return;

				return self.apply([ 'setup', 'bypass', up, ip ], kind, ip != self.lanip);
			};
		} else if (kind == 'dhcp') {
			var dIp = textInput(self.lanip, '192.168.2.1');

			body.push(field(_('本机地址'), dIp,
				_('本机 LAN 地址，默认 192.168.2.1。')));
			argsHint = _('WAN 口（eth1）会从上级路由自动获取 IP，本机开 DHCP 与 NAT。上级路由的 LAN 网段不要和本机地址冲突。');
			self._apply = function() {
				var ip = (dIp.value || '').trim();

				if (!ipv4ok(ip)) { notify(_('本机地址不是合法的 IPv4'), 'error'); return; }
				if (!confirm(_('将本机设为主路由（WAN 自动获取 + DHCP/NAT），继续？'))) return;

				return self.apply([ 'setup', 'dhcp', ip ], kind, ip != self.lanip);
			};
		} else {
			var userInput = textInput('', _('宽带账号'));
			var passInput = E('input', {
				'type': 'password', 'class': 'cbi-input-text',
				'placeholder': _('宽带密码'), 'style': 'width:16em'
			});
			var pIp = textInput(self.lanip, '192.168.2.1');

			body.push(field(_('宽带账号'), userInput));
			body.push(field(_('宽带密码'), passInput));
			body.push(field(_('本机地址'), pIp,
				_('本机 LAN 地址，默认 192.168.2.1。')));
			argsHint = _('光猫桥接时选这个：WAN 口（eth1）用 PPPoE 拨号，本机开 DHCP 与 NAT。');
			self._apply = function() {
				var u = (userInput.value || '').trim(), p = passInput.value || '';
				var ip = (pIp.value || '').trim();

				if (!u || !p) { notify(_('宽带账号和密码都要填'), 'error'); return; }
				if (!ipv4ok(ip)) { notify(_('本机地址不是合法的 IPv4'), 'error'); return; }
				if (!confirm(_('将用账号 ') + u + _(' 拨号，继续？'))) return;

				return self.apply([ 'setup', 'pppoe', u, p, ip ], kind, ip != self.lanip);
			};
		}

		var btnApply = E('button', {
			'class': 'cbi-button cbi-button-apply',
			'click': ui.createHandlerFn(self, function() { return self._apply(); })
		}, _('应用并继续'));

		var btnBack = E('button', {
			'class': 'cbi-button cbi-button-reset',
			'click': function() { self.paint('welcome'); }
		}, _('上一步'));

		return E('div', {}, [
			E('h2', {}, _('网络向导')),
			self.stepsBar(2),
			E('h3', {}, _(CARDS.filter(function(c) { return c.kind == kind; })[0].title)),
			E('div', { 'class': 'cbi-section' }, [
				E('div', { 'class': 'cbi-section-node' }, body)
			]),
			E('div', { 'class': 'h28k-note' }, argsHint),
			E('div', { 'class': 'h28k-actions' }, [ btnApply, btnBack ])
		]);
	},

	apply: function(args, kind, ipChanged) {
		var self = this;
		var btnLabel = _('正在应用，网络会短暂中断…');

		notify(btnLabel);

		return run(args).then(function(out) {
			self.lastOut = out || _('已应用');
			self.lanip = args[args.length - 1] || self.lanip;
			self.mode = (kind == 'bypass') ? 'bypass' : 'router';
			self.paint('done', kind);

			if (ipChanged) {
				notify(_('本机地址已改变，请用新地址重新访问'), 'warning');
				window.setTimeout(function() {
					location.href = 'http://' + self.lanip + '/';
				}, 6000);
			}
		}).catch(function(err) {
			notify(_('应用失败：') + (err.message || err), 'error');
		});
	},

	viewDone: function(kind) {
		var self = this;
		var title = (kind == 'bypass') ? _('已切换为旁路由') : _('已配置为主路由');
		var next;

		if (kind == 'bypass') {
			next = _('下一步：在主路由的 DHCP 设置里，把下发的「网关」和「DNS」改成 ') + self.lanip +
				_('（或只改需要走这台设备的终端）。之后终端会自动经本机出海。');
		} else {
			next = _('下一步：把光猫/上级设备的网线接在 WAN 口（eth1，RTL8111H 那颗），终端连 LAN 口即可上网。');
		}

		var btnHome = E('a', {
			'class': 'cbi-button cbi-button-apply',
			'href': '/'
		}, _('进入后台'));

		var btnAgain = E('button', {
			'class': 'cbi-button cbi-button-reset',
			'click': function() { self.paint('welcome'); }
		}, _('再配置一次'));

		return E('div', {}, [
			E('h2', {}, _('网络向导')),
			self.stepsBar(3),
			E('div', { 'class': 'h28k-done' }, [
				E('div', { 'class': 'h28k-ok' }, '✓'),
				E('h3', {}, title),
				E('div', { 'class': 'cbi-map-descr' }, _('本机地址：') + self.lanip)
			]),
			E('div', { 'class': 'h28k-pre' }, self.lastOut),
			E('div', { 'class': 'h28k-note' }, next),
			E('div', { 'class': 'h28k-actions' }, [ btnHome, btnAgain ])
		]);
	}
});

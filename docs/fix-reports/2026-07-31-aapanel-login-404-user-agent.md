# 修复复盘：宝塔安全入口因自定义 User-Agent 返回 404（2026-07-31）

## 摘要

访问宝塔安全入口 `https://admin.roguelife.de/30af1d83` 时出现 nginx `404 Not Found`。排查确认 DNS、Cloudflare、外层 nginx、宝塔进程、监听端口和安全入口均正常。真正原因是客户端把 `User-Agent` 修改成了长度不足 24 个字符的自定义值，触发 aaPanel 8.0.5 的爬虫防护。宝塔为避免暴露管理入口，主动以 404 响应拒绝该请求。

恢复浏览器标准 User-Agent 后，公网入口和登录页静态资源均返回 HTTP 200。服务器无需修改。

## 影响

- 受影响入口：`admin.roguelife.de` 的宝塔登录页面。
- 受影响客户端：使用短自定义 User-Agent 的浏览器、脚本或代理工具。
- 未受影响部分：DNS、Cloudflare、TLS、nginx 反向代理、宝塔后台进程和其他站点服务。
- 数据影响：无数据丢失，无配置损坏。

## 现象

公网访问返回：

```http
HTTP/2 404
server: cloudflare
content-type: text/html
```

响应正文为源站 nginx 风格的 404：

```html
<html>
<head><title>404 Not Found</title></head>
<body>
<center><h1>404 Not Found</h1></center>
<hr><center>nginx</center>
</body>
</html>
```

Cloudflare 状态为动态回源，因此不是 CDN 缓存中的旧 404。

## 排查过程

### 1. 检查 DNS 与公网响应

域名可正常解析到 Cloudflare IPv4/IPv6 地址，HTTPS 握手成功。响应头显示请求经过 Cloudflare，但 404 正文来自回源服务。

```bash
getent ahosts admin.roguelife.de
curl -k -D - https://admin.roguelife.de/30af1d83
```

结论：排除 DNS 失效、证书错误和 Cloudflare 无法回源。

### 2. 检查宝塔进程和监听端口

服务器上的宝塔相关进程均存在：

- `BT-Panel`
- `BT-Task`
- 宝塔内置 webserver

面板实际监听端口为 `41993`，Unix socket `/tmp/panel.sock` 也由当前 `BT-Panel` 进程持有。

```bash
ss -lntp
ps -ef | rg 'BT-Panel|BT-Task|webserver'
ss -xlpn | rg 'panel.sock'
```

结论：排除面板进程退出、端口未监听和 socket 残留。

### 3. 核对安全入口

宝塔配置中的端口和安全入口与访问地址一致：

```bash
tr -d '\n' < /www/server/panel/data/port.pl
tr -d '\n' < /www/server/panel/data/admin_path.pl
```

对应结果：

```text
41993
/30af1d83
```

结论：排除访问了旧安全入口或错误端口。

### 4. 绕过外层代理直连面板

直接请求本机面板端口和 Unix socket 时，短 User-Agent 仍返回同样的 404：

```bash
curl http://127.0.0.1:41993/30af1d83
curl --unix-socket /tmp/panel.sock http://localhost/30af1d83
```

这说明故障发生在宝塔应用内部，而不是 Cloudflare 或外层 nginx。

### 5. 检查宝塔请求日志

请求日志记录到安全入口，但短自定义 User-Agent 对应的状态均为 404；标准 Chrome User-Agent 对应状态为 200。

```bash
rg '"/30af1d83' /www/server/panel/logs/request/2026-07-31.json
```

日志对比结果：

| 请求类型 | User-Agent 特征 | 状态码 | 响应大小 |
|---|---|---:|---:|
| 自定义客户端 | 长度不足 24 | 404 | 138 B |
| curl | 包含 `curl` 且长度不足 | 404 | 138 B |
| 标准 Chrome | 正常浏览器标识 | 200 | 完整登录页 |

### 6. 定位应用代码

登录路由在渲染页面前执行爬虫判断：

```python
if public.is_spider():
    return abort(404)
```

`public.is_spider()` 最终调用 `panelDefense.bot_safe().spider()`。该实现会拒绝长度异常的 User-Agent：

```python
ua_len = len(user_agent)
if ua_len < 24 or ua_len > 350:
    return False
```

上层对结果取反后认为请求是爬虫，最终主动返回 404。这是隐藏管理入口的防扫描行为，不是路由不存在。

## 根因

客户端或浏览器扩展覆盖了标准 User-Agent，设置成长度不足 24 个字符的自定义值。aaPanel 8.0.5 将其识别为异常脚本请求，并在登录路由中执行 `abort(404)`。

完整触发链为：

```text
短自定义 User-Agent
  → panelDefense.spider() 返回 False
  → public.is_spider() 返回 True
  → 登录路由 abort(404)
  → 宝塔内置 webserver 返回 nginx 风格 404
  → 外层 nginx 与 Cloudflare 原样转发
```

## 处理

本次未修改服务器代码和配置。客户端关闭 User-Agent 覆盖，恢复标准浏览器 User-Agent 后即可访问。

不建议直接删除宝塔的爬虫防护逻辑，因为：

- 会降低管理入口对扫描器的隐藏能力；
- 宝塔升级可能覆盖本地代码改动；
- 根因位于客户端请求标识，服务端路由本身正常。

如果业务确实必须使用自定义 User-Agent，应采用长度在 24 到 350 个字符之间、且不包含已知扫描器或脚本工具关键字的合法浏览器格式。

## 验证

使用标准 Chrome User-Agent 分别验证本机直连和公网入口：

```bash
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/138.0.0.0 Safari/537.36'

curl -A "$UA" -o /dev/null -w '%{http_code}\n' \
  http://127.0.0.1:41993/30af1d83

curl -k -A "$UA" -o /dev/null -w '%{http_code}\n' \
  https://admin.roguelife.de/30af1d83
```

两条请求均返回：

```text
200
```

同时验证登录页静态资源返回 200：

```bash
curl -k -A "$UA" -o /dev/null -w '%{http_code}\n' \
  https://admin.roguelife.de/static/vite/favicon.ico
```

nginx 配置语法检查也通过：

```bash
nginx -t
```

## 日志检索方式

检索指定安全入口最近的请求：

```bash
rg '"/30af1d83' /www/server/panel/logs/request/$(date +%F).json
```

对比 404 与 200 的 User-Agent：

```bash
rg '"/30af1d83' /www/server/panel/logs/request/$(date +%F).json \
  | rg ', (200|404),'
```

查看宝塔应用异常：

```bash
tail -n 200 /www/server/panel/logs/error.log
```

查看外层 nginx 错误日志：

```bash
tail -n 200 /var/log/nginx/error.log
```

## 遗留风险与建议

1. 自定义 User-Agent 工具若再次启用，问题会复现；建议记录浏览器扩展和代理规则的用途。
2. curl 健康检查默认会得到 404，不能直接以此判断面板不可用；健康检查应使用明确的浏览器 User-Agent，或改为检查进程、端口和 socket。
3. 宝塔升级后防爬虫规则可能变化，复现时应重新检查 `panelDefense.py` 和登录路由。
4. 当前反向代理链中的面板请求日志主要显示本机代理地址。后续如需基于真实客户端 IP 做审计，应单独评估并修正可信代理与转发头配置，避免在未建立可信代理边界时直接信任外部头部。

## 结论

本次 404 并非基础设施故障，而是 aaPanel 对异常短 User-Agent 的预期防护响应。恢复标准浏览器 User-Agent 后服务立即正常，未进行服务器端变更。

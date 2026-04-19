# 阿里云上线指南

这份文档按 Ubuntu 22.04 的阿里云 ECS 编写，是当前项目最稳妥的一条上线路径：

- 前端页面继续保持现有交互；
- 服务端只读取仓库里的本地快照数据；
- 线上不再访问第三方股票接口；
- 仓库和服务器都不需要保留你的私密 API Key。

## 0. 先做一件最重要的事

仓库里之前存在过明文 `config.json` 和 `api_key`。即使当前版本已经删除，只要它曾经进入过 Git 历史，就默认视为已经泄露。

你现在应该立即：

1. 去对应模型服务平台把旧 key 作废。
2. 重新生成一个新 key。
3. 新 key 不要再提交到 GitHub。

如果后面你还要继续跑抽取脚本，再在本地手动创建一个不入库的 `config.json` 即可。

## 1. 域名和服务器准备

你需要确认这 4 件事：

1. 你已经有一台阿里云 ECS，系统推荐 `Ubuntu 22.04`。
2. 你有一个已经备案并能正常解析的域名。
3. 阿里云安全组已经放行端口：`22`、`80`、`443`。
4. 域名已经添加 `A` 记录指向 ECS 公网 IP。

建议 DNS 这样配：

- `@` -> 你的服务器公网 IP
- `www` -> 你的服务器公网 IP

等待解析生效后再继续。

## 2. 本地先生成上线快照

项目已经新增了快照脚本：

```bash
python3 scripts/build_deploy_snapshot.py
```

如果你想强制重新抓取一次所有股票历史数据：

```bash
python3 scripts/build_deploy_snapshot.py --force-refresh
```

执行成功后，重点会生成这些文件：

- `deploy_snapshot/current/index/*.json`
- `deploy_snapshot/current/stock_detail/*.json`
- `deploy_snapshot/current/stock_ohlc/*.json`
- `deploy_snapshot/current/manifest.json`

上线后页面只会读取这些本地快照，不再实时请求第三方股票接口。

你可以用下面命令确认是否全部成功：

```bash
python3 - <<'PY'
import json
from pathlib import Path
manifest = json.loads(Path("deploy_snapshot/current/manifest.json").read_text())
print("success:", manifest["success_count"])
print("failed:", manifest["failure_count"])
if manifest["failed"]:
    print(manifest["failed"][:10])
PY
```

`failure_count` 不一定必须是 `0`。现在脚本会为失败股票写入空快照占位，页面仍可正常打开，只是这只股票会显示“暂无快照行情数据”。

## 3. 上传代码到 GitHub

建议所有快照文件一起提交，这样服务器上就不需要再重新拉股票数据。

## 4. 登录阿里云服务器

在你自己的电脑终端执行：

```bash
ssh root@你的服务器IP
```

如果你使用的是普通用户，比如 `ubuntu`：

```bash
ssh ubuntu@你的服务器IP
```

## 5. 安装运行环境

在服务器执行：

```bash
apt update
apt install -y python3 python3-venv python3-pip git nginx
```

创建部署目录：

```bash
mkdir -p /var/www
cd /var/www
```

拉取项目：

```bash
git clone https://github.com/flyinthesky1020/duanyongping.git
cd duanyongping
```

创建虚拟环境并安装依赖：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 6. 在服务器本机先启动测试

先确认服务能跑起来：

```bash
source /var/www/duanyongping/.venv/bin/activate
gunicorn -w 2 -b 127.0.0.1:8000 app:app
```

看到没有报错后，打开另一个 SSH 窗口执行：

```bash
curl http://127.0.0.1:8000
```

如果返回 HTML，说明程序本身没问题。

然后按 `Ctrl + C` 停掉临时进程。

## 7. 配置 systemd 开机自启

把项目里的服务模板复制到系统目录：

```bash
cp /var/www/duanyongping/deploy/duanyongping.service /etc/systemd/system/duanyongping.service
```

如果你的登录用户不是 `www-data`，先编辑一下：

```bash
sed -n '1,120p' /etc/systemd/system/duanyongping.service
```

默认模板里这些值是：

- `User=www-data`
- `Group=www-data`
- `WorkingDirectory=/var/www/duanyongping`

如果目录不同，请用 `nano` 改掉：

```bash
nano /etc/systemd/system/duanyongping.service
```

创建运行用户目录权限：

```bash
chown -R www-data:www-data /var/www/duanyongping
```

启动服务：

```bash
systemctl daemon-reload
systemctl enable duanyongping
systemctl start duanyongping
systemctl status duanyongping
```

如果服务失败，查看日志：

```bash
journalctl -u duanyongping -n 100 --no-pager
```

## 8. 配置 Nginx 域名反向代理

复制模板：

```bash
cp /var/www/duanyongping/deploy/nginx.duanyongping.conf /etc/nginx/sites-available/duanyongping
```

编辑域名：

```bash
nano /etc/nginx/sites-available/duanyongping
```

把这行：

```nginx
server_name your-domain.com www.your-domain.com;
```

改成你的真实域名，例如：

```nginx
server_name dyp.yourdomain.com www.dyp.yourdomain.com;
```

启用站点：

```bash
ln -s /etc/nginx/sites-available/duanyongping /etc/nginx/sites-enabled/duanyongping
nginx -t
systemctl restart nginx
```

现在先访问：

```text
http://你的域名
```

能打开就说明 HTTP 已经通了。

## 9. 配 HTTPS 证书

安装 certbot：

```bash
apt install -y certbot python3-certbot-nginx
```

自动申请并配置证书：

```bash
certbot --nginx -d 你的域名 -d www.你的域名
```

成功后测试自动续期：

```bash
certbot renew --dry-run
```

## 10. 上线后隐私检查

上线后请做下面这些检查：

1. 浏览器打开网页，功能是否正常。
2. 点开几个股票详情，确认 K 线能加载。
3. 在服务器执行下面命令，确认项目目录里没有 `config.json`：

```bash
find /var/www/duanyongping -name 'config.json'
```

4. 确认网页请求没有访问第三方股票接口。

可以在浏览器开发者工具 Network 里看，正常情况下应只请求你自己域名下的页面、静态资源和 API。

## 11. 以后怎么更新网站

以后你只要按这个顺序：

```bash
cd /你的本地项目目录
python3 scripts/build_deploy_snapshot.py --force-refresh
git add .
git commit -m "refresh deploy snapshot"
git push
```

然后登录服务器：

```bash
cd /var/www/duanyongping
git pull
systemctl restart duanyongping
```

就更新完成了。

## 12. 如果你完全不熟服务器，最推荐的实际执行顺序

你只需要按下面做，不要跳步：

1. 本地执行 `python3 scripts/build_deploy_snapshot.py --force-refresh`
2. 检查 `deploy_snapshot/current/manifest.json`
3. 提交并推送代码到 GitHub
4. SSH 登录阿里云服务器
5. 安装 `python3-venv git nginx`
6. `git clone` 项目到 `/var/www/duanyongping`
7. 建 `.venv` 并 `pip install -r requirements.txt`
8. 本机先用 `gunicorn -w 2 -b 127.0.0.1:8000 app:app` 测试
9. 配 `systemd`
10. 配 `nginx`
11. 配 `https`
12. 用你的域名实际打开并检查页面

如果你愿意，下一步我可以继续直接帮你把这份文档再收敛成一份“你只要复制粘贴命令”的极简版本。

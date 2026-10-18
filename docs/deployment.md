# 阿里云 Ubuntu 部署与维护

本文面向 Ubuntu 26.04 64 位、已安装 Nginx 的单服务器环境。命令中的 `blog.example.com`、服务器地址和密码必须替换为实际值。以下步骤尚未在你的阿里云服务器执行。

## 1. 上线前核实

在阿里云控制台确认实例地域、CPU、内存、磁盘和公网 IP；服务器执行：

```bash
cat /etc/os-release
free -h
df -h
python3 --version
sudo nginx -T
sudo systemctl status nginx
```

先备份现有 Nginx 配置。新增独立站点配置，不覆盖其他站点。确认没有重复的 `server_name`。

内地服务器使用域名公开网站前，按阿里云要求完成 ICP 备案；香港与海外地域以对应规则为准。域名未就绪时，通过 SSH 隧道进行私有测试，不对公网开放开发服务器或管理后台。

安全组开放 TCP 80/443；SSH 22 限定自己的管理来源。若使用 UFW，先保证 SSH 放行，再启用防火墙。应用 8001 和 PostgreSQL 5432 不向公网放行。

## 2. 系统依赖与目录

```bash
sudo apt update
sudo apt install python3-venv python3-dev build-essential libpq-dev postgresql postgresql-client certbot
sudo adduser --system --group --home /srv/life-blog blog
sudo install -d -o blog -g www-data -m 0750 /srv/life-blog/app /srv/life-blog/static /var/lib/life-blog/media
sudo install -d -o blog -g blog -m 0700 /var/backups/life-blog
sudo chmod 0755 /srv/life-blog
sudo chmod 0755 /var/lib/life-blog
```

将项目代码（不要上传 `.venv`、`.env`、`db.sqlite3`、`media`、`.tools` 或 `artifacts`）放到 `/srv/life-blog/app`。推荐用 Git 发布；首次也可上传经过检查的源码压缩包。

```bash
sudo chown -R blog:www-data /srv/life-blog/app
sudo -u blog python3 -m venv /srv/life-blog/venv
sudo -u blog /srv/life-blog/venv/bin/pip install -r /srv/life-blog/app/requirements.txt
```

数据库只监听本机。创建普通数据库角色和数据库：

```bash
sudo -u postgres createuser --pwprompt blog
sudo -u postgres createdb --owner=blog blog
```

不要给生产角色 superuser 或 createdb 权限。验证时使用独立测试账号与测试库。

## 3. 生产环境变量

复制 `deploy/production.env.example` 到 `/etc/life-blog.env`，权限设为 `root:blog 0640`，用 `sudoedit` 填写实际值：

```bash
sudo install -o root -g blog -m 0640 /srv/life-blog/app/deploy/production.env.example /etc/life-blog.env
sudoedit /etc/life-blog.env
/srv/life-blog/venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(64))'
```

最后一个命令用于本机生成随机 SECRET_KEY，不要把输出提交到 Git。数据库密码若含特殊字符，填入 DATABASE_URL 前需 URL 编码。SITE_URL 必须为正式 HTTPS 域名；ALLOWED_HOSTS 不包含协议。使用兼容 shell 和 systemd 的 `KEY=value` 形式，不写 `export`；密码中不要保留未编码的 shell 特殊字符。

在应用账号的维护 shell 中加载环境，再执行管理命令：

```bash
sudo -u blog -g www-data bash
cd /srv/life-blog/app
set -a
. /etc/life-blog.env
set +a
/srv/life-blog/venv/bin/python manage.py migrate
/srv/life-blog/venv/bin/python manage.py collectstatic --noinput
/srv/life-blog/venv/bin/python manage.py createsuperuser
/srv/life-blog/venv/bin/python manage.py check --deploy
exit
```

生产运行不使用 `runserver`。上传文件目录属于应用数据，代码更新不得覆盖。Nginx 的 `www-data` 组必须能读取媒体目录及其父目录。服务的 UMask=0027 保持新文件对该组可读。

## 4. HTTPS 与 Nginx

完成备案（适用时）及域名 A 记录解析后：

```bash
sudo install -d -m 0755 /var/www/letsencrypt
sudo cp /srv/life-blog/app/deploy/nginx-bootstrap.conf /etc/nginx/sites-available/life-blog
sudoedit /etc/nginx/sites-available/life-blog
sudo ln -s /etc/nginx/sites-available/life-blog /etc/nginx/sites-enabled/life-blog
sudo nginx -t
sudo systemctl reload nginx
sudo certbot certonly --webroot -w /var/www/letsencrypt -d blog.example.com
```

在编辑步骤替换域名。已存在的同名符号链接无需重建。首次证书申请前只响应 ACME 校验，其他请求返回 503。

拿到证书后安装正式配置：

```bash
sudo cp /srv/life-blog/app/deploy/nginx-proxy.conf /etc/nginx/snippets/life-blog-proxy.conf
sudo cp /srv/life-blog/app/deploy/nginx.conf /etc/nginx/sites-available/life-blog
sudoedit /etc/nginx/sites-available/life-blog
sudo nginx -t
sudo systemctl reload nginx
```

正式配置中同步替换域名和证书路径。Nginx 内部路径 `/_protected_media/` 必须保留 `internal`：匿名用户不能绕过 Django 直接请求图片。不要为上传目录添加公开 alias，也不要开启代理缓存；撤回要求下次请求立即重新检查权限。

配置续期成功后重载 Nginx：

```bash
sudo install -d /etc/letsencrypt/renewal-hooks/deploy
printf '#!/bin/sh\n/usr/sbin/nginx -t && /usr/bin/systemctl reload nginx\n' | sudo tee /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh >/dev/null
sudo chmod 0755 /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
sudo systemctl enable --now certbot.timer
sudo certbot renew --dry-run
```

应用要求通过 HTTPS 登录；默认启用安全 Cookie 与 HSTS。部署检查出现告警时先解决，不要直接忽略。

## 5. 启动与验收

```bash
sudo cp /srv/life-blog/app/deploy/life-blog.service /etc/systemd/system/
sudo cp /srv/life-blog/app/deploy/life-blog-backup.service /etc/systemd/system/
sudo cp /srv/life-blog/app/deploy/life-blog-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now life-blog
sudo systemctl enable --now life-blog-backup.timer
sudo systemctl status life-blog
curl -I https://blog.example.com/
```

验收：登录后台，保存草稿并传图；无痕窗口访问草稿和图片应为 404；发布后为 200；撤回后再次为 404。检查归档、标签、站点地图与手机页面。首次公开前在合适的维护时段重启服务器，确认 `life-blog`、Nginx、PostgreSQL 和备份 timer 自动恢复。

查看日志与状态：

```bash
sudo journalctl -u life-blog -n 100 --no-pager
sudo journalctl -u life-blog-backup -n 50 --no-pager
sudo systemctl list-timers life-blog-backup.timer
sudo tail -n 50 /var/log/nginx/life-blog.error.log
```

首版利用 systemd 状态、journal 与 Nginx 日志排查故障；暂未接入外部告警服务。

## 6. 备份与下载

备份每天北京时间 03:30 左右执行，同时保存 PostgreSQL 快照、所有图片和校验清单。图片文件不可变且数据库先备份，允许在线执行；清理旧图片或批量迁移文件前应停写并做完整备份。数据库备份不含角色密码；环境文件需单独安全保存。

手动备份和检查：

```bash
sudo systemctl start life-blog-backup
sudo ls -lh /var/backups/life-blog
# 替换为实际归档名
sudo -u blog /srv/life-blog/venv/bin/python /srv/life-blog/app/scripts/backup.py verify /var/backups/life-blog/life-blog-实际时间.zip
```

只有成功生成新归档后才清理超过 7 天的同名前缀 ZIP。压缩归档不加密，备份目录仅应用账号可读。

使用有 SSH 登录权限的维护账号下载：先在服务器将某个归档复制到该账号的私有目录，并设为该账号所有、0600 权限，再在本地 PowerShell 执行：

```powershell
scp 运维账号@服务器IP:/home/运维账号/私有目录/life-blog-实际时间.zip .\backups\
```

本地副本不受服务器 7 天清理策略影响。数据库和图片应至少保留一份异机副本。

## 7. 恢复演练与故障恢复

优先在隔离的新数据库、新媒体目录演练，验证后再用于生产。备份只支持同类数据库恢复，SQLite 归档不能直接恢复到 PostgreSQL。

1. 停止应用与备份 timer，保留一份当前完整备份；数据库恢复会替换目标中的内容。
2. 将原媒体目录移动到带日期的保留目录，创建一个空的新媒体目录，保持 blog:www-data 权限。
3. 在维护 shell 加载目标环境，执行校验和恢复。确认参数必须和 DATABASE_URL 中的目标数据库名完全一致：

```bash
/srv/life-blog/venv/bin/python scripts/backup.py verify /path/to/archive.zip
/srv/life-blog/venv/bin/python scripts/backup.py restore /path/to/archive.zip --confirm-restore blog
/srv/life-blog/venv/bin/python manage.py check
```

4. 使用与备份相匹配的代码版本；必要时审查后再执行迁移。
5. 检查文章数量、照片、管理员登录及草稿权限，成功后重启应用与 timer。恢复失败时保持停服，保留归档与旧数据继续处理。

SQLite 本地恢复的确认参数应为数据库文件的完整路径。恢复前关闭开发服务器。脚本会先验证归档、路径和全部 SHA-256，再开始数据库恢复；PostgreSQL 使用单事务恢复。图片复制失败时不会自动回滚数据库，需保持停服并从相同归档重试到空媒体目录。

可运行 `python scripts/postgres_smoke.py` 对临时 PostgreSQL 数据库进行迁移、上传图片、备份与恢复验证。只对专用测试连接运行，测试角色需要 CREATEDB，脚本创建并清理自己生成的随机数据库。

## 8. 更新与回退

在部署目录记录当前 Git 提交号，先执行备份并验证。拉取经过测试的提交，安装锁定依赖。存在数据库迁移时短暂停服，再运行 `migrate`、`collectstatic` 和 `check --deploy`；重启应用并检查首页、后台和图片。更新失败时检查日志，避免反复重启。

纯代码变更可切回前一已知版本；涉及数据库结构时不要盲目回退代码，按对应迁移的可逆性处理，必要时恢复更新前的数据库及图片备份。Git 不保存线上文章和照片。

## 参考

- [Django 部署检查](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/)
- [阿里云服务器地域与备案](https://help.aliyun.com/zh/icp-filing/basic-icp-service/user-guide/icp-filing-server-access-information-check)

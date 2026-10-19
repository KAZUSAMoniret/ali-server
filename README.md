
Django 5.2 + Markdown 写作后台。手机与电脑均可阅读；草稿及草稿图片仅管理员可见。

## 本地运行（Windows PowerShell）

需要 Python 3.12 或其他 Django 5.2 支持的 Python 版本。本项目已准备独立 `.venv`，当前电脑可以从安装依赖之后的步骤开始。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

打开 <http://127.0.0.1:8000/>，后台为 <http://127.0.0.1:8000/admin/>。没有预置管理员密码；使用 `createsuperuser` 自己设置账号。

可选：`python manage.py seed_demo` 导入四篇演示文章，重复运行不会覆盖已有文章，生产环境禁止运行。本地首次交付已导入演示内容；服务器新数据库不会包含它们。

如果没有系统 Python，当前电脑也可以使用 Codex 提供的 Python 创建虚拟环境；已有 `.venv` 时直接使用上面的完整路径即可。虚拟环境不可复制到 Linux，服务器需要重新创建。

## 写作流程

1. 登录后台，新增文章，填写标题、摘要和 Markdown 正文，以“草稿”保存。
2. 再次编辑，使用正文下方“写作工具”上传图片，系统自动插入 Markdown 图片地址。
3. 在“封面”下拉框中选择本篇文章的图片；标签可以通过旁边的添加按钮创建。
4. “预览当前 Markdown”显示未保存正文；“打开已保存文章预览”展示完整页面，但仅含上次保存内容。
5. 状态改为“已发布”并保存，访客立即可读；改回“草稿”并保存即可撤回。
6. 在“站点设置”维护名称、简介、关于页（Markdown）和备案号。联系方式可以自行写进关于页。

文章链接在第一次保存时自动生成；编辑标题不会修改链接。首次发布时间在重新发布时保留。正文图片支持 JPEG、PNG、WebP，每张上限 10 MB / 4000 万像素；处理为最长边不超过 2560 像素的 WebP，移除 EXIF，动画只保留首帧。

本地上传图片保存在 `media/`，数据库为 `db.sqlite3`，均不进入 Git。上传图片通过权限检查后的 `/photos/<UUID>/` 提供，不能直接访问 `media/`。已经被访客下载的内容无法通过撤回远程删除。

## 开发与验证

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
node --check static/blog/editor.js
```

生产数据库测试：设置临时测试库的 `DATABASE_URL` 后执行相同迁移和测试。测试账号需有创建测试数据库的权限，不能对线上数据执行验证脚本。GitHub Actions 同时验证 SQLite 与 PostgreSQL。

主要结构：

- `config/`：环境配置、URL 和 WSGI 入口。
- `blog/`：模型、权限、后台、Markdown 与图片处理、迁移和测试。
- `templates/`、`static/blog/`：前台页面与后台写作工具，所有资源本地提供。
- `deploy/`、`scripts/`：Ubuntu 配置、备份恢复工具。
- [部署与维护说明](docs/deployment.md)。

依赖在 `requirements.txt` 中完整锁定，顶层依赖记录于 `requirements.in`。更新依赖后重新运行测试并更新锁定文件。

## 本地备份

```powershell
.\.venv\Scripts\python.exe scripts/backup.py backup --output backups
.\.venv\Scripts\python.exe scripts/backup.py verify backups/实际备份文件.zip
```

备份同时包含数据库、图片与 SHA-256 校验清单，自动清理该目录中超过 7 天的 `life-blog-*.zip`。恢复会替换目标数据库，须停止服务并明确指定目标；详见部署文档。

## 当前范围

单作者、中文、北京时间。已包含文章、标签、归档、关于页、站点地图、后台管理；评论、读者注册、独立相册、定时发布留到后续。演示页面的抽象封面为 CSS 绘制，上传真实照片后自动替换。

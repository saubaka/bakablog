# 项目目录与命名规范

## 1. 规划目录

```text
project-root/
├─ app/
│  ├─ __init__.py                 # create_app 应用工厂
│  ├─ config.py                   # 配置类，不保存真实密钥
│  ├─ extensions.py               # db、login、csrf、migrate 等扩展
│  ├─ blueprints/
│  │  ├─ public/
│  │  ├─ blog/
│  │  ├─ portfolio/
│  │  ├─ moments/
│  │  ├─ gallery/
│  │  ├─ links/
│  │  ├─ interaction/
│  │  ├─ search/
│  │  ├─ auth/
│  │  ├─ admin/
│  │  └─ api/
│  ├─ models/                     # SQLAlchemy 模型，按领域拆分
│  ├─ services/                   # 业务规则和事务边界
│  ├─ queries/                    # 复杂查询、分页和搜索
│  ├─ forms/                      # WTForms 表单
│  ├─ policies/                   # 权限策略
│  ├─ templates/
│  │  ├─ layouts/
│  │  ├─ components/
│  │  ├─ public/
│  │  ├─ blog/
│  │  ├─ admin/
│  │  └─ errors/
│  ├─ static/
│  │  ├─ css/
│  │  ├─ js/
│  │  ├─ fonts/
│  │  ├─ icons/
│  │  ├─ images/
│  │  └─ vendor/                  # 审查并本地化的浏览器第三方资源
│  ├─ cli/                        # 初始化、备份、检查和索引命令
│  └─ utils/                      # 小型无业务状态工具
├─ migrations/                   # Alembic/Flask-Migrate 迁移
├─ tests/
│  ├─ unit/
│  ├─ integration/
│  ├─ e2e/
│  ├─ performance/
│  └─ fixtures/
├─ instance/                     # 不提交生产内容
│  ├─ config.py
│  ├─ data/site.db
│  ├─ uploads/
│  ├─ cache/
│  ├─ logs/
│  ├─ backups/
│  └─ tmp/
├─ scripts/                      # 本地安装、启动、发布和恢复辅助脚本
├─ wheelhouse/                   # 可选离线 Python wheel，不默认提交大文件
├─ docs/
│  ├─ phase-1/
│  ├─ adr/
│  └─ operations/
├─ requirements.in              # 人工维护的直接依赖
├─ requirements.txt             # 锁定生产依赖
├─ requirements-dev.txt         # 锁定开发/测试依赖
├─ pyproject.toml                # 工具配置与项目元数据
├─ wsgi.py                       # 生产 WSGI 入口
├─ .env.example                 # 无密钥示例
├─ .gitignore
└─ README.md
```

## 2. 模块组织规则

- 每个Blueprint包含路由、模板入口和必要表单，不私自初始化全局扩展。
- SQLAlchemy扩展只在`extensions.py`创建，在应用工厂中绑定应用。
- 模型关系可跨领域，但避免循环导入；公共基类和枚举放入明确模块。
- 服务函数使用动词命名，例如`publish_post`、`approve_comment`。
- 查询函数描述结果，例如`list_published_posts`、`get_home_modules`。
- 权限检查集中在`policies`或统一装饰器中，服务层对关键写入再次校验调用上下文。
- `utils`只存放通用小工具，不能成为无边界的业务杂物目录。

## 3. URL和命名

- Python文件、函数、变量使用`snake_case`。
- 类使用`PascalCase`，常量使用`UPPER_SNAKE_CASE`。
- Blueprint名使用单数领域词或清晰复数词，全项目保持一致。
- 数据库表使用小写复数`snake_case`。
- 公开URL使用小写短横线，结尾斜杠规则统一。
- 权限代码采用`resource.action`，例如`post.publish`。
- 缓存键采用`namespace:version:identifier`。
- 媒体存储路径只使用ASCII安全字符，不含用户原始路径片段。

## 4. 配置边界

可提交配置：

- 默认分页数量、允许格式、主题默认值和功能开关默认值。
- 数据库连接模板和本地目录相对位置。
- 日志级别默认值与安全响应头默认策略。

不可提交内容：

- `SECRET_KEY`、管理员初始密码和恢复密钥。
- 生产SQLite文件、WAL/SHM文件、上传、日志和备份。
- 真实域名私钥、证书私钥或访客联系方式。

配置优先级建议：代码安全默认值 → 环境配置类 → 实例配置/环境变量。生产启动时若关键密钥仍为默认值必须拒绝启动。

## 5. 版本控制忽略策略

`.gitignore`至少覆盖：

- `.venv/`、Python缓存、测试缓存和覆盖率结果。
- `instance/data/*`、`instance/uploads/*`、`instance/cache/*`、`instance/logs/*`和`instance/backups/*`。
- SQLite的`*.db-wal`、`*.db-shm`和临时备份文件。
- `.env`与包含真实密钥的实例配置。
- 编辑器、操作系统临时文件和本地构建产物。

实例目录应保留空目录说明或`.gitkeep`，但不提交真实数据。

## 6. 文档和测试位置

- 架构决策写入`docs/adr/`，使用编号和状态。
- 部署、备份、恢复和故障处理写入`docs/operations/`。
- 每个关键服务至少有单元测试；数据库、迁移和权限使用集成测试。
- 性能测试脚本与结果说明放入`tests/performance/`或专用报告目录。
- 测试使用临时SQLite文件，不能连接生产数据库。

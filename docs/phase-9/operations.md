# 运维、监控、升级与回滚

## 健康和日志

- `/healthz`只说明进程可响应，返回服务名、stage和版本。
- `/readyz`同时检查数据库连接、生产迁移revision等于代码head、数据目录和上传目录可写；失败返回503且不向访客泄漏内部异常。
- `instance/logs/cloud-diary.log`按5MiB轮转并保留5个历史文件。每条请求带请求ID、状态和耗时；后台“系统状态”页面只展示安全摘要，不展示物理路径和密钥。

建议每分钟从本机监控`/readyz`，连续3次失败告警；同时监控服务进程、磁盘可用空间、证书剩余时间、备份新鲜度和日志中的`ERROR`/连续5xx。告警渠道属于部署环境，可接入现有邮件或即时消息系统，但应用运行本身不依赖外部监控服务。

## 日常计划

- 每日低峰：执行联合备份，随后`site-backup-verify`。
- 每周低峰：执行`maintenance.ps1 -RetentionDays 30`；它运行完整性检查、被动checkpoint/优化、备份并只删除备份目录内过期的标准备份。
- 每月维护窗口：在确认没有长事务后执行`maintenance.ps1 -TruncateWal`，并抽取一个备份在隔离实例恢复。
- 每次发布：备份、升级迁移、补齐权限、`system-check`、自动化回归、重启、检查`/readyz`。

Windows任务计划程序调用脚本时使用：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\path\scripts\maintenance.ps1
```

真实环境变量由任务身份安全注入。脚本显式传播每个Python命令的非零退出码，便于计划程序告警。

## 备份格式与恢复

联合备份v2是ZIP，包含SQLite在线快照、`uploads/`和`manifest.json`。清单记录应用版本、迁移revision、数据库SHA-256、每个媒体的路径/大小/SHA-256。恢复步骤：

1. 停止应用写流量并进入维护窗口。
2. 在另一目录执行`site-backup-verify`确认归档安全、哈希和SQLite完整性。
3. Windows运行`restore.ps1 -Archive <path> -ConfirmRestore`；Linux运行`flask site-restore <path> --yes`。
4. 恢复命令先创建`pre-restore-safety-*.zip`，再替换数据库和媒体。
5. 执行`system-check`、`/readyz`、登录、文章和媒体抽查；失败时保留现场并使用安全副本恢复。

本机小型空实例恢复演练用时在秒级，但RTO取决于真实媒体体积和磁盘速度，不能用该数字承诺生产RTO。建议目标为每日备份RPO不超过24小时、单机恢复RTO不超过2小时，并用真实数据量演练修正。

## 升级与密钥轮换

Windows升级使用`upgrade.ps1`，默认先备份。需要轮换Flask密钥时把新密钥设为`CLOUD_DIARY_SECRET_KEY`，旧密钥短期放入`CLOUD_DIARY_SECRET_KEY_FALLBACKS`，待旧会话过期后删除fallback。fallback仍是敏感信息，绝不能写进文档或Git。

## 故障处理

- `/healthz`失败：检查服务进程、标准错误、端口占用和依赖导入。
- `/healthz`成功但`/readyz`失败：运行`system-check`，检查迁移、磁盘权限、磁盘空间和SQLite完整性。
- 持续数据库锁：停止异常长写事务，确认只有单机应用与单个维护任务写入；不要通过降低安全参数掩盖多写主机问题。
- 迁移失败：不要继续启动新代码；保存日志和当前联合备份，根据兼容性选择修复迁移或联合恢复后回滚代码。
- 媒体缺失：验证最近备份的媒体哈希，恢复整个联合备份或从安全副本提取受控文件，不手工覆盖正在运行的实例目录。

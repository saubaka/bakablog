# Windows运行边界

当前项目不再把Windows作为生产部署目标。Windows仅使用Flask开发服务器进行本机功能测试，完整命令见[Windows本地测试](../windows-local-testing.md)。

正式部署统一按[Debian 12生产部署规划](deployment-linux.md)执行。仓库中保留的Waitress和PowerShell生产脚本只用于旧版兼容与维护演练，不是当前推荐发布路径。

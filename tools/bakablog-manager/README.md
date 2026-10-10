# bakablog Windows 本地服务管理器

项目根目录中的`bakablog.exe`是Windows 11/10 x64自包含单文件程序，不要求目标机器预装.NET。

双击后会显示应用状态、端口、PID、Windows版本、管理器版本和当前用户开机自启状态。菜单支持：

1. 启动bakablog
2. 停止bakablog
3. 重新启动bakablog
4. 获取仅限本机、五分钟有效、只可使用一次的管理员恢复入口
5. 重置管理器选项
6. 切换当前Windows用户的开机自启
0. 退出

“重置管理器选项”只会停止服务、关闭开机自启并清理管理器状态/日志，不会删除SQLite数据库、上传文件或网站设置。

源码位于本目录。重新发布：

```powershell
dotnet publish bakablog.csproj -c Release -r win-x64 --self-contained true -o publish
```

# 本地离线依赖目录

运行`scripts/bootstrap.ps1 -DownloadWheels`后，当前Windows/Python平台需要的wheel文件会下载到这里。

安装时使用：

```powershell
.\scripts\bootstrap.ps1 -Offline
```

wheel文件是本机安装制品，默认不进入版本控制。Windows与Linux、不同Python版本需要分别准备兼容的wheelhouse，不能混用带原生扩展的平台包。

using System.Diagnostics;
using System.Globalization;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace BakaGateManager;

internal sealed class GateConfig
{
    public string Domain { get; set; } = "";
    public string ProjectRoot { get; set; } = "/opt/bakablog/current";
    public string InstanceRoot { get; set; } = "/var/lib/bakablog";
    public int LocalPort { get; set; } = 8080;
    public int RetentionDays { get; set; } = 14;
    public int RetentionFiles { get; set; } = 14;
    public int MaxLogSizeMb { get; set; } = 50;
}

internal sealed record CommandResult(int ExitCode, string Output, string Error);

internal static class Program
{
    private const string ServiceName = "bakablog.service";
    private const string ManagerName = "bakagate";
    private const string ConfigDirectory = "/etc/bakagate";
    private const string ConfigPath = "/etc/bakagate/bakagate.conf";
    private const string EnvironmentPath = "/etc/bakablog.env";
    private const string InstalledBinaryPath = "/usr/local/bin/bakagate";
    private const string ServicePath = "/etc/systemd/system/bakablog.service";
    private const string TimerPath = "/etc/systemd/system/bakagate-log-maintenance.timer";
    private const string TimerServicePath = "/etc/systemd/system/bakagate-log-maintenance.service";
    private const string NginxSitePath = "/etc/nginx/conf.d/bakablog.conf";
    private const string LogrotatePath = "/etc/logrotate.d/bakablog";
    private const string CertificatePath = "/etc/bakagate/tls/cloudflare-origin.pem";
    private const string PrivateKeyPath = "/etc/bakagate/tls/cloudflare-origin.key";
    private const string RuntimePortPath = "/run/bakablog/port";
    private const string RuntimeLaunchPath = "/run/bakablog/launch.sh";
    private const string LogDirectory = "/var/log/bakablog";
    private static readonly UTF8Encoding Utf8NoBom = new(false);
    private static readonly Regex SafeDomainLabel = new(
        @"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$",
        RegexOptions.Compiled | RegexOptions.CultureInvariant
    );

    private static async Task<int> Main(string[] args)
    {
        Console.OutputEncoding = Utf8NoBom;
        Console.InputEncoding = Utf8NoBom;

        try
        {
            if (TryValue(args, "--validate-domain", out string? domainValue))
            {
                Console.WriteLine(NormalizeDomain(domainValue!));
                return 0;
            }
            if (TryValue(args, "--select-local-port", out string? rawPreferredPort))
            {
                int preferredPort = ParseBounded(rawPreferredPort, 1024, 65535, -1);
                if (preferredPort < 0)
                {
                    throw new InvalidOperationException("--select-local-port 必须在 1024 到 65535 之间。");
                }
                Console.WriteLine(IsPortAvailable(preferredPort) ? preferredPort : FindAvailablePort(preferredPort));
                return 0;
            }
            if (args.Contains("--render-test", StringComparer.OrdinalIgnoreCase))
            {
                return RenderTest(args);
            }
            if (args.Contains("--version", StringComparer.OrdinalIgnoreCase))
            {
                Console.WriteLine(ManagerVersion());
                return 0;
            }
            EnsureLinux();
            if (args.Contains("--status-json", StringComparer.OrdinalIgnoreCase))
            {
                await PrintStatusJson();
                return 0;
            }
            if (args.Contains("--install", StringComparer.OrdinalIgnoreCase))
            {
                RequireRoot();
                return await InstallOrUpdate() ? 0 : 1;
            }
            if (args.Contains("--start", StringComparer.OrdinalIgnoreCase))
            {
                RequireRoot();
                return await StartManagedService(showMessages: true) ? 0 : 1;
            }
            if (args.Contains("--stop", StringComparer.OrdinalIgnoreCase))
            {
                RequireRoot();
                return (await Systemctl("stop", ServiceName)).ExitCode;
            }
            if (args.Contains("--restart", StringComparer.OrdinalIgnoreCase))
            {
                RequireRoot();
                return await RestartManagedService(showMessages: true) ? 0 : 1;
            }
            if (args.Contains("--toggle-startup", StringComparer.OrdinalIgnoreCase))
            {
                RequireRoot();
                return await ToggleStartup() ? 0 : 1;
            }
            if (args.Contains("--configure-edge", StringComparer.OrdinalIgnoreCase))
            {
                RequireRoot();
                return await ConfigureEdgeInteractive() ? 0 : 1;
            }
            if (args.Contains("--maintain-logs", StringComparer.OrdinalIgnoreCase))
            {
                RequireRoot();
                MaintainLogs(ReadConfig());
                return 0;
            }
            if (args.Contains("--prepare-port", StringComparer.OrdinalIgnoreCase))
            {
                RequireRoot();
                return await PreparePortForService() ? 0 : 1;
            }
            if (args.Contains("--doctor", StringComparer.OrdinalIgnoreCase))
            {
                return await Doctor() ? 0 : 1;
            }

            await RunMenu();
            return 0;
        }
        catch (Exception error) when (
            error is InvalidOperationException
            or IOException
            or UnauthorizedAccessException
            or CryptographicException)
        {
            WriteColor($"错误：{error.Message}", ConsoleColor.Red);
            return 1;
        }
    }

    private static async Task RunMenu()
    {
        while (true)
        {
            SafeClear();
            GateConfig config = ReadConfig();
            await DrawStatus(config);
            DrawMenu();
            Console.Write("请输入操作编号：");
            string choice = (Console.ReadLine() ?? "0").Trim();
            Console.WriteLine();
            switch (choice)
            {
                case "1":
                    RequireRoot();
                    await InstallOrUpdate();
                    break;
                case "2":
                    RequireRoot();
                    await StartManagedService(showMessages: true);
                    break;
                case "3":
                    RequireRoot();
                    ShowResult(await Systemctl("stop", ServiceName), "服务已停止。");
                    break;
                case "4":
                    RequireRoot();
                    await RestartManagedService(showMessages: true);
                    break;
                case "5":
                    RequireRoot();
                    await ToggleStartup();
                    break;
                case "6":
                    RequireRoot();
                    await ConfigureEdgeInteractive();
                    break;
                case "7":
                    await ShowLogs();
                    break;
                case "8":
                    RequireRoot();
                    ConfigureRetention();
                    break;
                case "9":
                    await Doctor();
                    break;
                case "0":
                    return;
                default:
                    WriteColor("无法识别该编号。", ConsoleColor.Red);
                    break;
            }
            Console.WriteLine();
            WriteColor("按 Enter 返回主菜单……", ConsoleColor.DarkGray);
            Console.ReadLine();
        }
    }

    private static async Task DrawStatus(GateConfig config)
    {
        bool installed = File.Exists(ServicePath) && File.Exists(InstalledBinaryPath);
        bool running = (await Run("systemctl", ["is-active", "--quiet", ServiceName])).ExitCode == 0;
        bool enabled = (await Run("systemctl", ["is-enabled", "--quiet", ServiceName])).ExitCode == 0;
        bool nginx = (await Run("systemctl", ["is-active", "--quiet", "nginx.service"])).ExitCode == 0;
        string portState = running ? "由 bakablog 使用" : IsPortAvailable(config.LocalPort) ? "可用" : "被其他进程占用，启动时将自动切换";

        WriteColor("╭────────────────────────────────────────────────────────╮", ConsoleColor.Cyan);
        WriteColor("│  bakagate · Linux 部署与服务管理器                      │", ConsoleColor.Cyan);
        WriteColor("╰────────────────────────────────────────────────────────╯", ConsoleColor.Cyan);
        Console.WriteLine($"系统版本：{LinuxDescription()}");
        Console.WriteLine($"管理版本：{ManagerVersion()}");
        Console.Write("部署状态：");
        WriteStatus(installed, installed ? "已安装" : "未安装");
        Console.Write("应用服务：");
        WriteStatus(running, running ? "运行中" : "已停止");
        Console.Write("开机自启：");
        WriteStatus(enabled, enabled ? "已启用" : "未启用");
        Console.Write("Nginx：   ");
        WriteStatus(nginx, nginx ? "运行中" : "未运行");
        Console.WriteLine($"本地端口：127.0.0.1:{config.LocalPort}（{portState}）");
        Console.WriteLine($"唯一域名：{(config.Domain.Length == 0 ? "未配置" : config.Domain)}");
        Console.WriteLine($"源站证书：{await CertificateSummary()}");
        Console.WriteLine($"项目目录：{config.ProjectRoot}");
        Console.WriteLine($"日志策略：保留 {config.RetentionDays} 天 / {config.RetentionFiles} 份 / 单文件 {config.MaxLogSizeMb} MiB");
        Console.WriteLine();
    }

    private static void DrawMenu()
    {
        MenuLine("1", "安装或更新 Linux 部署");
        MenuLine("2", "启动 bakablog");
        MenuLine("3", "停止 bakablog");
        MenuLine("4", "重新启动 bakablog");
        MenuLine("5", "切换开机自启");
        MenuLine("6", "设置唯一域名并导入 Cloudflare 源站证书");
        MenuLine("7", "查看本地服务日志");
        MenuLine("8", "设置日志保留与定时清理");
        MenuLine("9", "执行部署与安全检查");
        MenuLine("0", "退出", ConsoleColor.DarkGray);
        Console.WriteLine();
    }

    private static async Task<bool> InstallOrUpdate()
    {
        VerifySupportedLinux();
        GateConfig existing = ReadConfig();
        string detected = FindProjectRoot() ?? existing.ProjectRoot;
        string projectRoot = Prompt("项目绝对目录", detected);
        ValidateProjectRoot(projectRoot);
        string domain = NormalizeDomain(Prompt("唯一公开域名（不能包含协议或路径）", existing.Domain));

        WriteColor("正在安装 Linux 系统依赖……", ConsoleColor.Yellow);
        if (!await InstallSystemPackages())
        {
            return false;
        }

        await EnsureServiceAccount();
        GateConfig config = existing;
        config.Domain = domain;
        config.ProjectRoot = Path.GetFullPath(projectRoot);
        Directory.CreateDirectory(ConfigDirectory);
        Directory.CreateDirectory(Path.GetDirectoryName(CertificatePath)!);
        Directory.CreateDirectory(config.InstanceRoot);
        Directory.CreateDirectory(LogDirectory);
        Chmod("0750", ConfigDirectory, Path.GetDirectoryName(CertificatePath)!, config.InstanceRoot, LogDirectory);
        await Run("chown", ["-R", "bakablog:bakablog", config.InstanceRoot, LogDirectory]);

        bool serviceRunning = (await Run("systemctl", ["is-active", "--quiet", ServiceName])).ExitCode == 0;
        if (!serviceRunning)
        {
            EnsureAvailablePort(config, showMessages: true);
        }

        CopySelf();
        WriteConfig(config);
        WriteEnvironment(config, preserveSecret: true);
        if (!await PreparePython(config))
        {
            return false;
        }
        if (!await RunApplicationMigrations(config))
        {
            return false;
        }

        if (!File.Exists(CertificatePath) || !File.Exists(PrivateKeyPath))
        {
            WriteColor("尚未安装 Cloudflare 源站证书；现在进入证书导入。", ConsoleColor.Yellow);
            if (!await ImportCertificateInteractive(config.Domain))
            {
                return false;
            }
        }

        WriteManagedFiles(config);

        CommandResult daemonReload = await Systemctl("daemon-reload");
        if (daemonReload.ExitCode != 0)
        {
            ShowFailure("systemd 配置加载失败", daemonReload);
            return false;
        }
        await Run("systemctl", ["enable", "--now", "bakagate-log-maintenance.timer"]);
        await Run("systemctl", ["enable", ServiceName]);
        if (!await ValidateNginx())
        {
            return false;
        }
        CommandResult nginxReload = await Run("systemctl", ["reload", "nginx.service"]);
        if (nginxReload.ExitCode != 0)
        {
            ShowFailure("Nginx 重新加载失败", nginxReload);
            return false;
        }
        if (!await RestartManagedService(showMessages: false))
        {
            return false;
        }
        WriteColor("Linux 部署已经完成。", ConsoleColor.Green);
        WriteColor($"当前本地端口：127.0.0.1:{ReadConfig().LocalPort}；公开地址：https://{domain}", ConsoleColor.Cyan);
        return true;
    }

    private static async Task EnsureServiceAccount()
    {
        if ((await Run("id", ["-u", "bakablog"])).ExitCode != 0)
        {
            CommandResult create = await Run(
                "useradd",
                ["--system", "--home-dir", "/var/lib/bakablog", "--shell", "/usr/sbin/nologin", "--user-group", "bakablog"]
            );
            if (create.ExitCode != 0)
            {
                throw new InvalidOperationException("无法创建 bakablog 系统账户：" + LastLines(create.Error, 4));
            }
        }
    }

    private static async Task<bool> InstallSystemPackages()
    {
        Dictionary<string, string> release = ReadOsRelease();
        string id = release.GetValueOrDefault("ID", "").ToLowerInvariant();
        string like = release.GetValueOrDefault("ID_LIKE", "").ToLowerInvariant();
        CommandResult result;
        if (id is "debian" or "ubuntu" || like.Contains("debian", StringComparison.Ordinal))
        {
            result = await Run("apt-get", ["update"]);
            if (result.ExitCode == 0)
            {
                result = await Run("apt-get", ["install", "-y", "python3", "python3-venv", "python3-pip", "nginx", "openssl", "curl", "ca-certificates", "logrotate", "git"]);
            }
        }
        else if (id is "fedora" or "rhel" or "centos" or "rocky" or "almalinux" || like.Contains("rhel", StringComparison.Ordinal) || like.Contains("fedora", StringComparison.Ordinal))
        {
            result = await Run("dnf", ["install", "-y", "python3", "python3-pip", "nginx", "openssl", "curl", "ca-certificates", "logrotate", "git"]);
        }
        else if (id is "arch" or "manjaro" || like.Contains("arch", StringComparison.Ordinal))
        {
            result = await Run("pacman", ["-Sy", "--noconfirm", "--needed", "python", "python-pip", "nginx", "openssl", "curl", "ca-certificates", "logrotate", "git"]);
        }
        else if (id is "opensuse-leap" or "opensuse-tumbleweed" or "sles" || like.Contains("suse", StringComparison.Ordinal))
        {
            result = await Run("zypper", ["--non-interactive", "install", "python3", "python3-pip", "nginx", "openssl", "curl", "ca-certificates", "logrotate", "git"]);
        }
        else
        {
            WriteColor($"暂不支持自动安装当前发行版（ID={id}）。支持 Debian/Ubuntu、Fedora/RHEL 系、Arch 系和 openSUSE/SLES。", ConsoleColor.Red);
            return false;
        }
        if (result.ExitCode != 0)
        {
            ShowFailure("系统依赖安装失败", result);
            return false;
        }
        return true;
    }

    private static async Task<bool> StartManagedService(bool showMessages)
    {
        if ((await Run("systemctl", ["is-active", "--quiet", ServiceName])).ExitCode == 0)
        {
            if (showMessages)
            {
                WriteColor($"服务已经运行在 127.0.0.1:{ReadConfig().LocalPort}。", ConsoleColor.Green);
            }
            return true;
        }
        GateConfig config = ReadConfig();
        bool changed = EnsureAvailablePort(config, showMessages);
        if (changed)
        {
            WriteConfig(config);
            WriteManagedFiles(config);
            await Systemctl("daemon-reload");
            if (!await ValidateNginx())
            {
                return false;
            }
            CommandResult nginxReload = await Run("systemctl", ["reload", "nginx.service"]);
            if (nginxReload.ExitCode != 0)
            {
                ShowFailure("本地端口改变后 Nginx 重新加载失败", nginxReload);
                return false;
            }
        }
        CommandResult start = await Systemctl("start", ServiceName);
        if (start.ExitCode != 0)
        {
            ShowFailure("应用启动失败", start);
            return false;
        }
        config = ReadConfig();
        bool healthy = await WaitForHealth(config.LocalPort, TimeSpan.FromSeconds(35));
        if (showMessages)
        {
            WriteColor(
                healthy ? $"服务已启动，本地端口为 127.0.0.1:{config.LocalPort}。" : $"服务已启动但端口 {config.LocalPort} 尚未通过健康检查。",
                healthy ? ConsoleColor.Green : ConsoleColor.Red
            );
        }
        return healthy;
    }

    private static async Task<bool> RestartManagedService(bool showMessages)
    {
        CommandResult stop = await Systemctl("stop", ServiceName);
        if (stop.ExitCode != 0)
        {
            ShowFailure("停止旧服务失败", stop);
            return false;
        }
        return await StartManagedService(showMessages);
    }

    private static async Task<bool> PreparePortForService()
    {
        GateConfig config = ReadConfig();
        EnsureAvailablePort(config, showMessages: true);
        WriteConfig(config);
        Directory.CreateDirectory(Path.GetDirectoryName(RuntimePortPath)!);
        AtomicWrite(RuntimePortPath, config.LocalPort.ToString(CultureInfo.InvariantCulture) + "\n", "0644");
        string gunicorn = Path.Combine(config.ProjectRoot, ".venv", "bin", "gunicorn");
        string launch = $"#!/bin/sh\nexec '{gunicorn}' --bind 127.0.0.1:{config.LocalPort} --workers 2 --threads 4 --timeout 120 --access-logfile {LogDirectory}/access.log --error-logfile {LogDirectory}/error.log wsgi:app\n";
        AtomicWrite(RuntimeLaunchPath, launch, "0750");
        await Run("chown", ["bakablog:bakablog", RuntimePortPath, RuntimeLaunchPath]);
        AtomicWrite(NginxSitePath, RenderNginx(config), "0644");
        if (!await ValidateNginx())
        {
            return false;
        }
        CommandResult reload = await Run("nginx", ["-s", "reload"]);
        if (reload.ExitCode != 0)
        {
            ShowFailure("自动端口更新后 Nginx 重新加载失败", reload);
            return false;
        }
        return true;
    }

    private static bool EnsureAvailablePort(GateConfig config, bool showMessages)
    {
        int original = config.LocalPort;
        if (IsPortAvailable(original))
        {
            return false;
        }
        config.LocalPort = FindAvailablePort(original);
        if (showMessages)
        {
            WriteColor($"本地端口 {original} 已被占用，已自动切换到 {config.LocalPort}。", ConsoleColor.Yellow);
        }
        return true;
    }

    private static int FindAvailablePort(int preferred)
    {
        const int minimum = 1024;
        const int maximum = 65535;
        int range = maximum - minimum + 1;
        for (int offset = 1; offset < range; offset++)
        {
            int candidate = minimum + ((preferred - minimum + offset) % range);
            if (IsPortAvailable(candidate))
            {
                return candidate;
            }
        }
        throw new InvalidOperationException("没有可用于本地服务的空闲TCP端口。");
    }

    private static bool IsPortAvailable(int port)
    {
        try
        {
            TcpListener listener = new(IPAddress.Loopback, port);
            listener.Start();
            listener.Stop();
            return true;
        }
        catch (SocketException)
        {
            return false;
        }
    }

    private static async Task<bool> WaitForHealth(int port, TimeSpan timeout)
    {
        DateTimeOffset deadline = DateTimeOffset.UtcNow + timeout;
        while (DateTimeOffset.UtcNow < deadline)
        {
            CommandResult result = await Run("curl", ["--silent", "--fail", $"http://127.0.0.1:{port}/healthz"], timeout: TimeSpan.FromSeconds(3));
            if (result.ExitCode == 0 && result.Output.Contains("cloudtrace", StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
            await Task.Delay(500);
        }
        return false;
    }

    private static async Task<bool> PreparePython(GateConfig config)
    {
        WriteColor("正在准备 Python 虚拟环境与依赖……", ConsoleColor.Yellow);
        string venvPython = Path.Combine(config.ProjectRoot, ".venv", "bin", "python");
        if (!File.Exists(venvPython))
        {
            string python = await FindSupportedPython();
            CommandResult venv = await Run(python, ["-m", "venv", Path.Combine(config.ProjectRoot, ".venv")]);
            if (venv.ExitCode != 0)
            {
                ShowFailure("创建虚拟环境失败", venv);
                return false;
            }
        }
        string pip = Path.Combine(config.ProjectRoot, ".venv", "bin", "pip");
        CommandResult install;
        string wheelhouse = Path.Combine(config.ProjectRoot, "wheelhouse");
        bool offline = Directory.Exists(wheelhouse) && Directory.EnumerateFiles(wheelhouse, "*.whl").Any();
        if (offline)
        {
            install = await Run(pip, ["install", "--no-index", "--find-links", wheelhouse, "-r", Path.Combine(config.ProjectRoot, "requirements.txt")]);
            if (install.ExitCode != 0)
            {
                WriteColor("本地 wheelhouse 与当前 Linux/Python 不兼容，改用 PyPI 安装。", ConsoleColor.Yellow);
                install = await Run(pip, ["install", "-r", Path.Combine(config.ProjectRoot, "requirements.txt")]);
            }
        }
        else
        {
            install = await Run(pip, ["install", "-r", Path.Combine(config.ProjectRoot, "requirements.txt")]);
        }
        if (install.ExitCode != 0)
        {
            ShowFailure("Python 依赖安装失败", install);
            return false;
        }
        CommandResult check = await Run(pip, ["check"]);
        if (check.ExitCode != 0)
        {
            ShowFailure("Python 依赖完整性检查失败", check);
            return false;
        }
        await Run("chown", ["-R", "root:root", Path.Combine(config.ProjectRoot, ".venv")]);
        return true;
    }

    private static async Task<string> FindSupportedPython()
    {
        foreach (string candidate in new[] { "python3.14", "python3.13", "python3.12", "python3.11", "python3" })
        {
            CommandResult result = await Run(candidate, ["-c", "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 15) else 1)"]);
            if (result.ExitCode == 0)
            {
                return candidate;
            }
        }
        throw new InvalidOperationException("没有找到 Python 3.11–3.14；请先使用当前发行版的软件源安装兼容版本。");
    }

    private static async Task<bool> RunApplicationMigrations(GateConfig config)
    {
        WriteColor("正在执行数据库迁移、权限同步和系统检查……", ConsoleColor.Yellow);
        string flask = Path.Combine(config.ProjectRoot, ".venv", "bin", "flask");
        foreach (string[] command in new[]
        {
            new[] { "db", "upgrade" },
            new[] { "seed-permissions" },
            new[] { "configure-deployment-domain", config.Domain },
            new[] { "system-check" },
        })
        {
            List<string> arguments =
            [
                "-u",
                "bakablog",
                "--",
                "env",
                "PYTHONUTF8=1",
                $"CLOUD_DIARY_INSTANCE_PATH={config.InstanceRoot}",
                $"CLOUD_DIARY_ENV=production",
                $"CLOUD_DIARY_SITE_URL=https://{config.Domain}",
                "bash",
                "-c",
                $"set -a; . '{EnvironmentPath}'; set +a; exec '{flask}' --app wsgi:app {string.Join(' ', command)}"
            ];
            CommandResult result = await Run("runuser", arguments, config.ProjectRoot, TimeSpan.FromMinutes(5));
            if (result.ExitCode != 0)
            {
                ShowFailure($"Flask 命令 {string.Join(' ', command)} 失败", result);
                return false;
            }
        }
        return true;
    }

    private static async Task<bool> ConfigureEdgeInteractive()
    {
        GateConfig config = ReadConfig();
        string domain = NormalizeDomain(Prompt("唯一公开域名", config.Domain));
        if (!await ImportCertificateInteractive(domain))
        {
            return false;
        }
        config.Domain = domain;
        WriteConfig(config);
        WriteEnvironment(config, preserveSecret: true);
        WriteManagedFiles(config);
        if (!await ConfigureApplicationDomain(config))
        {
            return false;
        }
        await Systemctl("daemon-reload");
        if (!await ValidateNginx())
        {
            return false;
        }
        CommandResult reload = await Run("systemctl", ["reload", "nginx.service"]);
        if (reload.ExitCode != 0)
        {
            ShowFailure("Nginx 重新加载失败", reload);
            return false;
        }
        if (!await RestartManagedService(showMessages: false))
        {
            return false;
        }
        WriteColor("域名和 Cloudflare 源站证书已经启用。", ConsoleColor.Green);
        return true;
    }

    private static async Task<bool> ConfigureApplicationDomain(GateConfig config)
    {
        string flask = Path.Combine(config.ProjectRoot, ".venv", "bin", "flask");
        string shell = $"set -a; . '{EnvironmentPath}'; set +a; exec '{flask}' --app wsgi:app configure-deployment-domain {config.Domain}";
        CommandResult result = await Run(
            "runuser",
            ["-u", "bakablog", "--", "env", "PYTHONUTF8=1", "bash", "-c", shell],
            config.ProjectRoot,
            TimeSpan.FromMinutes(2)
        );
        if (result.ExitCode == 0)
        {
            return true;
        }
        ShowFailure("应用域名与HTTPS策略写入失败", result);
        return false;
    }

    private static async Task<bool> ImportCertificateInteractive(string domain)
    {
        Console.WriteLine("请在 Cloudflare 控制台创建 Origin CA 源站证书，然后把证书和私钥文件上传到服务器。");
        string certificateSource = Prompt("源站证书 PEM 文件绝对路径", "");
        string keySource = Prompt("源站私钥 PEM 文件绝对路径", "");
        ValidateReadableRegularFile(certificateSource, "源站证书");
        ValidateReadableRegularFile(keySource, "源站私钥");
        if (!await ValidateCloudflareCertificate(certificateSource, keySource, domain))
        {
            return false;
        }
        Directory.CreateDirectory(Path.GetDirectoryName(CertificatePath)!);
        AtomicCopy(certificateSource, CertificatePath);
        AtomicCopy(keySource, PrivateKeyPath);
        Chmod("0644", CertificatePath);
        Chmod("0600", PrivateKeyPath);
        await Run("chown", ["root:root", CertificatePath, PrivateKeyPath]);
        WriteColor("Cloudflare Origin CA 证书与私钥已经安全导入。", ConsoleColor.Green);
        return true;
    }

    private static async Task<bool> ValidateCloudflareCertificate(string certificate, string key, string domain)
    {
        CommandResult cert = await Run("openssl", ["x509", "-in", certificate, "-noout", "-issuer", "-subject", "-dates", "-checkhost", domain]);
        if (cert.ExitCode != 0 || !cert.Output.Contains("does match certificate", StringComparison.OrdinalIgnoreCase))
        {
            ShowFailure("证书无效、已过期或不包含当前域名", cert);
            return false;
        }
        if (!cert.Output.Contains("CloudFlare Origin", StringComparison.OrdinalIgnoreCase))
        {
            WriteColor("拒绝导入：该证书不是 Cloudflare Origin CA 源站证书。", ConsoleColor.Red);
            return false;
        }
        CommandResult validity = await Run("openssl", ["x509", "-in", certificate, "-noout", "-checkend", "604800"]);
        if (validity.ExitCode != 0)
        {
            WriteColor("拒绝导入：源站证书已经过期或将在七天内过期。", ConsoleColor.Red);
            return false;
        }
        CommandResult keyCheck = await Run("openssl", ["pkey", "-in", key, "-check", "-noout"]);
        if (keyCheck.ExitCode != 0)
        {
            ShowFailure("私钥格式或完整性检查失败", keyCheck);
            return false;
        }
        CommandResult certPublic = await Run("openssl", ["x509", "-in", certificate, "-pubkey", "-noout"]);
        CommandResult keyPublic = await Run("openssl", ["pkey", "-in", key, "-pubout"]);
        if (certPublic.ExitCode != 0 || keyPublic.ExitCode != 0 || !FixedEquals(certPublic.Output, keyPublic.Output))
        {
            WriteColor("证书与私钥不匹配。", ConsoleColor.Red);
            return false;
        }
        return true;
    }

    private static void ConfigureRetention()
    {
        GateConfig config = ReadConfig();
        config.RetentionDays = PromptInt("日志最多保留天数", config.RetentionDays, 1, 3650);
        config.RetentionFiles = PromptInt("每类轮转文件最多保留份数", config.RetentionFiles, 1, 365);
        config.MaxLogSizeMb = PromptInt("单个日志文件最大 MiB", config.MaxLogSizeMb, 1, 2048);
        WriteConfig(config);
        WriteLogrotate(config);
        MaintainLogs(config);
        WriteColor("日志轮转与定时清理策略已经更新。", ConsoleColor.Green);
    }

    private static void MaintainLogs(GateConfig config)
    {
        if (!Directory.Exists(LogDirectory))
        {
            return;
        }
        DateTime cutoff = DateTime.UtcNow.AddDays(-config.RetentionDays);
        string[] safePrefixes = ["access.log.", "error.log.", "service.log.", "nginx-access.log.", "nginx-error.log."];
        foreach (string file in Directory.EnumerateFiles(LogDirectory))
        {
            string name = Path.GetFileName(file);
            if (!safePrefixes.Any(prefix => name.StartsWith(prefix, StringComparison.Ordinal)))
            {
                continue;
            }
            FileInfo info = new(file);
            if (info.LastWriteTimeUtc < cutoff)
            {
                info.Delete();
            }
        }
        foreach (string prefix in safePrefixes)
        {
            FileInfo[] files = Directory.EnumerateFiles(LogDirectory, prefix + "*")
                .Select(path => new FileInfo(path))
                .OrderByDescending(file => file.LastWriteTimeUtc)
                .ToArray();
            foreach (FileInfo old in files.Skip(config.RetentionFiles))
            {
                old.Delete();
            }
        }
    }

    private static async Task ShowLogs()
    {
        CommandResult result = await Run("journalctl", ["-u", ServiceName, "-n", "80", "--no-pager", "--output", "short-iso"]);
        if (result.ExitCode == 0 && result.Output.Trim().Length > 0)
        {
            Console.WriteLine(result.Output.TrimEnd());
        }
        foreach (string name in new[] { "service.log", "error.log", "access.log" })
        {
            string path = Path.Combine(LogDirectory, name);
            if (!File.Exists(path))
            {
                continue;
            }
            WriteColor($"\n—— {path}（末尾 40 行）——", ConsoleColor.Cyan);
            Console.WriteLine(string.Join(Environment.NewLine, File.ReadLines(path).TakeLast(40)));
        }
    }

    private static async Task<bool> Doctor()
    {
        GateConfig config = ReadConfig();
        bool good = true;
        good &= Check("受支持的Linux/systemd", IsSupportedLinux());
        good &= Check("管理配置", File.Exists(ConfigPath));
        good &= Check("项目入口", File.Exists(Path.Combine(config.ProjectRoot, "wsgi.py")));
        good &= Check("systemd 单元", File.Exists(ServicePath));
        good &= Check("Cloudflare 源站证书", File.Exists(CertificatePath) && File.Exists(PrivateKeyPath));
        good &= Check("精确唯一域名", TryNormalizeDomain(config.Domain, out _));
        CommandResult nginx = await Run("nginx", ["-t"]);
        good &= Check("Nginx 配置", nginx.ExitCode == 0);
        CommandResult service = await Run("systemctl", ["is-active", "--quiet", ServiceName]);
        good &= Check("应用服务", service.ExitCode == 0);
        CommandResult localPort = await Run("curl", ["--silent", "--show-error", "--fail", $"http://127.0.0.1:{config.LocalPort}/healthz"]);
        good &= Check($"本地端口 {config.LocalPort}", localPort.ExitCode == 0 && localPort.Output.Contains("cloudtrace", StringComparison.OrdinalIgnoreCase));
        CommandResult enabled = await Run("systemctl", ["is-enabled", "--quiet", ServiceName]);
        good &= Check("开机自启", enabled.ExitCode == 0);
        CommandResult timer = await Run("systemctl", ["is-active", "--quiet", "bakagate-log-maintenance.timer"]);
        good &= Check("日志清理计时器", timer.ExitCode == 0);
        WriteColor(good ? "部署与安全检查全部通过。" : "检查发现问题，请根据红色项目修复。", good ? ConsoleColor.Green : ConsoleColor.Red);
        return good;
    }

    private static async Task PrintStatusJson()
    {
        GateConfig config = ReadConfig();
        bool running = (await Run("systemctl", ["is-active", "--quiet", ServiceName])).ExitCode == 0;
        bool enabled = (await Run("systemctl", ["is-enabled", "--quiet", ServiceName])).ExitCode == 0;
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            manager = ManagerName,
            version = ManagerVersion(),
            service = ServiceName,
            running,
            startup_enabled = enabled,
            domain = config.Domain,
            local_host = "127.0.0.1",
            local_port = config.LocalPort,
            port_state = running ? "service" : IsPortAvailable(config.LocalPort) ? "available" : "occupied",
            log_retention_days = config.RetentionDays,
            platform = LinuxDescription(),
        }));
    }

    private static async Task<bool> ToggleStartup()
    {
        bool enabled = (await Run("systemctl", ["is-enabled", "--quiet", ServiceName])).ExitCode == 0;
        CommandResult result = enabled
            ? await Run("systemctl", ["disable", ServiceName])
            : await Run("systemctl", ["enable", ServiceName]);
        if (result.ExitCode != 0)
        {
            ShowFailure("切换开机自启失败", result);
            return false;
        }
        WriteColor(enabled ? "开机自启已关闭，当前运行状态不变。" : "开机自启已启用。", ConsoleColor.Green);
        return true;
    }

    private static void WriteManagedFiles(GateConfig config)
    {
        AtomicWrite(ServicePath, RenderService(config), "0644");
        AtomicWrite(TimerServicePath, RenderTimerService(), "0644");
        AtomicWrite(TimerPath, RenderTimer(), "0644");
        AtomicWrite(NginxSitePath, RenderNginx(config), "0644");
        AtomicWrite(LogrotatePath, RenderLogrotate(config), "0644");
        string legacySite = "/etc/nginx/sites-enabled/bakablog.conf";
        if (File.Exists(legacySite))
        {
            File.Delete(legacySite);
        }
        string defaultSite = "/etc/nginx/sites-enabled/default";
        if (File.Exists(defaultSite))
        {
            File.Delete(defaultSite);
        }
    }

    private static void WriteLogrotate(GateConfig config) =>
        AtomicWrite(LogrotatePath, RenderLogrotate(config), "0644");

    private static string RenderService(GateConfig config)
    {
        string root = SystemdQuote(config.ProjectRoot);
        return $"""
[Unit]
Description=baka blog (managed by bakagate)
After=network-online.target nginx.service
Wants=network-online.target nginx.service

[Service]
Type=simple
User=bakablog
Group=bakablog
WorkingDirectory={root}
EnvironmentFile={EnvironmentPath}
Environment=PYTHONDONTWRITEBYTECODE=1
RuntimeDirectory=bakablog
RuntimeDirectoryMode=0750
ExecStartPre=+{InstalledBinaryPath} --prepare-port
ExecStart=/bin/sh {RuntimeLaunchPath}
Restart=on-failure
RestartSec=5s
TimeoutStopSec=30s
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
ReadWritePaths={SystemdQuote(config.InstanceRoot)} {LogDirectory} /run/bakablog /etc/bakagate /etc/nginx/conf.d
StandardOutput=append:{LogDirectory}/service.log
StandardError=append:{LogDirectory}/service.log

[Install]
WantedBy=multi-user.target
""";
    }

    private static string RenderNginx(GateConfig config) => $$"""
# Managed by bakagate. Manual edits are overwritten.
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    return 444;
}

server {
    listen 443 ssl default_server;
    listen [::]:443 ssl default_server;
    ssl_reject_handshake on;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name {{config.Domain}};

    ssl_certificate {{CertificatePath}};
    ssl_certificate_key {{PrivateKeyPath}};
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_cache shared:BakaTLS:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;

    client_max_body_size 16m;
    access_log {{LogDirectory}}/nginx-access.log;
    error_log {{LogDirectory}}/nginx-error.log warn;

    location / {
        proxy_pass http://127.0.0.1:{{config.LocalPort}};
        proxy_http_version 1.1;
        proxy_set_header Host {{config.Domain}};
        proxy_set_header X-Forwarded-Host {{config.Domain}};
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header Accept-Encoding "";
        proxy_read_timeout 120s;
    }
}
""";

    private static string RenderLogrotate(GateConfig config) => $$"""
{{LogDirectory}}/*.log {
    daily
    maxsize {{config.MaxLogSizeMb}}M
    rotate {{config.RetentionFiles}}
    maxage {{config.RetentionDays}}
    missingok
    notifempty
    compress
    delaycompress
    copytruncate
    su root root
}
""";

    private static string RenderTimerService() => $"""
[Unit]
Description=Clean rotated baka blog logs

[Service]
Type=oneshot
ExecStart={InstalledBinaryPath} --maintain-logs
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths={LogDirectory}
""";

    private static string RenderTimer() => """
[Unit]
Description=Daily baka blog log maintenance

[Timer]
OnCalendar=daily
Persistent=true
RandomizedDelaySec=15m
Unit=bakagate-log-maintenance.service

[Install]
WantedBy=timers.target
""";

    private static void WriteEnvironment(GateConfig config, bool preserveSecret)
    {
        string? existingSecret = preserveSecret ? ReadEnvironmentValue("CLOUD_DIARY_SECRET_KEY") : null;
        string secret = existingSecret is { Length: >= 32 } ? existingSecret : Convert.ToHexString(RandomNumberGenerator.GetBytes(48)).ToLowerInvariant();
        string content = $"""
CLOUD_DIARY_ENV=production
CLOUD_DIARY_SECRET_KEY={secret}
CLOUD_DIARY_SITE_URL=https://{config.Domain}
CLOUD_DIARY_INSTANCE_PATH={config.InstanceRoot}
CLOUD_DIARY_TRUST_PROXY_HEADERS=1
CLOUD_DIARY_TEXT_COMPRESSION=0
""";
        AtomicWrite(EnvironmentPath, content, "0600");
    }

    private static string? ReadEnvironmentValue(string key)
    {
        if (!File.Exists(EnvironmentPath))
        {
            return null;
        }
        string prefix = key + "=";
        return File.ReadLines(EnvironmentPath)
            .FirstOrDefault(line => line.StartsWith(prefix, StringComparison.Ordinal))
            ?[prefix.Length..].Trim();
    }

    private static GateConfig ReadConfig()
    {
        GateConfig config = new();
        if (!File.Exists(ConfigPath))
        {
            string? root = FindProjectRoot();
            if (root is not null)
            {
                config.ProjectRoot = root;
            }
            return config;
        }
        Dictionary<string, string> values = File.ReadLines(ConfigPath)
            .Where(line => line.Contains('=') && !line.TrimStart().StartsWith('#'))
            .Select(line => line.Split('=', 2))
            .ToDictionary(parts => parts[0].Trim(), parts => parts[1].Trim(), StringComparer.Ordinal);
        config.Domain = values.GetValueOrDefault("DOMAIN", config.Domain);
        config.ProjectRoot = values.GetValueOrDefault("PROJECT_ROOT", config.ProjectRoot);
        config.InstanceRoot = values.GetValueOrDefault("INSTANCE_ROOT", config.InstanceRoot);
        config.LocalPort = ParseBounded(values.GetValueOrDefault("LOCAL_PORT"), 1024, 65535, config.LocalPort);
        config.RetentionDays = ParseBounded(values.GetValueOrDefault("RETENTION_DAYS"), 1, 3650, config.RetentionDays);
        config.RetentionFiles = ParseBounded(values.GetValueOrDefault("RETENTION_FILES"), 1, 365, config.RetentionFiles);
        config.MaxLogSizeMb = ParseBounded(values.GetValueOrDefault("MAX_LOG_SIZE_MB"), 1, 2048, config.MaxLogSizeMb);
        return config;
    }

    private static void WriteConfig(GateConfig config)
    {
        string content = $"""
# Managed by bakagate.
DOMAIN={config.Domain}
PROJECT_ROOT={config.ProjectRoot}
INSTANCE_ROOT={config.InstanceRoot}
LOCAL_PORT={config.LocalPort}
RETENTION_DAYS={config.RetentionDays}
RETENTION_FILES={config.RetentionFiles}
MAX_LOG_SIZE_MB={config.MaxLogSizeMb}
""";
        Directory.CreateDirectory(ConfigDirectory);
        AtomicWrite(ConfigPath, content, "0600");
    }

    private static int RenderTest(string[] args)
    {
        if (!TryValue(args, "--domain", out string? rawDomain) || !TryValue(args, "--project", out string? project) || !TryValue(args, "--output", out string? output))
        {
            throw new InvalidOperationException("--render-test 需要 --domain、--project 和 --output。");
        }
        GateConfig config = new() { Domain = NormalizeDomain(rawDomain!), ProjectRoot = Path.GetFullPath(project!) };
        if (TryValue(args, "--port", out string? rawPort))
        {
            config.LocalPort = ParseBounded(rawPort, 1024, 65535, -1);
            if (config.LocalPort < 0)
            {
                throw new InvalidOperationException("--port 必须在 1024 到 65535 之间。");
            }
        }
        Directory.CreateDirectory(output!);
        File.WriteAllText(Path.Combine(output!, "bakablog.service"), RenderService(config), Utf8NoBom);
        File.WriteAllText(Path.Combine(output!, "bakablog.nginx.conf"), RenderNginx(config), Utf8NoBom);
        File.WriteAllText(Path.Combine(output!, "bakablog.logrotate"), RenderLogrotate(config), Utf8NoBom);
        File.WriteAllText(Path.Combine(output!, "bakagate-log-maintenance.service"), RenderTimerService(), Utf8NoBom);
        File.WriteAllText(Path.Combine(output!, "bakagate-log-maintenance.timer"), RenderTimer(), Utf8NoBom);
        Console.WriteLine(output);
        return 0;
    }

    private static void CopySelf()
    {
        string source = Environment.ProcessPath ?? throw new InvalidOperationException("无法确定管理器二进制路径。");
        if (!Path.GetFullPath(source).Equals(InstalledBinaryPath, StringComparison.Ordinal))
        {
            AtomicCopy(source, InstalledBinaryPath);
        }
        Chmod("0755", InstalledBinaryPath);
    }

    private static async Task<bool> ValidateNginx()
    {
        CommandResult result = await Run("nginx", ["-t"]);
        if (result.ExitCode != 0)
        {
            ShowFailure("Nginx 配置检查失败，未重新加载", result);
            return false;
        }
        WriteColor("Nginx 配置检查通过。", ConsoleColor.Green);
        return true;
    }

    private static async Task<string> CertificateSummary()
    {
        if (!File.Exists(CertificatePath))
        {
            return "未安装";
        }
        CommandResult result = await Run("openssl", ["x509", "-in", CertificatePath, "-noout", "-enddate"]);
        if (result.ExitCode != 0)
        {
            return "无法读取";
        }
        return result.Output.Trim().Replace("notAfter=", "有效至 ", StringComparison.Ordinal);
    }

    private static string NormalizeDomain(string raw)
    {
        string value = raw.Trim().TrimEnd('.').ToLowerInvariant();
        if (value.Length == 0 || value.Contains("://", StringComparison.Ordinal) || value.Contains('/') || value.Contains('\\') || value.Contains(':') || value.Contains('*'))
        {
            throw new InvalidOperationException("域名只能填写一个完整主机名，不能包含协议、端口、路径或通配符。");
        }
        string ascii;
        try
        {
            ascii = new IdnMapping().GetAscii(value).ToLowerInvariant();
        }
        catch (ArgumentException)
        {
            throw new InvalidOperationException("域名包含无效字符。");
        }
        string[] labels = ascii.Split('.');
        if (ascii.Length > 253 || labels.Length < 2 || labels.Any(label => !SafeDomainLabel.IsMatch(label)) || IPAddress.TryParse(ascii, out _))
        {
            throw new InvalidOperationException("请输入有效的单个域名，不能使用 IP 地址或单段主机名。");
        }
        return ascii;
    }

    private static bool TryNormalizeDomain(string raw, out string normalized)
    {
        try
        {
            normalized = NormalizeDomain(raw);
            return true;
        }
        catch (InvalidOperationException)
        {
            normalized = "";
            return false;
        }
    }

    private static void ValidateProjectRoot(string value)
    {
        if (!Path.IsPathFullyQualified(value) || value.IndexOfAny(['\r', '\n', '\'']) >= 0 || !File.Exists(Path.Combine(value, "wsgi.py")) || !File.Exists(Path.Combine(value, "requirements.txt")))
        {
            throw new InvalidOperationException("项目目录必须是包含 wsgi.py 和 requirements.txt 的绝对路径。");
        }
    }

    private static void ValidateReadableRegularFile(string path, string label)
    {
        if (!Path.IsPathFullyQualified(path) || !File.Exists(path) || (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0)
        {
            throw new InvalidOperationException($"{label}必须是可读取的普通绝对路径文件，不能是符号链接。");
        }
    }

    private static string? FindProjectRoot()
    {
        foreach (string start in new[] { Directory.GetCurrentDirectory(), AppContext.BaseDirectory })
        {
            DirectoryInfo? directory = new(start);
            while (directory is not null)
            {
                if (File.Exists(Path.Combine(directory.FullName, "wsgi.py")) && File.Exists(Path.Combine(directory.FullName, "requirements.txt")))
                {
                    return directory.FullName;
                }
                directory = directory.Parent;
            }
        }
        return null;
    }

    private static void VerifySupportedLinux()
    {
        if (!IsSupportedLinux())
        {
            throw new InvalidOperationException("安装需要使用systemd的受支持Linux：Debian/Ubuntu、Fedora/RHEL系、Arch系或openSUSE/SLES。");
        }
    }

    private static bool IsSupportedLinux()
    {
        if (!OperatingSystem.IsLinux() || !Directory.Exists("/run/systemd/system"))
        {
            return false;
        }
        Dictionary<string, string> values = ReadOsRelease();
        string id = values.GetValueOrDefault("ID", "").ToLowerInvariant();
        string like = values.GetValueOrDefault("ID_LIKE", "").ToLowerInvariant();
        return id is "debian" or "ubuntu" or "fedora" or "rhel" or "centos" or "rocky" or "almalinux" or "arch" or "manjaro" or "opensuse-leap" or "opensuse-tumbleweed" or "sles"
            || new[] { "debian", "rhel", "fedora", "arch", "suse" }.Any(token => like.Contains(token, StringComparison.Ordinal));
    }

    private static Dictionary<string, string> ReadOsRelease()
    {
        if (!File.Exists("/etc/os-release"))
        {
            return new(StringComparer.Ordinal);
        }
        return File.ReadLines("/etc/os-release")
            .Where(line => line.Contains('='))
            .Select(line => line.Split('=', 2))
            .ToDictionary(parts => parts[0], parts => parts[1].Trim().Trim('"'), StringComparer.Ordinal);
    }

    private static string LinuxDescription()
    {
        if (!File.Exists("/etc/os-release"))
        {
            return RuntimeInformationDescription();
        }
        string? pretty = File.ReadLines("/etc/os-release").FirstOrDefault(line => line.StartsWith("PRETTY_NAME=", StringComparison.Ordinal));
        return (pretty?["PRETTY_NAME=".Length..].Trim().Trim('"') ?? "Linux") + $" · {System.Runtime.InteropServices.RuntimeInformation.OSArchitecture}";
    }

    private static string RuntimeInformationDescription() => $"{System.Runtime.InteropServices.RuntimeInformation.OSDescription} · {System.Runtime.InteropServices.RuntimeInformation.OSArchitecture}";

    private static void EnsureLinux()
    {
        if (!OperatingSystem.IsLinux())
        {
            throw new InvalidOperationException("bakagate 的部署与管理功能只能在 Linux 上运行；Windows 可使用 --render-test 验证模板。");
        }
    }

    private static void RequireRoot()
    {
        if (Environment.UserName != "root" && GetEffectiveUserId() != "0")
        {
            throw new InvalidOperationException("此操作需要 root 权限，请使用 sudo bakagate。");
        }
    }

    private static string GetEffectiveUserId()
    {
        try
        {
            using Process? process = Process.Start(new ProcessStartInfo("id", "-u") { RedirectStandardOutput = true, UseShellExecute = false });
            return process is null ? "" : process.StandardOutput.ReadToEnd().Trim();
        }
        catch
        {
            return "";
        }
    }

    private static async Task<CommandResult> Systemctl(params string[] arguments) => await Run("systemctl", arguments);

    private static async Task<CommandResult> Run(string executable, IReadOnlyList<string> arguments, string? workingDirectory = null, TimeSpan? timeout = null)
    {
        ProcessStartInfo info = new()
        {
            FileName = executable,
            WorkingDirectory = workingDirectory ?? Directory.GetCurrentDirectory(),
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Utf8NoBom,
            StandardErrorEncoding = Utf8NoBom,
        };
        if (Path.GetFileName(executable).Equals("apt-get", StringComparison.Ordinal))
        {
            info.Environment["DEBIAN_FRONTEND"] = "noninteractive";
        }
        foreach (string argument in arguments)
        {
            info.ArgumentList.Add(argument);
        }
        try
        {
            using Process? process = Process.Start(info);
            if (process is null)
            {
                return new(-1, "", $"无法启动 {executable}。");
            }
            Task<string> output = process.StandardOutput.ReadToEndAsync();
            Task<string> error = process.StandardError.ReadToEndAsync();
            using CancellationTokenSource cancellation = new(timeout ?? TimeSpan.FromMinutes(2));
            try
            {
                await process.WaitForExitAsync(cancellation.Token);
            }
            catch (OperationCanceledException)
            {
                process.Kill(entireProcessTree: true);
                return new(-1, await output, "操作超时。");
            }
            return new(process.ExitCode, await output, await error);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            return new(-1, "", error.Message);
        }
    }

    private static void AtomicWrite(string path, string content, string mode)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        string temporary = path + $".tmp-{Environment.ProcessId}-{RandomNumberGenerator.GetInt32(100000, 999999)}";
        try
        {
            File.WriteAllText(temporary, content.Replace("\r\n", "\n"), Utf8NoBom);
            Chmod(mode, temporary);
            File.Move(temporary, path, overwrite: true);
        }
        finally
        {
            File.Delete(temporary);
        }
    }

    private static void AtomicCopy(string source, string destination)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
        string temporary = destination + $".tmp-{Environment.ProcessId}-{RandomNumberGenerator.GetInt32(100000, 999999)}";
        try
        {
            File.Copy(source, temporary, overwrite: true);
            File.Move(temporary, destination, overwrite: true);
        }
        finally
        {
            File.Delete(temporary);
        }
    }

    private static void Chmod(string mode, params string[] paths)
    {
        foreach (string path in paths)
        {
            CommandResult result = Run("chmod", [mode, path]).GetAwaiter().GetResult();
            if (result.ExitCode != 0 && OperatingSystem.IsLinux())
            {
                throw new InvalidOperationException($"无法设置 {path} 的权限：{LastLines(result.Error, 2)}");
            }
        }
    }

    private static string SystemdQuote(string value) => "\"" + value.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";

    private static bool FixedEquals(string first, string second)
    {
        byte[] left = SHA256.HashData(Encoding.UTF8.GetBytes(first.Replace("\r", "").Trim()));
        byte[] right = SHA256.HashData(Encoding.UTF8.GetBytes(second.Replace("\r", "").Trim()));
        return CryptographicOperations.FixedTimeEquals(left, right);
    }

    private static string Prompt(string label, string fallback)
    {
        Console.Write($"{label}{(fallback.Length > 0 ? $" [{fallback}]" : "")}：");
        string value = (Console.ReadLine() ?? "").Trim();
        return value.Length == 0 ? fallback : value;
    }

    private static int PromptInt(string label, int fallback, int minimum, int maximum)
    {
        string raw = Prompt(label, fallback.ToString(CultureInfo.InvariantCulture));
        if (!int.TryParse(raw, out int value) || value < minimum || value > maximum)
        {
            throw new InvalidOperationException($"{label}必须在 {minimum} 到 {maximum} 之间。");
        }
        return value;
    }

    private static int ParseBounded(string? raw, int minimum, int maximum, int fallback) =>
        int.TryParse(raw, out int value) && value >= minimum && value <= maximum ? value : fallback;

    private static bool TryValue(string[] args, string name, out string? value)
    {
        int index = Array.FindIndex(args, item => item.Equals(name, StringComparison.OrdinalIgnoreCase));
        value = index >= 0 && index + 1 < args.Length ? args[index + 1] : null;
        return value is not null;
    }

    private static void SafeClear()
    {
        try { Console.Clear(); } catch (IOException) { }
    }

    private static void MenuLine(string number, string text, ConsoleColor color = ConsoleColor.Cyan)
    {
        WriteInlineColor(number, color);
        Console.WriteLine($"、{text}");
    }

    private static void WriteStatus(bool positive, string text) => WriteColor(positive ? $"[绿色] {text}" : $"[红色] {text}", positive ? ConsoleColor.Green : ConsoleColor.Red);

    private static bool Check(string label, bool success)
    {
        Console.Write($"{label,-24}");
        WriteStatus(success, success ? "通过" : "失败");
        return success;
    }

    private static void WriteColor(string text, ConsoleColor color)
    {
        ConsoleColor previous = Console.ForegroundColor;
        Console.ForegroundColor = color;
        Console.WriteLine(text);
        Console.ForegroundColor = previous;
    }

    private static void WriteInlineColor(string text, ConsoleColor color)
    {
        ConsoleColor previous = Console.ForegroundColor;
        Console.ForegroundColor = color;
        Console.Write(text);
        Console.ForegroundColor = previous;
    }

    private static void ShowResult(CommandResult result, string success)
    {
        if (result.ExitCode == 0) WriteColor(success, ConsoleColor.Green);
        else ShowFailure("操作失败", result);
    }

    private static void ShowFailure(string label, CommandResult result) => WriteColor($"{label}：{LastLines(result.Error + "\n" + result.Output, 8)}", ConsoleColor.Red);

    private static string LastLines(string value, int count) => string.Join(Environment.NewLine, value.Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).TakeLast(count));

    private static string ManagerVersion() => Assembly.GetExecutingAssembly().GetName().Version?.ToString(3) ?? "1.0.0";
}

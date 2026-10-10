using System.Diagnostics;
using System.Net;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.Win32;

namespace BakaLocalManager;

internal sealed record ServiceSpec(
    string Name,
    string ProductLabel,
    int Port,
    string HealthUrl,
    string HealthMarker,
    string EnvironmentName,
    string EnvironmentValue)
{
    internal static ServiceSpec Current()
    {
        string executable = Path.GetFileNameWithoutExtension(
            Environment.ProcessPath ?? AppContext.BaseDirectory
        );
        bool gateway = executable.Contains("gateway", StringComparison.OrdinalIgnoreCase);
        return gateway
            ? new(
                "bakagateway",
                "Baka Gateway",
                5100,
                "http://127.0.0.1:5100/healthz",
                "\"status\":\"ok\"",
                "CLOUD_GATEWAY_ENV",
                "local"
            )
            : new(
                "bakablog",
                "Baka Blog",
                5000,
                "http://127.0.0.1:5000/healthz",
                "\"service\":\"cloudtrace\"",
                "CLOUD_DIARY_ENV",
                "development"
            );
    }
}

internal sealed class RuntimeState
{
    public int RootProcessId { get; set; }
    public DateTimeOffset StartedAtUtc { get; set; }
}

internal sealed record ServiceStatus(
    bool Running,
    IReadOnlyList<int> ListenerProcessIds,
    bool StartupEnabled,
    string? Version);

internal static class Program
{
    private const int SwHide = 0;
    private static readonly UTF8Encoding Utf8NoBom = new(false);
    private static readonly ServiceSpec Spec = ServiceSpec.Current();
    private static readonly HttpClient Http = new()
    {
        Timeout = TimeSpan.FromSeconds(2),
    };
    private static string ProjectRoot = "";

    [DllImport("kernel32.dll")]
    private static extern uint SetConsoleOutputCP(uint codePage);

    [DllImport("kernel32.dll")]
    private static extern uint SetConsoleCP(uint codePage);

    [DllImport("kernel32.dll")]
    private static extern nint GetConsoleWindow();

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool ShowWindow(nint windowHandle, int command);

    private static async Task<int> Main(string[] args)
    {
        ConfigureConsole();
        ProjectRoot = FindProjectRoot();

        if (args.Contains("--autostart", StringComparer.OrdinalIgnoreCase))
        {
            HideConsole();
            return await StartService(showMessages: false) ? 0 : 1;
        }
        if (args.Contains("--status-json", StringComparer.OrdinalIgnoreCase))
        {
            ServiceStatus status = await ReadStatus();
            Console.WriteLine(
                JsonSerializer.Serialize(
                    new
                    {
                        service = Spec.Name,
                        running = status.Running,
                        startup_enabled = status.StartupEnabled,
                        port = Spec.Port,
                        listener_pids = status.ListenerProcessIds,
                        version = status.Version,
                        windows = WindowsDescription(),
                    }
                )
            );
            return 0;
        }
        if (args.Contains("--start", StringComparer.OrdinalIgnoreCase))
        {
            return await StartService(showMessages: true) ? 0 : 1;
        }
        if (args.Contains("--stop", StringComparer.OrdinalIgnoreCase))
        {
            return await StopService(showMessages: true) ? 0 : 1;
        }
        if (args.Contains("--restart", StringComparer.OrdinalIgnoreCase))
        {
            return await RestartService() ? 0 : 1;
        }
        if (args.Contains("--recovery-url", StringComparer.OrdinalIgnoreCase))
        {
            return await ShowRecoveryUrl(openBrowser: false) ? 0 : 1;
        }
        if (args.Contains("--toggle-startup", StringComparer.OrdinalIgnoreCase))
        {
            ToggleStartup(showMessages: true);
            return 0;
        }
        if (args.Contains("--reset-manager", StringComparer.OrdinalIgnoreCase))
        {
            await ResetManagerOptions(requireConfirmation: false);
            return 0;
        }

        Console.Title = $"{Spec.Name} · 本地服务管理器";
        await RunMenu();
        return 0;
    }

    private static void ConfigureConsole()
    {
        try
        {
            SetConsoleOutputCP(65001);
            SetConsoleCP(65001);
            Console.OutputEncoding = Utf8NoBom;
            Console.InputEncoding = Utf8NoBom;
        }
        catch (IOException)
        {
            // Autostart can intentionally run without a visible console.
        }
    }

    private static void HideConsole()
    {
        nint handle = GetConsoleWindow();
        if (handle != nint.Zero)
        {
            ShowWindow(handle, SwHide);
        }
    }

    private static string FindProjectRoot()
    {
        foreach (string candidate in new[] { AppContext.BaseDirectory, Directory.GetCurrentDirectory() })
        {
            DirectoryInfo? directory = new(candidate);
            while (directory is not null)
            {
                if (
                    File.Exists(Path.Combine(directory.FullName, "start.bat"))
                    && File.Exists(Path.Combine(directory.FullName, "wsgi.py"))
                )
                {
                    return directory.FullName;
                }
                directory = directory.Parent;
            }
        }
        throw new InvalidOperationException(
            $"{Spec.Name} 必须放在包含 start.bat 和 wsgi.py 的项目目录中运行。"
        );
    }

    private static async Task RunMenu()
    {
        while (true)
        {
            SafeClear();
            ServiceStatus status = await ReadStatus();
            DrawHeader(status);
            DrawMenu();
            Console.Write("请输入操作编号：");
            string? input = Console.ReadLine();
            if (input is null)
            {
                return;
            }
            string choice = input.Trim();
            Console.WriteLine();
            switch (choice)
            {
                case "1":
                    await StartService(showMessages: true);
                    break;
                case "2":
                    await StopService(showMessages: true);
                    break;
                case "3":
                    await RestartService();
                    break;
                case "4":
                    await ShowRecoveryUrl(openBrowser: true);
                    break;
                case "5":
                    await ResetManagerOptions(requireConfirmation: true);
                    break;
                case "6":
                    ToggleStartup(showMessages: true);
                    break;
                case "0":
                    return;
                default:
                    WriteColor("无法识别该编号。", ConsoleColor.Red);
                    break;
            }
            Console.WriteLine();
            WriteColor("按任意键返回主菜单……", ConsoleColor.DarkGray);
            if (!Console.IsInputRedirected)
            {
                Console.ReadKey(intercept: true);
            }
        }
    }

    private static void SafeClear()
    {
        try
        {
            Console.Clear();
        }
        catch (IOException)
        {
            // Redirected test output has no screen buffer to clear.
        }
    }

    private static void DrawHeader(ServiceStatus status)
    {
        WriteColor("╭────────────────────────────────────────────────────╮", ConsoleColor.Cyan);
        WriteColor($"│  {Spec.Name,-48}│", ConsoleColor.Cyan);
        WriteColor("╰────────────────────────────────────────────────────╯", ConsoleColor.Cyan);
        Console.WriteLine($"服务名称：{Spec.Name}（{Spec.ProductLabel}）");
        Console.WriteLine($"Windows：{WindowsDescription()}");
        Console.Write("运行状态：");
        WriteStatus(status.Running, status.Running ? "运行中" : "已停止");
        Console.Write("开机自启：");
        WriteStatus(status.StartupEnabled, status.StartupEnabled ? "已启用" : "未启用");
        Console.WriteLine($"监听端口：{Spec.Port}");
        Console.WriteLine(
            $"进程编号：{(status.ListenerProcessIds.Count > 0 ? string.Join(", ", status.ListenerProcessIds) : "—")}"
        );
        Console.WriteLine($"应用版本：{status.Version ?? "无法读取"}");
        Console.WriteLine($"管理器版本：{ManagerVersion()}");
        Console.WriteLine();
    }

    private static void DrawMenu()
    {
        WriteInlineColor("1", ConsoleColor.Cyan);
        Console.WriteLine($"、启动 {Spec.Name}");
        WriteInlineColor("2", ConsoleColor.Cyan);
        Console.WriteLine($"、停止 {Spec.Name}");
        WriteInlineColor("3", ConsoleColor.Cyan);
        Console.WriteLine($"、重新启动 {Spec.Name}");
        WriteInlineColor("4", ConsoleColor.Cyan);
        Console.WriteLine("、获取本机临时恢复入口");
        WriteInlineColor("5", ConsoleColor.Cyan);
        Console.WriteLine("、重置管理器选项（不会删除数据库或业务文件）");
        WriteInlineColor("6", ConsoleColor.Cyan);
        Console.WriteLine("、切换开机自启");
        WriteInlineColor("0", ConsoleColor.DarkGray);
        Console.WriteLine("、退出");
        Console.WriteLine();
    }

    private static void WriteStatus(bool positive, string text)
    {
        WriteColor(
            positive ? $"[绿色] {text}" : $"[红色] {text}",
            positive ? ConsoleColor.Green : ConsoleColor.Red
        );
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

    private static async Task<ServiceStatus> ReadStatus()
    {
        string? version = null;
        bool running = false;
        try
        {
            using HttpResponseMessage response = await Http.GetAsync(Spec.HealthUrl);
            string body = await response.Content.ReadAsStringAsync();
            running = response.IsSuccessStatusCode && body.Contains(
                Spec.HealthMarker,
                StringComparison.OrdinalIgnoreCase
            );
            if (running)
            {
                using JsonDocument document = JsonDocument.Parse(body);
                if (document.RootElement.TryGetProperty("version", out JsonElement value))
                {
                    version = value.GetString();
                }
            }
        }
        catch (HttpRequestException)
        {
            running = false;
        }
        catch (TaskCanceledException)
        {
            running = false;
        }
        return new(
            running,
            FindListenerProcessIds(),
            IsStartupEnabled(),
            version
        );
    }

    private static async Task<bool> StartService(bool showMessages)
    {
        ServiceStatus current = await ReadStatus();
        if (current.Running)
        {
            if (showMessages)
            {
                WriteColor($"{Spec.Name} 已经在运行。", ConsoleColor.Green);
            }
            return true;
        }
        if (current.ListenerProcessIds.Count > 0)
        {
            if (showMessages)
            {
                WriteColor(
                    $"端口 {Spec.Port} 已被其他程序占用，未执行启动。",
                    ConsoleColor.Red
                );
            }
            return false;
        }

        string startBatch = Path.Combine(ProjectRoot, "start.bat");
        if (!File.Exists(startBatch))
        {
            if (showMessages)
            {
                WriteColor("找不到 start.bat。", ConsoleColor.Red);
            }
            return false;
        }
        if (showMessages)
        {
            WriteColor("正在执行离线依赖、数据库迁移和应用预检……", ConsoleColor.Yellow);
        }
        ProcessResult preflight = await RunProcess(
            "cmd.exe",
            ["/d", "/c", "start.bat", "--check-only"],
            TimeSpan.FromMinutes(3)
        );
        if (preflight.ExitCode != 0)
        {
            if (showMessages)
            {
                WriteColor("启动预检失败：", ConsoleColor.Red);
                Console.WriteLine(LastLines(preflight.Output + preflight.Error, 16));
            }
            return false;
        }

        string logs = Path.Combine(ProjectRoot, "instance", "logs");
        string runtime = Path.Combine(ProjectRoot, "instance", "runtime");
        Directory.CreateDirectory(logs);
        Directory.CreateDirectory(runtime);
        string logPath = Path.Combine(logs, $"{Spec.Name}-service.log");
        string relativeLog = Path.Combine(
            "instance",
            "logs",
            $"{Spec.Name}-service.log"
        );
        string command = $"call start.bat 1>>{relativeLog} 2>>&1";
        ProcessStartInfo startInfo = new()
        {
            FileName = "cmd.exe",
            Arguments = $"/d /s /c \"{command}\"",
            WorkingDirectory = ProjectRoot,
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        startInfo.Environment[Spec.EnvironmentName] = Spec.EnvironmentValue;
        startInfo.Environment["FLASK_DEBUG"] = "0";
        startInfo.Environment["PYTHONUTF8"] = "1";
        Process? process = Process.Start(startInfo);
        if (process is null)
        {
            if (showMessages)
            {
                WriteColor("无法创建服务进程。", ConsoleColor.Red);
            }
            return false;
        }
        WriteRuntimeState(
            new RuntimeState
            {
                RootProcessId = process.Id,
                StartedAtUtc = process.StartTime.ToUniversalTime(),
            }
        );
        bool ready = await WaitForRunning(expected: true, TimeSpan.FromSeconds(35));
        if (showMessages)
        {
            WriteColor(
                ready ? $"{Spec.Name} 启动成功。" : $"{Spec.Name} 启动超时，请检查日志：{logPath}",
                ready ? ConsoleColor.Green : ConsoleColor.Red
            );
        }
        return ready;
    }

    private static async Task<bool> StopService(bool showMessages)
    {
        ServiceStatus current = await ReadStatus();
        RuntimeState? state = ReadRuntimeState();
        if (!current.Running && current.ListenerProcessIds.Count == 0)
        {
            DeleteRuntimeState();
            if (showMessages)
            {
                WriteColor($"{Spec.Name} 已经停止。", ConsoleColor.Green);
            }
            return true;
        }
        if (showMessages)
        {
            WriteColor($"正在停止 {Spec.Name}……", ConsoleColor.Yellow);
        }
        if (state is not null)
        {
            TryKillManagedRoot(state);
        }
        await Task.Delay(700);
        if ((await ReadStatus()).Running)
        {
            foreach (int processId in current.ListenerProcessIds)
            {
                TryKillProcessTree(processId);
            }
        }
        bool stopped = await WaitForRunning(expected: false, TimeSpan.FromSeconds(15));
        DeleteRuntimeState();
        if (showMessages)
        {
            WriteColor(
                stopped ? $"{Spec.Name} 已停止。" : $"{Spec.Name} 未能在规定时间内停止。",
                stopped ? ConsoleColor.Green : ConsoleColor.Red
            );
        }
        return stopped;
    }

    private static async Task<bool> RestartService()
    {
        if (!await StopService(showMessages: true))
        {
            return false;
        }
        await Task.Delay(500);
        return await StartService(showMessages: true);
    }

    private static async Task<bool> ShowRecoveryUrl(bool openBrowser)
    {
        if (!(await ReadStatus()).Running && !await StartService(showMessages: true))
        {
            return false;
        }
        string python = Path.Combine(ProjectRoot, ".venv", "Scripts", "python.exe");
        if (!File.Exists(python))
        {
            WriteColor("找不到项目本地 Python。", ConsoleColor.Red);
            return false;
        }
        ProcessResult result = await RunProcess(
            python,
            ["-m", "flask", "--app", "wsgi:app", "local-recovery-link"],
            TimeSpan.FromSeconds(30)
        );
        string? url = (result.Output + "\n" + result.Error)
            .Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries)
            .FirstOrDefault(line => line.StartsWith("RECOVERY_URL=", StringComparison.Ordinal))
            ?.Remove(0, "RECOVERY_URL=".Length)
            .Trim();
        if (result.ExitCode != 0 || string.IsNullOrWhiteSpace(url))
        {
            WriteColor("无法生成恢复入口：", ConsoleColor.Red);
            Console.WriteLine(LastLines(result.Output + result.Error, 10));
            return false;
        }
        bool bootstrap = url.Contains("/setup/administrator/", StringComparison.Ordinal);
        WriteColor(
            bootstrap
                ? "当前没有活动管理员，已提供本机首位管理员创建入口："
                : "已生成仅限本机、五分钟有效且只能使用一次的恢复入口：",
            ConsoleColor.Yellow
        );
        WriteColor(url, ConsoleColor.Cyan);
        if (openBrowser)
        {
            Console.Write("是否立即使用默认浏览器打开？[Y/n]：");
            string answer = (Console.ReadLine() ?? "").Trim();
            if (answer.Length == 0 || answer.Equals("y", StringComparison.OrdinalIgnoreCase))
            {
                Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
                WriteColor("已交给默认浏览器打开。", ConsoleColor.Green);
            }
        }
        return true;
    }

    private static async Task ResetManagerOptions(bool requireConfirmation)
    {
        if (requireConfirmation)
        {
            WriteColor(
                "此操作会停止服务、关闭开机自启并删除管理器状态和管理器日志；不会删除数据库、上传文件或网站设置。",
                ConsoleColor.Yellow
            );
            Console.Write("请输入 RESET 确认：");
            if (!string.Equals(Console.ReadLine()?.Trim(), "RESET", StringComparison.Ordinal))
            {
                WriteColor("已取消。", ConsoleColor.DarkGray);
                return;
            }
        }
        await StopService(showMessages: false);
        DisableStartup();
        DeleteRuntimeState();
        string log = Path.Combine(ProjectRoot, "instance", "logs", $"{Spec.Name}-service.log");
        try
        {
            File.Delete(log);
        }
        catch (IOException)
        {
            // The service has already been stopped; a short-lived file handle may remain.
        }
        WriteColor("管理器选项已经重置，业务数据保持不变。", ConsoleColor.Green);
    }

    private static async Task<bool> WaitForRunning(bool expected, TimeSpan timeout)
    {
        DateTimeOffset deadline = DateTimeOffset.UtcNow + timeout;
        while (DateTimeOffset.UtcNow < deadline)
        {
            bool running = (await ReadStatus()).Running;
            if (running == expected)
            {
                return true;
            }
            await Task.Delay(500);
        }
        return (await ReadStatus()).Running == expected;
    }

    private static IReadOnlyList<int> FindListenerProcessIds()
    {
        try
        {
            ProcessStartInfo info = new()
            {
                FileName = "netstat.exe",
                Arguments = "-ano -p tcp",
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                StandardOutputEncoding = Encoding.ASCII,
            };
            using Process? process = Process.Start(info);
            if (process is null)
            {
                return [];
            }
            string output = process.StandardOutput.ReadToEnd();
            process.WaitForExit(5000);
            Regex pattern = new(
                $@"^\s*TCP\s+\S+:{Spec.Port}\s+\S+\s+LISTENING\s+(\d+)\s*$",
                RegexOptions.Multiline | RegexOptions.IgnoreCase
            );
            return pattern
                .Matches(output)
                .Select(match => int.Parse(match.Groups[1].Value))
                .Distinct()
                .ToArray();
        }
        catch (InvalidOperationException)
        {
            return [];
        }
    }

    private static void TryKillManagedRoot(RuntimeState state)
    {
        try
        {
            using Process process = Process.GetProcessById(state.RootProcessId);
            DateTimeOffset started = process.StartTime.ToUniversalTime();
            if (Math.Abs((started - state.StartedAtUtc).TotalSeconds) <= 3)
            {
                process.Kill(entireProcessTree: true);
                process.WaitForExit(5000);
            }
        }
        catch (ArgumentException)
        {
            // The recorded process already exited.
        }
        catch (InvalidOperationException)
        {
            // The recorded process already exited.
        }
    }

    private static void TryKillProcessTree(int processId)
    {
        if (processId == Environment.ProcessId)
        {
            return;
        }
        try
        {
            using Process process = Process.GetProcessById(processId);
            process.Kill(entireProcessTree: true);
            process.WaitForExit(5000);
        }
        catch (ArgumentException)
        {
            // The listener exited between netstat and termination.
        }
        catch (InvalidOperationException)
        {
            // The listener exited between netstat and termination.
        }
    }

    private static string RuntimeStatePath() =>
        Path.Combine(ProjectRoot, "instance", "runtime", $"{Spec.Name}.json");

    private static RuntimeState? ReadRuntimeState()
    {
        try
        {
            string path = RuntimeStatePath();
            return File.Exists(path)
                ? JsonSerializer.Deserialize<RuntimeState>(File.ReadAllText(path, Encoding.UTF8))
                : null;
        }
        catch (JsonException)
        {
            return null;
        }
        catch (IOException)
        {
            return null;
        }
    }

    private static void WriteRuntimeState(RuntimeState state)
    {
        string path = RuntimeStatePath();
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, JsonSerializer.Serialize(state), Utf8NoBom);
    }

    private static void DeleteRuntimeState()
    {
        try
        {
            File.Delete(RuntimeStatePath());
        }
        catch (IOException)
        {
            // A stale state file does not change the real health status.
        }
    }

    private static RegistryKey OpenStartupKey(bool writable) =>
        Registry.CurrentUser.CreateSubKey(
            @"Software\Microsoft\Windows\CurrentVersion\Run",
            writable
        ) ?? throw new InvalidOperationException("无法打开当前用户开机启动注册表。");

    private static bool IsStartupEnabled()
    {
        if (!OperatingSystem.IsWindows())
        {
            return false;
        }
        using RegistryKey key = OpenStartupKey(writable: false);
        return key.GetValue(Spec.Name) is string value && value.Contains(
            "--autostart",
            StringComparison.OrdinalIgnoreCase
        );
    }

    private static void ToggleStartup(bool showMessages)
    {
        if (IsStartupEnabled())
        {
            DisableStartup();
            if (showMessages)
            {
                WriteColor($"{Spec.Name} 开机自启已关闭。", ConsoleColor.Green);
            }
            return;
        }
        string executable = Environment.ProcessPath
            ?? throw new InvalidOperationException("无法确定管理器路径。");
        using RegistryKey key = OpenStartupKey(writable: true);
        key.SetValue(Spec.Name, $"\"{executable}\" --autostart", RegistryValueKind.String);
        if (showMessages)
        {
            WriteColor($"{Spec.Name} 开机自启已启用（当前Windows用户）。", ConsoleColor.Green);
        }
    }

    private static void DisableStartup()
    {
        using RegistryKey key = OpenStartupKey(writable: true);
        key.DeleteValue(Spec.Name, throwOnMissingValue: false);
    }

    private static async Task<ProcessResult> RunProcess(
        string executable,
        IReadOnlyList<string> arguments,
        TimeSpan timeout)
    {
        ProcessStartInfo info = new()
        {
            FileName = executable,
            WorkingDirectory = ProjectRoot,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Utf8NoBom,
            StandardErrorEncoding = Utf8NoBom,
        };
        foreach (string argument in arguments)
        {
            info.ArgumentList.Add(argument);
        }
        info.Environment[Spec.EnvironmentName] = Spec.EnvironmentValue;
        info.Environment["FLASK_DEBUG"] = "0";
        info.Environment["PYTHONUTF8"] = "1";
        using Process? process = Process.Start(info);
        if (process is null)
        {
            return new(-1, "", "无法创建子进程。");
        }
        Task<string> outputTask = process.StandardOutput.ReadToEndAsync();
        Task<string> errorTask = process.StandardError.ReadToEndAsync();
        using CancellationTokenSource cancellation = new(timeout);
        try
        {
            await process.WaitForExitAsync(cancellation.Token);
        }
        catch (OperationCanceledException)
        {
            process.Kill(entireProcessTree: true);
            return new(-1, await outputTask, "操作超时。");
        }
        return new(process.ExitCode, await outputTask, await errorTask);
    }

    private static string LastLines(string value, int count)
    {
        string[] lines = value.Split(
            ['\r', '\n'],
            StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries
        );
        return string.Join(Environment.NewLine, lines.TakeLast(count));
    }

    private static string ManagerVersion()
    {
        string executable = Environment.ProcessPath ?? "";
        return FileVersionInfo.GetVersionInfo(executable).FileVersion ?? "1.0.0.0";
    }

    private static string WindowsDescription()
    {
        Version version = Environment.OSVersion.Version;
        string product = version.Build >= 22000 ? "Windows 11" : "Windows 10";
        string? displayVersion = Registry.GetValue(
            @"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion",
            "DisplayVersion",
            null
        ) as string;
        string architecture = RuntimeInformation.OSArchitecture.ToString();
        return $"{product} {displayVersion ?? ""} (Build {version.Build}) · {architecture}".Replace(
            "  ",
            " "
        );
    }

    private sealed record ProcessResult(int ExitCode, string Output, string Error);
}

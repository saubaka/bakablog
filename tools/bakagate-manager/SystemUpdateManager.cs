using System.Diagnostics;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace BakaGateManager;

internal static class SystemUpdateManager
{
    private const string ManifestUrl = "https://raw.githubusercontent.com/saubaka/bakablog/main/updates/stable.json";
    private const string ConfigPath = "/etc/bakagate/bakagate.conf";
    private const string EnvironmentPath = "/etc/bakablog.env";
    private const string ServiceName = "bakablog.service";
    private const long MaximumArchiveBytes = 2L * 1024 * 1024 * 1024;
    private const long MaximumExpandedBytes = 8L * 1024 * 1024 * 1024;
    private const int MaximumArchiveFiles = 100_000;
    private static readonly string[] AllowedHosts = ["github.com", "objects.githubusercontent.com", "raw.githubusercontent.com"];
    private static readonly HttpClient Http = new(new HttpClientHandler { AllowAutoRedirect = true }) { Timeout = TimeSpan.FromMinutes(10) };

    internal static async Task<bool> CheckAsync(bool download)
    {
        UpdateConfig config = ReadConfig();
        Directory.CreateDirectory(config.UpdateRoot);
        WriteState(config, "checking", 5, "正在连接官方仓库");
        try
        {
            JsonObject manifest = await FetchManifest();
            string latest = RequiredString(manifest, "version");
            string current = ReadCurrentVersion(config.ProjectRoot);
            bool available = CompareVersion(latest, current) > 0;
            JsonObject state = ReadState(config);
            state["current_version"] = current;
            state["latest_version"] = latest;
            state["available"] = available;
            state["release"] = manifest.DeepClone();
            state["package"] = manifest["package"]?.DeepClone();
            state["checked_at"] = DateTimeOffset.UtcNow.ToString("O");
            WriteState(config, state, available ? "available" : "current", 100, available ? $"发现新版本 v{latest}" : "当前已经是最新版本");
            if (!available)
            {
                Console.WriteLine("当前已经是最新版本。");
                return true;
            }
            Console.WriteLine($"发现新版本 v{latest}。");
            return !download || await DownloadAsync(config, state);
        }
        catch (Exception error)
        {
            WriteState(config, "error", 0, SafeMessage(error));
            Console.Error.WriteLine(SafeMessage(error));
            return false;
        }
    }

    internal static async Task<bool> InstallAsync()
    {
        UpdateConfig config = ReadConfig();
        JsonObject state = ReadState(config);
        string archive = config.PackagePath;
        if (!File.Exists(archive))
        {
            Console.Error.WriteLine("尚未找到已经下载并校验的软件包。");
            return false;
        }
        string expectedHash = state["package"]?["sha256"]?.GetValue<string>() ?? "";
        if (!Regex.IsMatch(expectedHash, "^[a-f0-9]{64}$") || !FixedHash(archive, expectedHash))
        {
            WriteState(config, state, "error", 0, "软件包 SHA-256 复核失败");
            return false;
        }
        string targetVersion;
        using (ZipArchive zip = ZipFile.OpenRead(archive))
        {
            ValidateArchive(zip);
            ZipArchiveEntry descriptor = zip.GetEntry("update.json") ?? throw new InvalidOperationException("软件包缺少 update.json。");
            using Stream stream = descriptor.Open();
            JsonObject packageManifest = JsonNode.Parse(stream) as JsonObject ?? throw new InvalidOperationException("软件包描述无效。");
            if (packageManifest["schema_version"]?.GetValue<int>() != 1)
            {
                throw new InvalidOperationException("软件包格式版本无效。");
            }
            targetVersion = RequiredString(packageManifest, "version");
            if (!string.Equals(targetVersion, state["latest_version"]?.GetValue<string>(), StringComparison.Ordinal))
            {
                throw new InvalidOperationException("软件包版本与已检查版本不一致。");
            }
        }

        string parent = Directory.GetParent(config.ProjectRoot)?.FullName ?? throw new InvalidOperationException("项目目录没有有效的父目录。");
        string token = DateTime.UtcNow.ToString("yyyyMMdd-HHmmss") + "-" + RandomNumberGenerator.GetHexString(6).ToLowerInvariant();
        string stage = Path.Combine(parent, ".bakablog-stage-" + token);
        string oldCode = Path.Combine(parent, ".bakablog-rollback-" + token);
        string failedCode = Path.Combine(parent, ".bakablog-failed-" + token);
        string backup = Path.Combine(config.UpdateRoot, "backups", token + ".zip");
        bool stopped = false;
        try
        {
            EnsureDiskSpace(config, archive);
            WriteState(config, state, "installing", 8, "正在建立同盘暂存副本");
            CopyTree(config.ProjectRoot, stage);
            ExtractPayload(archive, stage);
            await Run("chown", ["-R", "root:root", stage]);
            WriteState(config, state, "installing", 30, "正在停止服务并创建完整数据备份");
            await RequireSuccess("systemctl", ["stop", ServiceName], "无法停止应用服务");
            stopped = true;
            Directory.CreateDirectory(Path.GetDirectoryName(backup)!);
            await Run("chown", ["-R", "bakablog:bakablog", config.UpdateRoot]);
            await RunFlask(config, config.ProjectRoot, ["site-backup", "--output", backup]);

            WriteState(config, state, "installing", 48, "正在原子切换应用代码");
            Directory.Move(config.ProjectRoot, oldCode);
            Directory.Move(stage, config.ProjectRoot);

            WriteState(config, state, "installing", 62, "正在安装依赖并执行数据库迁移");
            if (!await PreparePython(config) || !await RunMigrations(config))
            {
                throw new InvalidOperationException("依赖、迁移或系统检查未通过。");
            }
            await Run("systemctl", ["start", ServiceName]);
            if (!await WaitForHealth(config.LocalPort))
            {
                throw new InvalidOperationException("新版本健康检查未通过。");
            }
            JsonObject rollback = new()
            {
                ["schema_version"] = 1,
                ["created_at"] = DateTimeOffset.UtcNow.ToString("O"),
                ["from_version"] = ReadCurrentVersion(oldCode),
                ["to_version"] = targetVersion,
                ["code_path"] = oldCode,
                ["data_backup"] = backup,
            };
            AtomicJson(config.RollbackPath, rollback);
            await Run("chown", ["bakablog:bakablog", config.RollbackPath]);
            state["current_version"] = targetVersion;
            state["available"] = false;
            state["downloaded"] = false;
            state["can_install"] = false;
            state["can_rollback"] = true;
            WriteState(config, state, "completed", 100, $"v{targetVersion} 安装完成，健康检查已通过");
            TryInstallBundledManager(config.ProjectRoot);
            Console.WriteLine($"v{targetVersion} 安装完成。");
            return true;
        }
        catch (Exception error)
        {
            if (!stopped)
            {
                WriteState(config, state, "error", 0, "安装准备未通过，当前站点没有被修改");
                Console.Error.WriteLine(SafeMessage(error));
                return false;
            }
            WriteState(config, state, "rolling_back", 72, "安装失败，正在恢复更新前状态");
            try
            {
                await Run("systemctl", ["stop", ServiceName]);
                if (Directory.Exists(config.ProjectRoot) && Directory.Exists(oldCode)) Directory.Move(config.ProjectRoot, failedCode);
                if (Directory.Exists(oldCode)) Directory.Move(oldCode, config.ProjectRoot);
                if (File.Exists(backup)) await RunFlask(config, config.ProjectRoot, ["site-restore", backup, "--yes"]);
                await Run("systemctl", ["start", ServiceName]);
                await WaitForHealth(config.LocalPort);
                WriteState(config, state, "rolled_back", 100, "安装失败，旧代码与数据已经完整恢复");
            }
            catch (Exception rollbackError)
            {
                WriteState(config, state, "error", 0, "安装失败且自动回退未完成，请立即运行 bakablog --update-rollback");
                Console.Error.WriteLine(rollbackError.Message);
            }
            Console.Error.WriteLine(SafeMessage(error));
            return false;
        }
        finally
        {
            if (!stopped && Directory.Exists(stage)) Directory.Delete(stage, true);
        }
    }

    internal static async Task<bool> RollbackAsync()
    {
        UpdateConfig config = ReadConfig();
        if (!File.Exists(config.RollbackPath))
        {
            Console.Error.WriteLine("没有可用的更新前备份。");
            return false;
        }
        JsonObject rollback = JsonNode.Parse(await File.ReadAllTextAsync(config.RollbackPath)) as JsonObject ?? throw new InvalidOperationException("回退记录无效。");
        string oldCode = RequiredPath(rollback, "code_path");
        string backup = RequiredPath(rollback, "data_backup");
        if (!Directory.Exists(oldCode) || !File.Exists(backup)) throw new InvalidOperationException("回退代码或数据备份已经不存在。");
        string failedCode = config.ProjectRoot + ".before-rollback-" + DateTime.UtcNow.ToString("yyyyMMdd-HHmmss");
        JsonObject state = ReadState(config);
        WriteState(config, state, "rolling_back", 10, "正在停止服务并恢复上一版本");
        try
        {
            await RequireSuccess("systemctl", ["stop", ServiceName], "无法停止应用服务");
            Directory.Move(config.ProjectRoot, failedCode);
            Directory.Move(oldCode, config.ProjectRoot);
            await RunFlask(config, config.ProjectRoot, ["site-restore", backup, "--yes"]);
            if (!await RunMigrations(config)) throw new InvalidOperationException("回退后的迁移或系统检查失败。");
            await Run("systemctl", ["start", ServiceName]);
            if (!await WaitForHealth(config.LocalPort)) throw new InvalidOperationException("回退版本健康检查失败。");
            File.Delete(config.RollbackPath);
            state["current_version"] = ReadCurrentVersion(config.ProjectRoot);
            state["can_rollback"] = false;
            WriteState(config, state, "rolled_back", 100, "代码、数据库与媒体已经回退到上一版本");
            Console.WriteLine("完整回退已经完成。");
            return true;
        }
        catch (Exception error)
        {
            WriteState(config, state, "error", 0, "回退未完成，已保留全部备份，请检查服务日志");
            Console.Error.WriteLine(SafeMessage(error));
            return false;
        }
    }

    internal static async Task<bool> ProcessRequestAsync()
    {
        UpdateConfig config = ReadConfig();
        if (!File.Exists(config.RequestPath)) return true;
        JsonObject request = JsonNode.Parse(await File.ReadAllTextAsync(config.RequestPath)) as JsonObject ?? throw new InvalidOperationException("更新请求格式无效。");
        File.Delete(config.RequestPath);
        if (request["schema_version"]?.GetValue<int>() != 1) throw new InvalidOperationException("更新请求版本无效。");
        return request["action"]?.GetValue<string>() switch
        {
            "install" => await InstallAsync(),
            "rollback" => await RollbackAsync(),
            _ => throw new InvalidOperationException("更新请求包含不支持的动作。"),
        };
    }

    private static async Task<bool> DownloadAsync(UpdateConfig config, JsonObject state)
    {
        JsonObject package = state["package"] as JsonObject ?? throw new InvalidOperationException("版本清单没有软件包信息。");
        Uri url = ValidateUrl(RequiredString(package, "url"));
        long expected = package["size"]?.GetValue<long>() ?? 0;
        string checksum = RequiredString(package, "sha256").ToLowerInvariant();
        if (expected <= 0 || expected > MaximumArchiveBytes || !Regex.IsMatch(checksum, "^[a-f0-9]{64}$")) throw new InvalidOperationException("软件包体积或哈希无效。");
        EnsureDiskSpace(config, expected);
        string part = config.PackagePath + ".part";
        Directory.CreateDirectory(Path.GetDirectoryName(part)!);
        using HttpResponseMessage response = await Http.GetAsync(url, HttpCompletionOption.ResponseHeadersRead);
        response.EnsureSuccessStatusCode();
        ValidateUrl(response.RequestMessage?.RequestUri?.ToString() ?? "");
        await using Stream source = await response.Content.ReadAsStreamAsync();
        await using FileStream target = new(part, FileMode.Create, FileAccess.Write, FileShare.None);
        using IncrementalHash digest = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        byte[] buffer = new byte[1024 * 1024];
        long received = 0;
        int read;
        while ((read = await source.ReadAsync(buffer)) > 0)
        {
            received += read;
            if (received > expected || received > MaximumArchiveBytes) throw new InvalidOperationException("下载内容超过清单声明体积。");
            await target.WriteAsync(buffer.AsMemory(0, read));
            digest.AppendData(buffer, 0, read);
            WriteState(config, state, "downloading", Math.Clamp((int)(received * 100 / expected), 1, 99), $"正在下载 {received / 1024 / 1024} / {expected / 1024 / 1024} MiB");
        }
        await target.FlushAsync();
        if (received != expected || !CryptographicOperations.FixedTimeEquals(digest.GetHashAndReset(), Convert.FromHexString(checksum))) throw new InvalidOperationException("软件包体积或 SHA-256 校验失败。");
        File.Move(part, config.PackagePath, true);
        state["downloaded"] = true;
        state["can_install"] = true;
        WriteState(config, state, "downloaded", 100, "下载与完整性校验完成");
        Console.WriteLine("下载与完整性校验完成。");
        return true;
    }

    private static async Task<JsonObject> FetchManifest()
    {
        Uri url = ValidateUrl(ManifestUrl);
        string raw = await Http.GetStringAsync(url);
        if (Encoding.UTF8.GetByteCount(raw) > 256 * 1024) throw new InvalidOperationException("版本清单过大。");
        JsonObject manifest = JsonNode.Parse(raw) as JsonObject ?? throw new InvalidOperationException("版本清单无效。");
        if (manifest["schema_version"]?.GetValue<int>() != 1 || manifest["channel"]?.GetValue<string>() != "stable") throw new InvalidOperationException("版本清单格式或通道无效。");
        ParseVersion(RequiredString(manifest, "version"));
        if (manifest["package"] is JsonObject package) ValidateUrl(RequiredString(package, "url"));
        return manifest;
    }

    private static void ValidateArchive(ZipArchive zip)
    {
        if (zip.Entries.Count > MaximumArchiveFiles) throw new InvalidOperationException("软件包文件数量超出限制。");
        long expanded = 0;
        bool hasPayload = false;
        foreach (ZipArchiveEntry entry in zip.Entries)
        {
            string name = entry.FullName.Replace('\\', '/');
            if (name.StartsWith('/') || name.Contains("../", StringComparison.Ordinal) || name.Contains('\0')) throw new InvalidOperationException("软件包包含不安全路径。");
            if (name.StartsWith("payload/", StringComparison.Ordinal)) hasPayload = true;
            if (name != "update.json" && !name.StartsWith("payload/", StringComparison.Ordinal)) throw new InvalidOperationException("软件包包含未授权的顶层内容。");
            if ((entry.ExternalAttributes & 0xF0000000) == 0xA0000000) throw new InvalidOperationException("软件包不得包含符号链接。");
            expanded += entry.Length;
            if (expanded > MaximumExpandedBytes) throw new InvalidOperationException("软件包展开体积超出限制。");
        }
        if (!hasPayload) throw new InvalidOperationException("软件包缺少 payload 内容。");
    }

    private static void ExtractPayload(string archive, string stage)
    {
        string stageFull = Path.GetFullPath(stage) + Path.DirectorySeparatorChar;
        using ZipArchive zip = ZipFile.OpenRead(archive);
        ValidateArchive(zip);
        foreach (ZipArchiveEntry entry in zip.Entries.Where(item => item.FullName.StartsWith("payload/", StringComparison.Ordinal)))
        {
            string relative = entry.FullName[8..].Replace('/', Path.DirectorySeparatorChar);
            if (relative.Length == 0) continue;
            string destination = Path.GetFullPath(Path.Combine(stage, relative));
            if (!destination.StartsWith(stageFull, StringComparison.Ordinal)) throw new InvalidOperationException("软件包路径逃逸暂存目录。");
            if (entry.FullName.EndsWith('/')) { Directory.CreateDirectory(destination); continue; }
            Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
            entry.ExtractToFile(destination, true);
        }
    }

    private static void CopyTree(string source, string destination)
    {
        HashSet<string> excluded = new(StringComparer.Ordinal) { ".git", ".venv", "instance", "__pycache__", ".pytest_cache", ".ruff_cache", "bakagit" };
        Directory.CreateDirectory(destination);
        Stack<(string Source, string Target)> pending = new();
        pending.Push((source, destination));
        while (pending.Count > 0)
        {
            (string currentSource, string currentTarget) = pending.Pop();
            foreach (string directory in Directory.EnumerateDirectories(currentSource))
            {
                if (excluded.Contains(Path.GetFileName(directory))) continue;
                string childTarget = Path.Combine(currentTarget, Path.GetFileName(directory));
                Directory.CreateDirectory(childTarget);
                pending.Push((directory, childTarget));
            }
            foreach (string file in Directory.EnumerateFiles(currentSource))
            {
                if (Path.GetExtension(file).Equals(".pyc", StringComparison.OrdinalIgnoreCase)) continue;
                File.Copy(file, Path.Combine(currentTarget, Path.GetFileName(file)), true);
            }
        }
    }

    private static async Task<bool> PreparePython(UpdateConfig config)
    {
        string python = "/usr/bin/python3";
        Result venv = await Run(python, ["-m", "venv", Path.Combine(config.ProjectRoot, ".venv")], config.ProjectRoot, TimeSpan.FromMinutes(4));
        if (venv.Code != 0) return false;
        string pip = Path.Combine(config.ProjectRoot, ".venv", "bin", "pip");
        Result install = await Run(pip, ["install", "-r", Path.Combine(config.ProjectRoot, "requirements.txt")], config.ProjectRoot, TimeSpan.FromMinutes(12));
        return install.Code == 0 && (await Run(pip, ["check"], config.ProjectRoot)).Code == 0;
    }

    private static async Task<bool> RunMigrations(UpdateConfig config)
    {
        foreach (string[] command in new[] { new[] { "db", "upgrade" }, new[] { "seed-permissions" }, new[] { "configure-deployment-domain", config.Domain }, new[] { "system-check" } })
        {
            Result result = await RunFlask(config, config.ProjectRoot, command, throwOnFailure: false);
            if (result.Code != 0) return false;
        }
        return true;
    }

    private static async Task<Result> RunFlask(UpdateConfig config, string projectRoot, string[] command, bool throwOnFailure = true)
    {
        string flask = Path.Combine(projectRoot, ".venv", "bin", "flask");
        List<string> args = ["-u", "bakablog", "--", "env", "PYTHONUTF8=1", $"CLOUD_DIARY_INSTANCE_PATH={config.InstanceRoot}", "CLOUD_DIARY_ENV=production", $"CLOUD_DIARY_SITE_URL=https://{config.Domain}", "bash", "-c", $"set -a; . '{EnvironmentPath}'; set +a; exec '{flask}' --app wsgi:app {string.Join(' ', command.Select(ShellQuote))}"];
        Result result = await Run("runuser", args, projectRoot, TimeSpan.FromMinutes(12));
        if (throwOnFailure && result.Code != 0) throw new InvalidOperationException("Flask 维护命令失败：" + LastLines(result.Error, 5));
        return result;
    }

    private static async Task<bool> WaitForHealth(int port)
    {
        DateTimeOffset deadline = DateTimeOffset.UtcNow.AddSeconds(45);
        while (DateTimeOffset.UtcNow < deadline)
        {
            Result result = await Run("curl", ["--silent", "--fail", $"http://127.0.0.1:{port}/healthz"], timeout: TimeSpan.FromSeconds(3));
            if (result.Code == 0 && result.Output.Contains("cloudtrace", StringComparison.OrdinalIgnoreCase)) return true;
            await Task.Delay(700);
        }
        return false;
    }

    private static void EnsureDiskSpace(UpdateConfig config, string archive) => EnsureDiskSpace(config, new FileInfo(archive).Length);
    private static void EnsureDiskSpace(UpdateConfig config, long packageSize)
    {
        long projectSize = DirectorySize(config.ProjectRoot);
        long instanceSize = DirectorySize(config.InstanceRoot);
        long required = Math.Max(256L * 1024 * 1024, packageSize * 3 + projectSize * 2 + instanceSize * 2);
        DriveInfo drive = new(Path.GetPathRoot(config.ProjectRoot)!);
        if (drive.AvailableFreeSpace < required) throw new InvalidOperationException($"可用空间不足：至少需要 {required / 1024 / 1024} MiB，当前 {drive.AvailableFreeSpace / 1024 / 1024} MiB。");
    }

    private static long DirectorySize(string path)
    {
        if (!Directory.Exists(path)) return 0;
        try { return Directory.EnumerateFiles(path, "*", SearchOption.AllDirectories).Sum(file => new FileInfo(file).Length); }
        catch (IOException) { return 0; }
    }

    private static bool FixedHash(string path, string expected)
    {
        using FileStream stream = File.OpenRead(path);
        byte[] actual = SHA256.HashData(stream);
        return CryptographicOperations.FixedTimeEquals(actual, Convert.FromHexString(expected));
    }

    private static string ReadCurrentVersion(string root)
    {
        string config = File.ReadAllText(Path.Combine(root, "app", "config.py"));
        Match match = Regex.Match(config, "APP_VERSION\\s*=\\s*\"(?<version>[0-9]+\\.[0-9]+\\.[0-9]+)\"");
        return match.Success ? match.Groups["version"].Value : throw new InvalidOperationException("无法读取当前应用版本。");
    }

    private static int CompareVersion(string left, string right) => ParseVersion(left).CompareTo(ParseVersion(right));
    private static Version ParseVersion(string value) => Version.TryParse(value, out Version? version) && value.Count(c => c == '.') == 2 ? version : throw new InvalidOperationException("版本号必须使用 x.y.z 格式。");
    private static Uri ValidateUrl(string value)
    {
        if (!Uri.TryCreate(value, UriKind.Absolute, out Uri? uri) || uri.Scheme != Uri.UriSchemeHttps || !AllowedHosts.Contains(uri.Host, StringComparer.OrdinalIgnoreCase) || !string.IsNullOrEmpty(uri.UserInfo) || !uri.IsDefaultPort) throw new InvalidOperationException("更新地址不是官方 GitHub HTTPS 地址。");
        return uri;
    }

    private static UpdateConfig ReadConfig()
    {
        Dictionary<string, string> values = File.Exists(ConfigPath) ? File.ReadLines(ConfigPath).Where(line => line.Contains('=') && !line.TrimStart().StartsWith('#')).Select(line => line.Split('=', 2)).ToDictionary(parts => parts[0].Trim(), parts => parts[1].Trim(), StringComparer.Ordinal) : [];
        string project = Path.GetFullPath(values.GetValueOrDefault("PROJECT_ROOT", "/opt/bakablog/current"));
        string instance = Path.GetFullPath(values.GetValueOrDefault("INSTANCE_ROOT", "/var/lib/bakablog"));
        if (!Path.IsPathRooted(project) || project == "/" || !File.Exists(Path.Combine(project, "wsgi.py"))) throw new InvalidOperationException("项目目录无效。");
        return new(project, instance, values.GetValueOrDefault("DOMAIN", ""), int.TryParse(values.GetValueOrDefault("LOCAL_PORT"), out int port) ? port : 8080);
    }

    private static JsonObject ReadState(UpdateConfig config)
    {
        try { return JsonNode.Parse(File.ReadAllText(config.StatePath)) as JsonObject ?? new(); }
        catch (Exception error) when (error is IOException or JsonException) { return new(); }
    }

    private static void WriteState(UpdateConfig config, string status, int progress, string message) => WriteState(config, ReadState(config), status, progress, message);
    private static void WriteState(UpdateConfig config, JsonObject state, string status, int progress, string message)
    {
        state["schema_version"] = 1;
        state["status"] = status;
        state["progress"] = progress;
        state["message"] = message;
        state["updated_at"] = DateTimeOffset.UtcNow.ToString("O");
        JsonArray events = state["events"] as JsonArray ?? [];
        while (events.Count >= 12) events.RemoveAt(0);
        events.Add(new JsonObject { ["at"] = state["updated_at"]?.DeepClone(), ["status"] = status, ["message"] = message });
        state["events"] = events;
        AtomicJson(config.StatePath, state);
        Run("chown", ["bakablog:bakablog", config.StatePath]).GetAwaiter().GetResult();
        Run("chmod", ["0640", config.StatePath]).GetAwaiter().GetResult();
    }

    private static void AtomicJson(string path, JsonObject value)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        string temporary = path + ".tmp-" + Environment.ProcessId;
        File.WriteAllText(temporary, value.ToJsonString(new JsonSerializerOptions { WriteIndented = true }) + "\n", new UTF8Encoding(false));
        File.Move(temporary, path, true);
    }

    private static string RequiredString(JsonObject value, string key) => value[key]?.GetValue<string>() is string item && item.Length > 0 ? item : throw new InvalidOperationException($"缺少 {key}。");
    private static string RequiredPath(JsonObject value, string key)
    {
        string path = Path.GetFullPath(RequiredString(value, key));
        if (!path.StartsWith("/opt/bakablog/", StringComparison.Ordinal) && !path.StartsWith("/var/lib/bakablog/", StringComparison.Ordinal)) throw new InvalidOperationException("回退记录路径超出受管目录。");
        return path;
    }
    private static string ShellQuote(string value) => "'" + value.Replace("'", "'\\''") + "'";
    private static string SafeMessage(Exception error) => error is InvalidOperationException or IOException or HttpRequestException ? error.Message : "更新任务异常终止，当前版本未被修改。";
    private static string LastLines(string value, int count) => string.Join(Environment.NewLine, value.Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).TakeLast(count));

    private static async Task RequireSuccess(string file, IEnumerable<string> args, string message)
    {
        Result result = await Run(file, args);
        if (result.Code != 0) throw new InvalidOperationException(message + "：" + LastLines(result.Error, 4));
    }

    private static async Task<Result> Run(string file, IEnumerable<string> args, string? workingDirectory = null, TimeSpan? timeout = null)
    {
        ProcessStartInfo start = new(file) { RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false, WorkingDirectory = workingDirectory ?? "/" };
        foreach (string arg in args) start.ArgumentList.Add(arg);
        using Process process = Process.Start(start) ?? throw new InvalidOperationException($"无法启动 {file}。");
        Task<string> output = process.StandardOutput.ReadToEndAsync();
        Task<string> error = process.StandardError.ReadToEndAsync();
        using CancellationTokenSource cancellation = new(timeout ?? TimeSpan.FromMinutes(3));
        try { await process.WaitForExitAsync(cancellation.Token); }
        catch (OperationCanceledException) { process.Kill(true); return new(-1, await output, "操作超时。"); }
        return new(process.ExitCode, await output, await error);
    }

    private static void TryInstallBundledManager(string projectRoot)
    {
        string architecture = System.Runtime.InteropServices.RuntimeInformation.ProcessArchitecture == System.Runtime.InteropServices.Architecture.Arm64 ? "linux-arm64" : "linux-x64";
        string bundled = Path.Combine(projectRoot, "dist", "bakablog", architecture, "bakablog");
        if (!File.Exists(bundled)) return;
        string temporary = "/usr/local/bin/bakablog.next";
        File.Copy(bundled, temporary, true);
        Run("chmod", ["0755", temporary]).GetAwaiter().GetResult();
        File.Move(temporary, "/usr/local/bin/bakablog", true);
    }

    private sealed record UpdateConfig(string ProjectRoot, string InstanceRoot, string Domain, int LocalPort)
    {
        public string UpdateRoot => Path.Combine(InstanceRoot, "updates");
        public string StatePath => Path.Combine(UpdateRoot, "state.json");
        public string RequestPath => Path.Combine(UpdateRoot, "request.json");
        public string PackagePath => Path.Combine(UpdateRoot, "downloads", "pending-update.zip");
        public string RollbackPath => Path.Combine(UpdateRoot, "rollback.json");
    }
    private sealed record Result(int Code, string Output, string Error);
}

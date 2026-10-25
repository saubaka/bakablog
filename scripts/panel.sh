#!/bin/bash
# Baka Blog 本机面板：在这台 Mac 上启动、停止、查看博客，不用记命令。
#
#   scripts/panel.sh              打开数字菜单（双击项目根目录的 run-local.command 也是这个）
#   scripts/panel.sh start        启动本机服务（后台运行，关掉终端窗口不会停）
#   scripts/panel.sh stop         停止
#   scripts/panel.sh restart      重启（改了后端代码之后要做）
#   scripts/panel.sh status       现在的状态（在不在跑、版本、前端构建新不新、有没有管理员）
#   scripts/panel.sh logs [N]     看最近 N 行日志（默认 60）
#   scripts/panel.sh open [admin] 用浏览器打开首页（admin = 管理后台）
#   scripts/panel.sh build        重新构建前端（npm run build）
#   scripts/panel.sh seed         往空的本机数据库灌示例内容
#   scripts/panel.sh qa-start|qa-stop     测试用的后台实例（:5310，单独的数据）
#   scripts/panel.sh autostart-status|autostart-probe|autostart-install|autostart-uninstall   登录后自动启动
#
# 它管的是你本机的开发 / 预览服务（首选 http://127.0.0.1:5300，数据在 backend/data）。线上服务器的更新是 deploy/deploy.sh，不在这里。
# 端口：首选 5300；被别的程序占着时自动顺延到 5301、5302 …（最多往后 20 个，跳过 5310 和 5173），实际用了哪个端口会显示在菜单顶部的“地址 / 端口”那一行，
# 也记在 backend/data/panel/port 里，停止 / 状态 / 打开浏览器都按它走。
# 写法上的一个坑：变量后面紧跟中文必须写成 ${变量名}（bash 3.2 在 C 区域设置下会把中文的第一个字节当成变量名的一部分，launchd 启动时就是 C 区域）。
# 这个脚本不加 set -e：一条命令失败要显示原因并回到菜单，而不是把窗口关掉。需要 bash 3.2（macOS 自带的）就能跑。
#
# 给测试用的环境变量（平时不用）：
#   BAKA_PANEL_PORT      首选端口（默认 5300）      BAKA_PANEL_DATA   数据目录（默认 backend/data）
#   BAKA_PANEL_RESERVED  顺延时额外要跳过的端口（空格分隔；5310 测试实例和 5173 前端热更新本来就会跳过）
#   BAKA_PANEL_STATE     放 pid 和日志的目录         BAKA_PANEL_NO_OPEN=1  不真的打开浏览器
#   BAKA_PANEL_LABEL     自动启动用的 launchd 名字   BAKA_PANEL_PLIST_DIR  放 plist 的目录
#   BAKA_PANEL_PROBE_TARGET  自动启动探针要读的目录（默认 backend）
set -u

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd) || exit 1
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
HOST="127.0.0.1"
PREFERRED="${BAKA_PANEL_PORT:-5300}"   # 首选端口；被占用时往后顺延
SPAN="${BAKA_PANEL_SPAN:-20}"            # 最多试 首选 … 首选+19（测试时可以用 BAKA_PANEL_SPAN 改小）
PORT="$PREFERRED"                      # 这次实际在用（或将要用）的端口：resolve_active / pick_port 会改它
QA_PORT=5310
DEV_PORT=5173
STATE="${BAKA_PANEL_STATE:-$BACKEND/data/panel}"
LOG="$STATE/server.log"
PIDFILE="$STATE/gunicorn.pid"
PORT_FILE="$STATE/port"                # 面板启动服务时记下“实际端口 首选端口”
LABEL="${BAKA_PANEL_LABEL:-com.saubaka.bakablog.local}"
PLIST_DIR="${BAKA_PANEL_PLIST_DIR:-$HOME/Library/LaunchAgents}"
GUNICORN="$BACKEND/.venv/bin/gunicorn"
FLASK="$BACKEND/.venv/bin/flask"
URL="http://$HOST:$PORT"
set_port() { PORT="$1"; URL="http://$HOST:$PORT"; }
[ -n "${BAKA_PANEL_DATA:-}" ] && export BLOG_DATA_DIR="$BAKA_PANEL_DATA"
SETUP_TOKEN_FILE="${BLOG_DATA_DIR:-$BACKEND/data}/setup-token.txt"

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  B=$'\033[1m'; D=$'\033[2m'; R=$'\033[31m'; G=$'\033[32m'; Y=$'\033[33m'; P=$'\033[35m'; N=$'\033[0m'
else
  B=''; D=''; R=''; G=''; Y=''; P=''; N=''
fi
INTERACTIVE=0; [ -t 0 ] && [ -t 1 ] && INTERACTIVE=1

say()  { printf '%s\n' "$*"; }
ok()   { printf '  %s✓%s %s\n' "$G" "$N" "$*"; }
warn() { printf '  %s!%s %s\n' "$Y" "$N" "$*"; }
bad()  { printf '  %s✗%s %s\n' "$R" "$N" "$*"; }
dim()  { printf '  %s%s%s\n' "$D" "$*" "$N"; }

pause()   { [ "$INTERACTIVE" = 1 ] && { printf '\n%s按回车返回菜单%s ' "$D" "$N"; read -r _ || true; }; return 0; }
confirm() { [ "$INTERACTIVE" = 1 ] || return 1; local a; printf '  %s (y/N) ' "$1"; read -r a || return 1; case "$a" in y|Y|yes|YES) return 0 ;; *) return 1 ;; esac; }

# ---------------------------------------------------------------------------------------------------------------------------------
# 进程与端口
# ---------------------------------------------------------------------------------------------------------------------------------
listeners() { lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null | sort -u; }
alive()     { [ -n "${1:-}" ] && kill -0 "$1" 2>/dev/null; }
cmd_of()    { ps -o command= -p "$1" 2>/dev/null; }
is_ours()   { case "$(cmd_of "$1")" in *gunicorn*wsgi:app*) return 0 ;; *) return 1 ;; esac; }

# ---------------------------------------------------------------------------------------------------------------------------------
# 端口：首选 → 被占用就顺延；实际用哪个端口，由 resolve_active（已经在跑的）和 pick_port（要启动的）决定
# ---------------------------------------------------------------------------------------------------------------------------------
reserved_port() { case " $QA_PORT $DEV_PORT ${BAKA_PANEL_RESERVED:-} " in *" $1 "*) return 0 ;; esac; return 1; }
port_busy()     { [ -n "$(listeners "$1")" ]; }
busy_by() {     # 谁占着这个端口：python3.12 进程 1234
  local q; q=$(listeners "$1" | head -1); [ -n "$q" ] || return 1
  printf '%s 进程 %s' "$(basename "$(ps -o comm= -p "$q" 2>/dev/null)")" "$q"
}

# 这个博客的服务现在在哪个端口。只认三处：面板上次记下的端口、pid 文件里那个进程监听的端口、首选端口（别的方式启动的，比如桌面应用的“运行”按钮）；
# 找到就把 PORT 设成它（返回 0），找不到就回到首选端口（返回 1）。故意不去扫一整段端口：那会把 5310 的测试实例或别人起的开发服务当成自己的，进而去停它。
resolve_active() {
  local saved="" pf="" pairs p pid
  [ -f "$PORT_FILE" ] && saved=$(awk '{print $1}' "$PORT_FILE" 2>/dev/null)
  [ -f "$PIDFILE" ] && pf=$(tr -d '[:space:]' < "$PIDFILE" 2>/dev/null)
  pairs=$(lsof -nP -iTCP -sTCP:LISTEN -Fpn 2>/dev/null | awk '/^p/{pid=substr($0,2)} /^n/{n=split($0,a,":"); print pid, a[n]}' | sort -u)
  local from_pid=""
  [ -n "$pf" ] && from_pid=$(printf '%s\n' "$pairs" | awk -v q="$pf" '$1==q{print $2}')
  for p in $saved $from_pid "$PREFERRED"; do
    for pid in $(printf '%s\n' "$pairs" | awk -v p="$p" '$2==p{print $1}'); do
      if is_ours "$pid"; then set_port "$p"; return 0; fi
    done
  done
  set_port "$PREFERRED"; return 1
}

# 要启动的话该用哪个端口：从首选开始，第一个没被占用的（5310 测试实例、5173 前端热更新和 BAKA_PANEL_RESERVED 里的端口不占用，也不去抢）
pick_port() {
  local i p
  for i in $(seq 0 $((SPAN - 1))); do
    p=$((PREFERRED + i))
    [ "$i" -gt 0 ] && reserved_port "$p" && continue
    port_busy "$p" && continue
    echo "$p"; return 0
  done
  return 1
}

# 菜单里“地址 / 端口”那一行的内容（也用在状态里）：端口 5400，首选 5399 被 Python 进程 1234 占用，已顺延
port_info() {
  local who
  if master_pid >/dev/null; then
    if [ "$PORT" = "$PREFERRED" ]; then printf '端口 %s' "$PORT"
    elif who=$(busy_by "$PREFERRED"); then printf '端口 %s，首选 %s 被 %s 占用，已顺延' "$PORT" "$PREFERRED" "$who"
    else printf '端口 %s，首选 %s 启动时被占用，已顺延' "$PORT" "$PREFERRED"; fi
  elif who=$(busy_by "$PREFERRED"); then printf '首选端口 %s 现在被 %s 占用，启动时会顺延到 %s' "$PREFERRED" "$who" "$(pick_port || echo '?')"
  else printf '首选端口 %s，空闲' "$PREFERRED"; fi
}

# 监听这个端口的 gunicorn 主进程（有 pid 文件先信它；否则在监听者里找“父进程不在监听者里”的那个）
master_pid() {
  local p q all="" pp
  for q in $(listeners "$PORT"); do is_ours "$q" && all="$all $q"; done   # 只算 gunicorn（wsgi:app）：别的程序占着端口时，面板不会把它当成自己的、更不会去结束它
  all=$(echo $all)
  [ -n "$all" ] || return 1
  if [ -f "$PIDFILE" ]; then   # pid 文件里的进程也得真的在监听这个端口（它可能是上一次别的端口留下的，或者 pid 已被别的进程重用）
    p=$(tr -d '[:space:]' < "$PIDFILE" 2>/dev/null)
    if alive "$p" && is_ours "$p"; then
      for q in $all; do
        [ "$q" = "$p" ] && { echo "$p"; return 0; }
        [ "$(ps -o ppid= -p "$q" 2>/dev/null | tr -d ' ')" = "$p" ] && { echo "$p"; return 0; }
      done
    fi
  fi
  for p in $all; do
    pp=$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' ')
    case " $all " in *" $pp "*) ;; *) echo "$p"; return 0 ;; esac
  done
  echo "${all%% *}"
}

health_json() { curl -fsS --max-time 2 "$URL/api/health" 2>/dev/null; }
json_field()  { sed -n "s/.*\"$1\": *\"\{0,1\}\([^\",}]*\)\"\{0,1\}.*/\1/p" | head -1; }

# “dd-hh:mm:ss” 之类的运行时长 → 秒
etime_secs() {
  local t="$1" d=0 h=0 m=0 s=0
  case "$t" in *-*) d=${t%%-*}; t=${t#*-} ;; esac
  IFS=: read -r a b c <<EOF
$t
EOF
  if [ -n "${c:-}" ]; then h=$a; m=$b; s=$c; elif [ -n "${b:-}" ]; then m=$a; s=$b; else s=$a; fi
  echo $(( 10#$d * 86400 + 10#$h * 3600 + 10#$m * 60 + 10#$s ))
}
human_secs() {
  local s=$1
  if [ "$s" -ge 86400 ]; then printf '%s 天 %s 小时' $((s / 86400)) $((s % 86400 / 3600))
  elif [ "$s" -ge 3600 ]; then printf '%s 小时 %s 分' $((s / 3600)) $((s % 3600 / 60))
  elif [ "$s" -ge 60 ]; then printf '%s 分钟' $((s / 60))
  else printf '%s 秒' "$s"; fi
}
newest_mtime() { find "$@" -type f -exec stat -f %m {} + 2>/dev/null | sort -n | tail -1; }

# ---------------------------------------------------------------------------------------------------------------------------------
# 检查环境
# ---------------------------------------------------------------------------------------------------------------------------------
need_venv() {
  [ -x "$GUNICORN" ] && return 0
  bad "还没有 Python 环境（$BACKEND/.venv）。"
  if command -v uv >/dev/null 2>&1; then
    if confirm "现在用 uv 建一个（cd backend && make venv，要联网下载依赖）？"; then
      ( cd "$BACKEND" && make venv ) && [ -x "$GUNICORN" ] && { ok "环境建好了。"; return 0; }
      bad "建环境没成功，看上面的输出。"
    fi
  else
    dim "没有找到 uv。先装 uv（brew install uv），再在 backend 目录运行 make venv。"
  fi
  return 1
}

# ---------------------------------------------------------------------------------------------------------------------------------
# 启动 / 停止 / 重启
# ---------------------------------------------------------------------------------------------------------------------------------
cmd_start() {
  local p pick who
  if resolve_active && p=$(master_pid); then
    if health_json >/dev/null; then ok "已经在运行（进程 ${p}，$(port_info)）：$URL"; return 0; fi
    bad "端口 $PORT 上有 gunicorn（进程 ${p}）但没有回应 /api/health。先选“停止”，再启动。"; return 1
  fi
  need_venv || return 1
  pick=$(pick_port) || { bad "从 $PREFERRED 起连续 $SPAN 个端口都不可用（被占用，或留给测试实例 / 前端热更新），没法启动。可以用 BAKA_PANEL_PORT 换一个首选端口。"; return 1; }
  if [ "$pick" != "$PREFERRED" ]; then
    who=$(busy_by "$PREFERRED") || who="别的程序"
    warn "端口 $PREFERRED 不可用（被 $who 占用），自动顺延到 ${pick}。面板不会动那个程序。"
  fi
  set_port "$pick"
  mkdir -p "$STATE" || { bad "建不了 $STATE"; return 1; }
  [ -f "$LOG" ] && [ "$(stat -f %z "$LOG" 2>/dev/null || echo 0)" -gt 5242880 ] && mv -f "$LOG" "$LOG.old"
  [ -f "$FRONTEND/dist/public.html" ] || warn "还没有构建过前端（frontend/dist），打开会是没有样式的简易页面。选“重新构建前端”。"
  printf '%s %s\n' "$PORT" "$PREFERRED" > "$PORT_FILE"
  printf '\n===== %s 面板启动 :%s（首选 %s）=====\n' "$(date '+%F %T')" "$PORT" "$PREFERRED" >> "$LOG"
  # 整个后台任务的输入输出都改道：不然这条命令被接进管道（| tee、| sed）时，管道会一直等着服务退出才算结束
  ( cd "$BACKEND" || exit 1; exec nohup "$GUNICORN" -w 2 --threads 4 --keep-alive 5 -b "$HOST:$PORT" --pid "$PIDFILE" --access-logfile - --error-logfile - wsgi:app >> "$LOG" 2>&1 < /dev/null ) &
  say "  正在启动……"
  local i
  for i in $(seq 1 60); do
    if health_json >/dev/null; then
      local h v b; h=$(health_json); v=$(echo "$h" | json_field version); b=$(echo "$h" | json_field build)
      ok "已启动：$URL   （$(port_info)，版本 ${v:-?}，进程 $(master_pid || echo ?)）"
      dim "后台：$URL/admin/    日志：选 5，或 scripts/panel.sh logs"
      return 0
    fi
    if [ "$i" -gt 8 ] && ! master_pid >/dev/null; then break; fi
    sleep 0.5
  done
  bad "没有在 30 秒内启动起来。日志最后几行："
  tail -n 15 "$LOG" 2>/dev/null | sed 's/^/    /'
  rm -f "$PORT_FILE"
  return 1
}

cmd_stop() {
  local p who i
  resolve_active >/dev/null
  p=$(master_pid) || {
    if who=$(busy_by "$PREFERRED"); then ok "没有在运行。（首选端口 $PREFERRED 被 $who 占着，那不是这个博客，面板不会动它。）"; else ok "没有在运行。"; fi
    rm -f "$PIDFILE" "$PORT_FILE"; return 0
  }
  say "  正在停止（进程 ${p}，$(port_info)）……"
  kill -TERM "$p" 2>/dev/null
  for i in $(seq 1 40); do
    [ -z "$(listeners "$PORT")" ] && ! alive "$p" && break
    sleep 0.3
  done
  if [ -z "$(listeners "$PORT")" ]; then ok "已停止。"; rm -f "$PIDFILE" "$PORT_FILE"; return 0; fi
  bad "12 秒了还没停下来。"
  if confirm "强制结束它（kill -9）？正在处理的请求会被打断。"; then
    for p in $(listeners "$PORT"); do is_ours "$p" && kill -KILL "$p" 2>/dev/null; done
    sleep 0.5
    [ -z "$(listeners "$PORT")" ] && { ok "已强制结束。"; rm -f "$PIDFILE" "$PORT_FILE"; return 0; }
  fi
  return 1
}

cmd_restart() { cmd_stop && cmd_start; }

# ---------------------------------------------------------------------------------------------------------------------------------
# 状态
# ---------------------------------------------------------------------------------------------------------------------------------
cmd_status() {
  local p h v b et age newest started
  resolve_active >/dev/null
  say "${B}博客服务${N}  $URL   $(port_info)"
  if p=$(master_pid); then
    h=$(health_json)
    if [ -n "$h" ]; then
      v=$(echo "$h" | json_field version); b=$(echo "$h" | json_field build)
      et=$(ps -o etime= -p "$p" 2>/dev/null | tr -d ' '); age=$(etime_secs "${et:-0}")
      ok "运行中：进程 ${p}，已运行 $(human_secs "$age")，版本 ${v:-?}（${b:-开发}）"
      newest=$(newest_mtime "$BACKEND/app" -name '*.py'); started=$(( $(date +%s) - age ))
      [ -n "$newest" ] && [ "$newest" -gt "$started" ] && warn "后端代码比这个服务新（改过之后没有重启）：选 3 重启。"
      local a; a=$(curl -fsS --max-time 2 "$URL/api/admin/auth/status" 2>/dev/null)
      case "$a" in
        *'"setup_required": true'*|*'"setup_required":true'*) warn "还没有创建管理员：打开 $URL/admin/setup（一次性口令在 ${SETUP_TOKEN_FILE#$ROOT/}，面板不会显示它）。" ;;
        *'setup_required'*) ok "管理员已创建：$URL/admin/" ;;
      esac
    else
      warn "端口上有 gunicorn（进程 ${p}），但没有回应 /api/health。"
    fi
  else
    warn "没有在运行。选 1 启动。"
  fi

  say ""; say "${B}前端构建${N}"
  if [ -f "$FRONTEND/dist/public.html" ]; then
    local built; built=$(stat -f %Sm -t '%F %T' "$FRONTEND/dist/public.html" 2>/dev/null)
    if [ -n "$(find "$FRONTEND/src" -type f -newer "$FRONTEND/dist/public.html" 2>/dev/null | head -1)" ]; then
      warn "构建于 ${built}，但之后改过前端源码：选 8 重新构建。"
    else
      ok "构建于 ${built}，和源码一致。"
    fi
  else
    warn "还没有构建过（frontend/dist 不存在）：选 8。"
  fi
  [ -d "$FRONTEND/node_modules" ] || dim "（frontend/node_modules 不存在：构建时会先问要不要 npm install）"

  say ""; say "${B}数据${N}"
  local data="${BAKA_PANEL_DATA:-$BACKEND/data}"
  if [ -f "$data/blog.sqlite" ]; then ok "$data/blog.sqlite（$(du -h "$data/blog.sqlite" | cut -f1)）"; else warn "$data 里还没有数据库（第一次启动会自动建；选 9 可以灌示例内容）。"; fi

  say ""; say "${B}其他${N}"
  if [ -n "$(listeners "$QA_PORT")" ]; then ok "测试用的后台实例在运行：http://$HOST:${QA_PORT}（选 10 管理）"; else dim "测试用的后台实例（:${QA_PORT}）没有运行。"; fi
  [ -n "$(listeners "$DEV_PORT")" ] && ok "前端热更新（npm run dev）在运行：http://$HOST:$DEV_PORT"
  if pgrep -f "node qa/" >/dev/null 2>&1; then warn "现在有浏览器检查（node qa/…）在跑：这时候构建前端会让它们全部失败。"; fi
  local plist="$PLIST_DIR/$LABEL.plist"
  if [ -f "$plist" ]; then ok "登录后自动启动：已安装（${LABEL}）"; else dim "登录后自动启动：没有安装（选 11）。"; fi
  return 0
}

# ---------------------------------------------------------------------------------------------------------------------------------
# 日志 / 浏览器 / 构建 / 示例内容 / 测试实例
# ---------------------------------------------------------------------------------------------------------------------------------
cmd_logs() {
  local n="${1:-60}"
  [ -f "$LOG" ] || { warn "还没有日志（${LOG}）。"; return 0; }
  if [ "$INTERACTIVE" = 1 ] && [ "${2:-}" != "--once" ]; then
    dim "最近 $n 行，之后实时跟着。按 Ctrl-C 回到菜单。"
    trap ':' INT
    ( trap - INT; exec tail -n "$n" -f "$LOG" ) || true
    trap - INT
  else
    tail -n "$n" "$LOG"
  fi
  return 0
}

cmd_open() {
  local path="/"
  [ "${1:-}" = "admin" ] && path="/admin/"
  health_json >/dev/null || { warn "服务还没运行，先选 1 启动。"; return 1; }
  if [ -n "${BAKA_PANEL_NO_OPEN:-}" ]; then say "  （不打开浏览器）$URL$path"; return 0; fi
  open "$URL$path" && ok "已在浏览器里打开 $URL$path"
}

cmd_build() {
  command -v npm >/dev/null 2>&1 || { bad "没有找到 npm（需要 Node.js）。"; return 1; }
  if pgrep -f "node qa/" >/dev/null 2>&1; then
    warn "现在有浏览器检查（node qa/…）在跑。构建会清空 frontend/dist，正在跑的检查会全部失败。"
    confirm "还是要构建吗？" || { say "  已取消。"; return 1; }
  fi
  if [ ! -d "$FRONTEND/node_modules" ]; then
    confirm "frontend/node_modules 不存在，先 npm install（要联网）吗？" || { say "  已取消。"; return 1; }
    ( cd "$FRONTEND" && npm install ) || { bad "npm install 失败。"; return 1; }
  fi
  say "  正在构建前端（类型检查 + 打包 + 体积检查，大约半分钟）……"
  local out="$STATE/build.log"; mkdir -p "$STATE"
  if ( cd "$FRONTEND" && npm run build ) > "$out" 2>&1; then
    ok "构建完成。"; grep -E "first screen|admin first screen" "$out" | sed 's/^/    /'
    dim "只改了前端的话不用重启服务，刷新浏览器就行。"
    return 0
  fi
  bad "构建失败，最后几行："; tail -n 20 "$out" | sed 's/^/    /'; dim "完整输出：$out"
  return 1
}

cmd_seed() {
  need_venv || return 1
  warn "给本机数据库灌示例文章、动态、图片和一个页面（只能在空库里做，里面有内容会被拒绝）。"
  confirm "继续吗？" || { say "  已取消。"; return 1; }
  local out rc
  out=$( cd "$BACKEND" && "$FLASK" --app app seed-demo 2>&1 ); rc=$?
  printf '%s\n' "$out" | grep -vE "alembic\.runtime|setup plugin|One-time setup token|========" | sed 's/^/    /'
  [ "$rc" -eq 0 ] && ok "完成。服务在运行的话刷新浏览器就能看到。" || bad "没有成功（上面是原因）。"
  return "$rc"
}

cmd_qa_start() { "$ROOT/scripts/qa-instance.sh" start; }
cmd_qa_stop()  { "$ROOT/scripts/qa-instance.sh" stop; }

# ---------------------------------------------------------------------------------------------------------------------------------
# 登录后自动启动（launchd）
#   这个项目放在 ~/Desktop 下时，macOS 不允许 launchd 启动的后台任务读取桌面文件夹（隐私保护），自动启动会失败。
#   所以安装之前先用一个真的 launchd 任务试读一次（探针），读不了就如实说，不装。
# ---------------------------------------------------------------------------------------------------------------------------------
UID_N=$(id -u)
launchd_domain() { echo "gui/$UID_N"; }

plist_xml() {   # $1 label  $2 路径列表（每个参数一行）…
  local label="$1"; shift
  printf '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0"><dict>\n'
  printf '<key>Label</key><string>%s</string>\n<key>ProgramArguments</key><array>\n' "$label"
  local a; for a in "$@"; do printf '<string>%s</string>\n' "$(printf '%s' "$a" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g')"; done
  printf '</array>\n'
}

cmd_autostart_probe() {
  local target="${BAKA_PANEL_PROBE_TARGET:-$BACKEND}" tmp label plist res err i
  tmp=$(mktemp -d "${TMPDIR:-/tmp}/bakapanel.XXXXXX") || return 2
  label="$LABEL.probe.$$"; plist="$tmp/$label.plist"; res="$tmp/result"; err="$tmp/err"
  { plist_xml "$label" /bin/sh -c 'ls "$1" >/dev/null 2>"$2"; find "$1" -maxdepth 1 -type f -exec head -c 1 {} \; >/dev/null 2>>"$2"; if grep -qi "not permitted" "$2"; then echo blocked >"$3"; else echo ok >"$3"; fi' sh "$target" "$err" "$res"
    printf '<key>RunAtLoad</key><true/>\n</dict></plist>\n'; } > "$plist"
  plutil -lint "$plist" >/dev/null 2>&1 || { bad "探针的 plist 生成失败。"; rm -rf "$tmp"; return 2; }
  launchctl bootstrap "$(launchd_domain)" "$plist" >/dev/null 2>&1 || launchctl load "$plist" >/dev/null 2>&1
  for i in $(seq 1 20); do [ -s "$res" ] && break; sleep 0.5; done
  launchctl bootout "$(launchd_domain)/$label" >/dev/null 2>&1 || launchctl unload "$plist" >/dev/null 2>&1
  local out; out=$(cat "$res" 2>/dev/null); rm -rf "$tmp"
  case "$out" in
    ok)      ok "探针：后台任务可以读 ${target}，自动启动可行。"; return 0 ;;
    blocked) bad "探针：macOS 不让后台任务读 ${target}（隐私保护）。项目放在桌面 / 文稿 / 下载里时，自动启动做不到。"
             dim "办法：把整个项目文件夹挪到别处（比如 ~/Developer），再来装；或者给 /bin/sh 完全磁盘访问权限（有安全代价，不建议）。"; return 1 ;;
    *)       warn "探针没有在 10 秒内给出结果（launchd 没有运行它？）。不能说自动启动可行。"; return 2 ;;
  esac
}

cmd_autostart_status() {
  local plist="$PLIST_DIR/$LABEL.plist"
  if [ -f "$plist" ]; then
    ok "已安装：$plist"
    if launchctl print "$(launchd_domain)/$LABEL" >/dev/null 2>&1; then ok "launchd 已加载它（登录后会自动启动，意外退出会自动重启）。"; else warn "plist 在，但 launchd 没有加载它（可能是登录之前装的，或被卸载了）。"; fi
  else
    say "  没有安装登录后自动启动。"
  fi
}

cmd_autostart_install() {
  need_venv || return 1
  cmd_autostart_probe || { bad "没有安装。"; return 1; }
  local plist="$PLIST_DIR/$LABEL.plist"
  if master_pid >/dev/null; then
    resolve_active >/dev/null
    warn "现在有一个手动启动的服务在 :$PORT 上；自动启动的服务会再启动一个（端口顺延），所以先停掉手动的比较干净。"
    confirm "先停掉手动启动的这个吗？" && cmd_stop || { bad "没有安装。"; return 1; }
  fi
  mkdir -p "$PLIST_DIR" "$STATE"
  { plist_xml "$LABEL" /bin/bash "$ROOT/scripts/panel.sh" serve-foreground
    printf '<key>RunAtLoad</key><true/>\n<key>KeepAlive</key><true/>\n<key>ThrottleInterval</key><integer>10</integer>\n'
    printf '<key>WorkingDirectory</key><string>%s</string>\n<key>StandardOutPath</key><string>%s</string>\n<key>StandardErrorPath</key><string>%s</string>\n' "$BACKEND" "$LOG" "$LOG"
    printf '<key>EnvironmentVariables</key><dict><key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>'
    [ -n "${BLOG_DATA_DIR:-}" ] && printf '<key>BLOG_DATA_DIR</key><string>%s</string>' "$BLOG_DATA_DIR"
    printf '<key>BAKA_PANEL_PORT</key><string>%s</string></dict>\n</dict></plist>\n' "$PREFERRED"; } > "$plist"
  plutil -lint "$plist" >/dev/null 2>&1 || { bad "生成的 plist 有问题，已删除。"; rm -f "$plist"; return 1; }
  launchctl bootout "$(launchd_domain)/$LABEL" >/dev/null 2>&1
  if launchctl bootstrap "$(launchd_domain)" "$plist" >/dev/null 2>&1 || launchctl load -w "$plist" >/dev/null 2>&1; then
    ok "已安装并启动：$LABEL"
    local i; for i in $(seq 1 30); do resolve_active >/dev/null; health_json >/dev/null && { ok "服务已经在回应：${URL}（$(port_info)）"; return 0; }; sleep 0.5; done
    warn "已安装，但 15 秒内服务没有回应。最常见的原因是项目放在桌面 / 文稿 / 下载里被 macOS 拦住；看日志（选 5），不行就先卸载。"
    return 1
  fi
  bad "launchctl 没有接受它。"; rm -f "$plist"; return 1
}

cmd_autostart_uninstall() {
  local plist="$PLIST_DIR/$LABEL.plist"
  [ -f "$plist" ] || { ok "本来就没有安装。"; return 0; }
  launchctl bootout "$(launchd_domain)/$LABEL" >/dev/null 2>&1 || launchctl unload "$plist" >/dev/null 2>&1
  rm -f "$plist" && ok "已卸载（服务也已被 launchd 停掉；之后可以用选 1 手动启动）。"
}

cmd_serve_foreground() {   # 给 launchd 用：前台运行，输出交给 launchd 写进日志；端口被占用时同样顺延
  cd "$BACKEND" || exit 1
  local pick; pick=$(pick_port) || { echo "从 $PREFERRED 起连续 $SPAN 个端口都不可用" >&2; exit 1; }
  [ "$pick" != "$PREFERRED" ] && echo "端口 $PREFERRED 不可用，顺延到 $pick" >&2
  set_port "$pick"
  mkdir -p "$STATE" && printf '%s %s\n' "$PORT" "$PREFERRED" > "$PORT_FILE"
  exec "$GUNICORN" -w 2 --threads 4 --keep-alive 5 -b "$HOST:$PORT" --access-logfile - --error-logfile - wsgi:app
}

# ---------------------------------------------------------------------------------------------------------------------------------
# 菜单
# ---------------------------------------------------------------------------------------------------------------------------------
header_line() {
  local p v
  if p=$(master_pid) && health_json >/dev/null; then v=$(health_json | json_field version); printf '%s●%s 运行中   版本 %s' "$G" "$N" "${v:-?}"
  else printf '%s○%s 没有运行' "$D" "$N"; fi
}

# 菜单顶部的“地址 / 端口”信息位：实际用的端口一直显示在这里；顺延了或首选端口被占用时用黄色
port_line() {
  local info colour="$D"; info=$(port_info)
  case "$info" in *顺延*) colour="$Y" ;; esac
  if master_pid >/dev/null && health_json >/dev/null; then printf '  地址 %s%s%s   %s%s%s\n' "$B" "$URL" "$N" "$colour" "$info" "$N"
  else printf '  %s%s%s\n' "$colour" "$info" "$N"; fi
}

qa_menu() {
  say ""; say "${B}测试用的后台实例${N}（:${QA_PORT}，数据在 backend/data-qa，给浏览器检查用，和你的博客数据分开）"
  say "  1) 启动     2) 停止     0) 返回"
  local c; printf '  选择: '; read -r c || return 0
  case "$c" in 1) cmd_qa_start ;; 2) cmd_qa_stop ;; esac
}

autostart_menu() {
  say ""; say "${B}登录后自动启动${N}"; cmd_autostart_status
  say "  1) 先试一下行不行（探针）   2) 安装   3) 卸载   0) 返回"
  local c; printf '  选择: '; read -r c || return 0
  case "$c" in 1) cmd_autostart_probe ;; 2) cmd_autostart_install ;; 3) cmd_autostart_uninstall ;; esac
}

menu() {
  local c
  while true; do
    [ "$INTERACTIVE" = 1 ] && [ -n "${TERM:-}" ] && clear
    resolve_active >/dev/null
    printf '\n  %sBaka Blog 本机面板%s   %s\n' "$B$P" "$N" "$(header_line)"
    port_line
    dim "$ROOT"
    cat <<EOF

   1) 启动              6) 打开博客首页
   2) 停止              7) 打开管理后台
   3) 重启              8) 重新构建前端
   4) 状态              9) 灌入示例内容（空库）
   5) 看日志           10) 测试用的后台实例
                       11) 登录后自动启动
   0) 退出（服务不会停；关掉这个窗口也不会停）
EOF
    printf '\n  选择: '
    read -r c || { say ""; return 0; }
    say ""
    case "$c" in
      1) cmd_start; pause ;;
      2) cmd_stop; pause ;;
      3) cmd_restart; pause ;;
      4) cmd_status; pause ;;
      5) cmd_logs 60 ;;
      6) cmd_open; pause ;;
      7) cmd_open admin; pause ;;
      8) cmd_build; pause ;;
      9) cmd_seed; pause ;;
      10) qa_menu; pause ;;
      11) autostart_menu; pause ;;
      0|q|Q) return 0 ;;
      *) warn "没有这个选项。"; sleep 1 ;;
    esac
  done
}

usage() { sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; }

resolve_active >/dev/null

case "${1:-menu}" in
  menu)               menu ;;
  start)              cmd_start ;;
  stop)               cmd_stop ;;
  restart)            cmd_restart ;;
  status)             cmd_status ;;
  logs)               cmd_logs "${2:-60}" "${3:-}" ;;
  open)               cmd_open "${2:-}" ;;
  build)              cmd_build ;;
  seed)               cmd_seed ;;
  qa-start)           cmd_qa_start ;;
  qa-stop)            cmd_qa_stop ;;
  autostart-status)   cmd_autostart_status ;;
  autostart-probe)    cmd_autostart_probe ;;
  autostart-install)  cmd_autostart_install ;;
  autostart-uninstall) cmd_autostart_uninstall ;;
  serve-foreground)   cmd_serve_foreground ;;
  -h|--help|help)     usage ;;
  *)                  usage; exit 2 ;;
esac

#!/bin/sh
# 双击这个文件，会在“终端”里打开 Baka Blog 本机面板（启动 / 停止 / 状态 / 日志 …）。
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 1
/bin/bash "$DIR/scripts/panel.sh" "$@"
RC=$?
if [ "$RC" -ne 0 ] && [ -t 0 ]; then
    printf '\n面板异常退出（%s）。按回车键关闭窗口。' "$RC"
    read -r _ || true
fi
exit "$RC"

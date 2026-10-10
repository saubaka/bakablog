#!/bin/sh

PROJECT_DIRECTORY=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 1
"$PROJECT_DIRECTORY/start-macos.sh" "$@"
RUN_EXIT=$?

if [ "$RUN_EXIT" -ne 0 ] && [ -t 0 ]; then
    printf '\n启动失败。请查看上方信息；按回车键关闭窗口。\n'
    read -r _ || true
fi
exit "$RUN_EXIT"

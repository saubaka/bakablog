#!/bin/sh
set -eu

REPOSITORY_URL="https://github.com/saubaka/bakablog.git"
BRANCH="main"
PROJECT_DIRECTORY="/opt/bakablog/current"
MANAGER_ONLY=0

usage() {
    printf '%s\n' \
        "Usage: sudo sh deploy-linux.sh [options]" \
        "" \
        "  --repo URL          Git repository (default: ${REPOSITORY_URL})" \
        "  --branch NAME       Git branch (default: ${BRANCH})" \
        "  --project-dir PATH  Absolute deployment path (default: ${PROJECT_DIRECTORY})" \
        "  --manager-only      Install bakablog without starting interactive deployment" \
        "  --help              Show this help"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --repo)
            [ "$#" -ge 2 ] || { printf '%s\n' "Missing value for --repo." >&2; exit 2; }
            REPOSITORY_URL=$2
            shift 2
            ;;
        --branch)
            [ "$#" -ge 2 ] || { printf '%s\n' "Missing value for --branch." >&2; exit 2; }
            BRANCH=$2
            shift 2
            ;;
        --project-dir)
            [ "$#" -ge 2 ] || { printf '%s\n' "Missing value for --project-dir." >&2; exit 2; }
            PROJECT_DIRECTORY=$2
            shift 2
            ;;
        --manager-only)
            MANAGER_ONLY=1
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            printf 'Unknown option: %s\n' "$1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

[ "$(id -u)" -eq 0 ] || {
    printf '%s\n' "Run this script as root: sudo sh deploy-linux.sh" >&2
    exit 1
}

case "$REPOSITORY_URL" in
    https://*) ;;
    *) printf '%s\n' "Repository URL must use HTTPS." >&2; exit 2 ;;
esac
case "$BRANCH" in
    ""|-*|*..*|*[!A-Za-z0-9._/-]*) printf '%s\n' "Invalid branch name." >&2; exit 2 ;;
esac
case "$PROJECT_DIRECTORY" in
    /*) ;;
    *) printf '%s\n' "Project directory must be an absolute path." >&2; exit 2 ;;
esac
if [ "$PROJECT_DIRECTORY" = "/" ] || [ "$PROJECT_DIRECTORY" = "/opt" ] || [ "$PROJECT_DIRECTORY" = "/usr" ]; then
    printf '%s\n' "Refusing to use a broad system directory." >&2
    exit 2
fi

[ -r /etc/os-release ] || {
    printf '%s\n' "This installer requires a Linux distribution with /etc/os-release." >&2
    exit 1
}
. /etc/os-release

install_bootstrap_tools() {
    case "${ID:-}:${ID_LIKE:-}" in
        debian:*|ubuntu:*|*:debian*)
            export DEBIAN_FRONTEND=noninteractive
            apt-get update
            apt-get install -y git ca-certificates
            ;;
        fedora:*|rhel:*|centos:*|rocky:*|almalinux:*|*:rhel*|*:fedora*)
            dnf install -y git ca-certificates
            ;;
        arch:*|manjaro:*|*:arch*)
            pacman -Sy --noconfirm --needed git ca-certificates
            ;;
        opensuse-leap:*|opensuse-tumbleweed:*|sles:*|*:suse*)
            zypper --non-interactive install git ca-certificates
            ;;
        *)
            printf 'Unsupported distribution: ID=%s ID_LIKE=%s\n' "${ID:-unknown}" "${ID_LIKE:-}" >&2
            exit 1
            ;;
    esac
}

install_bootstrap_tools

case "$(uname -m)" in
    x86_64|amd64) RUNTIME="linux-x64" ;;
    aarch64|arm64) RUNTIME="linux-arm64" ;;
    *) printf 'Unsupported CPU architecture: %s\n' "$(uname -m)" >&2; exit 1 ;;
esac

PARENT_DIRECTORY=$(dirname "$PROJECT_DIRECTORY")
install -d -o root -g root -m 0755 "$PARENT_DIRECTORY"

if [ -d "$PROJECT_DIRECTORY/.git" ]; then
    if [ -n "$(git -C "$PROJECT_DIRECTORY" status --porcelain --untracked-files=normal)" ]; then
        printf '%s\n' "The deployment checkout has local changes; refusing to overwrite them." >&2
        exit 1
    fi
    git -C "$PROJECT_DIRECTORY" fetch --prune origin "$BRANCH"
    git -C "$PROJECT_DIRECTORY" checkout "$BRANCH"
    git -C "$PROJECT_DIRECTORY" merge --ff-only "origin/$BRANCH"
elif [ -e "$PROJECT_DIRECTORY" ]; then
    if [ -n "$(find "$PROJECT_DIRECTORY" -mindepth 1 -maxdepth 1 -print -quit)" ]; then
        printf '%s\n' "Project directory exists and is not an empty Git checkout: $PROJECT_DIRECTORY" >&2
        exit 1
    fi
    git clone --branch "$BRANCH" --single-branch "$REPOSITORY_URL" "$PROJECT_DIRECTORY"
else
    git clone --branch "$BRANCH" --single-branch "$REPOSITORY_URL" "$PROJECT_DIRECTORY"
fi

MANAGER_BINARY="$PROJECT_DIRECTORY/dist/bakablog/$RUNTIME/bakablog"
[ -f "$MANAGER_BINARY" ] || MANAGER_BINARY="$PROJECT_DIRECTORY/dist/bakagate/$RUNTIME/bakagate"
[ -f "$MANAGER_BINARY" ] || {
    printf 'Missing manager binary in repository: %s\n' "$MANAGER_BINARY" >&2
    exit 1
}
install -o root -g root -m 0755 "$MANAGER_BINARY" /usr/local/bin/bakablog
ln -sfn /usr/local/bin/bakablog /usr/local/bin/bakagate

printf '%s\n' "bakablog installed: /usr/local/bin/bakablog"
printf 'Project checkout: %s\n' "$PROJECT_DIRECTORY"

if [ "$MANAGER_ONLY" -eq 1 ]; then
    printf '%s\n' "Run 'sudo bakablog' to open the management menu."
    exit 0
fi

cd "$PROJECT_DIRECTORY"
exec /usr/local/bin/bakablog --install

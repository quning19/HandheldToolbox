#!/system/bin/sh

BASE="/storage/emulated/0/Android/data/org.es_de.frontend/files/themes"
GOOD="$BASE/playstation-x-es-de"
BAD="$BASE/art-book-next-es-de"

echo "========================================"
echo " ES-DE art-book-next-es-de repair"
echo "========================================"

# 必须 root
if [ "$(id -u)" != "0" ]; then
    echo "ERROR: This script must be run as root."
    exit 1
fi

# 检查目录
if [ ! -d "$GOOD/.git" ]; then
    echo "ERROR: Reference repository not found:"
    echo "$GOOD/.git"
    exit 1
fi

if [ ! -d "$BAD/.git" ]; then
    echo "ERROR: Target repository not found:"
    echo "$BAD/.git"
    exit 1
fi

echo
echo "[1] Stop ES-DE"
am force-stop org.es_de.frontend 2>/dev/null

echo
echo "[2] Read owner from good repository"

GOOD_UID=$(stat -c %u "$GOOD/.git")
GOOD_GID=$(stat -c %g "$GOOD/.git")

echo "UID=$GOOD_UID"
echo "GID=$GOOD_GID"

echo
echo "[3] Current target state"

stat -c '%u:%g %a %n' \
    "$BAD" \
    "$BAD/.git" \
    "$BAD/.git/index"

ls -Zd "$BAD" "$BAD/.git"

echo
echo "[4] Fix .git owner"

chown -R "$GOOD_UID:$GOOD_GID" "$BAD/.git"

if [ $? -ne 0 ]; then
    echo "ERROR: chown failed"
    exit 1
fi

echo
echo "[5] Fix .git permissions"

find "$BAD/.git" -type d -exec chmod 2770 {} \;
find "$BAD/.git" -type f -exec chmod 660 {} \;

echo
echo "[6] Copy SELinux context from good repository"

GOOD_CTX=$(ls -Zd "$GOOD/.git" | awk '{print $1}')

echo "Reference context:"
echo "$GOOD_CTX"

if [ -n "$GOOD_CTX" ]; then
    chcon -R "$GOOD_CTX" "$BAD/.git"

    if [ $? -ne 0 ]; then
        echo "WARNING: chcon failed."
        echo "Trying restorecon..."
        restorecon -RF "$BAD/.git"
    fi
else
    echo "WARNING: Could not read SELinux context."
fi

echo
echo "[7] Final state"

stat -c '%u:%g %a %n' \
    "$GOOD/.git" \
    "$GOOD/.git/index" \
    "$BAD/.git" \
    "$BAD/.git/index"

echo
echo "SELinux:"
ls -Zd \
    "$GOOD/.git" \
    "$BAD/.git"

echo
echo "[8] Git metadata sanity check"

echo "HEAD:"
cat "$BAD/.git/HEAD"

echo
echo "main:"
cat "$BAD/.git/refs/heads/main" 2>/dev/null

echo
echo "config:"
cat "$BAD/.git/config"

echo
echo "========================================"
echo " Finished."
echo " Now start ES-DE again and check Theme Downloader."
echo "========================================"
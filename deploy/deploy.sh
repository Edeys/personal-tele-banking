#!/usr/bin/env bash
# Deploy Tele-Banking lên server Linux (VPS / máy chạy 24/7).
#
# Không hardcode host của ai — cấu hình qua biến môi trường:
#   DEPLOY_HOST   bắt buộc, dạng user@host  (ví dụ root@103.0.0.1)
#   REMOTE_DIR    mặc định /opt/tele-banking
#   SERVICE_NAME  mặc định tele-banking
#   SSH_KEY       đường dẫn private key (bỏ trống nếu dùng ssh-agent)
#
# Ví dụ:
#   DEPLOY_HOST=root@1.2.3.4 SSH_KEY=~/.ssh/mykey ./deploy/deploy.sh
set -euo pipefail

: "${DEPLOY_HOST:?Đặt DEPLOY_HOST, dạng user@host}"
REMOTE_DIR="${REMOTE_DIR:-/opt/tele-banking}"
SERVICE_NAME="${SERVICE_NAME:-tele-banking}"

SSH_ARGS=()
[[ -n "${SSH_KEY:-}" ]] && SSH_ARGS=(-i "${SSH_KEY}")

echo "==> Đồng bộ code lên ${DEPLOY_HOST}:${REMOTE_DIR}"
rsync -avz \
  --exclude='.git' --exclude='.github' --exclude='.env' \
  --exclude='__pycache__' --exclude='.venv' --exclude='venv' \
  --exclude='*.pkl' --exclude='receipts' --exclude='data/config.json' \
  -e "ssh ${SSH_ARGS[*]:-}" \
  ./ "${DEPLOY_HOST}:${REMOTE_DIR}/"

echo "==> Cài dependencies và restart service"
ssh "${SSH_ARGS[@]:-}" "${DEPLOY_HOST}" "
  set -e
  cd ${REMOTE_DIR}
  python3 -m venv venv 2>/dev/null || true
  . venv/bin/activate
  pip install -q -r requirements.txt
  python3 -m py_compile main.py config.py onboarding.py keyboards.py bot.py ocr.py imaging.py anomaly.py backends/*.py
  if [ ! -f .env ]; then
    echo 'CẢNH BÁO: chưa có .env trong ${REMOTE_DIR} — bot sẽ không chạy được.' >&2
  fi
  sudo systemctl restart ${SERVICE_NAME}
  sleep 3
  systemctl is-active --quiet ${SERVICE_NAME} && echo 'OK: service đang chạy'
"

echo "==> Xong. Xem log: ssh ${DEPLOY_HOST} 'journalctl -u ${SERVICE_NAME} -n 30 --no-pager'"

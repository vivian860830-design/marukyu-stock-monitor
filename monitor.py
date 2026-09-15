name: Marukyu Stock Monitor

on:
  # 可以在 GitHub Actions 頁面手動執行
  workflow_dispatch:

  # 自動排程
  # GitHub Actions cron 使用 UTC
  #
  # 日本時間 JST = UTC + 9
  #
  # 週一～週五：
  # 09:00 JST = 00:00 UTC
  # 10:00 JST = 01:00 UTC
  # 11:00 JST = 02:00 UTC
  # 12:00 JST = 03:00 UTC
  # 13:00 JST = 04:00 UTC
  # 14:00 JST = 05:00 UTC
  # 15:00 JST = 06:00 UTC
  # 16:00 JST = 07:00 UTC
  # 17:00 JST = 08:00 UTC
  # 17:30 JST = 08:30 UTC

  schedule:
    - cron: '0 0-8 * * 1-5'
    - cron: '30 8 * * 1-5'


# ============================================================
# 權限
# ============================================================
#
# 允許 GitHub Actions 將更新後的 stock_state.json
# commit 回 repository
#

permissions:
  contents: write


# ============================================================
# Jobs
# ============================================================

jobs:

  monitor:

    name: Check Marukyu Stock

    runs-on: ubuntu-latest

    timeout-minutes: 10


    steps:

      # ======================================================
      # 1. 取得 Repository
      # ======================================================

      - name: Checkout repository
        uses: actions/checkout@v6
        with:
          fetch-depth: 0


      # ======================================================
      # 2. Python
      # ======================================================

      - name: Setup Python
        uses: actions/setup-python@v6
        with:
          python-version: '3.12'


      # ======================================================
      # 3. 顯示執行資訊
      # ======================================================

      - name: Show run information
        run: |
          echo "========================================"
          echo "Marukyu Koyamaen Stock Monitor"
          echo "========================================"
          echo "UTC time:"
          date -u
          echo ""
          echo "Japan time:"
          TZ=Asia/Tokyo date
          echo ""
          echo "Repository:"
          echo "${{ github.repository }}"
          echo ""
          echo "Trigger:"
          echo "${{ github.event_name }}"
          echo "========================================"


      # ======================================================
      # 4. 確認必要 Secrets 已設定
      # ======================================================
      #
      # 不會輸出 Secret 本身，只確認是否存在。
      #

      - name: Check required secrets
        env:
          GAS_WEBHOOK_URL: ${{ secrets.GAS_WEBHOOK_URL }}
          MONITOR_SECRET: ${{ secrets.MONITOR_SECRET }}
        run: |
          if [ -z "$GAS_WEBHOOK_URL" ]; then
            echo "ERROR: GAS_WEBHOOK_URL is not configured."
            exit 1
          fi

          if [ -z "$MONITOR_SECRET" ]; then
            echo "ERROR: MONITOR_SECRET is not configured."
            exit 1
          fi

          echo "Required secrets are configured."


      # ======================================================
      # 5. 執行 12 款抹茶庫存檢查
      # ======================================================

      - name: Check Marukyu stock
        env:
          GAS_WEBHOOK_URL: ${{ secrets.GAS_WEBHOOK_URL }}
          MONITOR_SECRET: ${{ secrets.MONITOR_SECRET }}
          PYTHONUNBUFFERED: '1'
        run: |
          python monitor.py


      # ======================================================
      # 6. 確認 stock_state.json 有成功產生
      # ======================================================

      - name: Verify stock state
        run: |
          if [ ! -f stock_state.json ]; then
            echo "ERROR: stock_state.json was not created."
            exit 1
          fi

          echo "stock_state.json exists."
          echo ""
          echo "Current stock state:"
          cat stock_state.json


      # ======================================================
      # 7. 儲存新的庫存狀態
      # ======================================================
      #
      # 第一次執行：
      #   建立 stock_state.json 並 commit
      #
      # 後續執行：
      #   有庫存狀態改變才 commit
      #
      # 完全沒改變：
      #   不建立無意義的 commit
      #

      - name: Save stock state
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

          git add stock_state.json

          if git diff --cached --quiet; then
            echo "Stock state unchanged."
            echo "No commit required."
            exit 0
          fi

          echo "Stock state changed."
          echo "Saving new state..."

          git commit -m "Update Marukyu stock state"

          git push

          echo "Stock state saved successfully."

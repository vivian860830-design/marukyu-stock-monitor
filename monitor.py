name: Marukyu Stock Monitor

on:
  workflow_dispatch:

  schedule:
    # GitHub cron 使用 UTC
    #
    # 日本 09:00 = UTC 00:00
    # 日本 17:00 = UTC 08:00
    #
    # 丸久官方補貨：
    # Mon-Fri 09:00-17:30 JST
    #
    # 因此每個工作日：
    # 09:00 / 10:00 / ... / 17:00 JST
    - cron: '0 0-8 * * 1-5'

permissions:
  contents: write

jobs:

  monitor:

    runs-on: ubuntu-latest

    steps:

      - name: Checkout repository
        uses: actions/checkout@v6

      - name: Setup Python
        uses: actions/setup-python@v6
        with:
          python-version: '3.12'

      - name: Check Marukyu stock
        env:
          GAS_WEBHOOK_URL: ${{ secrets.GAS_WEBHOOK_URL }}
          MONITOR_SECRET: ${{ secrets.MONITOR_SECRET }}
        run: python monitor.py

      - name: Save stock state
        run: |

          if [ ! -f stock_state.json ]; then
            echo "stock_state.json does not exist."
            exit 1
          fi

          git add stock_state.json

          if git diff --cached --quiet; then
            echo "Stock state unchanged."
            exit 0
          fi

          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

          git commit -m "Update Marukyu stock state"
          git push

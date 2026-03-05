from datetime import date, timedelta
import yaml
from pathlib import Path
from core.discover.crossref import CrossrefClient, CrossrefConfig, discover_recent_papers_for_journal

def main():
    BASE_DIR = Path(__file__).resolve().parents[1]  # E:\paperbot
    CONFIG_PATH = BASE_DIR / "config" / "config.yml"
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    lookback = int(cfg["pipeline"]["lookback_days"])
    until_d = date.today()
    from_d = until_d - timedelta(days=lookback)

    cr_cfg_dict = cfg.get("crossref", {}) or {}
    cr_cfg = CrossrefConfig(
        mailto=cr_cfg_dict.get("mailto"),
        timeout_sec=int(cr_cfg_dict.get("timeout_sec", 30)),
        per_page=int(cr_cfg_dict.get("per_page", 200)),
        polite_sleep_sec=float(cr_cfg_dict.get("polite_sleep_sec", 1.0)),
    )

    client = CrossrefClient(cr_cfg)

    all_items = []
    for j in cfg["journals"]:
        items = discover_recent_papers_for_journal(client, j, from_d, until_d)
        print(f"[{j['name']}] found {len(items)} items")
        all_items.extend(items)

    # 先简单打印前 3 条
    for it in all_items[:3]:
        print(it["published_date"], it["journal"], it["doi"], it["title"][:80])

if __name__ == "__main__":
    main()
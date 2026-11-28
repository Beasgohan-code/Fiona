import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WAIFU = ROOT / "waifu" / "aoiwaifu"


class FionaRichUiTests(unittest.TestCase):
    def test_search_results_are_visual_cards_with_pagination_and_inline_bridge(self):
        source = (WAIFU / "modules" / "sips.py").read_text(encoding="utf-8")
        self.assertIn("reply_photo_panel(", source)
        self.assertIn("rich_progress_bar(", source)
        self.assertIn("_search_caption(", source)
        self.assertIn("<blockquote>", source)
        self.assertIn("callback_data=f\"sips:{query}:{page + 1}\"", source)
        self.assertIn("switch_inline_query_current_chat=", source)

    def test_leaderboards_use_structured_rich_tables_without_random_art(self):
        source = (WAIFU / "modules" / "leaderboard.py").read_text(encoding="utf-8")
        self.assertIn("rich_table((\"RANK\", \"NAME\", \"SCORE\")", source)
        self.assertIn("PHOTO_URL[0]", source)
        self.assertNotIn("random.choice(PHOTO_URL)", source)
        self.assertNotIn("random.choice", source)
        self.assertIn("_rank_rows(", source)

    def test_inline_rank_tabs_render_structured_tables(self):
        source = (WAIFU / "modules" / "rank.py").read_text(encoding="utf-8")
        self.assertIn("rich_table(('RANK', 'COLLECTOR', 'SCORE')", source)
        self.assertIn("def _rank_table(", source)
        self.assertIn("def rank_row(", source)
        self.assertIn("leaderboard_header(", source)

    def test_progress_bars_are_available_to_rich_cards(self):
        rich_ui = (WAIFU / "unit" / "rich_ui.py").read_text(encoding="utf-8")
        rarity = (WAIFU / "modules" / "rarity.py").read_text(encoding="utf-8")
        achievements = (WAIFU / "modules" / "achievements.py").read_text(encoding="utf-8")
        self.assertIn("def rich_progress_bar(", rich_ui)
        self.assertIn("rich_progress_bar(count, total_count, 8)", rarity)
        self.assertIn("rich_progress_bar(progress, goal, 10)", achievements)

    def test_inline_video_thumbnails_have_stable_fallbacks(self):
        source = (WAIFU / "modules" / "inlinequery.py").read_text(encoding="utf-8")
        self.assertIn("PHOTO_URL", source)
        self.assertIn('character.get("img_url")', source)
        self.assertNotIn("https://envs.sh/6Y3.jpg", source)


if __name__ == "__main__":
    unittest.main()
